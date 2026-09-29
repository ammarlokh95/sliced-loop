---
description: One supervision tick — make the mechanical moves, call the supervisor only if needed, dispatch
argument-hint: "[idle ticks before the loop ends — default 5, 0 = never]"
---

One supervision tick, run by hand. The terminal loop runs the same tick without
a conversation to fill:

```
{{loop}}
```

A script works out most of the tick. Act only on what it can't decide, and keep
every reply to a line or two: in an in-session loop, everything you print lands
in this conversation again on every tick.

## 1. Plan

```bash
python3 "{{scripts}}/tick.py" plan --harness {{harness}}
```

It makes the mechanical moves itself: it unblocks tasks whose dependencies are
done. Then it prints the changes, who to dispatch, and whether the supervisor
is needed.

- **`MIGRATE`**: run `python3 "{{scripts}}/agents.py" migrate --harness {{harness}}`.
  Tell the user to restart the harness if it registers agents at startup, and
  end the tick.
- **`SYNC`**: run `python3 "{{scripts}}/agents.py" sync`, then do the same.
- **`QUIET`**: nothing to do. Say so in one line and end the tick. Don't read
  task files, spawn anything or narrate.
<!-- if:claude -->

  First record the quiet tick. If `{{args}}` is a number, pass it as the limit:

  ```bash
  python3 "{{scripts}}/tasks.py" tick quiet            # or: tick quiet --limit <N>
  ```

  Put the count it prints in your line. When it prints **`STOP`**, end the loop
  that runs this command. A `/loop` with an interval is a scheduled job: find
  it with `CronList` and delete it with `CronDelete`. A self-paced `/loop` ends
  when you call `ScheduleWakeup` with `stop: true`. Delete only that job.
<!-- endif -->

## 2. Supervisor, only if needed

If it printed **`SUPERVISOR not needed`**, skip this step. Don't spawn the
supervisor to look around.

If it printed **`SUPERVISOR needed`**, {{spawn:supervisor}}. Pass it
everything from `DIGEST` to the end of the output, verbatim: the digest of the
tasks it must decide, and its instructions for the tick. Don't add files or
summaries of your own. The digest is what keeps its session small.

## 3. Dispatch

After the supervisor, if it ran, get the dispatch list again, since its
decisions change it:

```bash
python3 "{{scripts}}/tick.py" next
```

Each `DISPATCH <agent> <task>` line is an agent that isn't busy, with its
highest-priority ready task. Wake exactly those and no others.

<!-- if:inproc -->
Spawn each one, concurrently, with its task ID and a reminder to follow the
session loop in its brief: read its memory file, claim the task, complete it,
update memory, commit, report, and stop.
<!-- endif -->
<!-- if:opencode -->
Use the task tool with `subagent_type` set to the agent's name.
<!-- endif -->
<!-- if:codex -->
Use `spawn_agent` with `agent_type` set to the agent's name. A generic agent
would go unconfined.
<!-- endif -->
<!-- if:headless -->
Start each one as its own headless session, so its scope is enforced:

```bash
python3 "{{scripts}}/dispatch.py" --harness {{harness}} <agent> <task-id>
```

It returns at once; the session runs detached and logs to
`<workspace>/.state/logs/`.
<!-- endif -->

A line marked **`(resume)`** is a claim whose session died.
<!-- if:inproc -->
Tell that agent: its earlier session on this task died mid-task and the work is
on disk. It must read the thread and run its checks before changing anything,
not start over, and not tick any criterion it hasn't verified itself.
<!-- endif -->
<!-- if:headless -->
Add `--resume`, which tells the agent that.
<!-- endif -->

<!-- if:inproc -->
When an agent returns, run `tick.py next` again and dispatch what it lists. Stop
after **six agent sessions** in this tick, when it lists nothing, or when
`tick.py plan --peek` says the supervisor is needed again.
<!-- endif -->

## 4. Report

One line: what was accepted or triaged, who was woken and on what. If the plan
listed anything **`WAITING`** on a human for access, add a second line naming
it.
<!-- if:claude -->

A tick that got this far did something, so reset the idle count:

```bash
python3 "{{scripts}}/tasks.py" tick active
```
<!-- endif -->
