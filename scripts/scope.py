#!/usr/bin/env python3
"""Confine each specialist agent to the directories it owns — for any harness.

    scope.py hook <harness>         read a hook payload on stdin, answer in that
                                    harness's own deny format (claude, gemini,
                                    cursor, codex)
    scope.py check --agent A --kind read|write|shell (--path P | --command C) [--cwd D]
                                    exit 0 if allowed; exit 2 with the reason on
                                    stderr if not (the OpenCode plugin calls this)

The rules live here once; each harness only differs in how it hands over the
tool call and how it expects to hear "no".

    frontend  read+write  <frontend>/ <workspace>/
                          read-only: <workspace>/capabilities/, memory/backend.md
    backend   read+write  <backend>/  <workspace>/
                          read-only: memory/frontend.md
    research  read        <workspace>/   write only <workspace>/research/

Which agent is acting comes from the harness when it can say (Claude Code's
`agent_type`), otherwise from `SLICED_LOOP_AGENT`, which the loop driver sets
when it launches a specialist as its own headless process. The main thread, the
supervisor and anything unrecognised pass through untouched, and so does a
project with no `.sliced-loop.json`.

File tools are enforced exactly. Shell commands are checked by pattern only: a
shell has routes a text check cannot see, so this is a guard rail, not a jail.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as cfg_module  # noqa: E402

SCOPED = ("frontend", "backend", "research")
AGENT_ENV = "SLICED_LOOP_AGENT"
ROOT_ENVS = ("SLICED_LOOP_ROOT", "CLAUDE_PROJECT_DIR", "GEMINI_PROJECT_DIR")


# --- the rules --------------------------------------------------------------

def find_root(cwd: str | None) -> Path | None:
    for name in ROOT_ENVS:
        env = os.environ.get(name)
        if env and Path(env).is_dir():
            root = Path(env).resolve()
            return root if (root / cfg_module.CONFIG_NAME).is_file() else None
    if not cwd:
        return None
    here = Path(cwd).resolve()
    for candidate in (here, *here.parents):
        if (candidate / cfg_module.CONFIG_NAME).is_file():
            return candidate
    return None


def load_layout(root: Path) -> dict:
    try:
        cfg = cfg_module.load(root)
    except SystemExit:
        # Unreadable config: fall back to the defaults rather than failing open.
        cfg = dict(cfg_module.DEFAULTS)
    return {k: str(cfg[k]).strip().strip("/") for k in cfg_module.DEFAULTS}


def rules(agent: str, layout: dict) -> dict:
    fe, be, ws = layout["frontend"], layout["backend"], layout["workspace"]
    if agent == "frontend":
        return {
            "read": [fe, ws], "write": [fe, ws],
            "write_deny": rf"^{re.escape(ws)}/(capabilities(/|$)|memory/backend\.md$)",
            "write_deny_why": f"the published API contract in {ws}/capabilities/ and the backend's memory file",
            "shell_deny": [be],
        }
    if agent == "backend":
        return {
            "read": [be, ws], "write": [be, ws],
            "write_deny": rf"^{re.escape(ws)}/memory/frontend\.md$",
            "write_deny_why": "the frontend's memory file",
            "shell_deny": [fe],
        }
    return {
        "read": [ws], "write": [f"{ws}/research"],
        "write_deny": "", "write_deny_why": "",
        "shell_deny": [fe, be],
    }


def _under(abs_path: str, root: Path, rels: list[str]) -> bool:
    for rel in rels:
        base = os.path.normpath(os.path.join(os.path.realpath(root), rel))
        if abs_path == base or abs_path.startswith(base + os.sep):
            return True
    return False


def _listing(rels: list[str]) -> str:
    return ", ".join(f"{r}/" for r in rels)


def decide(agent: str, kind: str, root: Path, *, path: str = "",
           command: str = "", cwd: str = "") -> str | None:
    """None if the call is allowed, otherwise the reason it is not."""
    if agent not in SCOPED:
        return None
    layout = load_layout(root)
    r = rules(agent, layout)
    ws = layout["workspace"]

    if kind in ("read", "write"):
        if not path:
            return None
        base = cwd or str(root)
        abs_path = os.path.realpath(path if os.path.isabs(path) else os.path.join(base, path))
        allowed = r[kind]
        if not _under(abs_path, root, allowed):
            return (f"Out of scope: the {agent} agent may {kind} only within {_listing(allowed)}. "
                    f"Blocked: {abs_path}. If this needs work outside your scope, open a task in "
                    f"{ws}/tasks/ for the agent that owns it and mark yourself blocked on it.")
        if kind == "write" and r["write_deny"]:
            rel = os.path.relpath(abs_path, os.path.realpath(root))
            if re.search(r["write_deny"], rel):
                return (f"Read-only for the {agent} agent: {r['write_deny_why']}. Blocked write: {rel}. "
                        f"If it is wrong, raise it in a task rather than editing it.")
        return None

    if kind == "shell" and command:
        dirs = "|".join(re.escape(d) for d in r["shell_deny"])
        if re.search(rf"(^|[^A-Za-z0-9_.-])\.{{0,2}}/?({dirs})(/|$)", command, re.M):
            names = " or ".join(f"{d}/" for d in r["shell_deny"])
            return f"Out of scope: the {agent} agent must not touch {names}. Command referenced it: {command}"
    return None


# --- harness adapters -------------------------------------------------------
#
# Each adapter turns a payload into (agent, kind, path, command, cwd) and knows
# how to print a denial. Tool names differ per harness; unknown tools pass.

def _get(d: dict, *keys: str) -> str:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v:
            return v
    return ""


def _env_agent() -> str:
    # The GEMINI_CLI_ copy survives Gemini's hook-environment redaction.
    return (os.environ.get(AGENT_ENV) or os.environ.get("GEMINI_CLI_" + AGENT_ENV) or "").strip()


CLAUDE_TOOLS = {"Read": "read", "Glob": "read", "Grep": "read",
                "Edit": "write", "Write": "write", "NotebookEdit": "write",
                "Bash": "shell"}

GEMINI_TOOLS = {"read_file": "read", "read_many_files": "read", "glob": "read",
                "search_file_content": "read", "grep": "read", "list_directory": "read",
                "write_file": "write", "replace": "write", "edit": "write",
                "run_shell_command": "shell"}


CURSOR_TOOLS = {"shell": "shell", "read": "read", "grep": "read", "glob": "read",
                "write": "write", "edit": "write", "delete": "write"}


def parse_claude(p: dict) -> tuple:
    agent = _get(p, "agent_type") or _env_agent()
    ti = p.get("tool_input") or {}
    kind = CLAUDE_TOOLS.get(p.get("tool_name", ""), "")
    return (agent, kind, _get(ti, "file_path", "notebook_path", "path"),
            _get(ti, "command"), _get(p, "cwd"))


def parse_gemini(p: dict) -> tuple:
    ti = p.get("tool_input") or {}
    kind = GEMINI_TOOLS.get(p.get("tool_name", ""), "")
    path = _get(ti, "file_path", "absolute_path", "path", "dir_path")
    if not path and isinstance(ti.get("paths"), list) and ti["paths"]:
        path = str(ti["paths"][0])
    return (_get(p, "agent_type", "agent_name") or _env_agent(), kind, path,
            _get(ti, "command"), _get(p, "cwd"))


def parse_cursor(p: dict) -> tuple:
    event = _get(p, "hook_event_name")
    roots = p.get("workspace_roots") or []
    cwd = _get(p, "cwd") or (roots[0] if roots else "")
    agent = _get(p, "agent_type", "subagent_type") or _env_agent()
    if event == "beforeShellExecution" or "command" in p:
        return (agent, "shell", "", _get(p, "command"), cwd)
    if event == "beforeReadFile":
        return (agent, "read", _get(p, "file_path"), "", cwd)
    if event == "preToolUse":
        ti = p.get("tool_input") or {}
        name = str(p.get("tool_name", "")).lower()
        kind = CURSOR_TOOLS.get(name, "")
        return (agent, kind, _get(ti, "file_path", "path", "target_file"),
                _get(ti, "command"), cwd)
    return (agent, "write" if _get(p, "file_path") else "", _get(p, "file_path"), "", cwd)


def parse_codex(p: dict) -> tuple:
    ti = p.get("tool_input") or {}
    name = _get(p, "tool_name")
    kind = "shell" if name in ("Bash", "shell", "exec_command", "local_shell") else ""
    command = _get(ti, "command")
    if not command and isinstance(ti.get("command"), list):
        command = " ".join(map(str, ti["command"]))
    if name == "apply_patch":
        kind = "write"
    return (_get(p, "agent_type", "agent_role") or _env_agent(), kind,
            _get(ti, "file_path", "path"), command, _get(p, "cwd"))


def deny_claude(reason: str) -> int:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))
    return 0


def deny_gemini(reason: str) -> int:
    print(json.dumps({"decision": "deny", "reason": reason}))
    return 0


def deny_cursor(reason: str) -> int:
    print(json.dumps({"permission": "deny", "user_message": reason, "agent_message": reason}))
    return 0


def allow_cursor() -> int:
    print(json.dumps({"permission": "allow"}))
    return 0


def deny_codex(reason: str) -> int:
    return deny_claude(reason)


ADAPTERS = {
    "claude": (parse_claude, deny_claude, lambda: 0),
    "gemini": (parse_gemini, deny_gemini, lambda: 0),
    "cursor": (parse_cursor, deny_cursor, allow_cursor),
    "codex": (parse_codex, deny_codex, lambda: 0),
}


def apply_patch_paths(patch: str) -> list[str]:
    return re.findall(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", patch, re.M)


def cmd_hook(harness: str) -> int:
    parse, deny, allow = ADAPTERS[harness]
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return allow()
    agent, kind, path, command, cwd = parse(payload)
    if agent not in SCOPED or not kind:
        return allow()
    root = find_root(cwd or os.getcwd())
    if root is None:
        return allow()

    # Codex writes through apply_patch: every file the patch names is a write.
    if harness == "codex" and kind == "write" and not path:
        patch = _get(payload.get("tool_input") or {}, "input", "patch", "command")
        for target in apply_patch_paths(patch):
            reason = decide(agent, "write", root, path=target.strip(), cwd=cwd)
            if reason:
                return deny(reason)
        return allow()

    reason = decide(agent, kind, root, path=path, command=command, cwd=cwd)
    return deny(reason) if reason else allow()


def cmd_check(args: argparse.Namespace) -> int:
    agent = args.agent or _env_agent()
    root = find_root(args.cwd or os.getcwd())
    if root is None:
        return 0
    reason = decide(agent, args.kind, root, path=args.path or "",
                    command=args.command or "", cwd=args.cwd or "")
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("hook")
    h.add_argument("harness", choices=sorted(ADAPTERS))
    c = sub.add_parser("check")
    c.add_argument("--agent", default="")
    c.add_argument("--kind", required=True, choices=["read", "write", "shell"])
    c.add_argument("--path")
    c.add_argument("--command")
    c.add_argument("--cwd")
    args = parser.parse_args()
    return cmd_hook(args.harness) if args.cmd == "hook" else cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
