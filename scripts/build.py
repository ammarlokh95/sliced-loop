#!/usr/bin/env python3
"""Render the agents and commands in src/ for each supported harness.

    build.py                  render Claude Code's files at the repo root
    build.py --check          fail if the committed Claude Code files are stale
    build.py <harness>...     render that harness into dist/<harness>/

The prompts are written once, in src/, with a handful of tokens for what really
differs between harnesses — how a command is invoked, how its arguments arrive,
how a subagent is spawned, where the scripts live. Everything else is shared.

Claude Code's output is committed, because a Claude plugin is installed straight
from the repository. Every other harness's output goes to dist/ (gitignored):
those harnesses have no plugin-root variable a prompt can use, so their files
carry this checkout's absolute path. `install.py` puts them where each harness
looks.

Tokens:
    {{scripts}} {{templates}}   where this plugin's scripts and templates live
    {{args}}                    the command's arguments
    {{cmd:NAME}}                how the user invokes command NAME
    {{spawn:NAME}} {{Spawn:NAME}}  how to hand work to subagent NAME
    {{loop}}                    how to start the supervision loop
    {{harness}}                 this harness's id
    {{restart_note}}            what to say about picking up a fresh install

Conditional blocks, not nested:
    <!-- if:inproc -->  …  <!-- endif -->   subagents run inside the session
    <!-- if:headless --> … <!-- endif -->   specialists run as their own process
    <!-- if:claude,codex --> … <!-- endif -->  named harnesses
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from tasklib import parse_frontmatter  # noqa: E402

PLUGIN_ROOT = HERE.parent
SRC = PLUGIN_ROOT / "src"
DIST = PLUGIN_ROOT / "dist"
PREFIX = "sliced-loop"

# How each harness runs a specialist. `inproc`: as a subagent of the session,
# because the scope hook can tell which subagent is calling. `headless`: as its
# own process with SLICED_LOOP_AGENT set, because the hook cannot.
HARNESSES = {
    "claude":   {"mode": "inproc"},
    "opencode": {"mode": "inproc"},
    "codex":    {"mode": "inproc"},
    "gemini":   {"mode": "headless"},
    "cursor":   {"mode": "headless"},
}
SPECIALISTS = ("frontend", "backend", "research")

ARGS_PREAMBLE = ("`<ARGUMENTS>` below stands for whatever the user wrote after invoking "
                 "this command. It may be empty.\n\n")

RESTART_NOTES = {
    "claude": ("**the agents and the scope hook are\nread at startup**, so this session "
               "cannot use them. They register on the next\n`claude` launch — "
               "`claude --continue` keeps this conversation."),
    "opencode": ("**OpenCode loads agents, commands and\nplugins at startup**, so this session "
                 "cannot use them. Restart `opencode` — `opencode --continue` keeps this "
                 "conversation."),
    "codex": ("**Codex loads agents, skills and hooks\nat startup**, so this session cannot use "
              "them. Restart `codex`, then approve the sliced-loop scope hook in `/hooks` — "
              "Codex does not run a hook until it has been reviewed, and without it the "
              "specialists are unconfined."),
    "gemini": ("**Gemini CLI loads extensions at\nstartup**, so this session cannot use it. "
               "Restart `gemini` — `gemini --resume latest` keeps this conversation."),
    "cursor": ("**Cursor loads plugins at startup**,\nso this session cannot use them. "
               "Reload the window, or restart `agent` for the CLI."),
}


def _cmd(h: str, name: str) -> str:
    if h in ("claude", "gemini"):
        return f"/{PREFIX}:{name}"
    if h == "codex":
        return f"${PREFIX}-{name}"
    return f"/{PREFIX}-{name}"


def _spawn(h: str, name: str) -> str:
    return {
        "claude":   f"spawn the `{name}` agent",
        "opencode": f"spawn the `{name}` subagent (the task tool, `subagent_type: {name}`)",
        "codex":    f"spawn the `{name}` agent (`spawn_agent` with `agent_type: \"{name}\"`)",
        "gemini":   f"delegate to the `{name}` subagent",
        "cursor":   f"delegate to the `{name}` subagent (the Task tool)",
    }[h]


def _args(h: str) -> str:
    if h in ("claude", "opencode"):
        return "$ARGUMENTS"
    if h == "gemini":
        return "{{args}}"
    return "<ARGUMENTS>"


def _root(h: str, root: Path) -> str:
    return "${CLAUDE_PLUGIN_ROOT}" if h == "claude" else str(root)


def _loop(h: str, root: Path) -> str:
    if h == "claude":
        return f"/loop 15m {_cmd(h, 'supervise')}"
    return f'python3 "{root}/scripts/loop.py" --harness {h} --every 15m'


COND = re.compile(r"<!-- if:([a-z,]+) -->\n?(.*?)<!-- endif -->\n?", re.S)


def render(text: str, h: str, root: Path = PLUGIN_ROOT) -> str:
    mode = HARNESSES[h]["mode"]

    def keep(m: re.Match) -> str:
        wanted = m.group(1).split(",")
        return m.group(2) if (h in wanted or mode in wanted) else ""

    text = COND.sub(keep, text)
    if "<!-- if:" in text or "<!-- endif -->" in text:
        raise SystemExit("unbalanced or nested <!-- if: --> block in a src/ file")
    text = re.sub(r"\n{3,}", "\n\n", text)

    base = _root(h, root)
    subs = {
        "scripts": f"{base}/scripts",
        "templates": f"{base}/templates",
        "loop": _loop(h, root),
        "harness": h,
        "restart_note": RESTART_NOTES[h],
    }
    text = re.sub(r"\{\{cmd:([a-z-]+)\}\}", lambda m: _cmd(h, m.group(1)), text)
    text = re.sub(r"\{\{spawn:([a-z<>-]+)\}\}", lambda m: _spawn(h, m.group(1)), text)
    text = re.sub(r"\{\{Spawn:([a-z<>-]+)\}\}",
                  lambda m: (s := _spawn(h, m.group(1)))[0].upper() + s[1:], text)
    for key, value in subs.items():
        text = text.replace("{{" + key + "}}", value)
    # Last, so a harness whose own syntax is {{args}} is not substituted twice.
    uses_args = "{{args}}" in text
    text = text.replace("{{args}}", _args(h))
    if uses_args and _args(h) == "<ARGUMENTS>":
        text = ARGS_PREAMBLE + text.lstrip("\n")
    return text


# --- sources ----------------------------------------------------------------

def split(path: Path) -> tuple[str, dict, str]:
    """(raw frontmatter, parsed fields, body) of a source file."""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"\A---\n(.*?)\n---\n?(.*)\Z", text, re.S)
    if not m:
        return "", {}, text
    fields, _ = parse_frontmatter(text)
    return m.group(1), fields, m.group(2)


def sources(kind: str) -> list[Path]:
    return sorted((SRC / kind).glob("*.md"))


def body_for(kind: str, name: str, h: str, root: Path = PLUGIN_ROOT) -> str:
    """A rendered agent brief or command body, without frontmatter."""
    _, _, body = split(SRC / kind / f"{name}.md")
    return render(body, h, root).lstrip("\n")


# --- per-harness writers ----------------------------------------------------

def _front(fields: dict) -> str:
    lines = []
    for k, v in fields.items():
        if isinstance(v, bool):
            v = "true" if v else "false"
        elif isinstance(v, (int, float)):
            v = str(v)
        elif any(c in str(v) for c in ":#[]{}'\"") or str(v) != str(v).strip():
            v = json.dumps(str(v), ensure_ascii=False)
        lines.append(f"{k}: {v}")
    return "---\n" + "\n".join(lines) + "\n---\n"


def _toml_str(s: str) -> str:
    # A JSON string is a valid TOML basic string: same escapes, and json.dumps
    # never emits `\/`, the one JSON escape TOML lacks.
    return json.dumps(s, ensure_ascii=False)


def _write(out: dict[Path, str], path: Path, text: str) -> None:
    out[path] = text if text.endswith("\n") else text + "\n"


def build_claude(root: Path) -> dict[Path, str]:
    out: dict[Path, str] = {}
    for kind in ("agents", "commands"):
        for src in sources(kind):
            raw, _, body = split(src)
            _write(out, root / kind / src.name, f"---\n{raw}\n---\n{render(body, 'claude')}")
    return out


def build_opencode(root: Path) -> dict[Path, str]:
    out: dict[Path, str] = {}
    base = DIST / "opencode"
    for src in sources("agents"):
        _, f, _ = split(src)
        text = _front({"description": f["description"], "mode": "subagent"})
        if f["name"] in SPECIALISTS:
            # One task per session: a specialist does not hand work onward.
            text = text[:-4] + "permission:\n  task: deny\n---\n"
        _write(out, base / "agents" / src.name, text + body_for("agents", src.stem, "opencode", root))
    for src in sources("commands"):
        _, f, _ = split(src)
        text = _front({"description": f["description"]})
        _write(out, base / "commands" / f"{PREFIX}-{src.name}",
               text + body_for("commands", src.stem, "opencode", root))
    plugin = (PLUGIN_ROOT / "harness" / "opencode" / "sliced-loop.js").read_text(encoding="utf-8")
    _write(out, base / "plugins" / "sliced-loop.js",
           plugin.replace("__SLICED_LOOP_ROOT__", json.dumps(str(root))[1:-1]))
    return out


def build_codex(root: Path) -> dict[Path, str]:
    out: dict[Path, str] = {}
    base = DIST / "codex"
    for src in sources("agents"):
        _, f, _ = split(src)
        lines = [
            f"name = {_toml_str(f['name'])}",
            f"description = {_toml_str(f['description'])}",
        ]
        if f.get("effort"):
            lines.append(f"model_reasoning_effort = {_toml_str(f['effort'])}")
        lines.append(f"developer_instructions = {_toml_str(body_for('agents', src.stem, 'codex', root))}")
        _write(out, base / "agents" / f"{src.stem}.toml", "\n".join(lines))
    for src in sources("commands"):
        _, f, _ = split(src)
        name = f"{PREFIX}-{src.stem}"
        desc = f"{f['description']}. Use only when the user invokes ${name}."
        _write(out, base / "skills" / name / "SKILL.md",
               _front({"name": name, "description": desc}) + "\n"
               + body_for("commands", src.stem, "codex", root))
    _write(out, base / "hooks.json", json.dumps(codex_hooks(root), indent=2))
    return out


def codex_hooks(root: Path) -> dict:
    return {"hooks": {"PreToolUse": [{
        "matcher": "Bash|apply_patch|Edit|Write",
        "hooks": [{
            "type": "command",
            "command": f'python3 "{root}/scripts/scope.py" hook codex',
            "timeout": 10,
        }],
    }]}}


def build_gemini(root: Path) -> dict[Path, str]:
    out: dict[Path, str] = {}
    base = DIST / "gemini"
    version = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]
    manifest = {"name": PREFIX, "version": version,
                "description": "Two specialist agents build one app from opposite sides of an API contract."}
    _write(out, base / "gemini-extension.json", json.dumps(manifest, indent=2))
    # Only the supervisor is a subagent here: Gemini's hook payload does not name
    # the subagent, so a specialist run in-session would go unconfined.
    _, f, _ = split(SRC / "agents" / "supervisor.md")
    front = _front({"name": f["name"], "description": f["description"],
                    "max_turns": 200, "timeout_mins": 60})
    _write(out, base / "agents" / "supervisor.md", front + body_for("agents", "supervisor", "gemini", root))
    for src in sources("commands"):
        _, f, _ = split(src)
        body = body_for("commands", src.stem, "gemini", root)
        if "'''" in body:
            raise SystemExit(f"{src.name}: ''' cannot appear in a Gemini TOML prompt")
        _write(out, base / "commands" / PREFIX / f"{src.stem}.toml",
               f"description = {_toml_str(f['description'])}\nprompt = '''\n{body}'''")
    hooks = {"hooks": {"BeforeTool": [{
        "matcher": "read_file|read_many_files|glob|grep_search|search_file_content|list_directory"
                   "|write_file|replace|edit|run_shell_command",
        "hooks": [{"name": "sliced-loop-scope", "type": "command",
                   "command": f'python3 "{root}/scripts/scope.py" hook gemini', "timeout": 10000}],
    }]}}
    _write(out, base / "hooks" / "hooks.json", json.dumps(hooks, indent=2))
    return out


def build_cursor(root: Path) -> dict[Path, str]:
    out: dict[Path, str] = {}
    base = DIST / "cursor"
    claude_manifest = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text())
    manifest = {"name": PREFIX, "version": claude_manifest["version"],
                "description": "Two specialist agents build one app from opposite sides of an API contract.",
                "license": "MIT"}
    if "author" in claude_manifest:
        manifest["author"] = claude_manifest["author"]
    _write(out, base / ".cursor-plugin" / "plugin.json", json.dumps(manifest, indent=2))
    # As with Gemini: Cursor's per-tool hooks do not say which subagent acts.
    _, f, _ = split(SRC / "agents" / "supervisor.md")
    _write(out, base / "agents" / "supervisor.md",
           _front({"name": f["name"], "description": f["description"], "model": "inherit"})
           + body_for("agents", "supervisor", "cursor", root))
    for src in sources("commands"):
        _write(out, base / "commands" / f"{PREFIX}-{src.name}", body_for("commands", src.stem, "cursor", root))
    hooks = {"version": 1, "hooks": {"preToolUse": [{
        "command": f'python3 "{root}/scripts/scope.py" hook cursor',
        "matcher": "Shell|Read|Grep|Glob|Write|Edit|Delete",
        "timeout": 10,
    }]}}
    _write(out, base / "hooks" / "hooks.json", json.dumps(hooks, indent=2))
    return out


BUILDERS = {"claude": build_claude, "opencode": build_opencode, "codex": build_codex,
            "gemini": build_gemini, "cursor": build_cursor}


def build(h: str, root: Path = PLUGIN_ROOT, write: bool = True) -> dict[Path, str]:
    files = BUILDERS[h](root)
    if write:
        if h != "claude":
            shutil.rmtree(DIST / h, ignore_errors=True)
        for path, text in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("harness", nargs="*", help=", ".join(HARNESSES))
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if the committed Claude Code files differ from src/")
    args = parser.parse_args()

    if args.check:
        stale = [p for p, text in build("claude", write=False).items()
                 if not p.is_file() or p.read_text(encoding="utf-8") != text]
        for p in stale:
            print(f"stale: {p.relative_to(PLUGIN_ROOT)}")
        if stale:
            print("run `python3 scripts/build.py` and commit the result")
        return 1 if stale else 0

    unknown = [h for h in args.harness if h not in HARNESSES]
    if unknown:
        parser.error(f"unknown harness {', '.join(unknown)} — choose from {', '.join(HARNESSES)}")
    for h in args.harness or ["claude"]:
        files = build(h)
        where = PLUGIN_ROOT if h == "claude" else DIST / h
        print(f"{h:9} {len(files)} file(s) -> {where.relative_to(PLUGIN_ROOT) if where != PLUGIN_ROOT else '.'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
