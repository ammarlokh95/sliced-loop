---
description: The supervisor's instructions for one tick, sent with the tick's digest
---

This is one supervision tick. The loop has already done the mechanical work. It
unblocked every task whose dependencies are done. After you finish, it wakes
each idle agent on its highest-priority `ready` task whose dependencies are
done. You steer that through status and priority. You don't name who to wake.

Your job this tick is only the judgment calls listed under **SUPERVISOR
needed**. The **DIGEST** holds the tasks involved, with just the sections you
need and the thread lines that are new since the last tick. Work from it. Open
a task file, a tree or a contract only when the digest isn't enough, e.g. to
check that finished work really meets its criteria.

- **Awaiting acceptance:** check the acceptance criteria against what landed.
  For a service's work, also check that `capabilities/<service>/` was updated.
  Then either set `done`, or send it back to `ready` with the specific gap named
  in the thread. "I'd have done it differently" isn't a gap.
- **Newly proposed:** decide whether it's worth doing. Set `ready` with a
  priority, leave it `proposed` for later, or close it with the reason in the
  thread.
- **A question in a blocked task's thread:** answer it in the thread. If that
  unblocks the task, set it `ready` in the same edit.
- **An agent with nothing ready:** promote its next proposed task or two to
  `ready`, in the order that makes the project useful earliest. Promote a few
  at a time, not the whole backlog.

Respect the sovereignty rules in your brief: you judge what and when, never
how. Bump `updated:` and append a thread line whenever you change a task.
**Verify your own writes**: re-read each file you edited, and report only what
you confirmed on disk.

Then commit, with exactly this and nothing else from git:

```bash
python3 "{{scripts}}/commit.py" supervisor
```

Report in at most five lines: what you accepted, sent back, triaged or
answered. Don't name agents to dispatch; the loop does that from the board.
