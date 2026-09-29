#!/usr/bin/env python3
"""Start one agent as its own headless session.

    dispatch.py --harness H <agent> <task-id> [--resume [BRIEF]] [--wait]
    dispatch.py --harness H research --question Q [--wait]

Each agent runs as its own process with SLICED_LOOP_AGENT set, which the scope
hook reads, so its scope holds on every harness — including Gemini CLI and
Cursor, whose hooks cannot tell which subagent is acting. The session gets its
brief and one task, does it, and exits: one task per session, and a fresh
context every time. loop.py uses this for every agent on every harness.

Where the harness can load an agent by name — Claude Code (`claude -p
--agent`) and OpenCode (`opencode run --agent`) — and the agent is registered,
it does; otherwise the rendered brief is sent as the prompt.

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

AGENTS = (*tasklib.OWNERS, "research", "supervisor")
MODEL_FLAG = {"claude": "--model", "opencode": "--model", "codex": "--model",
              "gemini": "--model", "cursor": "--model"}
RESUME = ("Your own earlier session on this task died mid-task and its claim went stale; its work "
          "is on disk. Before changing anything, find out how far it got: read the task's thread and "
          "run your tree's checks (tests, typecheck, lint, build).")


# --- headless commands ------------------------------------------------------

def _cursor_bin() -> str:
    return "agent" if shutil.which("agent") else "cursor-agent"


def default_command(harness: str, root: Path, agent: str | None) -> list[str]:
    if harness == "claude":
        # Unattended, like --yolo elsewhere. The scope hook still runs and still denies.
        cmd = ["claude", "-p", "--permission-mode", "bypassPermissions"]
        return cmd + (["--agent", agent] if agent else []) + ["{prompt}"]
    if harness == "opencode":
        cmd = ["opencode", "run", "--auto", "--dir", str(root)]
        return cmd + (["--agent", agent] if agent else []) + ["{prompt}"]
    if harness == "codex":
        return ["codex", "exec", "-C", str(root), "--sandbox", "workspace-write", "{prompt}"]
    if harness == "gemini":
        return ["gemini", "--yolo", "-p", "{prompt}"]
    if harness == "cursor":
        return [_cursor_bin(), "-p", "--force", "--trust", "--workspace", str(root), "{prompt}"]
    raise SystemExit(f"unknown harness {harness!r}")


def command_for(harness: str, root: Path, agent: str | None, prompt: str,
                native: bool = False) -> list[str]:
    """The headless command for `agent` (None: a bare session). `native`: the
    harness loads the agent's brief itself from its name."""
    try:
        declared = json.loads((root / cfg_module.CONFIG_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        declared = {}
    custom = (declared.get("headless") or {}).get(harness)
    template = list(custom or default_command(harness, root, native_name(harness, agent) if native else None))
    if "{prompt}" not in template:
        raise SystemExit(f'headless command for {harness} has no "{{prompt}}" placeholder')
    # The agent's own model, unless a custom command already names one.
    model = cfg_module.model_for(tasklib.AGENTS[agent], harness) if agent in tasklib.AGENTS else ""
    if model and not custom:
        at = template.index("{prompt}")
        if at and template[at - 1] in ("-p", "--prompt"):  # an option whose value is the prompt
            at -= 1
        template[at:at] = [MODEL_FLAG[harness], model]
    return [prompt if part == "{prompt}" else part for part in template]


def agent_env(agent: str | None, root: Path) -> dict:
    env = dict(os.environ)
    env["SLICED_LOOP_ROOT"] = str(root)
    # Started from inside a Claude Code session (the loop command), the marker
    # it sets would make each `claude -p` behave as a nested session.
    env.pop("CLAUDECODE", None)
    for key in ("SLICED_LOOP_AGENT", "GEMINI_CLI_SLICED_LOOP_AGENT"):
        # GEMINI_CLI_* survives Gemini's hook-environment redaction.
        if agent:
            env[key] = agent
        else:
            env.pop(key, None)
    return env


def native_name(harness: str, agent: str | None) -> str | None:
    # Claude Code namespaces a plugin's own agents.
    if agent and harness == "claude" and agent in build.PLUGIN_AGENTS:
        return f"{build.PREFIX}:{agent}"
    return agent


def is_native(harness: str, agent: str) -> bool:
    """Can the harness load this agent by name? The plugin's own agents are
    installed with it; tree agents are registered by agents.py sync."""
    folder = {"claude": ".claude/agents", "opencode": ".opencode/agents"}.get(harness)
    if folder is None:
        return False
    return agent in build.PLUGIN_AGENTS or (tasklib.ROOT / folder / f"{agent}.md").is_file()


# --- prompts ----------------------------------------------------------------

def prompt_for(harness: str, agent: str, task: str | None, resume: str | None,
               question: str | None, native_agent: bool) -> str:
    parts = []
    if not native_agent:
        parts.append(f"You are the `{agent}` agent. Your brief:\n\n"
                     + build.brief_for(agent, harness).strip()
                     + "\n\n---\n")
    if agent == "research":
        parts.append("Answer this question, verbatim as asked — do not rephrase it into a topic:\n\n"
                     f"> {question}\n\n"
                     "Follow your brief: cite sources, argue the other side, say where the evidence "
                     "is thin, and write the finding to the workspace's `research/` directory. "
                     "Commit it with the command your brief gives, then stop.")
    else:
        parts.append(f"Your task: `{task}`.\n\n"
                     "Follow the session loop in your brief: read your memory file, claim the task, "
                     "complete it, update your memory file, commit with the command your brief gives, "
                     "report in five lines, and stop. "
                     "One task only — this session ends when it is done.")
    if resume:
        extra = "" if resume == RESUME else f"\n\nWhat was verified just now:\n\n{resume}"
        parts.append("\n**This is a resume.** " + RESUME + extra + "\n\n"
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
           native_agent: bool, quiet: bool = False) -> int:
    root = tasklib.ROOT
    argv = command_for(harness, root, agent, prompt, native=native_agent)
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
    if not quiet:
        print(f"{agent} on {label} exited {code} — log: {rel}")
    return code


def run_task(harness: str, agent: str, task: str, resume: bool = False) -> tuple[int, str]:
    """Run one agent on one task in the foreground, as loop.py does.
    Returns (exit code, the log's last line)."""
    native = is_native(harness, agent)
    prompt = prompt_for(harness, agent, task, RESUME if resume else None, None, native)
    code = launch(harness, agent, prompt, wait=True, label=task, native_agent=native, quiet=True)
    return code, last_line(agent, task)


def run_supervisor(harness: str, tick_text: str) -> tuple[int, str]:
    """One supervisor session on this tick's digest."""
    native = is_native(harness, "supervisor")
    brief = "" if native else ("You are the `supervisor` agent. Your brief:\n\n"
                               + build.brief_for("supervisor", harness).strip() + "\n\n---\n\n")
    code = launch(harness, "supervisor", brief + tick_text, wait=True, label="tick",
                  native_agent=native, quiet=True)
    return code, last_line("supervisor", "tick")


def last_line(agent: str, label: str) -> str:
    logs = sorted((tasklib.state_dir() / "logs").glob(f"*-{agent}-{label}.log"))
    if not logs:
        return ""
    lines = [l for l in logs[-1].read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
    return lines[-1][:160] if lines else ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--harness", required=True, choices=list(build.HARNESSES))
    parser.add_argument("agent", choices=AGENTS)
    parser.add_argument("task", nargs="?", help="task ID, e.g. FE-004")
    parser.add_argument("--resume", metavar="BRIEF", nargs="?", const=RESUME,
                        help="re-dispatch a STALE claim, optionally with what you verified")
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

    native = is_native(args.harness, args.agent)
    prompt = prompt_for(args.harness, args.agent, args.task, args.resume, args.question, native)
    label = args.task or ("question" if args.agent == "research" else "tick")
    return launch(args.harness, args.agent, prompt, wait=args.wait, label=label, native_agent=native)


if __name__ == "__main__":
    sys.exit(main())
