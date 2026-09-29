"""Where this project keeps its source trees, who owns each, and its workspace.

A plugin cannot assume a layout. `.sliced-loop.json` at the project root names
every source tree and the agent that owns it; everything else — the scope hook,
the task CLI, the board, the agents' briefs — reads them from here rather than
hardcoding directories.

    {
      "workspace": ".claude/sliced-loop",
      "agents": {
        "frontend": {"path": "apps/web",     "role": "ui",      "prefix": "FE"},
        "backend":  {"path": "services/api", "role": "service", "prefix": "BE"},
        "mobile":   {"path": "apps/mobile",  "role": "ui",      "prefix": "MO",
                     "focus": "React Native app for iOS and Android",
                     "model": "sonnet"}
      }
    }

Each entry is one agent, confined to its `path`. `role` is what it owes the
others: a `service` publishes a contract in `capabilities/<name>/`; a `ui`
consumes contracts and publishes none. `prefix` starts its task IDs. `focus`
says what kind of code the tree holds. `model` picks the LLM that runs it — a
string, or one per harness: {"claude": "sonnet", "opencode": "anthropic/…"}.

The original two-key form is still read, as a frontend `ui` and a backend
`service`:

    {"frontend": "web", "backend": "api", "workspace": ".claude/sliced-loop"}

The workspace defaults inside `.claude/` so it stays out of the project's root
listing, while remaining in the repository: the backlog, the memory files and
the published contracts describe the code, so they belong in version control.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

CONFIG_NAME = ".sliced-loop.json"

DEFAULTS = {
    "frontend": "frontend",
    "backend": "backend",
    "workspace": ".claude/sliced-loop",
}

ROLES = ("ui", "service")
# Agents the plugin itself defines; a source tree cannot take these names.
RESERVED = ("supervisor", "research")
# What the two original agents default to when a config does not say.
DEFAULT_AGENTS = {
    "frontend": {"role": "ui", "prefix": "FE"},
    "backend": {"role": "service", "prefix": "BE"},
}
NAME = re.compile(r"^[a-z][a-z0-9-]{0,30}$")
PREFIX = re.compile(r"^[A-Z]{2,4}$")


def project_root(start: Path | None = None) -> Path:
    """The project being worked on — not the plugin, which lives elsewhere."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and Path(env).is_dir():
        return Path(env).resolve()

    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / CONFIG_NAME).is_file():
            return candidate
    return here


def _clean(path: str) -> str:
    return path.strip().strip("/")


def default_prefix(name: str, taken: set[str]) -> str:
    """FE/BE for the originals; otherwise the name's first letters, made unique."""
    if name in DEFAULT_AGENTS and DEFAULT_AGENTS[name]["prefix"] not in taken:
        return DEFAULT_AGENTS[name]["prefix"]
    letters = re.sub(r"[^a-z]", "", name).upper() or "X"
    for n in (2, 3, 4):
        if len(letters) >= n and letters[:n] not in taken:
            return letters[:n]
    for extra in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        if (cand := (letters[:1] + extra)) not in taken:
            return cand
    raise SystemExit(f"cannot find a free task prefix for {name!r} — set one with \"prefix\"")


def parse_agents(declared: dict) -> dict[str, dict]:
    """The agents map from a raw config, in either form, validated."""
    raw = declared.get("agents")
    if raw is None:
        # The original two-key form.
        raw = {name: {"path": declared.get(name) or name, **DEFAULT_AGENTS[name]}
               for name in ("frontend", "backend")}
    if not isinstance(raw, dict) or not raw:
        raise SystemExit(f'{CONFIG_NAME}: "agents" must name at least one source tree')

    agents: dict[str, dict] = {}
    taken: set[str] = {str(v.get("prefix")) for v in raw.values() if isinstance(v, dict) and v.get("prefix")}
    for name, spec in raw.items():
        if isinstance(spec, str):
            spec = {"path": spec}
        if not NAME.match(name):
            raise SystemExit(f"{CONFIG_NAME}: agent name {name!r} must be lowercase letters, digits and dashes")
        if name in RESERVED:
            raise SystemExit(f"{CONFIG_NAME}: {name!r} is reserved for the plugin's own agent")
        role = spec.get("role") or DEFAULT_AGENTS.get(name, {}).get("role") or "ui"
        if role not in ROLES:
            raise SystemExit(f"{CONFIG_NAME}: {name}.role must be one of {', '.join(ROLES)}, not {role!r}")
        prefix = spec.get("prefix")
        if not prefix:
            prefix = default_prefix(name, taken)
            taken.add(prefix)
        if not PREFIX.match(prefix):
            raise SystemExit(f"{CONFIG_NAME}: {name}.prefix must be 2-4 capital letters, not {prefix!r}")
        model = spec.get("model") or ""
        if not isinstance(model, (str, dict)) or (isinstance(model, dict) and not all(
                isinstance(v, str) for v in model.values())):
            raise SystemExit(f"{CONFIG_NAME}: {name}.model must be a model name, or an object "
                             f"mapping harnesses to model names")
        path = _clean(str(spec.get("path") or name))
        if not path or path == "." or ".." in Path(path).parts:
            raise SystemExit(f"{CONFIG_NAME}: {name}.path must be a directory inside the project")
        agents[name] = {
            "path": path,
            "role": role,
            "prefix": prefix,
            "focus": str(spec.get("focus") or "").strip(),
            "model": model,
        }

    prefixes = [a["prefix"] for a in agents.values()]
    if len(set(prefixes)) != len(prefixes):
        raise SystemExit(f"{CONFIG_NAME}: two agents share a task prefix — give each its own")
    paths = sorted((a["path"], n) for n, a in agents.items())
    for (p1, n1), (p2, n2) in zip(paths, paths[1:]):
        if p2 == p1 or p2.startswith(p1 + "/"):
            raise SystemExit(f"{CONFIG_NAME}: {n2}'s tree ({p2}) is inside {n1}'s ({p1}) — trees must not nest")
    return agents


def model_for(agent: dict, harness: str) -> str:
    model = agent.get("model")
    if isinstance(model, dict):
        return str(model.get(harness) or "")
    return str(model or "")


def load(root: Path | None = None) -> dict:
    """Config with defaults filled in, plus the resolved absolute paths."""
    root = root or project_root()
    path = root / CONFIG_NAME
    declared: dict = {}
    if path.is_file():
        try:
            declared = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise SystemExit(f"{path} is not valid JSON: {exc}")

    workspace = declared.get("workspace")
    workspace = _clean(workspace) if isinstance(workspace, str) and workspace.strip() else DEFAULTS["workspace"]
    agents = parse_agents(declared)
    for name, agent in agents.items():
        agent["path_abs"] = (root / agent["path"]).resolve()
        if agent["path_abs"] == (root / workspace).resolve() or \
                (root / workspace).resolve().is_relative_to(agent["path_abs"]):
            raise SystemExit(f"{CONFIG_NAME}: the workspace must not sit inside {name}'s tree")

    data = {
        "root": root,
        "configured": path.is_file(),
        "legacy": path.is_file() and "agents" not in declared,
        "workspace": workspace,
        "workspace_path": (root / workspace).resolve(),
        "agents": agents,
    }
    # The original keys, for anything still asking for the two classic trees.
    for key in ("frontend", "backend"):
        if key in agents:
            data[key] = agents[key]["path"]
            data[f"{key}_path"] = agents[key]["path_abs"]
    return data


def setting(key: str, default, root: Path | None = None):
    """A key beyond the layout, e.g. `idle_ticks` or `headless`."""
    path = (root or project_root()) / CONFIG_NAME
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get(key)
    except (OSError, ValueError):
        return default
    return default if value is None else value


def gitignore_add(root: Path, header: str, entries: list[str]) -> list[str]:
    """Add entries to the root .gitignore under one comment header, keeping the
    block together across calls. Returns the entries actually added."""
    path = root / ".gitignore"
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    have = {l.strip() for l in lines}
    new = [e for e in entries if e not in have]
    if not new:
        return []
    if header in have:
        at = lines.index(header) + 1
        while at < len(lines) and lines[at].strip() and not lines[at].startswith("#"):
            at += 1
        lines[at:at] = new
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines += [header, *new]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return new


def require(root: Path | None = None) -> dict:
    cfg = load(root)
    if not cfg["configured"]:
        raise SystemExit(
            f"no {CONFIG_NAME} in {cfg['root']} — run the sliced-loop init command to set this project up"
        )
    return cfg


if __name__ == "__main__":
    import sys

    cfg = load()
    if len(sys.argv) > 1:
        value = cfg.get(sys.argv[1], "")
        print(json.dumps(value, default=str) if isinstance(value, dict) else value)
    else:
        print(json.dumps(cfg, indent=2, default=str))
