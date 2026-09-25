#!/usr/bin/env python3
"""Commit one agent's work, and only that agent's.

    commit.py <frontend|backend> <task-id>    after finishing a task
    commit.py research                        after writing a finding
    commit.py supervisor                      after a review, triage or plan

Each file goes to the repository that holds it. With the layout `repos.py init`
sets up, an agent's code goes to its tree's own repository, and its workspace
files (task, memory, contract) go to the root repository, which the other agents
share. Where both trees live in one repository, everything goes there.

The workspace repository is written by several agents at once, so `git add -A`
or `git commit -a` would sweep another agent's half-finished work into this
commit. This stages and commits an explicit list of the files the agent owns,
so a commit never carries anything else:

    frontend    <frontend>/, memory/frontend.md, design/, and the task files
                it owns or opened
    backend     <backend>/, memory/backend.md, capabilities/, and the task
                files it owns or opened
    research    research/
    supervisor  PROJECT.md, memory/decisions.md, design/DESIGN.md, tasks/

Commits use `--only` with those paths, so even something another agent has
staged in the meantime stays out. If the other agent holds git's index lock,
this retries.

The message comes from the task file, not from the command line, so the agent
passes no free text for the shell scope check to misread. The subject is
`<ID>: <title>`, and the body is the status change plus the agent's latest
thread line. For the supervisor, the body is every task whose status moved.

Nothing is pushed. `"commit": false` in .sliced-loop.json turns this off.
Pre-commit hooks run; a failing one fails the commit, with its output.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config as cfg_module  # noqa: E402
import tasklib  # noqa: E402

AGENTS = ("frontend", "backend", "research", "supervisor")


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True)


def repo_of(path: Path) -> Path | None:
    """The top level of the repository holding `path` (which may not exist yet)."""
    probe = path
    while not probe.is_dir():
        probe = probe.parent
    out = git(probe, "rev-parse", "--show-toplevel")
    return Path(out.stdout.strip()).resolve() if out.returncode == 0 else None


def repo_blocked(repo: Path) -> str | None:
    gitdir = Path(git(repo, "rev-parse", "--absolute-git-dir").stdout.strip())
    for marker, what in (("MERGE_HEAD", "a merge"), ("rebase-merge", "a rebase"),
                         ("rebase-apply", "a rebase"), ("CHERRY_PICK_HEAD", "a cherry-pick")):
        if (gitdir / marker).exists():
            return f"{repo} is in the middle of {what} — a human needs to finish it"
    return None


# --- what belongs to whom ---------------------------------------------------

def owned_paths(agent: str) -> list[Path]:
    ws = tasklib.WORKSPACE
    if agent == "research":
        return [ws / "research"]
    if agent == "supervisor":
        return [ws / "PROJECT.md", ws / "memory" / "decisions.md", ws / "design" / "DESIGN.md",
                ws / "tasks"]
    paths = [tasklib.TREES[agent], ws / "memory" / f"{agent}.md",
             ws / ("capabilities" if agent == "backend" else "design")]
    for t in tasklib.load_tasks():
        if t["owner"] == agent or t["requested_by"] == agent:
            paths.append(tasklib.tasks_dir() / t["file"])
    return paths


def by_repo(paths: list[Path]) -> dict[Path, list[str]]:
    """Pathspecs grouped by the repository that holds them, relative to it."""
    groups: dict[Path, list[str]] = {}
    for p in paths:
        repo = repo_of(p.resolve())
        if repo is not None:
            groups.setdefault(repo, []).append(p.resolve().relative_to(repo).as_posix() or ".")
    return groups


def changed_files(repo: Path, pathspecs: list[str]) -> list[str]:
    """Every changed, added or deleted file under the pathspecs, as git sees it."""
    out = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", *pathspecs)
    if out.returncode != 0:
        raise SystemExit(f"git status failed: {out.stderr.strip()}")
    fields = out.stdout.split("\0")
    files, i = [], 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        files.append(path)
        if code[0] in "RC" and i < len(fields):  # a rename carries its old path next
            files.append(fields[i])
            i += 1
    return sorted(set(files))


# --- the message ------------------------------------------------------------

def head_status(task_path: Path) -> str:
    repo = repo_of(task_path)
    if repo is None:
        return ""
    shown = git(repo, "show", f"HEAD:{task_path.resolve().relative_to(repo).as_posix()}")
    if shown.returncode != 0:
        return ""
    fields, _ = tasklib.parse_frontmatter(shown.stdout)
    return str(fields.get("status", ""))


def last_thread_line(body: str, agent: str) -> str:
    heading = re.search(r"^## Thread[^\n]*$", body, re.M)
    if not heading:
        return ""
    mine = [l.strip() for l in body[heading.end():].splitlines()
            if re.match(rf"^-\s*\S+\s+{re.escape(agent)}:", l.strip())]
    return mine[-1] if mine else ""


def moves(changed: set[Path]) -> list[str]:
    lines = []
    for t in tasklib.by_priority(tasklib.load_tasks()):
        path = (tasklib.tasks_dir() / t["file"]).resolve()
        if path not in changed:
            continue
        was = head_status(path)
        if not was:
            lines.append(f"- {t['id']} opened ({t['status']}): {t['title']}")
        elif was != t["status"]:
            lines.append(f"- {t['id']} {was} -> {t['status']}: {t['title']}")
    return lines


def message(agent: str, task_id: str | None, changed: set[Path]) -> str:
    """One message for the task, used in every repository it touched."""
    if agent in tasklib.OWNERS:
        task = next(t for t in tasklib.load_tasks() if t["id"] == task_id)
        was = head_status(tasklib.tasks_dir() / task["file"])
        body = [f"{task['id']} {was or 'new'} -> {task['status']}"]
        if (note := last_thread_line(task["body"], agent)):
            body.append(note)
        body.append(f"\nAgent: {agent}")
        return f"{task['id']}: {task['title']}\n\n" + "\n".join(body)

    if agent == "research":
        titles = []
        for p in sorted(changed):
            if p.suffix == ".md" and p.name != "README.md" and p.is_file():
                fields, _ = tasklib.parse_frontmatter(p.read_text(encoding="utf-8"))
                titles.append(str(fields.get("title") or p.stem))
        subject = f"research: {titles[0]}" if titles else "research: update findings"
        rest = "\n".join(f"- {t}" for t in titles[1:])
        return subject + (f"\n\n{rest}" if rest else "") + "\n\nAgent: research"

    moved = moves(changed)
    subject = "supervisor: " + (f"{len(moved)} task(s) moved" if moved else "update the plan")
    return subject + ("\n\n" + "\n".join(moved) if moved else "") + "\n\nAgent: supervisor"


# --- commit -----------------------------------------------------------------

LOCK_ERRORS = ("index.lock", "cannot lock ref", "Unable to create", "unable to write new index")


def commit(repo: Path, files: list[str], msg: str) -> subprocess.CompletedProcess:
    for attempt in range(12):
        added = git(repo, "add", "-A", "--", *files)
        result = added if added.returncode != 0 else git(repo, "commit", "--only", "-m", msg, "--", *files)
        out = result.stderr + result.stdout
        # Another agent committing to the same repository holds the index or
        # HEAD for a moment; wait and retry rather than fail the close-out.
        if result.returncode == 0 or not any(m in out for m in LOCK_ERRORS):
            return result
        time.sleep(1 + attempt % 3)  # the other agent is committing; wait our turn
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("agent", choices=AGENTS)
    parser.add_argument("task", nargs="?", help="the task ID, for frontend and backend")
    parser.add_argument("--dry-run", action="store_true", help="show what would be committed")
    args = parser.parse_args()

    cfg_module.require()
    if cfg_module.setting("commit", True, tasklib.ROOT) is False:
        print('commits are off for this project ("commit": false) — nothing done')
        return 0
    if args.agent in tasklib.OWNERS:
        if not args.task:
            parser.error(f"{args.agent} needs the task ID it just finished")
        task = next((t for t in tasklib.load_tasks() if t["id"] == args.task), None)
        if task is None:
            print(f"no task with id {args.task!r}", file=sys.stderr)
            return 2
        if task["owner"] != args.agent:
            print(f"{args.task} is owned by {task['owner'] or 'nobody'}, not {args.agent}", file=sys.stderr)
            return 2
    groups = by_repo(owned_paths(args.agent))
    if not groups:
        print("not committing: not a git repository")
        return 0
    for repo in groups:
        if (why := repo_blocked(repo)):
            print(f"not committing: {why}", file=sys.stderr)
            return 1

    changes = {repo: files for repo, specs in groups.items() if (files := changed_files(repo, specs))}
    if not changes:
        print("nothing to commit")
        return 0
    changed = {(repo / f).resolve() for repo, files in changes.items() for f in files}
    msg = message(args.agent, args.task, changed)
    if args.dry_run:
        print(msg)
        for repo, files in changes.items():
            print(f"\n{repo}:\n" + "\n".join(f"  {f}" for f in files))
        return 0

    code = 0
    for repo, files in changes.items():
        result = commit(repo, files, msg)
        root = tasklib.ROOT.resolve()
        name = ("root" if root.is_relative_to(repo)
                else repo.relative_to(root).as_posix() if repo.is_relative_to(root) else str(repo))
        if result.returncode != 0:
            print(f"{name}: commit failed — nothing committed there:\n"
                  + (result.stdout + result.stderr).strip(), file=sys.stderr)
            code = 1
            continue
        sha = git(repo, "rev-parse", "--short", "HEAD").stdout.strip()
        print(f"{name}: committed {sha} {msg.splitlines()[0]} ({len(files)} file(s))")
    return code


if __name__ == "__main__":
    sys.exit(main())
