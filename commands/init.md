---
description: Set this repository up for the sliced-loop workflow
argument-hint: "[frontend-dir] [backend-dir]"
---

Set up **the repository you are in** to be worked by this plugin's agents.

## 1. Work out the layout

If `$ARGUMENTS` names two directories, use them as the frontend and backend
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
└── research/           findings from the research agent
```

Copy from `${CLAUDE_PLUGIN_ROOT}/templates/`, then replace `<project>`,
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

Create `<workspace>/tasks/` empty. Create the two source trees only if they do
not exist and the user asked you to.

**Never overwrite a file that already exists.** Check before writing each one.
If any are already there — most likely `PROJECT.md`, because people write the
brief before reaching for tooling — list what you found and ask how to handle
it, offering: keep theirs and create only what is missing (usually right),
or back the file up to `<name>.bak` and write the template over it. Do not
decide this for them: `PROJECT.md` is the one file in the workspace a person
is likely to have authored by hand, and it is the input `/sliced-loop:plan`
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

## 5. Tell the user what happens next

- `/sliced-loop:plan` turns a brief into a backlog of vertical slices
- `/loop 15m /sliced-loop:supervise` starts the supervision loop
- `/sliced-loop:status` shows the board state at any time

Mention the one thing that trips people up: **the agents and the scope hook are
read at startup**, so this session cannot use them. They register on the next
`claude` launch — `claude --continue` keeps this conversation.

Do not open tasks here. Planning is a separate step and a different job.
