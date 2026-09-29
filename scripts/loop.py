#!/usr/bin/env python3
"""The supervision loop, run from a terminal, for every harness.

    loop.py --harness H [--every 15m] [--idle-ticks N] [--once]      run in this terminal
    loop.py --harness H [--every 15m] [--idle-ticks N] --detach      start in the background
    loop.py --stop | --status                                         for a running loop

`--detach` is what the loop command uses from chat: the loop runs on after the
chat session ends, logging to <workspace>/.state/logs/loop.log.

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
import json
import os
import re
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
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


# --- running in the background ----------------------------------------------

def state_file() -> Path:
    return tasklib.state_dir() / "loop.json"


def log_file() -> Path:
    return tasklib.state_dir() / "logs" / "loop.log"


def running_loop() -> dict | None:
    """The loop running for this project, if one is."""
    try:
        info = json.loads(state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return info if tasklib.alive(int(info.get("pid", 0))) else None


def human_interval(seconds: int) -> str:
    return f"{seconds // 3600}h" if seconds % 3600 == 0 else (
        f"{seconds // 60}m" if seconds % 60 == 0 else f"{seconds}s")


def detach(args: argparse.Namespace) -> int:
    """Start this loop in its own session, logging to .state/logs/loop.log."""
    if (info := running_loop()):
        print(f"already running (pid {info['pid']}, {info['harness']}, every "
              f"{human_interval(info['every'])}) — `--status` to see it, `--stop` to end it")
        return 3
    argv = [sys.executable, str(Path(__file__).resolve()), "--harness", args.harness,
            "--every", str(args.every)]
    if args.idle_ticks is not None:
        argv += ["--idle-ticks", str(args.idle_ticks)]
    log_file().parent.mkdir(parents=True, exist_ok=True)
    with open(log_file(), "a", encoding="utf-8") as out:
        proc = subprocess.Popen(argv, cwd=str(tasklib.ROOT), env=dispatch.agent_env(None, tasklib.ROOT),
                                stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                                start_new_session=True)
    time.sleep(1.5)  # long enough to see it refuse or crash on start
    if proc.poll() is not None:
        tail = log_file().read_text(encoding="utf-8", errors="replace").splitlines()[-3:]
        if proc.returncode == 0:
            print("the loop started and has already stopped:\n  " + "\n  ".join(tail))
            return 0
        print("the loop failed to start:\n  " + "\n  ".join(tail))
        return 1
    limit = tasklib.idle_limit(args.idle_ticks)
    print(f"loop started (pid {proc.pid}): {args.harness}, a tick every {human_interval(args.every)}, "
          f"{'no idle limit' if not limit else f'stops after {limit} idle ticks'}. "
          f"Log: {log_file().relative_to(tasklib.ROOT)}")
    return 0


def stop() -> int:
    info = running_loop()
    if not info:
        print("no loop is running for this project")
        return 0
    os.kill(int(info["pid"]), signal.SIGTERM)
    for _ in range(20):
        if not tasklib.alive(int(info["pid"])):
            print(f"loop stopped (pid {info['pid']})")
            return 0
        time.sleep(0.5)
    print(f"asked the loop to stop (pid {info['pid']}); it ends when its current tick finishes")
    return 0


def status() -> int:
    info = running_loop()
    if info:
        limit = info.get("idle_ticks")
        print(f"running (pid {info['pid']}) since {info['started']}: {info['harness']}, a tick every "
              f"{human_interval(info['every'])}, "
              f"{'no idle limit' if not limit else f'stops after {limit} idle ticks'}")
    else:
        print("not running")
    try:
        idle = json.loads((tasklib.state_dir() / "idle.json").read_text()).get("count", 0)
        if info and idle:
            print(f"idle ticks in a row: {idle}")
    except (OSError, ValueError):
        pass
    if log_file().is_file():
        lines = [l for l in log_file().read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
        if lines:
            print(f"last lines of {log_file().relative_to(tasklib.ROOT)}:")
            print("\n".join(f"  {l}" for l in lines[-8:]))
    return 0


# --- the loop itself ----------------------------------------------------------

STOPPING = False


def _on_term(signum, frame) -> None:  # noqa: ARG001
    global STOPPING
    STOPPING = True  # finish the current tick, then stop


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--harness", choices=list(build.HARNESSES),
                        help="required to run or start the loop")
    parser.add_argument("--every", type=parse_interval, default=parse_interval("15m"),
                        help="time between ticks: 90s, 10m, 1h (default 15m)")
    parser.add_argument("--idle-ticks", type=int, metavar="N",
                        help=f"end after N consecutive idle ticks (default: idle_ticks in "
                             f".sliced-loop.json, else {tasklib.IDLE_TICKS}; 0 = never)")
    parser.add_argument("--once", action="store_true", help="run one tick and exit")
    what = parser.add_mutually_exclusive_group()
    what.add_argument("--detach", action="store_true",
                      help="start in the background, logging to .state/logs/loop.log, and return")
    what.add_argument("--stop", action="store_true", help="stop the running loop after its current tick")
    what.add_argument("--status", action="store_true", help="is it running, and its latest tick lines")
    args = parser.parse_args()
    cfg_module.require()

    if args.stop:
        return stop()
    if args.status:
        return status()
    if not args.harness:
        parser.error("--harness is required to run or start the loop")
    if args.detach:
        return detach(args)

    if (info := running_loop()) and int(info["pid"]) != os.getpid():
        print(f"another loop is already running (pid {info['pid']})", file=sys.stderr)
        return 3
    limit = tasklib.idle_limit(args.idle_ticks)
    state_file().parent.mkdir(parents=True, exist_ok=True)
    state_file().write_text(json.dumps({
        "pid": os.getpid(), "harness": args.harness, "every": args.every, "idle_ticks": limit,
        "started": time.strftime("%Y-%m-%d %H:%M")}), encoding="utf-8")
    # A new loop counts its own idle ticks, not the last loop's.
    (tasklib.state_dir() / "idle.json").write_text(json.dumps({"count": 0}), encoding="utf-8")
    signal.signal(signal.SIGTERM, _on_term)
    print(f"{time.strftime('%H:%M')}  loop started: {args.harness}, a tick every "
          f"{human_interval(args.every)}, {'no idle limit' if not limit else f'stops after {limit} idle ticks'}",
          flush=True)

    try:
        while True:
            quiet, line = tick(args.harness)
            r = tasklib.record_tick(quiet, limit)
            if r["why"] == "idle" and limit:
                line += f"  (idle {r['count']}/{limit})"
            print(f"{time.strftime('%H:%M')}  {line}", flush=True)
            if r["stop"]:
                print(f"{time.strftime('%H:%M')}  stopped: {limit} idle ticks in a row — nothing moved "
                      f"and nobody is working. Start the loop again to resume.", flush=True)
                return 0
            if args.once:
                return 0
            for _ in range(args.every):
                if STOPPING:
                    print(f"{time.strftime('%H:%M')}  stopped on request.", flush=True)
                    return 0
                time.sleep(1)
    except KeyboardInterrupt:
        print("\nstopped.")
        return 130
    finally:
        state_file().unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
