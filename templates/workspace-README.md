# <workspace>

The shared workspace. It is the **only** place the frontend and backend agents
meet — neither can read the other's source tree, so every requirement, answer,
and status change passes through here.

```
<workspace>/
├── PROJECT.md          what this is, scope, constraints, status
├── TEMPLATE.md         copy this to open a task
├── tasks/              one Markdown file per task
├── capabilities/       what the backend exposes (backend writes, frontend reads)
├── memory/             frontend.md · backend.md · decisions.md
└── research/           findings, with sources
```

## Task files

One file per task — `tasks/<ID>-<slug>.md`. File-per-task means two agents never
write the same file. IDs are `FE-###` and `BE-###`; the next is the highest
existing number for that prefix:

```bash
ls tasks/ | grep -o '^BE-[0-9]*' | sort -V | tail -1
```

## Status lifecycle

| status        | meaning                                              | who sets it |
|---------------|------------------------------------------------------|-------------|
| `proposed`    | filed, not yet prioritized                            | anyone      |
| `ready`       | prioritized and available to claim                    | supervisor  |
| `in-progress` | claimed and being worked                              | owner       |
| `blocked`     | waiting on `depends_on`, or on an unanswered question | owner       |
| `review`      | work complete, awaiting acceptance                    | owner       |
| `done`        | accepted                                              | supervisor  |

The owner moves its own task through `in-progress`, `blocked`, and `review`.
Only the supervisor promotes `proposed` → `ready` and accepts `review` → `done`.
That split is deliberate: the supervisor decides **what** gets built next and in
what order; the owning agent decides **how**, and that decision is not
overridden.

Always bump `updated:` and append a `## Thread` line when you change anything.

## Memory

Three files, so a fresh session starts productive instead of re-deriving what it
already knew:

| file | owner | contents |
|------|-------|----------|
| `memory/frontend.md` | frontend agent | its stack, layout, conventions, decisions, gotchas |
| `memory/backend.md` | backend agent | the same, for the server |
| `memory/decisions.md` | supervisor | cross-boundary rules both must honour |

Rewritten in place — superseded lines replaced, never stacked. No hard limit:
keep what a fresh session needs. `/sliced-loop:status` warns at 80 lines and
flags at 100, and the owning agent then **condenses** the file while closing out
its next task. Ownership is enforced: neither agent can write the other's.

## Cross-agent requests

Neither agent edits the other's code. To get something from the other side, open
a task owned by them with `status: proposed` and `requested_by:` yourself, then
link it from your own task's `depends_on:` and set yourself to `blocked`.

A frontend → backend request must state the contract precisely — method, path,
auth, request body, response JSON with field types, status codes, error shape,
pagination. "I need the user's orders" is not a request; the endpoint signature
is.

## Answering a question

Questions live in the `## Thread` of the task they concern. Append, never
rewrite history. When a thread unblocks you, move yourself off `blocked` in the
same edit.

## capabilities/

`capabilities/openapi.yaml` is the published API surface and `CAPABILITIES.md`
the human-readable summary. The backend updates both whenever an endpoint lands,
changes, or is deprecated — part of finishing the task, not a follow-up. The
frontend reads them as the contract and cannot write here; if something is
wrong, it opens a `BE-` task.
