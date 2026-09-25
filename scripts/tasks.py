#!/usr/bin/env python3
"""Task-state queries for the supervision loop.

    tasks.py changes [--peek]      what changed since the last check
    tasks.py status [--stale-after N]
                                   who is busy, who is idle, what is waiting
    tasks.py research [query]      research notes, filtered by title or slug
    tasks.py tick quiet|active [--limit N]
                                   count consecutive idle ticks; says STOP at the limit

`changes` compares the task files against a snapshot and then updates it, so
each call reports only what is new since the previous call. That keeps a
supervision tick cheap and deterministic instead of asking the model to
remember what it saw fifteen minutes ago.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tasklib  # noqa: E402

SNAPSHOT = tasklib.state_dir() / "tasks.snapshot.json"


def fingerprint() -> dict[str, dict]:
    snap = {}
    for task in tasklib.load_tasks():
        try:
            digest = hashlib.sha256(
                (tasklib.tasks_dir() / task["file"]).read_bytes()
            ).hexdigest()[:16]
        except OSError:
            continue
        snap[task["file"]] = {
            "hash": digest,
            "id": task["id"],
            "status": task["status"],
            "owner": task["owner"],
            "title": task["title"],
        }
    return snap


def cmd_changes(args: argparse.Namespace) -> int:
    current = fingerprint()
    try:
        previous = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = None

    def save() -> None:
        if not args.peek:
            SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
            SNAPSHOT.write_text(json.dumps(current, indent=2, sort_keys=True), encoding="utf-8")

    if previous is None:
        save()
        print(f"first run — now tracking {len(current)} task file(s), nothing to review")
        return 0

    def tag(rec: dict) -> str:
        return f"{rec['id']} [{rec['owner']}]"

    lines = []
    for key, now in sorted(current.items()):
        was = previous.get(key)
        if was is None:
            lines.append(f"NEW      {tag(now)} {now['status']}: {now['title']}")
        elif was["status"] != now["status"]:
            lines.append(f"MOVED    {tag(now)} {was['status']} -> {now['status']}: {now['title']}")
        elif was["hash"] != now["hash"]:
            lines.append(f"EDITED   {tag(now)} {now['status']}: {now['title']}")
    for key, was in sorted(previous.items()):
        if key not in current:
            lines.append(f"REMOVED  {tag(was)} was {was['status']}: {was['title']}")

    save()
    print("\n".join(lines) if lines else "no changes")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    tasks = tasklib.load_tasks()
    if not tasks:
        print("no tasks yet — the sliced-loop plan command turns a brief into a backlog")
        return 0

    for owner in tasklib.OWNERS:
        mine = [t for t in tasks if t["owner"] == owner]
        working = tasklib.by_priority([t for t in mine if t["status"] == "in-progress"])
        ready = tasklib.by_priority([t for t in mine if t["status"] == "ready"])
        blocked = tasklib.by_priority([t for t in mine if t["status"] == "blocked"])

        live = [(t, tasklib.claim_liveness(t, args.stale_after)) for t in working]
        stale = [(t, info) for t, info in live if info["stale"]]

        if stale:
            # A claim nothing has touched for longer than an agent session runs.
            # The session holding it is gone; without this the board reports BUSY
            # forever and the task is never dispatched again.
            detail = ", ".join(f"{t['id']} (idle {i['idle_minutes']}m)" for t, i in stale)
            state = f"STALE   abandoned claim on {detail}"
        elif working:
            state = "BUSY    on " + ", ".join(t["id"] for t in working)
            if ready:
                state += f"  ({len(ready)} ready behind it)"
        elif ready:
            nxt = ready[0]
            state = f"IDLE    next up {nxt['id']} ({nxt['priority'] or 'P?'}) {nxt['title']}"
            if len(ready) > 1:
                state += f"  (+{len(ready) - 1} more)"
        else:
            state = "IDLE    nothing ready"

        print(f"{owner:9} {state}")
        if stale:
            print(f"{'':9}         re-dispatch it as a resume — do not treat as busy")
        for t in blocked:
            if (need := tasklib.needs_access(t)):
                print(f"{'':9}         BLOCKED {t['id']} on access only a human can grant: {need}")
                continue
            on = ", ".join(t["depends_on"]) or "a question in its thread"
            print(f"{'':9}         BLOCKED {t['id']} on {on}")

    for label, status in (("awaiting acceptance", "review"), ("awaiting triage", "proposed")):
        pending = tasklib.by_priority([t for t in tasks if t["status"] == status])
        if pending:
            ids = ", ".join(f"{t['id']} ({t['priority'] or 'P?'})" for t in pending)
            print(f"supervisor {label}: {ids}")

    human = [t for t in tasks if tasklib.needs_access(t)]
    if human:
        print("waiting on a human: " + ", ".join(t["id"] for t in human)
              + " — grant the access its thread asks for, then say so there")

    sizes = tasklib.memory_sizes()
    over = [(n, c) for n, c in sizes if c >= tasklib.COMPACT_AT]
    near = [(n, c) for n, c in sizes if tasklib.WARN_AT <= c < tasklib.COMPACT_AT]
    if over:
        print(f"memory NEEDS COMPACTION (>= {tasklib.COMPACT_AT}): "
              + ", ".join(f"{n} {c} lines" for n, c in over))
        print(f"{'':9}         its owner condenses it at the end of its next task")
    if near:
        print("memory approaching compaction: " + ", ".join(f"{n} {c} lines" for n, c in near))
    return 0


def cmd_tick(args: argparse.Namespace) -> int:
    r = tasklib.record_tick(args.kind == "quiet", tasklib.idle_limit(args.limit))
    if r["stop"]:
        print(f"idle tick {r['count']} of {r['limit']} — STOP: end the supervision loop")
    elif r["why"] == "idle":
        of = f" of {r['limit']}" if r["limit"] else " (no limit)"
        print(f"idle tick {r['count']}{of}")
    elif r["why"] == "active":
        print("active tick — idle count reset")
    else:
        print(f"quiet, but not idle ({r['why']}) — idle count reset")
    return 0


def cmd_research(args: argparse.Namespace) -> int:
    query = " ".join(args.query)
    matches = tasklib.research_files(query)
    if not matches:
        if query:
            print(f"no research note matches {query!r}")
            others = tasklib.research_files()
            if others:
                print("available:")
                for r in others:
                    print(f"  {r['slug']}: {r['title']}")
        else:
            print("no research notes yet — ask the research agent a question")
        return 1

    print(f"{len(matches)} match(es)" if query else f"{len(matches)} note(s)")
    for r in matches:
        print(f"\n  {r['slug']}")
        print(f"    {r['title']}")
        if r["question"]:
            print(f"    asked: {r['question']}")
        if r["confidence"]:
            print(f"    confidence {r['confidence']}")
        print(f"    {r['path']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    changes = sub.add_parser("changes", help="what changed since the last check")
    changes.add_argument("--peek", action="store_true", help="report without advancing the snapshot")
    changes.set_defaults(fn=cmd_changes)

    status = sub.add_parser("status", help="who is busy, who is idle, what is waiting")
    status.add_argument("--stale-after", type=int, default=tasklib.STALE_AFTER_MINUTES,
                        metavar="N",
                        help=f"minutes of no activity before a claim reads as abandoned "
                             f"(default {tasklib.STALE_AFTER_MINUTES})")
    status.set_defaults(fn=cmd_status)

    tick = sub.add_parser("tick", help="record a supervision tick; say when the loop should end")
    tick.add_argument("kind", choices=["quiet", "active"])
    tick.add_argument("--limit", type=int, metavar="N",
                      help=f"idle ticks before stopping (default: idle_ticks in config, else "
                           f"{tasklib.IDLE_TICKS}; 0 = never)")
    tick.set_defaults(fn=cmd_tick)

    research = sub.add_parser("research", help="research notes, filtered")
    research.add_argument("query", nargs="*")
    research.set_defaults(fn=cmd_research)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
