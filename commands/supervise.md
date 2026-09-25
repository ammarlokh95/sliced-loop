---
description: One supervision tick — review changes, recover dead claims, dispatch the next task
---

One supervision tick. Keep it cheap: most ticks should do nothing and say so in
a single line.

## 1. Look

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tasks.py" changes
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tasks.py" status
```

`changes` reports only what is new since the previous tick and then advances its
snapshot, so anything it prints is genuinely new.

## 2. Decide whether to stop here

If `changes` says `no changes` **and** `status` shows no idle agent with a ready
task waiting **and** nothing `STALE`, there is nothing to do. Say so in one line
and end the tick. Do not spawn anything, do not read task files, do not narrate.

Quiet ticks are the normal case. Keeping them near-free is what lets this run
all day.

## 3. Recover abandoned claims

`status` reports an agent as **`STALE`** when a task is `in-progress` but
nothing — not the task file, not a single file in that agent's tree — has been
touched for longer than an agent session runs. That claim belongs to a session
that died: a rate limit, a crash, a closed terminal.

**A `STALE` agent is not busy. Re-dispatch it.** The "never wake a BUSY agent"
rule does not apply — there is no session to collide with, and left alone the
board reports it busy forever and the task is never dispatched again. This is
the failure that silently ends a long run.

Handle it before anything else, because the agent is idle in reality and the
board is lying about it:

1. **Find out how far it got.** Run that tree's own checks — tests, typecheck,
   lint, build — and read the task's `## Thread`. Work on disk and passing is
   work to build on.
2. **Leave `status: in-progress` alone.** The claim is being transferred to a
   fresh session, not withdrawn.
3. **Dispatch with a resume brief**: this is a resume of its own earlier session
   that was killed mid-task, the work is intact on disk, here is what you
   verified passing just now, here is what remains. Tell it **not to start over,
   not to rebuild, and not to second-guess the stack its earlier session chose**
   — that session was itself and its decisions stand.
4. If the checks show it barely started, say so — then it is a restart in
   practice and the agent should be told that instead.

A resumed session is where a task is most likely to be marked complete on the
strength of the previous session's momentum. Tell it not to tick any acceptance
criterion it has not verified itself.

## 4. Review the changes

If anything changed, spawn the `supervisor` agent with the exact output of both
commands, and ask it to:

- accept `review` → `done` against the acceptance criteria, triage `proposed` →
  `ready` with a priority, answer questions sitting in the `## Thread` of
  anything `blocked`, and unblock what the change has unblocked
- respect the sovereignty rules in its own brief: it judges what and when, never
  how
- **verify its own writes before reporting** — re-read each file after editing
  and report only what it has confirmed on disk. A reported-but-unwritten
  acceptance is worse than an unmade one, because nothing downstream notices.
- end with a dispatch decision, one line per agent, in exactly this shape:

```
DISPATCH: frontend FE-004 — <one line on why this is next>
DISPATCH: backend none — <one line on why nothing>
```

The supervisor decides; you carry the decision out. A tick where it only triages
and dispatches nothing is a normal tick.

## 5. Wake the agents it named

Spawn each named agent with its task ID and a reminder to follow the session
loop in its brief: read its memory file, claim the task, complete it, update
memory, report, and stop.

- **Never wake an agent reported `BUSY`** — it is mid-task and a second session
  on the same tree would collide. `STALE` is not `BUSY`.
- **Never wake an agent the supervisor did not name.**
- One task per session. The agent stops after one; that is deliberate, it is how
  its context gets discarded between tasks.
- Run both dispatches concurrently when both are named — different trees do not
  collide.

## 6. Keep going while there is work

When an agent returns and more work of its own is `ready`, dispatch a fresh
session straight away rather than waiting for the next tick — that fresh session
is the point, not the wait.

Stop dispatching within a tick when any of these is true: **six agent sessions**
have run, nothing is `ready` for an idle agent, or something needs the
supervisor's judgment again (a task hit `review` or `blocked`, or a new
`proposed` task appeared).

## 7. Report

One short line: what changed, what was accepted or triaged, who you woke and on
what. If nothing happened: "no changes, both agents idle with nothing ready".
Keep it terse — this line lands in your own context on every tick.
