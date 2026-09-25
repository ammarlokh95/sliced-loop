# sliced-loop

**Build a full-stack feature with agents that can't quietly break each other's
half.**

A single agent holding a whole codebase in context drifts. It changes a screen
to work around a server bug, invents an endpoint shape and then builds both
sides against the invention, marks its own work done, and loses everything it
learned the moment the session ends. The larger the project gets, the worse each
of those gets.

This plugin splits the work the way a team would, and then enforces the split.
Two engineers own one tree each and genuinely cannot see the other's. They
coordinate through a written API contract, the same as humans in different
repositories. A third agent decides what gets built next and accepts the work —
but never touches the code, so nobody grades their own homework.

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

**The boundary is enforced, not requested.** A `PreToolUse` hook blocks the
frontend agent from reading the backend tree and vice versa, before the read
happens. Neither can paper over the other's bug, so a frontend that needs an
endpoint has to open a task stating the exact contract — method, path, auth,
schemas, status codes, error shape.

**Work is cut vertically.** Layering — all the models, then all the endpoints,
then all the screens — leaves nothing demonstrable until the end and blocks
every frontend task behind every backend task. Slices give you something that
works after the first one.

**The plan is complete before the build starts.** The backlog covers the whole
initial scope, so reading it end to end shows you the finished project. Contract
details that genuinely depend on what earlier slices teach you are marked
provisional and sharpened later, not guessed at now.

**Nobody accepts their own work.** The supervisor decides *what* and *when*;
the specialists decide *how*, and that decision stands. It can reject a task as
not worth doing; it can't reject an implementation because it would have written
it differently.

**Context is spent deliberately.** One task per agent session, then the session
ends — that's what discards the context. What was learned carries forward in a
per-agent memory file, read first and rewritten last, condensed by its owner
when it grows past ~100 lines.

**Dead sessions are recovered.** A claim nothing has touched for longer than a
session runs is reported `STALE` and re-dispatched as a resume. Without this, one
rate limit leaves a task claimed forever while every tick reports success.

**Any layout works.** A config file names your two trees — `apps/web` +
`services/api`, `client/` + `server/`, anything. Without that file the plugin
stays completely inert, so installing it doesn't affect your other repositories.

**You outrank all of it.** The board writes your drag straight into the task
file and records it as a manual override. Nothing is hidden in a database.

## Install

```bash
/plugin marketplace add /path/to/sliced-loop
/plugin install sliced-loop@sliced-loop
```

Then, in the repository you want it to work on:

```
/sliced-loop:init
```

**Restart afterwards** (`claude --continue` keeps the conversation). Agents and
hooks are read at startup, so the session that installs the plugin cannot use it.

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

The board is part of the plugin, not your project. It is served from the plugin
install, so nothing is copied into your repository and there is nothing to
commit or gitignore. The only files it writes are the task files a drag edits.

Runtime state — the tick snapshot, and anything the tooling caches later — lives
in `<workspace>/.state/`, which `init` gitignores. It is all regenerable, so
losing it costs nothing.

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
the CLI, the board and every agent brief read these rather than assuming.
Without this file the plugin stays completely out of the way, so installing it
does not affect your other repositories.

**The workspace defaults inside `.claude/` on purpose.** It stays out of your
root listing, but stays in the repository: the backlog, the memory files and the
published API contract describe the code, so they belong in version control
beside it. Keeping them in the plugin install instead would put every project's
tasks in one shared directory and lose them on the next plugin upgrade, since
that path is versioned and re-fetched. If you gitignore `.claude/` wholesale,
`init` will spot it and offer a negation — otherwise a teammate who clones gets
no backlog and no memory, and the agents start blind.

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
  commands are checked by pattern, and a shell has routes a text check cannot
  see.
- **The loop lives in one session.** It stops when that session closes.
- **The supervisor is the acceptance gate**, and it is only as good as the
  acceptance criteria written into the task. Vague criteria produce vague
  acceptance.
