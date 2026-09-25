#!/usr/bin/env python3
"""Start one specialist agent as its own headless session.

    dispatch.py --harness H <agent> <task-id> [--resume BRIEF] [--wait]
    dispatch.py --harness H research --question Q [--wait]

For harnesses whose hooks cannot tell which subagent is acting (Gemini CLI,
Cursor), a specialist cannot safely run as a subagent: its scope would go
unenforced. Here it runs as a separate process instead, with SLICED_LOOP_AGENT
set, which the scope hook reads. The session gets the agent's rendered brief
and one task, does it, and exits — one task per session, as everywhere else.

By default the session is detached and this returns at once, logging to
`<workspace>/.state/logs/`. `--wait` runs it in the foreground.

Refuses an agent that already has a session running, or that holds a live
`in-progress` claim — a second session on the same tree would collide. A STALE
claim is not live; pass `--resume` to re-dispatch it.

The headless command for each harness can be overridden in .sliced-loop.json:

    "headless": {"gemini": ["gemini", "--yolo", "-m", "gemini-3-pro", "-p", "{prompt}"]}
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build  # noqa: E402
import config as cfg_module  # noqa: E402
import tasklib  # noqa: E402

AGENTS = ("frontend", "backend", "research", "supervisor")


# --- headless commands ------------------------------------------------------

def _cursor_bin() -> str:
    return "agent" if shutil.which("agent") else "cursor-agent"


def default_command(harness: str, root: Path, agent: str | None) -> list[str]:
    if harness == "opencode":
        cmd = ["opencode", "run", "--auto", "--dir", str(root)]
        return cmd + (["--agent", agent] if agent else []) + ["{prompt}"]
    if harness == "codex":
        return ["codex", "exec", "-C", str(root), "--sandbox", "workspace-write", "{prompt}"]
    if harness == "gemini":
        return ["gemini", "--yolo", "-p", "{prompt}"]
    if harness == "cursor":
        return [_cursor_bin(), "-p", "--force", "--trust", "--workspace", str(root), "{prompt}"]
    raise SystemExit(f"{harness} runs its agents in-session — use its supervise command instead")


def command_for(harness: str, root: Path, agent: str | None, prompt: str) -> list[str]:
    try:
        declared = json.loads((root / cfg_module.CONFIG_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        declared = {}
    template = (declared.get("headless") or {}).get(harness) or default_command(harness, root, agent)
    if "{prompt}" not in template:
        raise SystemExit(f'headless command for {harness} has no "{{prompt}}" placeholder')
    return [prompt if part == "{prompt}" else part for part in template]


def agent_env(agent: str | None, root: Path) -> dict:
    env = dict(os.environ)
    env["SLICED_LOOP_ROOT"] = str(root)
    for key in ("SLICED_LOOP_AGENT", "GEMINI_CLI_SLICED_LOOP_AGENT"):
        # GEMINI_CLI_* survives Gemini's hook-environment redaction.
        if agent:
            env[key] = agent
        else:
            env.pop(key, None)
    return env


# --- prompts ----------------------------------------------------------------

def prompt_for(harness: str, agent: str, task: str | None, resume: str | None,
               question: str | None, native_agent: bool) -> str:
    parts = []
    if not native_agent:
        parts.append(f"You are the `{agent}` agent. Your brief:\n\n"
                     + build.body_for("agents", agent, harness).strip()
                     + "\n\n---\n")
    if agent == "research":
        parts.append("Answer this question, verbatim as asked — do not rephrase it into a topic:\n\n"
                     f"> {question}\n\n"
                     "Follow your brief: cite sources, argue the other side, say where the evidence "
                     "is thin, and write the finding to the workspace's `research/` directory. "
                     "Then stop.")
    else:
        parts.append(f"Your task: `{task}`.\n\n"
                     "Follow the session loop in your brief: read your memory file, claim the task, "
                     "complete it, update your memory file, report in five lines, and stop. "
                     "One task only — this session ends when it is done.")
    if resume:
        parts.append("\n**This is a resume.** Your own earlier session on this task was killed "
                     "mid-task; its work is intact on disk. What the supervisor verified just now:\n\n"
                     f"{resume}\n\n"
                     "Do not start over, do not rebuild, and do not second-guess the stack your "
                     "earlier session chose — that session was you, and its decisions stand. Do not "
                     "tick any acceptance criterion you have not verified yourself in this session.")
    return "\n".join(parts)


# --- locks ------------------------------------------------------------------

def running_dir() -> Path:
    return tasklib.state_dir() / "running"


def running(agent: str) -> dict | None:
    path = running_dir() / f"{agent}.json"
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if tasklib.alive(int(info.get("pid", 0))):
        return info
    path.unlink(missing_ok=True)
    return None


def live_claim(agent: str) -> dict | None:
    for t in tasklib.load_tasks():
        if t["owner"] == agent and t["status"] == "in-progress":
            if not tasklib.claim_liveness(t)["stale"]:
                return t
    return None


# --- main -------------------------------------------------------------------

def launch(harness: str, agent: str, prompt: str, *, wait: bool, label: str,
           native_agent: bool) -> int:
    root = tasklib.ROOT
    argv = command_for(harness, root, agent if native_agent else None, prompt)
    if not shutil.which(argv[0]):
        raise SystemExit(f"{argv[0]} is not on PATH — is {harness} installed?")

    logs = tasklib.state_dir() / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    log = logs / f"{stamp}-{agent}-{label}.log"
    env = agent_env(agent if agent != "supervisor" else None, root)

    with open(log, "w", encoding="utf-8") as out:
        proc = subprocess.Popen(argv, cwd=str(root), env=env, stdin=subprocess.DEVNULL,
                                stdout=out, stderr=subprocess.STDOUT,
                                start_new_session=not wait)
    lock = running_dir() / f"{agent}.json"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"pid": proc.pid, "task": label, "harness": harness,
                                "started": stamp, "log": str(log)}), encoding="utf-8")
    rel = log.relative_to(root)
    if not wait:
        print(f"started {agent} on {label} ({harness}, pid {proc.pid}) — log: {rel}")
        return 0
    code = proc.wait()
    lock.unlink(missing_ok=True)
    print(f"{agent} on {label} exited {code} — log: {rel}")
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--harness", required=True, choices=[h for h in build.HARNESSES if h != "claude"])
    parser.add_argument("agent", choices=AGENTS)
    parser.add_argument("task", nargs="?", help="task ID, e.g. FE-004")
    parser.add_argument("--resume", metavar="BRIEF", help="re-dispatch a STALE claim with this resume brief")
    parser.add_argument("--question", help="the research question, verbatim")
    parser.add_argument("--wait", action="store_true", help="run in the foreground")
    args = parser.parse_args()

    cfg_module.require()
    if args.agent == "research":
        if not args.question:
            parser.error("research needs --question")
    elif args.agent != "supervisor" and not args.task:
        parser.error(f"{args.agent} needs a task ID")

    if (info := running(args.agent)):
        print(f"refused: {args.agent} already has a session running on {info['task']} "
              f"(pid {info['pid']}) — never wake a busy agent", file=sys.stderr)
        return 3
    if args.agent in tasklib.OWNERS and not args.resume and (t := live_claim(args.agent)):
        print(f"refused: {args.agent} is BUSY on {t['id']} — never wake a busy agent. "
              f"If `status` reports it STALE, pass --resume.", file=sys.stderr)
        return 3
    if args.task and args.agent in tasklib.OWNERS and tasklib.find_task_file(args.task) is None:
        print(f"refused: no task with id {args.task!r}", file=sys.stderr)
        return 2

    native = args.harness == "opencode"  # `opencode run --agent` loads the brief itself
    prompt = prompt_for(args.harness, args.agent, args.task, args.resume, args.question, native)
    label = args.task or ("question" if args.agent == "research" else "tick")
    return launch(args.harness, args.agent, prompt, wait=args.wait, label=label, native_agent=native)


if __name__ == "__main__":
    sys.exit(main())
