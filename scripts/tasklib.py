"""Reading and editing this project's task files.

Shared by the board server and the task CLI. Standard library only.

Layout, relative to the workspace named in `.sliced-loop.json`:

    <workspace>/tasks/<ID>-<slug>.md
              /capabilities/
              /memory/{frontend,backend,decisions}.md
              /research/
"""

from __future__ import annotations

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
