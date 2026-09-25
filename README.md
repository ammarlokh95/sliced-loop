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

**Any layout.** A config file names your two trees. Without it the plugin is
inert, so installing it can't disturb your other repos.

**You outrank it.** Drag a card on the board; it writes straight into the task
file as a manual override.

## Install

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

Then, in the repository you want it to work on:

```
/sliced-loop:init
```

**Restart afterwards** — `claude --continue` keeps the conversation. Agents,
hooks and commands are read at startup, so the session that installs the plugin
cannot use it. Check it loaded with `/agents` and `/hooks`.

## Use it

```
/sliced-loop:plan                     # reads PROJECT.md
/sliced-loop:plan ABC-123             # a Jira story or epic
/sliced-loop:plan notes/brief.md      # a file
/sliced-loop:plan "build a ..."       # prose
/loop 15m /sliced-loop:supervise
```

`plan` turns a brief into a backlog covering the whole initial scope. With no
argument it reads `<workspace>/PROJECT.md`; if that file is missing it tells you
rather than inventing a project. A brief you wrote is treated as authoritative —
it gets structured and sharpened, never quietly narrowed. `supervise`
is one tick; the loop runs it on an interval. Everything else is optional:

| command | what it does |
|---------|--------------|
| `/sliced-loop:status` | who is busy, who is idle, what waits on the supervisor |
| `/sliced-loop:changes` | what moved in the task files since the last check |
| `/sliced-loop:board` | drag-and-drop board; a human move outranks the rules |
| `/sliced-loop:run` | start both halves, wired to each other |
| `/sliced-loop:research` | ask a question, or search what's been answered |

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
└── research/           findings, with sources
```

## Requirements

Python 3 and `jq` for the tooling; `/sliced-loop:run` additionally assumes npm on
both sides. Nothing else — the plugin has no dependencies of its own.

## Limits worth knowing

- **Bash is a guard rail, not a jail.** File tools are enforced exactly; shell
  commands are only pattern-checked, and a shell has routes text can't see.
- **The loop lives in one session** and stops when that session closes.
- **Acceptance is only as good as the criteria** written into the task. Vague
  criteria, vague acceptance.
