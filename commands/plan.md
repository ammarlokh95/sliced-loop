---
description: Turn a brief into a backlog of vertical slices covering the whole initial scope
argument-hint: "[a brief, a file path, or a research slug]"
---

Turn **$ARGUMENTS** into this project's backlog.

## 1. Find the brief

`$ARGUMENTS` can be any of these. Work out which it is before reading anything:

- **A file path** — read it.
- **A research slug** — `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tasks.py" research $ARGUMENTS`,
  then read the file it names.
- **A Jira story or epic** — an issue key like `ABC-123`, or a browse URL.
  Fetch it with an Atlassian tool if one is available in this session; an epic
  means reading its child issues too, since the epic itself is usually a title
  and the scope lives in the children. **If you cannot reach Jira, say so
  plainly and ask the user to paste the description.** Never reconstruct a
  ticket you could not read — a plausible-looking invented scope is worse than
  no plan, because everything downstream is built against it.
- **Prose** — that is the brief.
- **Nothing** — read `<workspace>/PROJECT.md`.
  - **Missing** — stop and tell the user: there is no brief to plan from. Point
    them at the three ways to give one (a file, a Jira issue, or prose), or at
    `/sliced-loop:init` if the workspace itself was never created. Do not invent
    a project.
  - **Still the placeholder template** — ask what the project is rather than
    filling it in from imagination.
  - **Written** — that is the brief. Treat what the user wrote as authoritative:
    sharpen and structure it, never quietly drop a constraint or narrow the
    scope they stated.

Check the board first: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tasks.py" status`.
If tasks already exist, this is a **scope extension**, not a first plan — say so,
and seed only the new work, sequenced behind what is already there.

## 2. If PROJECT.md already exists, ask before touching it

Whenever `<workspace>/PROJECT.md` exists and is **not** still the placeholder
template, stop and ask the user how to handle it — whatever the brief came from.
Never overwrite it on your own judgement. It may hold constraints, scope
decisions and out-of-scope calls that someone thought about, and a rewrite that
silently drops one is invisible until something is built wrong.

Ask **here, before spawning anything** — the supervisor is a subagent and cannot
put a question in front of the user.

Offer these, and say which you would pick and why:

- **Use it as the brief, unchanged** — the supervisor reads it, generates tasks
  from it, and does not edit it beyond appending to its Status section. Right
  when the file already says what the project is.
- **Let the supervisor fill the gaps** — it may add what is missing and
  structure what is there, but may not remove or narrow anything stated. Right
  when the file is a rough brief rather than a finished scope.
- **Replace it from the new brief** — only when the user says so explicitly.
  Copy the existing file to `PROJECT.md.bak` first and tell them where it went.
- **Cancel** — they wanted to look at it first.

When `$ARGUMENTS` gave a brief **and** a written `PROJECT.md` exists, say plainly
that there are now two briefs and which one you would treat as authoritative,
rather than merging them silently.

Carry the answer into the supervisor's instruction below as an explicit rule.
If the file does not exist, or is still the untouched template, no question is
needed — go straight on.

## 3. Hand it to the supervisor

Spawn the `supervisor` agent with the brief and this instruction:

> Plan this project's initial scope.
>
> 1. Read `.sliced-loop.json` for the directory names, then `<workspace>/PROJECT.md`
>    and `memory/decisions.md`. That plus the brief is your context — do not tour
>    the source trees.
> 2. `PROJECT.md` — **<paste the user's answer from step 2 here as an explicit
>    rule: use unchanged / fill gaps only / replaced, already backed up>**.
>    Whatever the rule, you may always append to its Status section.
>
>    Where you are allowed to write: cover what it is and for whom, what is in
>    scope and explicitly what is out, the constraints that bind, and a status
>    line. Text the user wrote is authoritative — you may structure and sharpen
>    it, never drop or narrow it. If you think a stated constraint is wrong, say
>    so in your report rather than editing it away.
> 3. Seed `memory/decisions.md` with the cross-boundary calls you can make now —
>    auth scheme, error envelope, pagination style, date and money representation.
>    Leave genuinely open questions under "Open questions" rather than guessing.
> 4. Cut the scope into **vertical slices**. A slice is one user-visible outcome
>    that runs through both trees — "a customer can see their past orders", not
>    "the order model" or "the API layer". Layering horizontally leaves nothing
>    demonstrable until the end and blocks every frontend task behind every
>    backend task; slicing does not. A few genuinely cross-cutting tasks are not
>    slices and that is fine — authentication, the app shell and design tokens,
>    database setup. Those come first, because everything depends on them.
> 5. Open tasks in `<workspace>/tasks/` covering the **whole initial scope** as
>    written in `PROJECT.md` — not just the first slice. Read end to end, the
>    backlog should show the finished project. Work beyond that initial scope is
>    not seeded; it becomes new tasks later, worked out with the human.
>
>    Per slice, one task each side: the **backend** task owns the contract and
>    carries it in `## Contract` — method, path, auth, request and response
>    schemas with field types, status codes, error shape, pagination. The
>    **frontend** task consumes it and declares `depends_on: [BE-00n]`. A slice
>    needing no server work is a single frontend task, and the reverse.
>
>    Every task: real acceptance criteria including the failure cases,
>    `requested_by: supervisor`, a priority, and a thread line naming where it
>    came from. State the outcome, never the implementation.
>
>    Write contracts precisely where `PROJECT.md` already determines the shape.
>    Where a later slice's contract genuinely depends on what earlier slices
>    teach you, write it as far as you can and mark it `provisional — sharpen at
>    triage`. Do **not** leave acceptance criteria provisional: if you cannot say
>    what "done" means, the scope is not settled enough to seed it, and that
>    belongs in PROJECT.md's open questions.
> 6. Set priorities honestly: cross-cutting first, then slice by slice in the
>    order that makes the project useful earliest. Within a slice the backend
>    task outranks the frontend task that depends on it.
>
> Leave every task `proposed`. You will triage them to `ready` on the next
> supervision tick, a few at a time — `ready` means claimable now, and a board
> where everything is ready has no priorities in it.
>
> Report: the slices you cut the scope into, the tasks you opened with their IDs
> and one line each, and what you put out of scope.

## 4. Report back

Relay the slices, the tasks, and what was put out of scope. The backlog should
read as the whole initial project — if it obviously does not cover the scope in
`PROJECT.md`, say so rather than moving on.

Then say plainly that the tasks are `proposed`, and that
`/loop 15m /sliced-loop:supervise` starts the loop that will triage and build
them. Do not wake the specialists here: seeding is not dispatching.
