#!/usr/bin/env python3
"""The supervision loop, run from a terminal, for every harness.

    loop.py --harness H [--every 15m] [--idle-ticks N] [--once]

Each tick runs outside your conversation, so nothing accumulates in it:

1. **Look** (no model): `tick.plan --peek`. A quiet tick ends here and costs
   nothing — that is most of them.
2. **Mechanical moves** (no model): tasks whose dependencies are done go back
   to `ready`.
3. **Supervisor, only if judgment is needed** — work awaiting acceptance, a
   newly proposed task, a question, an agent with nothing ready. It runs as a
   fresh headless session and gets a digest of just those tasks.
4. **Dispatch** (no model decides it): each idle agent gets its highest-priority
   ready task, or a resume of its dead claim, as its own fresh headless session.
   They run at once; when they finish, the next round goes out — up to six
   sessions a tick, or until something needs the supervisor again.

The loop ends itself after N consecutive idle ticks (default 5, or `idle_ticks`
in .sliced-loop.json; `--idle-ticks 0` never stops). A tick is idle only when it
had nothing to do and no agent is mid-task, so a long task does not end the
loop under it. Anything that moves resets the count.

Ctrl-C stops the loop; a tick already running is allowed to finish.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import agents as agents_mod  # noqa: E402
import build  # noqa: E402
import config as cfg_module  # noqa: E402
import dispatch  # noqa: E402
import tasklib  # noqa: E402
import tick as tickmod  # noqa: E402


def parse_interval(text: str) -> int:
    m = re.fullmatch(r"(\d+)\s*([smh]?)", text.strip())
    if not m:
        raise argparse.ArgumentTypeError(f"not an interval: {text!r} (try 300, 5m, 1h)")
    return int(m.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600}[m.group(2)]


MAX_SESSIONS = 6  # agent sessions per tick, as the supervise command allows


def run_round(harness: str, todo: list[dict]) -> list[str]:
    """Run each dispatch as its own session, concurrently; one line per session."""
    def one(d: dict) -> str:
        code, last = dispatch.run_task(harness, d["agent"], d["task"], resume=d["resume"])
        kind = " (resume)" if d["resume"] else ""
        return f"{d['agent']} {d['task']}{kind} exit {code}" + (f": {last}" if last else "")
    with ThreadPoolExecutor(max_workers=max(1, len(todo))) as pool:
        return list(pool.map(one, todo))


def tick(harness: str) -> tuple[bool, str]:
    """(quiet, summary)."""
    look = tickmod.plan(peek=True)
    human = look["waiting_on_human"]
    note = f"  ·  waiting on a human for access: {', '.join(human)} (see status)" if human else ""
    for n in look["notices"]:
        if n.startswith("MIGRATE"):
            return False, n  # nothing can be dispatched safely until it is migrated
    if look["quiet"]:
        return True, "quiet — no changes, nothing to dispatch, nothing for the supervisor" + note

    lines: list[str] = [n for n in look["notices"]]
    if any(n.startswith("SYNC") for n in look["notices"]):
        agents_mod.sync(tasklib.CFG)  # fresh sessions load the new files at once
        lines.append("synced the tree agent files")
    plan = tickmod.plan()  # advances the snapshot; makes the mechanical moves
    lines += [f"auto: {a['id']} -> ready ({a['why']})" for a in plan["auto"]]

    if plan["supervisor"]:
        code, last = dispatch.run_supervisor(harness, tickmod.render(plan, harness))
        lines.append(f"supervisor ({'; '.join(plan['supervisor'])}) exit {code}" + (f": {last}" if last else ""))

    sessions = 0
    while sessions < MAX_SESSIONS:
        todo = tickmod.dispatch_list(tasklib.load_tasks())[:MAX_SESSIONS - sessions]
        if not todo:
            break
        lines += run_round(harness, todo)
        sessions += len(todo)
        # Mechanical moves again, without advancing: what the agents changed
        # stays new for the next tick's supervisor. Ready work keeps going out
        # meanwhile; a review or a question waits for that supervisor.
        if tickmod.plan(advance=False)["supervisor"] and not any("next tick" in l for l in lines):
            lines.append("the supervisor is needed again — next tick")
    return False, "\n        ".join(lines) + note


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--harness", required=True, choices=list(build.HARNESSES))
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
