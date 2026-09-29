# <workspace>

The shared workspace. It is the **only** place the agents meet — each is
confined to its own source tree and cannot read another's, so every requirement, answer,
and status change passes through here.

```
<workspace>/
├── PROJECT.md          what this is, scope, constraints, status
├── TEMPLATE.md         copy this to open a task
├── tasks/              one Markdown file per task
├── capabilities/       <service>/ — what each service exposes (it writes, the rest read)
├── memory/             <agent>.md per agent · decisions.md
├── design/             DESIGN.md — where the designs live and how to reach them
└── research/           findings, with sources
```

## Task files

One file per task — `tasks/<ID>-<slug>.md`. File-per-task means two agents never
write the same file. Each agent has a task-ID prefix — `FE-###`, `BE-###`,
`MO-###`; `agents.py list` shows them — and the next ID is the highest existing
number for that prefix:

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
| `memory/<agent>.md` | that agent | its stack, layout, conventions, decisions, gotchas |
| `memory/decisions.md` | supervisor | cross-boundary rules every agent must honour |

Rewritten in place — superseded lines replaced, never stacked. No hard limit:
keep what a fresh session needs. The `status` command warns at 80 lines and
flags at 100, and the owning agent then **condenses** the file while closing out
its next task. Ownership is enforced: no agent can write another's.

## Cross-agent requests

No agent edits another's code. To get something from another tree, open a task
owned by its agent with `status: proposed` and `requested_by:` yourself, then
link it from your own task's `depends_on:` and set yourself to `blocked`.

A request to a service must state the contract precisely — method, path,
auth, request body, response JSON with field types, status codes, error shape,
pagination. "I need the user's orders" is not a request; the endpoint signature
is.

## Answering a question

Questions live in the `## Thread` of the task they concern. Append, never
rewrite history. When a thread unblocks you, move yourself off `blocked` in the
same edit.

## capabilities/

Each service publishes its contract in `capabilities/<service>/`: `openapi.yaml`
is its API surface and `CAPABILITIES.md` the human-readable summary. The service
updates both whenever an endpoint lands, changes, or is deprecated — part of
finishing the task, not a follow-up. Every other agent reads them as the
contract and cannot write there; if something is wrong, it opens a task for
that service's agent.

## Designs and access

`design/DESIGN.md` lists every design source: its link, what it covers, how an
agent opens it (Figma MCP, the Artifact tool, a web fetch, or an export in
`design/`), and whether that has been verified. A UI task that follows a
design names the exact frame or section in its `## Design` section.

An agent that cannot open a source it needs **does not guess the design**. It
sets its task `blocked` and appends one thread line saying exactly what is
missing:

```
- 2026-09-24 mobile: needs-access: figma checkout-flow — no Figma MCP server in this session; connect one, or export "Cart / mobile" to design/checkout/
```

Only a human can grant access, so the status command reports these tasks as
waiting on you. Once access is granted, add a thread line saying so, e.g.
`- <date> human: access granted — Figma MCP connected`. The supervisor then
moves the task back to `ready`.
