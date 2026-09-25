"""Reading and editing this project's task files.

Shared by the board server and the task CLI. Standard library only.

Layout, relative to the workspace named in `.sliced-loop.json`:

    <workspace>/tasks/<ID>-<slug>.md
              /capabilities/
              /memory/{frontend,backend,decisions}.md
              /research/
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as cfg_module  # noqa: E402

STATUSES = ["proposed", "ready", "in-progress", "blocked", "review", "done"]
OWNERS = ("frontend", "backend")

COMPACT_AT = 100  # lines; past this the owning agent condenses the file
WARN_AT = 80      # lines; early warning so compaction is never a surprise

# An agent session runs minutes, not hours. Past this with nothing touched at
# all, an `in-progress` claim belongs to a session that died — rate limit,
# crash, closed terminal — and the task needs re-dispatching, not protecting.
STALE_AFTER_MINUTES = 45
# Consecutive quiet ticks after which the supervision loop ends itself. Override
# with `idle_ticks` in .sliced-loop.json, or per loop on its command line.
IDLE_TICKS = 5
SKIP_DIRS = {"node_modules", "dist", "build", "coverage", ".git",
             ".next", ".vite", ".turbo", "__pycache__", "target", "vendor"}

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.S)
INLINE_COMMENT = re.compile(r"\s+#.*$")
PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}

CFG = cfg_module.load()
ROOT = CFG["root"]
WORKSPACE = CFG["workspace_path"]
TREES = {"frontend": CFG["frontend_path"], "backend": CFG["backend_path"]}


def tasks_dir() -> Path:
    return WORKSPACE / "tasks"


def state_dir() -> Path:
    """Local runtime state: the tick snapshot, anything the board caches.

    Everything here is regenerable and machine-local, so it is gitignored. Any
    future runtime artifact belongs here too — nothing the tooling produces at
    run time should ever land somewhere a commit would pick it up.
    """
    return WORKSPACE / ".state"


# --- parsing ----------------------------------------------------------------

def parse_frontmatter(text: str) -> tuple[dict, str]:
    m = FRONTMATTER.match(text)
    if not m:
        return {}, text

    fields: dict[str, object] = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, _, raw = line.partition(":")
        value = INLINE_COMMENT.sub("", raw).strip().strip("'\"")
        key = key.strip()
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            fields[key] = [v.strip().strip("'\"") for v in inner.split(",") if v.strip()]
        else:
            fields[key] = value
    return fields, m.group(2)


def load_tasks() -> list[dict]:
    out = []
    folder = tasks_dir()
    if not folder.is_dir():
        return out
    for path in sorted(folder.glob("*.md")):
        if path.name == "TEMPLATE.md":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        fields, body = parse_frontmatter(text)
        status = str(fields.get("status", "proposed"))
        out.append({
            "id": str(fields.get("id") or path.stem),
            "file": path.name,
            "title": str(fields.get("title", path.stem)),
            "owner": str(fields.get("owner", "")),
            "status": status if status in STATUSES else "proposed",
            "priority": str(fields.get("priority", "")),
            "created": str(fields.get("created", "")),
            "updated": str(fields.get("updated", "")),
            "requested_by": str(fields.get("requested_by", "")),
            "depends_on": fields.get("depends_on") or [],
            "body": body.strip(),
            "malformed": not fields,
        })
    return out


def by_priority(tasks: list[dict]) -> list[dict]:
    return sorted(tasks, key=lambda t: (PRIORITY_RANK.get(t["priority"], 9), t["id"]))


def find_task_file(task_id: str) -> Path | None:
    """Resolve by reading frontmatter — never by joining user input into a path."""
    folder = tasks_dir()
    if not folder.is_dir():
        return None
    for path in folder.glob("*.md"):
        if path.name == "TEMPLATE.md":
            continue
        try:
            fields, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if str(fields.get("id", "")).strip() == task_id:
            return path
    return None


# --- editing ----------------------------------------------------------------

def _set_field(frontmatter: str, key: str, value: str) -> str:
    pattern = re.compile(rf"^{re.escape(key)}:[^\n]*$", re.M)
    if pattern.search(frontmatter):
        return pattern.sub(f"{key}: {value}", frontmatter, count=1)
    return f"{frontmatter}\n{key}: {value}"


def _append_thread(body: str, line: str) -> str:
    heading = re.search(r"^## Thread[^\n]*$", body, re.M)
    if not heading:
        return f"{body.rstrip()}\n\n## Thread\n\n{line}\n"
    following = re.compile(r"^## ", re.M).search(body, heading.end())
    cut = following.start() if following else len(body)
    section = body[heading.end():cut].rstrip()
    return f"{body[:heading.end()]}{section}\n{line}\n\n{body[cut:].lstrip()}".rstrip() + "\n"


def _write_atomic(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def move_task(task_id: str, new_status: str) -> dict:
    if new_status not in STATUSES:
        return {"ok": False, "error": f"unknown status {new_status!r}"}

    path = find_task_file(task_id)
    if path is None:
        return {"ok": False, "error": f"no task with id {task_id!r}"}

    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER.match(text)
    if not m:
        return {"ok": False, "error": f"{path.name} has no frontmatter"}

    frontmatter, body = m.group(1), m.group(2)
    fields, _ = parse_frontmatter(text)
    old_status = str(fields.get("status", "?"))
    if old_status == new_status:
        return {"ok": True, "unchanged": True}

    today = date.today().isoformat()
    frontmatter = _set_field(frontmatter, "status", new_status)
    frontmatter = _set_field(frontmatter, "updated", today)
    body = _append_thread(body, f"- {today} board: {old_status} → {new_status} (manual override)")

    _write_atomic(path, f"---\n{frontmatter}\n---\n\n{body.lstrip()}")
    return {"ok": True, "id": task_id, "from": old_status, "to": new_status}


# --- access requests --------------------------------------------------------

NEEDS_ACCESS = re.compile(r"needs-access:\s*(.+)$", re.I)
ACCESS_GRANTED = re.compile(r"access (granted|given|connected)", re.I)


def needs_access(task: dict) -> str:
    """What a blocked task is waiting for a human to grant, or ''.

    An agent that cannot open a design it needs blocks with a `needs-access:`
    thread line rather than guessing. Only a human can resolve that, so it is
    reported apart from ordinary blocks. A later thread line saying access was
    granted clears it, and the supervisor moves the task back to `ready`.
    """
    if task.get("status") != "blocked":
        return ""
    heading = re.search(r"^## Thread[^\n]*$", task.get("body", ""), re.M)
    if not heading:
        return ""
    need = ""
    for line in task["body"][heading.end():].splitlines():
        if line.startswith("## "):
            break
        if (m := NEEDS_ACCESS.search(line)):
            need = m.group(1).strip()
        elif need and ACCESS_GRANTED.search(line):
            need = ""
    return need[:160]


# --- claim liveness ---------------------------------------------------------

def _newest_mtime(root: Path) -> float:
    newest = 0.0
    if not root.is_dir():
        return newest
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            try:
                newest = max(newest, (Path(dirpath) / name).stat().st_mtime)
            except OSError:
                continue
    return newest


def claim_liveness(task: dict, stale_after: int = STALE_AFTER_MINUTES) -> dict:
    """Is this `in-progress` claim held by a session that is still alive?

    A working agent writes to its own source tree continuously; a dead one
    leaves the claim behind and nothing else moves. The freshest write across
    the task file and the agent's tree is the signal — no heartbeat to keep.
    """
    now = time.time()
    touched = 0.0
    try:
        touched = (tasks_dir() / task["file"]).stat().st_mtime
    except OSError:
        pass

    tree = TREES.get(task.get("owner", ""))
    if tree is not None:
        touched = max(touched, _newest_mtime(tree))

    idle = (now - touched) / 60 if touched else float("inf")
    return {
        "idle_minutes": int(idle) if idle != float("inf") else -1,
        "stale": idle > stale_after,
    }


# --- research ---------------------------------------------------------------

def research_files(query: str = "") -> list[dict]:
    out = []
    folder = WORKSPACE / "research"
    if not folder.is_dir():
        return out
    needle = query.strip().lower()
    for path in sorted(folder.glob("*.md")):
        if path.name == "README.md":
            continue
        try:
            fields, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        record = {
            "path": str(path.relative_to(ROOT)),
            "slug": str(fields.get("slug") or path.stem),
            "title": str(fields.get("title", path.stem)),
            "question": str(fields.get("question", "")),
            "confidence": str(fields.get("confidence", "")),
        }
        haystack = f"{record['slug']} {record['title']} {path.stem}".lower()
        if not needle or needle in haystack or all(w in haystack for w in needle.split()):
            out.append(record)
    return out


# --- memory -----------------------------------------------------------------

def memory_sizes() -> list[tuple[str, int]]:
    out = []
    memory = WORKSPACE / "memory"
    if memory.is_dir():
        for path in sorted(memory.glob("*.md")):
            try:
                out.append((path.name, len(path.read_text(encoding="utf-8").splitlines())))
            except OSError:
                continue
    return out


# --- sessions and the idle counter ------------------------------------------

def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # A zombie child of ours still answers kill(0); reap it if so.
    try:
        done, _ = os.waitpid(pid, os.WNOHANG)
        return done == 0
    except ChildProcessError:
        return True


def running_sessions() -> list[dict]:
    """Headless specialist sessions started by dispatch.py that are still alive."""
    out = []
    folder = state_dir() / "running"
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            info = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if alive(int(info.get("pid", 0))):
            out.append({**info, "agent": path.stem})
    return out


def idle_limit(override: int | None = None) -> int:
    if override is not None:
        return max(0, override)
    try:
        return max(0, int(cfg_module.setting("idle_ticks", IDLE_TICKS, ROOT)))
    except (TypeError, ValueError):
        return IDLE_TICKS


def record_tick(quiet: bool, limit: int) -> dict:
    """Count consecutive idle ticks; say when the loop should end itself.

    A tick is idle only when it had nothing to do *and* nobody is working. With
    no task-file changes but a specialist mid-task — a live claim or a running
    headless session — the project is not idle, it is busy, and the count
    resets. Otherwise a long task would end the loop under it.

    `limit` 0 means never stop. On stop the count resets, so a restarted loop
    starts fresh.
    """
    busy = [t["id"] for t in load_tasks()
            if t["status"] == "in-progress" and not claim_liveness(t)["stale"]]
    busy += [f"{s['agent']} session" for s in running_sessions()]

    path = state_dir() / "idle.json"
    try:
        count = int(json.loads(path.read_text(encoding="utf-8")).get("count", 0))
    except (OSError, ValueError):
        count = 0

    if not quiet:
        count, why = 0, "active"
    elif busy:
        count, why = 0, "busy: " + ", ".join(busy)
    else:
        count, why = count + 1, "idle"

    stop = limit > 0 and count >= limit
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"count": 0 if stop else count}), encoding="utf-8")
    return {"count": count, "limit": limit, "stop": stop, "why": why}
