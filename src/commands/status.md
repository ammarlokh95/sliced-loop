---
description: Who is busy, who is idle, what is waiting on the supervisor
---

```bash
python3 "{{scripts}}/tasks.py" status
```

Report the output as-is. It says, for each agent: `BUSY` on a task, `IDLE` with
what is next, or **`STALE`** — a claim nothing has touched for longer than an
agent session runs, left behind by a session that died. A `STALE` agent is idle,
not busy, and its task needs re-dispatching as a resume.

It also lists what is awaiting acceptance or triage, and flags any memory file
that has grown past its compaction threshold.
