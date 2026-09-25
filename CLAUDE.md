# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

`sliced-loop` is an **agent-harness plugin**, not an application. It started as a Claude Code plugin and now also targets OpenCode, Codex, Gemini CLI and Cursor. Its job is to be installed into *another* repository, where a supervisor agent cuts the work into vertical slices and a `frontend` and a `backend` agent build it. The two specialists are confined to their own trees and coordinate only through a published API contract. `README.md` is the user-facing description.

The parent directory's `CLAUDE.md` describes an older, non-plugin version of this system (`task-manager/`, `./commands`, a hook in `.claude/settings.local.json`). None of that exists here. In this repo, paths come from `.sliced-loop.json`, and the tooling runs through `${CLAUDE_PLUGIN_ROOT}/scripts/`.

## Layout and how the pieces connect

- **`src/agents/*.md` and `src/commands/*.md` are the only place to edit prompts.** Each is written once, with tokens for what differs per harness. `scripts/build.py` renders them.
  - The tokens are `{{scripts}}`, `{{args}}`, `{{cmd:NAME}}`, `{{spawn:NAME}}`/`{{Spawn:NAME}}`, `{{loop}}`, `{{harness}}` and `{{restart_note}}`.
  - Conditional blocks are `<!-- if:inproc|headless|<harness>[,…] --> … <!-- endif -->`. They can't be nested, and the build fails on an unbalanced block.
  - The source frontmatter is Claude-shaped. Each builder maps it to its harness's format.
- **Root `agents/` and `commands/` are generated Claude Code output, but committed**, because a Claude plugin installs straight from the repo. Never edit them by hand. Run `python3 scripts/build.py`, then check with `python3 scripts/build.py --check`.
- Output for every other harness goes to the gitignored `dist/<harness>/`, because it embeds this checkout's absolute path. `scripts/install.py <harness>` renders it and installs it. It keeps a manifest, refuses to overwrite files it didn't create, and supports `--uninstall`.
- `harness/opencode/sliced-loop.js` is the OpenCode scope plugin template. Its `__SLICED_LOOP_ROOT__` placeholder is filled at build time.
- `.claude-plugin/plugin.json` and `marketplace.json` hold the Claude manifest. Keep the two `version` fields in sync; the Gemini and Cursor manifests take their version from `plugin.json`.
- `hooks/hooks.json` holds the Claude hook, which is `scope.py hook claude`.
- `templates/` holds what `init` copies into the target repo's workspace. It's shared by every harness, so keep it free of any one harness's command syntax.
- `scripts/` holds all executable code. It uses only the standard library and has no install step. `jq` is needed only by `run.sh`.

### Two ways a specialist runs

The mode is set per harness in `build.HARNESSES`, and the whole design rests on it:
- **`inproc`** (Claude, OpenCode, Codex): the specialists are subagents of the session. This only works because the harness tells the scope check which subagent is calling:
  - Claude and Codex put `agent_type` in the hook payload.
  - OpenCode's plugin maps sessionID → agent using `chat.message`, falling back to `client.session.get`.
- **`headless`** (Gemini CLI, Cursor): their per-tool hooks don't name the subagent, so a specialist must never be installed or spawned as a subagent there.
  - Only `supervisor` ships as a subagent on these two.
  - `scripts/dispatch.py` starts each specialist as its own detached process, with `SLICED_LOOP_AGENT` set. It also sets `GEMINI_CLI_SLICED_LOOP_AGENT`, which survives Gemini's env redaction.
  - `dispatch.py` refuses a busy agent, using a pid lock in `.state/running/` and live `in-progress` claims.
- `scripts/loop.py` is the tick driver for every harness except Claude, which has `/loop`. It checks the board with no model call and runs a headless supervise session only when there is work. Both it and `dispatch.py` take per-harness command overrides from the `headless` key in `.sliced-loop.json`.

### Config is the single source of truth for paths

`scripts/config.py` resolves `.sliced-loop.json` in the target project. It finds the project root from `CLAUDE_PROJECT_DIR` first, then by walking up from the cwd. The config names `frontend`, `backend` and `workspace` (default `.claude/sliced-loop`). Every component reads these names instead of hardcoding directories: `scope.py`, `tasklib.py`, the board and `run.sh`. **With no `.sliced-loop.json`, everything must stay inert.** The hook exits 0, and `config.require()` tells the user to run init. Preserve this so the plugin can't disturb repos where it isn't set up.

### Scope enforcement (`scripts/scope.py`)

- The rules live here once. Each harness has an adapter.
  - `scope.py hook <claude|codex|gemini|cursor>` parses that harness's payload and prints its deny format. Cursor uses snake_case `user_message`/`agent_message`; Claude and Codex use `hookSpecificOutput`.
  - `scope.py check` is the CLI that the OpenCode plugin calls. It exits 2 on a denial.
- The agent comes from the payload (`agent_type`) or from `SLICED_LOOP_AGENT`. The main thread, the supervisor and unknown agents pass through untouched.
- `frontend` and `backend` can read and write their own tree plus the workspace.
  - `frontend` can't write `capabilities/` or `memory/backend.md`.
  - `backend` can't write `memory/frontend.md`.
- `research` can read the workspace and write only `research/`.
- File tools are checked exactly, against the resolved real path. Codex `apply_patch` is checked per file named in the patch.
- Shell commands are checked only by a regex on the command text. It's a guard rail, not a jail.

### Repositories and commits

- `scripts/repos.py init` (run by `init`) gives each tree its own git repository and adds both to the root `.gitignore`.
  - The root repository holds the config and the workspace. It's created only if the project isn't in a repository at all.
  - It never splits a tree the root repository already tracks unless given `--split-tracked`, which `init` must ask the user about first.
- Agents commit only through `scripts/commit.py <agent> [task-id]`. It builds an explicit file list of what the agent owns, groups it by the repository holding each file, and commits each group with `git commit --only -- <files>`.
  - That's what keeps concurrent agents out of each other's commits in the shared workspace repository. Don't replace it with `git add -A`/`-a`.
  - It retries on git lock errors (`LOCK_ERRORS`). Concurrent commits to one repository really do hit `cannot lock ref 'HEAD'`.
  - The message comes from the task file, never the command line. An agent-supplied message could contain the other tree's directory name and trip the shell scope check.
  - It never pushes. `"commit": false` in config disables it.

### Ending the loop on idle

- `tasklib.record_tick()` counts consecutive idle ticks in `.state/idle.json`, and `tasks.py tick quiet|active [--limit N]` is its command-line form.
  - A tick counts as idle only if it was quiet **and** no specialist is working: no live `in-progress` claim and no running `dispatch.py` session. Otherwise it resets, so a long task can't end the loop under itself.
  - The limit comes from the CLI flag, then `idle_ticks` in `.sliced-loop.json`, then `IDLE_TICKS` (5). `0` means never stop.
- `loop.py` records the count itself and exits once it reaches the limit.
- On Claude only, the supervise command records it through `tasks.py tick`, with an optional number as its argument. On `STOP`, the command ends its own `/loop`: `CronDelete` on a fixed-interval loop, or `ScheduleWakeup` with `stop: true` on a self-paced one. On the other harnesses those steps are left out, because `loop.py` does the counting.

### Designs and access requests

- `<workspace>/design/DESIGN.md` (template `templates/design/DESIGN.md`) lists each design source: its link, what it covers, how an agent opens it (`figma-mcp`, `artifact`, `web` or `file`), and whether that was verified.
  - `init` asks for the sources and checks that each one opens.
  - `plan` gives frontend tasks a `## Design` section naming the exact frame or section.
- The frontend agent has no `tools:` allowlist, only `disallowedTools: Agent`. That is deliberate: an allowlist drops MCP tools, and the Figma server's name can't be known in advance. Putting `tools:` back would cut the agent off from Figma and the Artifact tool.
- A frontend agent that can't open a design blocks with a `- <date> frontend: needs-access: …` thread line instead of guessing.
  - `tasklib.needs_access()` parses that line. A later `access granted` line clears it.
  - `status` reports these tasks as "waiting on a human", and `loop.py` adds the same note to its tick line.
  - The supervisor must not resolve one itself.

### Task model (`scripts/tasklib.py`)

- Tasks are Markdown files in `<workspace>/tasks/` with frontmatter. The parser is a small hand-rolled YAML subset: scalars, inline `[a, b]` lists and `#` comments. It is not a YAML library, so don't introduce syntax it can't read.
- `STATUSES` are `proposed → ready → in-progress → blocked → review → done`. `OWNERS` are `frontend` and `backend`.
- An unknown status is read as `proposed`.
- Writes are atomic (`_write_atomic`). `move_task` sets `status:` and `updated:` and appends a manual-override line to `## Thread`. The board uses it.
- `claim_liveness` marks an `in-progress` task **STALE** when neither the task file nor anything in the owner's tree has been modified for `STALE_AFTER_MINUTES` (45). `SKIP_DIRS` are ignored in that check. STALE means the session died and the task must be re-dispatched. It must never be treated as BUSY.
- Runtime state goes only in `<workspace>/.state/` (`state_dir()`), which init gitignores. Anything new the tooling produces at run time belongs there.

### Entry points

```bash
python3 scripts/tasks.py changes [--peek]         # diff task files vs snapshot; advances the snapshot unless --peek
python3 scripts/tasks.py status [--stale-after N] # BUSY / IDLE / STALE per owner, review+triage queues, memory-file sizes
python3 scripts/tasks.py research [query]
python3 scripts/board/serve.py [--port 7777] [--no-open]   # kanban on 127.0.0.1, board/index.html is the UI
scripts/run.sh [--api-port N] [--web-port N] [--no-install] # starts backend `npm start` + frontend `npm run dev`
python3 scripts/config.py [key]                   # print the resolved config
python3 scripts/build.py [--check | <harness>…]   # render src/ (Claude to the root, others to dist/)
python3 scripts/install.py <harness> [--project DIR] [--uninstall]
python3 scripts/dispatch.py --harness H <agent> <task-id> [--resume BRIEF] [--wait]
python3 scripts/loop.py --harness H [--every 15m] [--idle-ticks N] [--once]
python3 scripts/tasks.py tick quiet|active [--limit N]   # the idle counter both loops use
python3 scripts/repos.py status|init [--split-tracked]     # one repository per tree
python3 scripts/commit.py <agent> [task-id] [--dry-run]    # commit only that agent's files
```

These run against whatever project `CLAUDE_PROJECT_DIR` or the cwd resolves to. To exercise them, run them from a scratch repo that has a `.sliced-loop.json` and a workspace. Running them from this repo resolves to the defaults, and no workspace exists here.

`run.sh` points the frontend at the real API with `VITE_API_STUB=false VITE_API_BASE_URL=...`. It kills whole process trees on exit, because `npm start` wraps the real server.

## Developing

- The repo has no test suite or linter. The only build is `scripts/build.py`, which renders the prompts.
- The OpenCode and Gemini output can be checked without a model:
  - OpenCode: `opencode agent list` and `opencode debug config` in a repo installed with `install.py opencode --project`. Point the `XDG_*` dirs at a scratch location.
  - Gemini: `HOME=<scratch> python3 scripts/install.py gemini`, which runs `gemini extensions link`.
  - Codex and Cursor output is built from their docs and has not been run against those CLIs.
- To try changes live, install the plugin from a local clone:
  1. Run `/plugin marketplace add /path/to/sliced-loop`, then `/plugin install sliced-loop@sliced-loop`.
  2. Run `/sliced-loop:init` in a target repo.
  3. **Restart Claude Code.** Agents, hooks and commands load only at startup.
- The agent briefs and command prompts are the product, as much as the scripts are. When you change a rule, update every file that states it. Rules like one task per session, STALE handling, capabilities being read-only for frontend, and memory compaction at 80/100 lines appear in `src/agents/*.md`, `src/commands/supervise.md`, `templates/workspace-README.md` and `README.md`. The headless path repeats some of them in code: the resume brief in `dispatch.py` and the "has work" rule in `loop.py`.
