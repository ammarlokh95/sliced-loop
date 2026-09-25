---
description: One supervision tick — review changes, recover dead claims, dispatch the next task
argument-hint: "[idle ticks before the loop ends — default 5, 0 = never]"
---

One supervision tick. Keep it cheap: most ticks should do nothing and say so in
a single line.

## 1. Look

```bash
python3 "{{scripts}}/tasks.py" changes
python3 "{{scripts}}/tasks.py" status
```

`changes` reports only what is new since the previous tick and then advances its
snapshot, so anything it prints is genuinely new.

## 2. Decide whether to stop here

If `changes` says `no changes` **and** `status` shows no idle agent with a ready
task waiting **and** nothing `STALE`, there is nothing to do. Say so in one line
and end the tick. Do not spawn anything, do not read task files, do not narrate.
<!-- if:claude -->

First record the quiet tick. If `{{args}}` is a number, pass it as the limit:

```bash
python3 "{{scripts}}/tasks.py" tick quiet            # or: tick quiet --limit <N>
```

It counts consecutive idle ticks and puts the count in your one line, e.g.
`idle tick 2 of 5`. A quiet tick while a specialist is mid-task isn't idle, so
it resets the count instead. **When it prints `STOP`**, nothing has moved for
that many ticks and nobody is working, so end the loop that runs this command:

- A `/loop` with an interval runs as a scheduled job. Find the one whose prompt
  runs this supervise command with `CronList`, and delete it with `CronDelete`.
- A self-paced `/loop` ends when you call `ScheduleWakeup` with `stop: true`.

Delete only the job that runs this command, never another one. Then say in one
line that the loop stopped after that many idle ticks, and that this starts it
again:

```
{{loop}}
```
<!-- endif -->

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

If anything changed, {{spawn:supervisor}} with the exact output of both
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

<!-- if:inproc -->
Spawn each named agent with its task ID and a reminder to follow the session
loop in its brief: read its memory file, claim the task, complete it, update
memory, report, and stop.
<!-- endif -->
<!-- if:opencode -->
Use the task tool with `subagent_type` set to the agent's name — the scope
plugin identifies the agent from that.
<!-- endif -->
<!-- if:codex -->
Use `spawn_agent` with `agent_type` set to the agent's name — the scope hook
identifies the agent from that, and a generic agent would go unconfined.
<!-- endif -->
<!-- if:headless -->
This harness cannot tell a hook which subagent is acting, so a specialist must
not run as a subagent of this session — its scope would go unenforced. Each one
runs as its own headless session, which the scope hook recognises. Start each
named agent with:

```bash
python3 "{{scripts}}/dispatch.py" --harness {{harness}} <agent> <task-id>
python3 "{{scripts}}/dispatch.py" --harness {{harness}} <agent> <task-id> --resume "<resume brief>"   # a STALE recovery
```

It returns at once: the session runs detached, logging to
`<workspace>/.state/logs/`, and follows the session loop in its brief — read its
memory file, claim the task, complete it, update memory, report, and stop.
`dispatch.py` refuses an agent that already has a session running.
<!-- endif -->

- **Never wake an agent reported `BUSY`** — it is mid-task and a second session
  on the same tree would collide. `STALE` is not `BUSY`.
- **Never wake an agent the supervisor did not name.**
- One task per session. The agent stops after one; that is deliberate, it is how
  its context gets discarded between tasks.
- Run both dispatches concurrently when both are named — different trees do not
  collide.

<!-- if:inproc -->
## 6. Keep going while there is work

When an agent returns and more work of its own is `ready`, dispatch a fresh
session straight away rather than waiting for the next tick — that fresh session
is the point, not the wait.

Stop dispatching within a tick when any of these is true: **six agent sessions**
have run, nothing is `ready` for an idle agent, or something needs the
supervisor's judgment again (a task hit `review` or `blocked`, or a new
`proposed` task appeared).
<!-- endif -->
<!-- if:headless -->
## 6. Leave the rest to the next tick

Detached sessions do not return to this one, so there is no chaining within a
tick: when an agent finishes, its task moves, and the next tick sees the change
and dispatches what comes after it.
<!-- endif -->

## 7. Report

One short line: what changed, what was accepted or triaged, who you woke and on
what. If `status` lists anything **waiting on a human**, a task blocked on access
only a human can grant, add a second line naming it and what it needs. That is
the one thing a tick can't do for itself. If nothing happened: "no changes, both agents idle with nothing ready".
Keep it terse — this line lands in your own context on every tick.
<!-- if:claude -->

A tick that got this far did something, so reset the idle count:

```bash
python3 "{{scripts}}/tasks.py" tick active
```
<!-- endif -->
