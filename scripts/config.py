"""Where this project keeps its two source trees and its workspace.

A plugin cannot assume a layout. `.sliced-loop.json` at the project root names
the directories; everything else — the scope hook, the task CLI, the board, the
agents' briefs — reads them from here rather than hardcoding `frontend/` and
`backend/`.

The workspace defaults inside `.claude/` so it stays out of the project's root
listing, while remaining in the repository: the backlog, the memory files and
the published contract describe the code, so they belong in version control
beside it rather than in the shared plugin install, which is wiped on upgrade.

    {
      "frontend":  "apps/web",
      "backend":   "services/api",
      "workspace": ".claude/sliced-loop"
    }
"""

from __future__ import annotations

import json
import os
from pathlib import Path

CONFIG_NAME = ".sliced-loop.json"

DEFAULTS = {
    "frontend": "frontend",
    "backend": "backend",
    "workspace": ".claude/sliced-loop",
}


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


def load(root: Path | None = None) -> dict:
    """Config with defaults filled in, plus the resolved absolute paths."""
    root = root or project_root()
    data = dict(DEFAULTS)

    path = root / CONFIG_NAME
    if path.is_file():
        try:
            declared = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise SystemExit(f"{path} is not valid JSON: {exc}")
        for key in DEFAULTS:
            value = declared.get(key)
            if isinstance(value, str) and value.strip():
                data[key] = value.strip().strip("/")

    data["root"] = root
    data["configured"] = path.is_file()
    for key in DEFAULTS:
        data[f"{key}_path"] = (root / data[key]).resolve()
    return data


def setting(key: str, default, root: Path | None = None):
    """A key beyond the three directories, e.g. `idle_ticks` or `headless`."""
    path = (root or project_root()) / CONFIG_NAME
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get(key)
    except (OSError, ValueError):
        return default
    return default if value is None else value


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
        print(cfg.get(sys.argv[1], ""))
    else:
        print(json.dumps({k: str(v) for k, v in cfg.items()}, indent=2))
