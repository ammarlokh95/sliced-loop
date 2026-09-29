#!/usr/bin/env python3
"""One supervision tick, worked out without a model.

    tick.py plan [--peek] [--harness H] [--json]
                    what this tick must do: the changes, the mechanical moves it
                    made, who to dispatch, and whether the supervisor is needed
    tick.py next [--json]
                    who to dispatch now, and on what (after the supervisor ran)

Most of a tick is bookkeeping a script can do, and a model reading files to do
it is where the tokens went. So:

- **Mechanical moves are made here.** A `blocked` task whose `depends_on` are
  all `done`, and which is not waiting on access only a human can grant, goes
  back to `ready`.
- **Dispatch is decided here.** Each agent that is not busy gets its
  highest-priority `ready` task whose dependencies are done, or a resume of its
  own STALE claim. The supervisor steers dispatch through status and priority;
  it does not name agents.
- **The supervisor is called only for judgment:** work awaiting acceptance, a
  newly proposed task, a question asked in a blocked task's thread, or an agent
  with nothing ready while its proposed work waits for triage. When it is
  called, it gets a digest of just those tasks — the sections it needs and the
  thread lines new since the last tick — instead of opening every file.

`plan` advances its own snapshot (separate from `tasks.py changes`, which is
for humans) unless `--peek`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tasklib  # noqa: E402

SNAPSHOT = tasklib.state_dir() / "tick.snapshot.json"
# Which version of each task the supervisor was last shown. A task goes back to
# it only once it has changed since — otherwise a review it chose to leave
# open would summon it on every tick, and the loop would never go idle.
PRESENTED = tasklib.state_dir() / "presented.json"
SECTION_LINES = 40   # longest a digest section gets before it is cut
THREAD_TAIL = 6      # thread lines shown for a task the snapshot has not seen


# --- reading tasks ----------------------------------------------------------

def thread_lines(body: str) -> list[str]:
    heading = re.search(r"^## Thread[^\n]*$", body, re.M)
    if not heading:
        return []
    out = []
    for line in body[heading.end():].splitlines():
        if line.startswith("## "):
            break
        if line.strip():
            out.append(line.rstrip())
    return out


def section(body: str, name: str) -> list[str]:
    m = re.search(rf"^## {re.escape(name)}[^\n]*$", body, re.M)
    if not m:
        return []
    lines = []
    for line in body[m.end():].splitlines():
        if line.startswith("## "):
            break
        lines.append(line.rstrip())
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if len(lines) > SECTION_LINES:
        lines = lines[:SECTION_LINES] + [f"… ({len(lines) - SECTION_LINES} more lines in the task file)"]
    return lines


def fingerprint(tasks: list[dict]) -> dict[str, dict]:
    snap = {}
    for t in tasks:
        try:
            digest = hashlib.sha256((tasklib.tasks_dir() / t["file"]).read_bytes()).hexdigest()[:16]
        except OSError:
            continue
        snap[t["id"]] = {"hash": digest, "status": t["status"], "owner": t["owner"],
                         "title": t["title"], "thread": len(thread_lines(t["body"]))}
    return snap


def load_snapshot() -> dict | None:
    try:
        return json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_snapshot(tasks: list[dict]) -> None:
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(fingerprint(tasks), indent=2, sort_keys=True), encoding="utf-8")


# --- the plan ---------------------------------------------------------------

def deps_done(t: dict, by_id: dict[str, dict]) -> bool:
    return all(by_id.get(d, {}).get("status") == "done" for d in t["depends_on"])


def unblockable(t: dict, by_id: dict[str, dict]) -> bool:
    return (t["status"] == "blocked" and bool(t["depends_on"]) and deps_done(t, by_id)
            and not tasklib.needs_access(t))


def dispatch_list(tasks: list[dict], stale_after: int = tasklib.STALE_AFTER_MINUTES) -> list[dict]:
    """Who to wake now: per agent, a resume of its dead claim, or its next task."""
    by_id = {t["id"]: t for t in tasks}
    running = {s["agent"] for s in tasklib.running_sessions()}
    out = []
    for agent in tasklib.OWNERS:
        if agent in running:
            continue
        mine = [t for t in tasks if t["owner"] == agent]
        claims = [t for t in mine if t["status"] == "in-progress"]
        stale = [t for t in claims if tasklib.claim_liveness(t, stale_after)["stale"]]
        if len(stale) < len(claims):
            continue  # a live claim: busy
        if stale:
            t = tasklib.by_priority(stale)[0]
            out.append({"agent": agent, "task": t["id"], "title": t["title"], "resume": True})
            continue
        ready = [t for t in tasklib.by_priority(mine) if t["status"] == "ready" and deps_done(t, by_id)]
        if ready:
            out.append({"agent": agent, "task": ready[0]["id"], "title": ready[0]["title"], "resume": False})
    return out


def load_presented() -> dict[str, str]:
    try:
        return json.loads(PRESENTED.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def judgment(tasks: list[dict], changes: list[dict], new_lines: dict[str, list[str]],
             dispatch: list[dict]) -> tuple[list[str], list[dict]]:
    """(why the supervisor is needed, the tasks it needs to see)."""
    by_id = {t["id"]: t for t in tasks}
    changed = {c["id"] for c in changes}
    hashes = {tid: f["hash"] for tid, f in fingerprint(tasks).items()}
    presented = load_presented()
    seen = lambda t: presented.get(t["id"]) == hashes.get(t["id"])  # noqa: E731
    reasons, focus = [], {}

    for t in tasks:
        if seen(t):
            continue  # shown to the supervisor already, unchanged since
        if t["status"] == "review":
            reasons.append(f"{t['id']} [{t['owner']}] awaits acceptance")
            focus[t["id"]] = "review"
        elif t["status"] == "proposed" and t["id"] in changed:
            reasons.append(f"{t['id']} [{t['owner']}] newly proposed by {t['requested_by'] or '?'}")
            focus[t["id"]] = "proposed"
        elif t["status"] == "blocked" and t["id"] in changed and not tasklib.needs_access(t):
            fresh = new_lines.get(t["id"], [])
            waiting_on_deps = t["depends_on"] and not deps_done(t, by_id) and not any("?" in l for l in fresh)
            if not waiting_on_deps:
                reasons.append(f"{t['id']} [{t['owner']}] blocked on a question in its thread")
                focus[t["id"]] = "question"

    dispatched = {d["agent"] for d in dispatch}
    busy = {s["agent"] for s in tasklib.running_sessions()} | {
        t["owner"] for t in tasks if t["status"] == "in-progress"}
    for agent in tasklib.OWNERS:
        if agent in dispatched or agent in busy:
            continue
        waiting = [t for t in tasks if t["owner"] == agent and t["status"] == "proposed"]
        if waiting and not all(seen(t) for t in waiting):
            reasons.append(f"{agent} has nothing ready; {len(waiting)} proposed task(s) await triage")
            for t in tasklib.by_priority(waiting)[:5]:
                focus.setdefault(t["id"], "triage")

    ordered = [by_id[i] | {"why": w} for i, w in focus.items() if i in by_id]
    return reasons, ordered


def digest(tasks: list[dict], new_lines: dict[str, list[str]]) -> str:
    """Only what the supervisor needs, per task."""
    parts = []
    for t in tasks:
        head = (f"### {t['id']} [{t['owner']}] {t['status']} · {t['priority'] or 'P?'} · {t['title']}"
                f"  ({tasklib.tasks_dir().name}/{t['file']})")
        body = [head]
        if t["depends_on"]:
            body.append(f"depends_on: {', '.join(t['depends_on'])}")
        wanted = {"review": ["Acceptance criteria"],
                  "proposed": ["Goal", "Acceptance criteria", "Contract"],
                  "triage": ["Goal"],
                  "question": []}[t["why"]]
        for name in wanted:
            lines = section(t["body"], name)
            if lines:
                body += [f"{name}:", *lines]
        fresh = new_lines.get(t["id"])
        if fresh is None:
            fresh = thread_lines(t["body"])[-THREAD_TAIL:]
            label = "Thread (latest):"
        else:
            label = "New in thread:"
        if fresh and t["why"] != "triage":
            body += [label, *fresh]
        parts.append("\n".join(body))
    return "\n\n".join(parts)


def plan(peek: bool = False, stale_after: int = tasklib.STALE_AFTER_MINUTES,
         advance: bool | None = None) -> dict:
    """`peek`: change nothing. Otherwise mechanical moves are made, and the
    snapshot advances unless `advance=False` — the loop re-plans mid-tick
    without advancing, so what the agents changed is still new next tick."""
    advance = (not peek) if advance is None else advance
    tasks = tasklib.load_tasks()
    previous = load_snapshot()
    first_run = previous is None
    previous = previous or {}

    changes, new_lines = [], {}
    for t in tasks:
        was = previous.get(t["id"])
        lines = thread_lines(t["body"])
        if was is None:
            if not first_run:
                changes.append({"kind": "NEW", "id": t["id"], "owner": t["owner"], "to": t["status"],
                                "title": t["title"]})
            continue
        new_lines[t["id"]] = lines[was.get("thread", 0):]
        cur = fingerprint([t]).get(t["id"], {})
        if was["status"] != t["status"]:
            changes.append({"kind": "MOVED", "id": t["id"], "owner": t["owner"], "from": was["status"],
                            "to": t["status"], "title": t["title"]})
        elif was["hash"] != cur.get("hash"):
            changes.append({"kind": "EDITED", "id": t["id"], "owner": t["owner"], "to": t["status"],
                            "title": t["title"]})
    ids = {t["id"] for t in tasks}
    for tid, was in previous.items():
        if tid not in ids:
            changes.append({"kind": "REMOVED", "id": tid, "owner": was["owner"], "to": was["status"],
                            "title": was["title"]})

    # Mechanical moves: nothing here needs judgment.
    by_id = {t["id"]: t for t in tasks}
    auto = []
    for t in tasks:
        if unblockable(t, by_id):
            auto.append({"id": t["id"], "owner": t["owner"], "from": "blocked", "to": "ready",
                         "why": f"its dependencies are done ({', '.join(t['depends_on'])})"})
            if not peek:
                tasklib.set_status(t["id"], "ready", f"loop: dependencies done ({', '.join(t['depends_on'])}) "
                                                     f"— back to ready")
    if auto and not peek:
        tasks = tasklib.load_tasks()

    dispatch = dispatch_list(tasks, stale_after)
    reasons, focus = judgment(tasks, changes, new_lines, dispatch)
    if advance and not peek:
        save_snapshot(tasks)
        if reasons:
            shown = load_presented()
            hashes = {tid: f["hash"] for tid, f in fingerprint(tasks).items()}
            shown.update({t["id"]: hashes[t["id"]] for t in focus if t["id"] in hashes})
            PRESENTED.write_text(json.dumps(shown, indent=2, sort_keys=True), encoding="utf-8")

    notices = []
    if tasklib.CFG["legacy"] or tasklib.legacy_contract():
        notices.append("MIGRATE  this project predates per-tree agents — run "
                       "`agents.py migrate --harness <yours>` before dispatching")
    else:
        import agents as agents_mod
        if (why := agents_mod.stale(tasklib.CFG)):
            notices.append(f"SYNC     tree agent files need regenerating ({why[0]}"
                           f"{f' +{len(why) - 1} more' if len(why) > 1 else ''}) — run `agents.py sync`")

    return {
        "notices": notices,
        "first_run": first_run,
        "changes": changes,
        "auto": auto,
        "dispatch": dispatch,
        "supervisor": reasons,
        "digest": digest(focus, new_lines) if reasons else "",
        "waiting_on_human": [t["id"] for t in tasks if tasklib.needs_access(t)],
        "quiet": not (first_run or changes or auto or dispatch or reasons),
    }


# --- printing ---------------------------------------------------------------

def render(p: dict, harness: str | None = None) -> str:
    out = list(p.get("notices", []))
    if p["first_run"]:
        out.append("first tick — now tracking the task files")
    if p["quiet"]:
        out.append("QUIET    no changes, nothing to dispatch, nothing for the supervisor")
    for c in p["changes"]:
        move = f"{c['from']} -> {c['to']}" if c["kind"] == "MOVED" else c["to"]
        out.append(f"{c['kind']:8} {c['id']} [{c['owner']}] {move}: {c['title']}")
    for a in p["auto"]:
        out.append(f"AUTO     {a['id']} [{a['owner']}] {a['from']} -> {a['to']}: {a['why']}")
    if p["supervisor"]:
        out.append("SUPERVISOR needed:")
        out += [f"  - {r}" for r in p["supervisor"]]
    else:
        out.append("SUPERVISOR not needed this tick")
    for d in p["dispatch"]:
        out.append(f"DISPATCH {d['agent']} {d['task']}{' (resume)' if d['resume'] else ''}: {d['title']}")
    if p["waiting_on_human"]:
        out.append(f"WAITING  on a human for access: {', '.join(p['waiting_on_human'])}")
    if p["digest"]:
        out.append("\nDIGEST — the tasks the supervisor needs, with only what it needs:\n")
        out.append(p["digest"])
        if harness:
            import build
            out.append("\n---\nINSTRUCTIONS FOR THE SUPERVISOR:\n")
            out.append(build.body_for("prompts", "tick", harness, absolute=True).strip())
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("plan")
    pl.add_argument("--peek", action="store_true", help="change nothing, advance nothing")
    pl.add_argument("--harness", help="include the supervisor's instructions, rendered for this harness")
    pl.add_argument("--json", action="store_true")
    nx = sub.add_parser("next")
    nx.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.cmd == "next":
        d = dispatch_list(tasklib.load_tasks())
        if args.json:
            print(json.dumps(d))
        else:
            print("\n".join(f"DISPATCH {x['agent']} {x['task']}{' (resume)' if x['resume'] else ''}: "
                            f"{x['title']}" for x in d) or "nothing to dispatch")
        return 0
    p = plan(peek=args.peek)
    print(json.dumps(p, indent=2) if args.json else render(p, args.harness))
    return 0


if __name__ == "__main__":
    sys.exit(main())
