# sliced-loop

**Build a full-stack feature with agents that can't quietly break each other's
half.**

One agent holding a whole codebase drifts. It patches a screen to hide a server
bug, invents an endpoint shape and builds both sides against the invention,
marks its own work done, and forgets everything when the session ends.

This plugin splits the work the way a team would, then enforces the split. Two
engineers own one tree each and cannot see the other's; they coordinate through
a written API contract. A third decides what gets built and accepts it, but
never writes code — so nobody grades their own homework.

## What it actually does

You give it a brief — a `PROJECT.md`, a Jira epic, a file, or a sentence.

1. **It plans.** The supervisor turns the brief into a backlog covering the
   whole initial scope, cut into *vertical slices*: "a customer can see their
   past orders", never "the order model". Each slice becomes a backend task that
   owns the API contract and a frontend task that depends on it.
2. **It builds.** On a timer, a supervision tick looks at the board, promotes
   what's genuinely unblocked, and wakes the agent that owns the next task. The
   backend ships an endpoint and publishes its contract; the frontend reads that
   contract and builds against it. Both sides work at once.
3. **It reviews.** Finished work goes to the supervisor, which checks it against
   the acceptance criteria written when the task was created — not against how
   it would have built it — and either accepts it or sends it back with a
   specific gap named.
4. **It keeps going** until the scope is done, without you in the loop.

You can watch it on a drag-and-drop board, and drag a card yourself to override
anything it decided.

## Features

**Enforced boundary.** A hook blocks each engineer from reading the other's tree
— before the read happens. Need an endpoint? Open a task stating the contract.

**Vertical slices.** Every task is one user-visible outcome through both trees,
so something works after the first slice instead of the last.

**Whole scope planned up front.** Read the backlog end to end and you see the
finished project. Details that depend on later learning are marked provisional,
not guessed.

**Nobody accepts their own work.** The supervisor decides what and when;
specialists decide how. It can reject a task as not worth doing — not an
implementation it would have written differently.

**One task per session.** Ending the session is what discards the context. What
was learned carries in a per-agent memory file, condensed by its owner past
~100 lines.

**Dead sessions recovered.** A claim nothing has touched for longer than a
session runs is re-dispatched as a resume. Otherwise one rate limit strands a
task forever while every tick reports success.

**Designs, or a request for access.** Point it at a Figma file or a Claude
artifact, and the frontend builds from the frame the task names. If it can't
open the design, it blocks and asks you for access instead of guessing.

**Any layout.** A config file names your two trees. Without it the plugin is
inert, so installing it can't disturb your other repos.

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

Run `init` (the exact command for each harness is under [Usage](#usage)). It
writes `.sliced-loop.json`, creates the workspace, and asks where your designs
live (see [Designs](#designs)).

**Restart the harness afterwards.** Agents, hooks and commands are read at
startup, so the session that installs the plugin can't use it. In Claude Code,
`claude --continue` keeps the conversation; check it loaded with `/agents` and
`/hooks`.

## Usage

The workflow is the same everywhere:

1. `init` sets up the repository.
2. `plan` turns a brief into a backlog covering the whole initial scope.
3. The loop runs `supervise` on an interval. It ends itself once the project
   goes idle (see [When the loop stops](#when-the-loop-stops)).

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
| `run` | start both halves, wired to each other |
| `research` | ask a question, or search what's been answered |

Only the command syntax and the loop differ between harnesses.

### Claude Code

```
/sliced-loop:init
/sliced-loop:plan                     # reads PROJECT.md
/sliced-loop:plan ABC-123             # a Jira story or epic
/sliced-loop:plan notes/brief.md      # a file
/sliced-loop:plan "build a ..."       # prose
/loop 15m /sliced-loop:supervise      # stops after 5 idle ticks
/loop 15m /sliced-loop:supervise 10   # ...or after 10; 0 never stops
```

The other commands are `/sliced-loop:status`, `/sliced-loop:board` and so on.
The loop lives in your session. It ends when the session closes, or when it
reaches its idle limit, at which point it cancels its own `/loop`.

### OpenCode

```
/sliced-loop-init
/sliced-loop-plan notes/brief.md
```

Commands are `/sliced-loop-<name>`. OpenCode has no `/loop`, so run the loop
from a terminal in the repository:

```
python3 /path/to/sliced-loop/scripts/loop.py --harness opencode --every 15m                  # stops after 5 idle ticks
python3 /path/to/sliced-loop/scripts/loop.py --harness opencode --every 15m --idle-ticks 10  # ...or after 10; 0 never stops
```

### Codex

```
$sliced-loop-init
$sliced-loop-plan notes/brief.md
```

The commands are skills, invoked as `$sliced-loop-<name>`. Run the loop from a
terminal:

```
python3 /path/to/sliced-loop/scripts/loop.py --harness codex --every 15m                  # stops after 5 idle ticks
python3 /path/to/sliced-loop/scripts/loop.py --harness codex --every 15m --idle-ticks 10  # ...or after 10; 0 never stops
```

### Gemini CLI

```
/sliced-loop:init
/sliced-loop:plan notes/brief.md
```

The command names are the same as in Claude Code. Run the loop from a terminal:

```
python3 /path/to/sliced-loop/scripts/loop.py --harness gemini --every 15m                  # stops after 5 idle ticks
python3 /path/to/sliced-loop/scripts/loop.py --harness gemini --every 15m --idle-ticks 10  # ...or after 10; 0 never stops
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
python3 /path/to/sliced-loop/scripts/loop.py --harness cursor --every 15m                  # stops after 5 idle ticks
python3 /path/to/sliced-loop/scripts/loop.py --harness cursor --every 15m --idle-ticks 10  # ...or after 10; 0 never stops
```

As on Gemini CLI, the specialists and `research` run as separate headless
sessions (`agent -p`), for the same reason.

### The terminal loop

`loop.py` checks the board itself, which costs no model call. It starts a
headless `supervise` session only when a tick has something to do: a change, an
idle agent with ready work, or a dead claim. Ctrl-C stops it, and a running
tick is allowed to finish.

The headless command it runs for each harness can be overridden in
`.sliced-loop.json`, for example to pick a model:

```json
"headless": { "gemini": ["gemini", "--yolo", "-m", "gemini-3-pro", "-p", "{prompt}"] }
```

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
| one Claude Code loop | a number after the command: `/loop 15m /sliced-loop:supervise 10` |
| one terminal loop | `loop.py … --idle-ticks 10` |
| the project's default | `"idle_ticks": 10` in `.sliced-loop.json` |

`0` means never stop. The command line wins over the config, and the config
wins over the default of 5.

### Designs

If the UI should follow a design, tell `init` where it lives: a Figma file, a
Claude artifact, or anything else with a link. It's recorded in
`<workspace>/design/DESIGN.md`, and the supervisor attaches the relevant part to
each frontend task.

The frontend agent reads a design through whatever access its session has:
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

Four agents, one workspace, one loop.

| agent | sees | does |
|-------|------|------|
| `frontend` | its own tree + the workspace | builds the UI against the published contract |
| `backend` | its own tree + the workspace | builds the server, publishes the contract |
| `supervisor` | everything | plans, prioritises, accepts, unblocks — writes no code |
| `research` | the workspace only | answers a question with cited evidence |

The **workspace** is the only place the two engineers meet. It holds the
backlog, the published API contract, the shared decisions both must honour, and
a memory file per agent.

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

`.sliced-loop.json` at the repository root names the directories. Defaults:

```json
{
  "frontend": "frontend",
  "backend": "backend",
  "workspace": ".claude/sliced-loop"
}
```

Any layout works — `apps/web` + `services/api`, `client/` + `server/`. The hook,
the CLI, the board and every agent brief read this file rather than assuming.
Without it the plugin is inert.

**The workspace sits inside `.claude/` on purpose:** out of your root listing,
but still in the repo. The backlog, memory files and published contract describe
the code, so they belong in version control beside it. If you gitignore
`.claude/` wholesale, `init` catches it and offers a fix — otherwise a teammate
who clones gets no backlog and the agents start blind.

## What it creates

```
<workspace>/
├── PROJECT.md          what this is, scope, constraints, status
├── README.md           the coordination protocol
├── TEMPLATE.md         the task template
├── tasks/              one Markdown file per task
├── capabilities/       the backend's published contract
├── memory/             frontend.md · backend.md · decisions.md
├── design/             DESIGN.md — where the designs live, and how to reach them
└── research/           findings, with sources
```

## Requirements

Python 3 for the tooling. `/sliced-loop:run` also needs `jq`, and assumes npm on
both sides. Nothing else — the plugin has no dependencies of its own.

## Limits worth knowing

- **Bash is a guard rail, not a jail.** File tools are enforced exactly; shell
  commands are only pattern-checked, and a shell has routes text can't see.
- **The loop lives in one session** and stops when that session closes. That's
  the Claude session, or the terminal running `loop.py`. It also ends itself
  after 5 idle ticks.
- **Headless dispatch doesn't chain.** On Gemini CLI and Cursor, a finished
  specialist's next task waits for the next tick, not the same one.
- **Codex and Cursor output is built from their docs.** It hasn't been run
  against those CLIs yet. The OpenCode and Gemini output loads in their CLIs.
- **Acceptance is only as good as the criteria** written into the task. Vague
  criteria, vague acceptance.
