---
description: Set this repository up for the sliced-loop workflow
argument-hint: "[source dirs…]"
---

Set up **the repository you are in** to be worked by this plugin's agents.

Every source tree gets its own agent, confined to that tree. Most projects have
a UI and a server; many have more, such as a web app and a mobile app, or an
API and a billing service. Each agent has:

- **a name**, lowercase, e.g. `frontend`, `backend`, `mobile`, `billing`. Not
  `supervisor` or `research`, which are the plugin's own agents.
- **a role**. `ui` builds an interface and consumes contracts. `service` builds
  a server and publishes its contract for the others.
- **a focus**, optional: what kind of code the tree holds, e.g. "React Native
  app for iOS and Android" or "Go billing worker". It goes into the agent's
  brief.
- **a model**, optional: the LLM that runs it, e.g. `sonnet` for a small tree,
  `opus` for the core API. Leave it out to use the harness's default. It can be
  one per harness: `{"claude": "sonnet", "opencode": "anthropic/claude-sonnet-5"}`.

## 1. Work out the layout

If `$ARGUMENTS` names directories, start from those. Otherwise look at what is
actually here before asking:

```bash
ls -d */ */*/ 2>/dev/null | head -40
cat .sliced-loop.json 2>/dev/null
```

- **Already has `.sliced-loop.json` with an `"agents"` map.** This repo is
  already set up. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/agents.py" list`, say what it
  shows, and stop. More trees are added with `/sliced-loop:add-agent`.
- **Has `.sliced-loop.json` without one.** It uses the original two-agent
  layout. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/agents.py" migrate --harness claude`,
  report what it did, and stop.
- **Recognisable trees exist**, such as `frontend/`+`backend/`,
  `apps/web`+`apps/mobile`+`services/api`, or `client/`+`server/`. Propose one
  agent per tree: name, role, and a focus if the tree makes it obvious. Confirm
  with the user before writing anything.
- **Nothing recognisable, or an empty repo.** Ask what the trees should be,
  what each one is for, and whether to create them. Don't guess: the whole
  enforcement model rests on these paths being right.

Ask whether any agent should run on a particular model. A project without both
a UI and a service is a poor fit for this plugin; say so plainly rather than
forcing a layout onto it.

## 2. Register each agent

For each agreed tree, run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/agents.py" add <name> --path <dir> --role <ui|service> \
    [--focus "<what the tree holds>"] [--model <model>] [--create] --harness claude
```

`--create` makes the directory if it doesn't exist; only pass it if the user
asked for it. Each run does four things:
- validates the agent against the ones already there, and writes it into
  `.sliced-loop.json`. The first run creates the file.
- creates the agent's memory file and, for a service, its contract in
  `<workspace>/capabilities/<name>/`.
- gives the tree its own git repository (see step 4).
- writes the agent's definition for this harness. That file is machine-specific,
  so it's gitignored.

Paths are relative to the repository root. The workspace defaults to
`.claude/sliced-loop`. For a different one, write
`{"workspace": "<dir>", "agents": {}}` to `.sliced-loop.json` before the first
`add`.

## 3. Create the workspace

```
<workspace>/
├── PROJECT.md          what this is, scope, constraints, status
├── TEMPLATE.md         the task template
├── tasks/              one Markdown file per task
├── capabilities/       <service>/ — each service's published contract
├── memory/             <agent>.md per agent · decisions.md
├── design/             DESIGN.md — where the designs live, and how to reach them
└── research/           findings from the research agent
```

`agents.py add` already created each agent's memory file and contract. Copy the
rest from `${CLAUDE_PLUGIN_ROOT}/templates/`, then replace `<project>`, `<workspace>` and `<date>`
throughout:

| template | goes to |
|----------|---------|
| `PROJECT.md` | `<workspace>/PROJECT.md` |
| `TEMPLATE.md` | `<workspace>/TEMPLATE.md` |
| `workspace-README.md` | `<workspace>/README.md` |
| `research/README.md` | `<workspace>/research/README.md` |
| `memory-decisions.md` | `<workspace>/memory/decisions.md` |
| `design/DESIGN.md` | `<workspace>/design/DESIGN.md` |

Create `<workspace>/tasks/` empty.

**Never overwrite a file that already exists.** Check before writing each one.
If any are already there — most likely `PROJECT.md`, because people write the
brief before reaching for tooling — list what you found and ask how to handle
it, offering: keep theirs and create only what is missing (usually right),
or back the file up to `<name>.bak` and write the template over it. Do not
decide this for them: `PROJECT.md` is the one file in the workspace a person
is likely to have authored by hand, and it is the input `/sliced-loop:plan`
reads.

## 4. Check each tree's repository

Every tree has its own git repository. Each agent then commits its code where
nothing else writes, and the histories stay as separate as the trees. The
project root keeps a repository too, for `.sliced-loop.json` and the workspace,
and ignores the trees.

`agents.py add` already set this up for each tree it registered. See where
things stand:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/repos.py" status
```

A root repository is created only if there is none; a project inside a larger
repository keeps using that one. A tree with no repository got one, with an
initial commit of what was already there, and was added to the root
`.gitignore`. A tree that already had its own repository was left alone.

**A tree the root repository already tracks is not split without asking.** That
is an existing monorepo. Splitting it removes the tree from the root
repository's index. Its history stays in the root repository, and the new one
starts from today. `agents.py add` reports this and leaves the tree as it is.
Explain it to the user and offer both choices:

- **Split it:** run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/repos.py" init --split-tracked`, then
  commit the removal in the root repository.
- **Keep one repository:** do nothing. Agents still commit only their own
  files; they just share the one repository.

Don't choose for them. Also mention that agents commit their own work when they
finish each task, and that `"commit": false` in `.sliced-loop.json` turns that
off. Nothing is ever pushed.

## 5. Make sure the workspace is actually tracked

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

## 6. Ask where the designs live

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
  Read it with the Artifact tool, not a web fetch.
- **A web page.** Fetch it.
- **Exports.** Confirm the files are in `<workspace>/design/`.

Mark each entry `status: ok <date>` or `status: needs-access`, with what is
missing. For anything that failed, tell the user exactly how to grant access:
connect Figma, either as the claude.ai Figma connector or Figma's MCP server
with `claude mcp add`; share the artifact with this account; or export into
`design/`.

Access granted after a restart counts. Setup doesn't wait on it: a frontend task
that needs a design it can't open blocks and asks for the design, instead of
guessing.

## 7. Tell the user what happens next

- `/sliced-loop:plan` turns a brief into a backlog of vertical slices
- `/loop 15m /sliced-loop:supervise` starts the supervision loop, which ends itself after 5 idle ticks
  in a row. Change that with `idle_ticks` in `.sliced-loop.json`, and use `0` to
  never stop.
- `/sliced-loop:status` shows the board state at any time

Mention the one thing that trips people up: **the agents and the scope hook are
read at startup**, so this session cannot use them. They register on the next
`claude` launch — `claude --continue` keeps this conversation.

Do not open tasks here. Planning is a separate step and a different job.
