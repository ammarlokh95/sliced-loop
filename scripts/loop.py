#!/usr/bin/env python3
"""The supervision loop, for harnesses without a built-in `/loop`.

    loop.py --harness H [--every 15m] [--idle-ticks N] [--once]

Claude Code runs the loop in-session (`/loop 15m /sliced-loop:supervise`). The
other harnesses have no scheduler, so this drives it from a terminal: every
interval it looks at the board itself, and only when there is something to do
does it start a headless session running that harness's supervise command.

The look is free — no model is called for a quiet tick, which is most of them.
"Something to do" is the same rule the supervise command applies: a change in
the task files, an idle agent with ready work, or a STALE claim.

The loop ends itself after N consecutive idle ticks (default 5, or `idle_ticks`
in .sliced-loop.json; `--idle-ticks 0` never stops). A tick is idle only when it
had nothing to do and no specialist is mid-task, so a long task does not end the
loop under it. Anything that moves resets the count.

Ctrl-C stops the loop; a tick already running is allowed to finish.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build  # noqa: E402
import config as cfg_module  # noqa: E402
import dispatch  # noqa: E402
import tasklib  # noqa: E402


def parse_interval(text: str) -> int:
    m = re.fullmatch(r"(\d+)\s*([smh]?)", text.strip())
    if not m:
        raise argparse.ArgumentTypeError(f"not an interval: {text!r} (try 300, 5m, 1h)")
    return int(m.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600}[m.group(2)]


def look() -> tuple[str, str]:
    def run(*args: str) -> str:
        return subprocess.run([sys.executable, str(HERE / "tasks.py"), *args],
                              capture_output=True, text=True, cwd=str(tasklib.ROOT)).stdout.strip()
    return run("changes", "--peek"), run("status")


def has_work(changes: str, status: str) -> bool:
    if changes != "no changes":
        return True
    return bool(re.search(r"^\S+\s+(STALE|IDLE    next up)", status, re.M))


def tick(harness: str) -> tuple[bool, str]:
    """(quiet, one-line summary)."""
    changes, status = look()
    human = re.search(r"^waiting on a human: (\S[^—]*)", status, re.M)
    note = f"  ·  waiting on a human: {human.group(1).strip()} (see status)" if human else ""
    if not has_work(changes, status):
        return True, "quiet — no changes, nothing ready for an idle agent, nothing stale" + note

    prompt = build.body_for("commands", "supervise", harness).replace(
        "<ARGUMENTS>", "")  # the command takes no arguments
    argv = dispatch.command_for(harness, tasklib.ROOT, None, prompt)
    logs = tasklib.state_dir() / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / f"{time.strftime('%Y%m%d-%H%M%S')}-tick.log"
    with open(log, "w", encoding="utf-8") as out:
        code = subprocess.run(argv, cwd=str(tasklib.ROOT), env=dispatch.agent_env(None, tasklib.ROOT),
                              stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT).returncode
    tail = [l for l in log.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()][-1:]
    summary = tail[0][:200] if tail else "(no output)"
    return False, f"tick ran (exit {code}) — {summary}  [log: {log.relative_to(tasklib.ROOT)}]{note}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--harness", required=True, choices=[h for h in build.HARNESSES if h != "claude"])
    parser.add_argument("--every", type=parse_interval, default=parse_interval("15m"))
    parser.add_argument("--idle-ticks", type=int, metavar="N",
                        help=f"end after N consecutive idle ticks (default: idle_ticks in "
                             f".sliced-loop.json, else {tasklib.IDLE_TICKS}; 0 = never)")
    parser.add_argument("--once", action="store_true", help="run one tick and exit")
    args = parser.parse_args()
    cfg_module.require()

    lock = tasklib.state_dir() / "loop.pid"
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        other = int(lock.read_text().strip())
        if other != os.getpid() and tasklib.alive(other):
            print(f"another loop is already running (pid {other})", file=sys.stderr)
            return 3
    except (OSError, ValueError):
        pass
    lock.write_text(str(os.getpid()))

    try:
        limit = tasklib.idle_limit(args.idle_ticks)
        while True:
            quiet, line = tick(args.harness)
            r = tasklib.record_tick(quiet, limit)
            if r["why"] == "idle" and limit:
                line += f"  (idle {r['count']}/{limit})"
            print(f"{time.strftime('%H:%M')}  {line}", flush=True)
            if r["stop"]:
                print(f"stopped: {limit} idle ticks in a row — nothing moved and nobody is working. "
                      f"Run the loop again to resume.")
                return 0
            if args.once:
                return 0
            time.sleep(args.every)
    except KeyboardInterrupt:
        print("\nstopped.")
        return 130
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
