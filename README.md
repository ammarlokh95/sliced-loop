# Sliced loop

**Build a full-stack feature with agents that can't quietly break each other's
half.**

One agent holding a whole codebase drifts. It patches a screen to hide a server
bug, invents an endpoint shape and builds both sides against the invention,
marks its own work done, and forgets everything when the session ends.

This plugin splits the work the way a team would, then enforces the split. Every
source tree — a web app, an API, a mobile app, a billing service — gets its own
engineer, who cannot see anyone else's tree; they coordinate through written API
contracts. A supervisor decides what gets built and accepts it, but never writes
code — so nobody grades their own homework.

## What it actually does

You give it a brief — a `PROJECT.md`, a Jira epic, a file, or a sentence.

1. **It plans.** The supervisor turns the brief into a backlog covering the
   whole initial scope, cut into *vertical slices*: "a customer can see their
   past orders", never "the order model". Each slice becomes a task for the
   service that owns the API contract, and a task for each UI that shows it.
2. **It builds.** On a timer, a supervision tick looks at the board, promotes
   what's genuinely unblocked, and wakes the agent that owns the next task. A
   service ships an endpoint and publishes its contract; each UI reads that
   contract and builds against it. Every tree works at once.
3. **It reviews.** Finished work goes to the supervisor, which checks it against
   the acceptance criteria written when the task was created — not against how
   it would have built it — and either accepts it or sends it back with a
   specific gap named.
4. **It keeps going** until the scope is done, without you in the loop.

You can watch it on a drag-and-drop board, and drag a card yourself to override
anything it decided.

## Features

**Enforced boundary.** A hook blocks each engineer from reading any other tree
— before the read happens. Need an endpoint? Open a task stating the contract.

**One agent per tree, as many trees as you have.** Two is the common case; add
a mobile app or a second service whenever you like. Each agent gets a role (`ui`
or `service`), an optional focus that shapes its brief, and optionally its own
model.

**Vertical slices.** Every task is one user-visible outcome through the trees it
needs, so something works after the first slice instead of the last.

**Whole scope planned up front.** Read the backlog end to end and you see the
finished project. Details that depend on later learning are marked provisional,
not guessed.

**Nobody accepts their own work.** The supervisor decides what and when;
specialists decide how. It can reject a task as not worth doing — not an
implementation it would have written differently.

**A commit per task.** Each agent commits its own work when it finishes a task:
code to its tree's own repository, and workspace files to the root's. A commit
never carries another agent's files. Nothing is pushed.

**One task per session.** Ending the session is what discards the context. What
was learned carries in a per-agent memory file, condensed by its owner past
~100 lines.

**Dead sessions recovered.** A claim nothing has touched for longer than a
session runs is re-dispatched as a resume. Otherwise one rate limit strands a
task forever while every tick reports success.

**Designs, or a request for access.** Point it at a Figma file or a Claude
artifact, and the UI agent builds from the frame the task names. If it can't
open the design, it blocks and asks you for access instead of guessing.

**Any layout.** A config file names your trees and their agents. Without it the
plugin is inert, so installing it can't disturb your other repos.

**You outrank it.** Drag a card on the board; it writes straight into the task
file as a manual override.

## Install

sliced-loop runs on **Claude Code**, **OpenCode**, **Codex**, **Gemini CLI** and
**Cursor**. However you install it, it does nothing in a repository until you run
`init` there, so installing it can't disturb your other repos.

### Claude Code

```
/plugin marketplace add ammarlokh95/sliced-loop
/plugin install sliced-loop@sliced-loop
```

From a local clone instead, point at the folder:

```
/plugin marketplace add /path/to/sliced-loop
```

A local marketplace reads from that path, so don't move the folder while it is
installed. `/plugin marketplace update sliced-loop` pulls later changes.

### OpenCode, Codex, Gemini CLI, Cursor

Clone this repo, then install for your harness:

```
git clone https://github.com/ammarlokh95/sliced-loop
python3 sliced-loop/scripts/install.py opencode     # or codex, gemini, cursor
```

That renders the prompts for that harness and puts them where it looks:

| harness | where it goes |
|---------|---------------|
| OpenCode | `~/.config/opencode/` — or one repo's `.opencode/` with `--project DIR` |
| Codex | `~/.codex/` agents, skills and a hook — or one repo with `--project DIR` |
| Gemini CLI | a linked extension (`gemini extensions link`); it asks you to consent to its hook |
| Cursor | a local plugin, `~/.cursor/plugins/local/sliced-loop` |

The installed files point at the clone by absolute path. Don't move the clone
while it is installed, and re-run the install after pulling. The install never
overwrites a file it didn't create. `--uninstall` removes exactly what it wrote.

**Codex:** use `install.py`, not `codex plugin marketplace add`. Codex will read
this repo's Claude manifest, but it doesn't load agents from a plugin. After
installing, approve the scope hook in `/hooks`. Codex skips a hook nobody has
reviewed, and until you approve it the specialists are unconfined.

### Then, in the repository you want it to work on

`init` sets the repository up so each source tree gets its own confined agent.
Run it (the exact command per harness is under [Usage](#usage)):

1. **Name the trees.** It proposes one agent per source directory it finds. For
   each, you confirm its role (`ui` or `service`). You can also give it a focus
   and a model (see [Agents](#agents)).
2. **Register them.** Each agent gets a memory file, a contract (for services)
   and its own git repository.
3. **Create the workspace.** This is where the backlog, contracts and memory
   live.
4. **Point at designs.** Optional: Figma files or Claude artifacts for the UI
   (see [Designs](#designs)).
5. **Restart the harness** so it loads the agents and hooks. In Claude Code,
   `claude --continue` keeps the conversation.

## Usage

The workflow is the same everywhere:

1. `init` sets up the repository.
2. `plan` turns a brief into a backlog covering the whole initial scope.
3. The loop, `loop.py` in a terminal, ticks on an interval until the project
   goes idle (see [The loop](#the-loop)).

`plan` takes a brief in any of four forms. With no argument it reads
`<workspace>/PROJECT.md`. If that file is missing, it tells you rather than
inventing a project. It also takes a Jira story or epic (`ABC-123`), a file
path, or prose in quotes. A brief you wrote is treated as authoritative: it gets
structured and sharpened, never quietly narrowed.

Everything else is optional:

| command | what it does |
|---------|--------------|
| `status` | who is busy, who is idle, what waits on the supervisor — and on you |
| `changes` | what moved in the task files since the last check |
| `board` | drag-and-drop board; a human move outranks the rules |
| `add-agent` | add a source tree, with its own agent (see [Agents](#agents)) |
| `run` | start a service and a UI, wired to each other |
| `research` | ask a question, or search what's been answered |

Only the command syntax and the loop differ between harnesses.

### Claude Code

```
/sliced-loop:init
/sliced-loop:plan                     # reads PROJECT.md
/sliced-loop:plan ABC-123             # a Jira story or epic
/sliced-loop:plan notes/brief.md      # a file
/sliced-loop:plan "build a ..."       # prose
```

Then run the loop from a terminal in the repository:

```
python3 ~/.claude/plugins/cache/sliced-loop/sliced-loop/<version>/scripts/loop.py --harness claude --every 15m
```

The other commands are `/sliced-loop:status`, `/sliced-loop:board` and so on.
You can also loop inside your session, with `/loop 15m /sliced-loop:supervise`
(add a number to change the idle limit). That costs more: every tick, and every
report it gets back, stays in your conversation.

### OpenCode

```
/sliced-loop-init
/sliced-loop-plan notes/brief.md
```

Commands are `/sliced-loop-<name>`. Run the loop from a terminal in the
repository:

```
python3 /path/to/sliced-loop/scripts/loop.py --harness opencode --every 15m
```

### Codex

```
$sliced-loop-init
$sliced-loop-plan notes/brief.md
```

The commands are skills, invoked as `$sliced-loop-<name>`. Run the loop from a
terminal:

```
python3 /path/to/sliced-loop/scripts/loop.py --harness codex --every 15m
```

### Gemini CLI

```
/sliced-loop:init
/sliced-loop:plan notes/brief.md
```

The command names are the same as in Claude Code. Run the loop from a terminal:

```
python3 /path/to/sliced-loop/scripts/loop.py --harness gemini --every 15m
```

Gemini's hooks can't tell which subagent is acting, so a specialist never runs
inside your session. Each one runs as its own headless session. It gets its
brief and one task, runs detached, and logs to `<workspace>/.state/logs/`.
`research` works the same way: it starts the research session and returns, and
`/sliced-loop:research` with no argument lists the finding once it is written.

### Cursor

```
/sliced-loop-init
/sliced-loop-plan notes/brief.md
```

Commands are `/sliced-loop-<name>`. Run the loop from a terminal:

```
python3 /path/to/sliced-loop/scripts/loop.py --harness cursor --every 15m
```

As on Gemini CLI, the specialists and `research` run as separate headless
sessions (`agent -p`), for the same reason.

### The loop

Each tick runs outside your conversation, and a model runs only where judgment
is needed:

1. **Look.** A script checks the board, with no model call. Most ticks end here.
2. **Mechanical moves.** The script sets tasks whose dependencies are done back
   to `ready`.
3. **Supervisor, only if needed.** Needed means work awaiting acceptance, a new
   proposal, a question, or an agent with nothing ready. It gets a digest of
   just those tasks, not the files. It isn't asked again about a task that
   hasn't changed since.
4. **Dispatch.** The script gives each idle agent its highest-priority ready
   task, in its own fresh headless session, all at once. When they finish,
   the next round goes out, up to six sessions a tick.

Logs go to `<workspace>/.state/logs/`. Ctrl-C stops the loop; a running tick
finishes. To pick a model or flags, override the headless command per harness in
`.sliced-loop.json`:

```json
"headless": { "gemini": ["gemini", "--yolo", "-m", "gemini-3-pro", "-p", "{prompt}"] }
```

Headless sessions run unattended: `claude -p --permission-mode
bypassPermissions`, `--yolo`, `--auto`, `--force`. The scope hook still confines
every agent.

### When the loop stops

Every loop ends itself after **5 idle ticks in a row**. A tick is idle when
nothing changed, no idle agent has ready work, nothing is stale, **and** no
specialist is mid-task. A long task keeps the loop alive, even if its task file
doesn't change for an hour. Anything that moves resets the count.

A task waiting on you for access is still idle, so an unanswered access request
lets the loop wind down instead of ticking all night. Grant it, then start the
loop again.

To change the limit:

| where | how |
|-------|-----|
| one loop | `loop.py … --idle-ticks 10` (in-session: `/loop 15m /sliced-loop:supervise 10`) |
| the project's default | `"idle_ticks": 10` in `.sliced-loop.json` |

`0` means never stop. The command line wins over the config, and the config
wins over the default of 5.

### Agents

Every source tree has one agent, and it can only touch that tree:

- **role:** a `ui` builds an interface from the services' contracts. A
  `service` builds a server and publishes its contract.
- **focus** (optional): what the tree holds, e.g. "React Native app". It shapes
  the agent's brief and where the supervisor sends work.
- **model** (optional): the LLM that runs it. Give one name, or one per
  harness: `{"claude": "sonnet", "opencode": "anthropic/claude-sonnet-4-5"}`.

**Adding a source directory later.** Use this for a mobile app, a second
service, an admin panel:

1. Run `add-agent` (e.g. `/sliced-loop:add-agent mobile apps/mobile ui`). It
   asks for anything missing.
2. It registers the agent, creates its memory file and repository, and writes
   its definition.
3. Restart the harness (Claude Code, OpenCode, Codex). Gemini CLI and Cursor
   pick it up right away.
4. Run `plan` with a brief for the new tree to give it work.

`agents.py list` shows every agent. The generated agent files are gitignored,
because they hold machine-specific paths. After cloning or a plugin update,
`status` says `SYNC`; run `agents.py sync`.

### Designs

If the UI should follow a design, tell `init` where it lives: a Figma file, a
Claude artifact, or anything else with a link. It's recorded in
`<workspace>/design/DESIGN.md`, and the supervisor attaches the relevant part to
each UI task.

A UI agent reads a design through whatever access its session has:
- Figma: a Figma MCP server.
- A Claude artifact: the Artifact tool in Claude Code.
- A public page: a web fetch.
- A file you exported into `<workspace>/design/`.

When a task points at a design it can't open, it **asks for access instead of
guessing**. It blocks the task with a `needs-access:` line that names exactly
what it needs. `status` and the loop's tick line report that as waiting on you.
Connect the server, share the link, or drop an export into `design/`, then note
in the task's thread that it's done. The supervisor unblocks it on the next
tick.

## The moving parts

One agent per source tree, two of the plugin's own, one workspace, one loop.

| agent | sees | does |
|-------|------|------|
| each `ui` agent | its own tree + the workspace | builds an interface against the published contracts |
| each `service` agent | its own tree + the workspace | builds a server, publishes its contract |
| `supervisor` | everything | plans, prioritises, accepts, unblocks — writes no code |
| `research` | the workspace only | answers a question with cited evidence |

The **workspace** is the only place the engineers meet. It holds the backlog,
each service's published API contract, the shared decisions every agent must
honour, and a memory file per agent.

The **loop** is one command (`/sliced-loop:supervise`) on a timer. Each tick
reads what changed since the last one, so a quiet tick costs almost nothing —
most of them are quiet. A tick with something in it recovers dead claims, calls
the supervisor to review and triage, then wakes whoever has work.

A **task** is a Markdown file with frontmatter: owner, status, priority,
dependencies, acceptance criteria, and a thread the agents append to. That file
is the whole coordination mechanism — there is no database and no state you
can't read or edit by hand.

## The board is local

The board lives in the plugin, not your project — nothing is copied into your
repo, and the only files it writes are the task files a drag edits.

Runtime state (the tick snapshot, anything cached later) goes in
`<workspace>/.state/`, which `init` gitignores. All of it is regenerable.

## Configuration

`.sliced-loop.json` at the repository root names every tree and its agent.
`init` and `add-agent` write it:

```json
{
  "workspace": ".claude/sliced-loop",
  "agents": {
    "frontend": { "path": "apps/web",     "role": "ui" },
    "backend":  { "path": "services/api", "role": "service", "model": "opus" },
    "mobile":   { "path": "apps/mobile",  "role": "ui", "focus": "React Native app", "model": "sonnet" }
  },
  "harnesses": ["claude"]
}
```

`harnesses` lists where agent files are generated; `agents.py sync --harness X`
adds one. Other optional keys: `idle_ticks` (see [When the loop stops](#when-the-loop-stops)),
`commit: false` to stop agents committing, and `headless` (see [The loop](#the-loop)).

Any layout works, as long as no tree sits inside another or inside the
workspace. The hook, the CLI, the board and every agent brief read this file
rather than assuming. Without it the plugin is inert.

The original two-key form, `{"frontend": "web", "backend": "api"}`, still reads
as a `ui` and a `service` agent. See [Upgrading](#upgrading).

**The workspace sits inside `.claude/` on purpose:** out of your root listing,
but still in the repo. The backlog, memory files and published contract describe
the code, so they belong in version control beside it. If you gitignore
`.claude/` wholesale, `init` catches it and offers a fix — otherwise a teammate
who clones gets no backlog and the agents start blind.

## Repositories and commits

`init` and `add-agent` give every tree its own repository:

```
<root>/            repository — .sliced-loop.json and the workspace
├── <tree>/        its own repository, ignored by the root one
├── <tree>/        …one per agent
└── <tree>/
```

Each agent commits when it finishes a task, through `scripts/commit.py`. Its
code goes to its tree's repository, where nothing else writes. Its task file,
memory and contract or design exports go to the root repository. The message
is built from the task: the subject is `FE-004: <title>`, and the body gives
the status change and the agent's closing thread line. The research and
supervisor agents commit their workspace files the same way.

`commit.py` stages an explicit list of the agent's own files, never `git add
-A`. The workspace is shared, and agents run concurrently. It retries if another
agent holds git's lock, and runs pre-commit hooks rather than skipping them.
Nothing is ever pushed.

A few cases differ:
- **An existing monorepo.** If the root repository already tracks a tree,
  `init` asks before splitting it out. Splitting removes the tree from the root
  repository's index, and the new repository starts fresh. If you'd rather keep
  one repository, agents still commit only their own files in it.
- **A project inside a larger repository.** It uses that repository for the
  workspace.
- **Turning commits off.** Set `"commit": false` in `.sliced-loop.json`.

## What it creates

```
<workspace>/
├── PROJECT.md          what this is, scope, constraints, status
├── README.md           the coordination protocol
├── TEMPLATE.md         the task template
├── tasks/              one Markdown file per task
├── capabilities/       <service>/ — each service's published contract
├── memory/             <agent>.md per agent · decisions.md
├── design/             DESIGN.md — where the designs live, and how to reach them
└── research/           findings, with sources
```

## Requirements

Python 3 for the tooling. `run` assumes npm in both trees it starts. Nothing
else — the plugin has no dependencies of its own.

## Limits worth knowing

- **Bash is a guard rail, not a jail.** File tools are enforced exactly; shell
  commands are only pattern-checked, and a shell has routes text can't see.
- **The loop lives in one session** and stops when that session closes. That's
  the Claude session, or the terminal running `loop.py`. It also ends itself
  after 5 idle ticks.
- **Running `supervise` by hand on Gemini CLI or Cursor doesn't chain.** It
  starts agents detached, so their next tasks wait for the next tick. `loop.py`
  chains on every harness.
- **A new agent needs a restart** on Claude Code, OpenCode and Codex, which load
  subagents at startup.
- **Codex and Cursor output is built from their docs.** It hasn't been run
  against those CLIs yet. The OpenCode and Gemini output loads in their CLIs.
- **Acceptance is only as good as the criteria** written into the task. Vague
  criteria, vague acceptance.

## Upgrading

Projects set up before per-tree agents (plugin 1.0.x) keep working, but need one
migration. `status` says `MIGRATE` until it's done:

```
python3 /path/to/sliced-loop/scripts/agents.py migrate --harness claude   # or your harness
```

It does three things:
- rewrites `.sliced-loop.json` with an `agents` map.
- moves the backend's contract from `capabilities/` to `capabilities/backend/`,
  with `git mv` so its history follows.
- writes the `frontend` and `backend` agent files.

Commit the result and restart the harness. The plugin no longer ships
`frontend` and `backend` itself. On Claude Code the plugin's agents are
namespaced (`sliced-loop:frontend`), and the scope hook never recognised those
names, so the two specialists ran unconfined there. Registered per project,
under their bare names, they're confined.
