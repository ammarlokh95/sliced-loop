#!/usr/bin/env python3
"""Install sliced-loop into a harness other than Claude Code.

    install.py <harness> [--project DIR] [--force]
    install.py <harness> --uninstall [--project DIR]

Renders the harness's files into dist/<harness>/ (see build.py), then puts them
where that harness looks:

    opencode  ~/.config/opencode/{agents,commands,plugins}/   (--project: DIR/.opencode/)
    codex     ~/.codex/{agents,skills}/ + a hook in ~/.codex/hooks.json
                                          (--project: DIR/.codex/ and DIR/.agents/skills/)
    gemini    `gemini extensions link dist/gemini`
    cursor    ~/.cursor/plugins/local/sliced-loop -> dist/cursor

The rendered files point at this checkout by absolute path, so — as with a
local Claude marketplace — don't move the folder while it is installed. Re-run
this after pulling changes.

Like the Claude plugin, an install is inert in any repository without a
`.sliced-loop.json`: the scope check passes everything through.

A manifest of what was written is kept beside it, so a reinstall replaces only
its own files and never overwrites one it did not create (unless --force), and
--uninstall removes exactly what it put there.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build  # noqa: E402

MANIFEST = ".sliced-loop-install.json"
HOME = Path.home()


def plan(harness: str, project: Path | None) -> list[tuple[Path, Path]]:
    """(source in dist, destination) pairs for a copying install."""
    dist = build.DIST / harness
    pairs: list[tuple[Path, Path]] = []
    if harness == "opencode":
        base = project / ".opencode" if project else HOME / ".config" / "opencode"
        for sub in ("agents", "commands", "plugins"):
            for f in sorted((dist / sub).glob("*")):
                pairs.append((f, base / sub / f.name))
    elif harness == "codex":
        agents = (project / ".codex" if project else HOME / ".codex") / "agents"
        skills = project / ".agents" / "skills" if project else HOME / ".codex" / "skills"
        for f in sorted((dist / "agents").glob("*.toml")):
            pairs.append((f, agents / f.name))
        for d in sorted((dist / "skills").iterdir()):
            pairs.append((d / "SKILL.md", skills / d.name / "SKILL.md"))
    return pairs


def manifest_path(harness: str, project: Path | None) -> Path:
    if harness == "opencode":
        return (project / ".opencode" if project else HOME / ".config" / "opencode") / MANIFEST
    return (project / ".codex" if project else HOME / ".codex") / MANIFEST


def read_manifest(path: Path) -> list[str]:
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("files", [])
    except (OSError, ValueError):
        return []


# --- codex hooks.json -------------------------------------------------------

def _is_ours(entry: dict) -> bool:
    return any("scope.py" in h.get("command", "") and "hook codex" in h.get("command", "")
               for h in entry.get("hooks", []))


def merge_codex_hook(path: Path, remove: bool = False) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        data = {}
    except ValueError as exc:
        raise SystemExit(f"{path} is not valid JSON ({exc}) — fix it, then re-run")
    hooks = data.setdefault("hooks", {})
    pre = [e for e in hooks.get("PreToolUse", []) if not _is_ours(e)]
    if not remove:
        pre += build.codex_hooks(build.PLUGIN_ROOT)["hooks"]["PreToolUse"]
    if pre:
        hooks["PreToolUse"] = pre
    else:
        hooks.pop("PreToolUse", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# --- install / uninstall ----------------------------------------------------

def copy_install(harness: str, project: Path | None, force: bool) -> list[str]:
    mpath = manifest_path(harness, project)
    ours = set(read_manifest(mpath))
    pairs = plan(harness, project)
    clashes = [str(d) for _, d in pairs if d.exists() and str(d) not in ours]
    if clashes and not force:
        raise SystemExit("refusing to overwrite files sliced-loop did not create:\n  "
                         + "\n  ".join(clashes) + "\nmove them aside, or pass --force")
    written = []
    for src, dst in pairs:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        written.append(str(dst))
    # Drop files a previous install wrote that this one no longer ships.
    for old in ours - set(written):
        Path(old).unlink(missing_ok=True)
    mpath.parent.mkdir(parents=True, exist_ok=True)
    mpath.write_text(json.dumps({"plugin_root": str(build.PLUGIN_ROOT), "files": written}, indent=2) + "\n")
    return written


def copy_uninstall(harness: str, project: Path | None) -> list[str]:
    mpath = manifest_path(harness, project)
    removed = []
    for f in read_manifest(mpath):
        p = Path(f)
        if p.exists():
            p.unlink()
            removed.append(f)
            try:
                p.parent.rmdir()  # skill directories; leaves anything non-empty alone
            except OSError:
                pass
    mpath.unlink(missing_ok=True)
    return removed


def cursor_link() -> Path:
    return HOME / ".cursor" / "plugins" / "local" / build.PREFIX


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("harness", choices=[h for h in build.HARNESSES if h != "claude"])
    parser.add_argument("--project", type=Path, help="install into this repository instead of user-wide")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--force", action="store_true", help="overwrite files sliced-loop did not create")
    args = parser.parse_args()
    h = args.harness
    project = args.project.resolve() if args.project else None
    if project and h in ("gemini", "cursor"):
        parser.error(f"{h} installs user-wide (it is inert in repos without .sliced-loop.json)")

    if args.uninstall:
        if h in ("opencode", "codex"):
            removed = copy_uninstall(h, project)
            if h == "codex":
                merge_codex_hook((project / ".codex" if project else HOME / ".codex") / "hooks.json", remove=True)
            print(f"removed {len(removed)} file(s)")
        elif h == "gemini":
            return subprocess.call(["gemini", "extensions", "uninstall", build.PREFIX])
        elif h == "cursor":
            link = cursor_link()
            if link.is_symlink():
                link.unlink()
                print(f"removed {link}")
        return 0

    build.build(h)
    dist = build.DIST / h

    if h in ("opencode", "codex"):
        written = copy_install(h, project, args.force)
        print(f"installed {len(written)} file(s) for {h}")
        if h == "codex":
            hooks = (project / ".codex" if project else HOME / ".codex") / "hooks.json"
            merge_codex_hook(hooks)
            print(f"added the scope hook to {hooks}")
            print("next: restart codex and approve the hook in /hooks — until then the specialists are unconfined")
        else:
            print("next: restart opencode")
    elif h == "gemini":
        if not shutil.which("gemini"):
            print(f"gemini is not on PATH. Once it is: gemini extensions link {dist}")
            return 1
        # Gemini asks the user to consent to an extension with hooks; leave that
        # prompt to them. It exits 0 even when declined, so check the result.
        subprocess.call(["gemini", "extensions", "link", str(dist)])
        r = subprocess.run(["gemini", "extensions", "list"], capture_output=True, text=True)
        listed = r.stdout + r.stderr  # it prints the list to stderr
        if str(dist) not in listed:
            print("the extension was not linked (declined, or gemini failed) — nothing installed")
            return 1
        print("next: restart gemini")
    elif h == "cursor":
        link = cursor_link()
        link.parent.mkdir(parents=True, exist_ok=True)
        if link.exists() or link.is_symlink():
            if not link.is_symlink() and not args.force:
                raise SystemExit(f"{link} exists and is not our link — move it aside, or pass --force")
            if link.is_symlink() or link.is_file():
                link.unlink()
            else:
                shutil.rmtree(link)
        os.symlink(dist, link, target_is_directory=True)
        print(f"linked {link} -> {dist}")
        print("next: reload Cursor (or pass --plugin-dir to `agent`)")

    print("then, in the repository to work on, run its init command:",
          build._cmd(h, "init"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
