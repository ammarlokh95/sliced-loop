# sliced-loop

Two specialist agents build one application from opposite sides of an API
contract, **never reading each other's code**. A supervisor cuts the scope into
vertical slices, dispatches one task per session, and accepts the work against
its acceptance criteria. A timed loop keeps it moving.

The name is the two mechanics: **sliced** — every task is one user-visible
outcome cut through both trees, never a horizontal layer; **loop** — a
supervision tick that reviews, recovers and dispatches on an interval.

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

## How it works

**The boundary is enforced, not asked for.** A `PreToolUse` hook reads
`agent_type` from the payload and blocks the frontend agent from reading the
backend tree and vice versa — before the read happens. Neither can work around
the other: a frontend that needs an endpoint opens a task stating the exact
contract and marks itself blocked.

**Vertical slices, not layers.** "A customer can see their past orders" is a
slice; "the order model" is a layer. Layering leaves nothing demonstrable until
the end and blocks every frontend task behind every backend task. Each slice
becomes a backend task owning the contract and a frontend task that
`depends_on` it.

**The supervisor decides what, never how.** It sets priority and sequence and
accepts work against acceptance criteria. Framework, architecture, data
modelling and testing strategy belong to the agent that owns the tree, and that
decision is not overridden.

**Context is the constraint.** An agent does exactly one task per session and
then stops — ending the session is what discards the context. What it learned
carries forward in a memory file it reads first and rewrites last. Files past
~100 lines get condensed by their owner rather than truncated.

**Dead sessions are recovered.** An `in-progress` claim that nothing has touched
for longer than a session runs is reported `STALE`, not `BUSY`, and re-dispatched
as a resume. Without this a killed session leaves a claim that blocks its task
forever while every tick reports success.

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
