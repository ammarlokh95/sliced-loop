#!/usr/bin/env python3
"""Give every agent's source tree its own git repository.

    repos.py status               what each tree and the project root are now
    repos.py init [AGENT…]        create what is missing; never touches tracked work
    repos.py init --split-tracked also split out a tree the root repo already tracks

The layout this sets up:

    <root>/            repository — .sliced-loop.json and the workspace
    ├── <tree>/        one per agent in .sliced-loop.json: its own
    └── <tree>/        repository, ignored by the root one

Each specialist commits its code to its own repository, where nothing else
writes. The shared workspace (backlog, memory, published contract) stays in the
root repository, beside the config that points at both trees.

`init` is safe to re-run: a tree that already has its own repository is left
alone, and so is one the root repository tracks — splitting that one out
removes it from the root repository's index (its history stays there, the new
repository starts fresh), which is a decision for a human. `--split-tracked`
makes it.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config as cfg_module  # noqa: E402


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)


def toplevel(path: Path) -> Path | None:
    probe = path if path.is_dir() else path.parent
    out = git(probe, "rev-parse", "--show-toplevel")
    return Path(out.stdout.strip()).resolve() if out.returncode == 0 else None


def tree_state(root: Path, tree: Path) -> str:
    """own | tracked-by-root | untracked-in-root | missing | no-root-repo"""
    if not tree.is_dir():
        return "missing"
    if (tree / ".git").exists():
        return "own"
    root_top = toplevel(root)
    if root_top is None:
        return "no-root-repo"
    rel = tree.resolve().relative_to(root_top).as_posix()
    tracked = git(root_top, "ls-files", "--", rel).stdout.strip()
    return "tracked-by-root" if tracked else "untracked-in-root"


def ignore_in_root(root: Path, rels: list[str]) -> list[str]:
    """Add /<tree>/ lines to the root .gitignore; return the ones added."""
    path = root / ".gitignore"
    have = {l.strip() for l in path.read_text(encoding="utf-8").splitlines()} if path.is_file() else set()
    wanted = [f"/{r}/" for r in rels if not {f"/{r}/", f"{r}/", f"/{r}"} & have]
    return cfg_module.gitignore_add(root, "# source trees with their own repositories (sliced-loop)", wanted)


def first_commit(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    if not git(repo, "status", "--porcelain").stdout.strip():
        return "empty — its first commit comes with its first task"
    out = git(repo, "commit", "-m", message)
    if out.returncode != 0:
        return "files left uncommitted: " + (out.stderr or out.stdout).strip().splitlines()[-1]
    return "initial commit " + git(repo, "rev-parse", "--short", "HEAD").stdout.strip()


def cmd_status(cfg: dict) -> int:
    root = cfg["root"]
    top = toplevel(root)
    where = "no repository" if top is None else ("repository" if top == root.resolve() else f"inside {top}")
    print(f"root      {where}")
    for name, a in cfg["agents"].items():
        print(f"{name:12} {tree_state(root, a['path_abs']):18} {a['path']}/")
    return 0


def cmd_init(cfg: dict, split_tracked: bool, only: list[str] | None = None) -> int:
    root = cfg["root"]
    code = 0

    # A project inside a larger repository keeps using it for the workspace;
    # only a project with no repository at all gets one here.
    if toplevel(root) is None:
        git(root, "init", "-q")
        print(f"root      initialised a repository at {root}")

    split = []
    for key, a in cfg["agents"].items():
        if only and key not in only:
            continue
        tree, rel = a["path_abs"], a["path"]
        state = tree_state(root, tree)
        if state == "missing":
            print(f"{key:12} {rel}/ does not exist — create it, then re-run")
            code = 1
            continue
        if state == "own":
            print(f"{key:12} {rel}/ already has its own repository — left alone")
            split.append(rel)
            continue
        if state == "tracked-by-root":
            if not split_tracked:
                print(f"{key:12} {rel}/ is tracked by the root repository — NOT split. Splitting it "
                      f"removes it from the root repository's index; its history stays there. "
                      f"Re-run with --split-tracked once the user has agreed.")
                code = 1
                continue
            git(root, "rm", "-r", "-q", "--cached", "--", rel)
            print(f"{key:12} removed {rel}/ from the root repository's index — commit that removal "
                  f"in the root repository")
        git(tree, "init", "-q")
        print(f"{key:12} initialised {rel}/ — {first_commit(tree, f'Initial {key} tree')}")
        split.append(rel)

    if split:
        added = ignore_in_root(root, split)
        if added:
            print(f"root      .gitignore now excludes {', '.join(added)} — "
                  f"{'it is its own repository' if len(added) == 1 else 'each is its own repository'}")
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    i = sub.add_parser("init")
    i.add_argument("agents", nargs="*", help="only these agents' trees (default: all)")
    i.add_argument("--split-tracked", action="store_true",
                   help="also split out a tree the root repository tracks (ask the user first)")
    args = parser.parse_args()
    cfg = cfg_module.require()
    if args.cmd == "status":
        return cmd_status(cfg)
    unknown = [a for a in args.agents if a not in cfg["agents"]]
    if unknown:
        parser.error(f"no agent named {', '.join(unknown)} in {cfg_module.CONFIG_NAME}")
    return cmd_init(cfg, args.split_tracked, args.agents)


if __name__ == "__main__":
    sys.exit(main())
