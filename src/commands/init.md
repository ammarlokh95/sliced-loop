---
description: Set this repository up for the sliced-loop workflow
argument-hint: "[frontend-dir] [backend-dir]"
---

Set up **the repository you are in** to be worked by this plugin's agents.

## 1. Work out the layout

If `{{args}}` names two directories, use them as the frontend and backend
trees. Otherwise look at what is actually here before asking:

```bash
ls -d */ 2>/dev/null | head -20
cat .sliced-loop.json 2>/dev/null
```

- **Already has `.sliced-loop.json`** — this repo is already set up. Say what it
  points at and stop; do not overwrite it.
- **Recognisable trees already exist** — `frontend/`+`backend/`, `apps/web`+
  `services/api`, `client/`+`server/`, `web/`+`api/`. Propose what you found and
  confirm before writing.
- **Nothing recognisable, or it is an empty repo** — ask what the two trees
  should be called, and whether you should create them. Do not guess: the whole
  enforcement model rests on these two paths being right.

A project with no meaningful frontend/backend split is a bad fit for this
plugin. Say so plainly rather than forcing a layout onto it.

## 2. Write the config

`.sliced-loop.json` at the repository root:

```json
{
  "frontend": "<frontend dir>",
  "backend": "<backend dir>",
  "workspace": ".claude/sliced-loop"
}
```

Paths are relative to the repo root, no leading or trailing slash. The workspace
may be called anything; `.claude/sliced-loop` is the default.

## 3. Create the workspace

```
<workspace>/
├── PROJECT.md          what this is, scope, constraints, status
├── TEMPLATE.md         the task template
├── tasks/              one Markdown file per task
├── capabilities/       CAPABILITIES.md + openapi.yaml — the backend publishes here
├── memory/             frontend.md · backend.md · decisions.md
├── design/             DESIGN.md — where the designs live, and how to reach them
└── research/           findings from the research agent
```

Copy from `{{templates}}/`, then replace `<project>`,
`<workspace>` and `<date>` throughout:

| template | goes to |
|----------|---------|
| `PROJECT.md` | `<workspace>/PROJECT.md` |
| `TEMPLATE.md` | `<workspace>/TEMPLATE.md` |
| `workspace-README.md` | `<workspace>/README.md` |
| `capabilities/` | `<workspace>/capabilities/` |
| `research/README.md` | `<workspace>/research/README.md` |
| `memory-agent.md` | `<workspace>/memory/frontend.md` **and** `memory/backend.md` (set `<agent>` in each) |
| `memory-decisions.md` | `<workspace>/memory/decisions.md` |
| `design/DESIGN.md` | `<workspace>/design/DESIGN.md` |

Create `<workspace>/tasks/` empty. Create the two source trees only if they do
not exist and the user asked you to.

**Never overwrite a file that already exists.** Check before writing each one.
If any are already there — most likely `PROJECT.md`, because people write the
brief before reaching for tooling — list what you found and ask how to handle
it, offering: keep theirs and create only what is missing (usually right),
or back the file up to `<name>.bak` and write the template over it. Do not
decide this for them: `PROJECT.md` is the one file in the workspace a person
is likely to have authored by hand, and it is the input `{{cmd:plan}}`
reads.

## 4. Make sure the workspace is actually tracked

The workspace defaults to `.claude/sliced-loop/`, which keeps it out of the root
listing while leaving it in the repository — the backlog, the memory files and
the published contract describe the code, so they belong in version control
beside it.

**Check that nothing excludes it**, because ignoring `.claude/` wholesale is
common:

```bash
git check-ignore -v .claude/sliced-loop/PROJECT.md 2>/dev/null
```

If that prints a matching rule, the workspace would never be committed — a
teammate cloning the repo would get no backlog and no memory, and the agents
would start blind on work already done. Tell the user, and offer to fix it.

**A bare negation does not work.** Git does not descend into an excluded
directory, so `!.claude/sliced-loop/` cannot rescue anything while `.claude/`
itself is excluded. Exclude the *contents* instead, then negate:

```gitignore
.claude/*
!.claude/sliced-loop/
.claude/sliced-loop/.state/
```

If they ignore `.claude/` only to keep `settings.local.json` out, the simpler
fix is to ignore that file by name and drop the directory rule entirely.

Verify whichever you apply rather than assuming — the failure is silent:

```bash
git check-ignore -q .claude/sliced-loop/PROJECT.md      && echo "STILL IGNORED"
git check-ignore -q .claude/sliced-loop/.state/x.json   && echo ".state ignored, correct"
```

Add `<workspace>/.state/` to `.gitignore` regardless — it holds the tick
snapshot, which is local state, not project data.

## 5. Ask where the designs live

Ask the user whether the UI should follow an existing design, and where it is:
a Figma file, a Claude artifact, a page on the web, image or HTML exports, or
nothing yet. "Nothing yet" is a fine answer. Record it and move on.

For each source they name, add an entry to `<workspace>/design/DESIGN.md`: the
link, what it covers, and how an agent opens it. Then **check that it actually
opens from here**, because the frontend agent will have the same access this
session has, and no more:

- **Figma.** Look for a Figma MCP tool in this session and use it to read the
  file or one frame.
- **A Claude artifact** (a `claude.ai/…/artifact/…` link).
<!-- if:claude -->
  Read it with the Artifact tool, not a web fetch.
<!-- endif -->
<!-- if:opencode,codex,gemini,cursor -->
  This harness has no Artifact tool, and an artifact is private unless shared,
  so a web fetch usually can't read it either. Ask the user to export it (the
  page's HTML, or screenshots) into `<workspace>/design/`, and record the
  export as its access.
<!-- endif -->
- **A web page.** Fetch it.
- **Exports.** Confirm the files are in `<workspace>/design/`.

Mark each entry `status: ok <date>` or `status: needs-access`, with what is
missing. For anything that failed, tell the user exactly how to grant access:
<!-- if:claude -->
connect Figma, either as the claude.ai Figma connector or Figma's MCP server
with `claude mcp add`; share the artifact with this account; or export into
`design/`.
<!-- endif -->
<!-- if:opencode -->
add a Figma MCP server to `opencode.json` under `"mcp"`, or export into
`design/`.
<!-- endif -->
<!-- if:codex -->
add a Figma MCP server with `codex mcp add` (it lands in `~/.codex/config.toml`),
or export into `design/`.
<!-- endif -->
<!-- if:gemini -->
add a Figma MCP server with `gemini mcp add`, or export into `design/`.
<!-- endif -->
<!-- if:cursor -->
add a Figma MCP server in Cursor's MCP settings (`~/.cursor/mcp.json`), or
export into `design/`.
<!-- endif -->

Access granted after a restart counts. Setup doesn't wait on it: a frontend task
that needs a design it can't open blocks and asks for the design, instead of
guessing.

## 6. Tell the user what happens next

- `{{cmd:plan}}` turns a brief into a backlog of vertical slices
- `{{loop}}` starts the supervision loop, which ends itself after 5 idle ticks
  in a row. Change that with `idle_ticks` in `.sliced-loop.json`, and use `0` to
  never stop.
- `{{cmd:status}}` shows the board state at any time

Mention the one thing that trips people up: {{restart_note}}

Do not open tasks here. Planning is a separate step and a different job.
