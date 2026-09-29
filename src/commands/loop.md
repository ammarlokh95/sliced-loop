---
description: Start, stop or check the supervision loop, which runs in the background outside this chat
argument-hint: "[start [every] [idle-ticks] | stop | status]"
---

Control this project's supervision loop. It runs in the background, outside
this conversation. Each tick is a fresh headless session, so nothing piles up
here, and the loop keeps running after this chat ends.

`{{args}}` is one of:

| arguments | what it does |
|-----------|--------------|
| *(nothing)* or `start` | start the loop: a tick every 15 minutes, stopping after 5 idle ticks |
| `start <every>` | start it with that time between ticks: `90s`, `10m`, `1h` |
| `start <every> <idle-ticks>` | …and stop after that many idle ticks in a row; `0` never stops |
| `stop` | stop it; a tick already running finishes first |
| `status` | whether it's running, its settings, and its latest tick lines |

For example, `start 10m 8` ticks every 10 minutes and stops after 8 idle ticks.
A tick is idle when nothing changed, nothing was dispatched, the supervisor
wasn't needed, and no agent was mid-task. Without `<idle-ticks>`, the limit is
`idle_ticks` in `.sliced-loop.json`, or 5.

Work out the action from `{{args}}`, then run exactly one of these:

```bash
# start, with the defaults
python3 "{{scripts}}/loop.py" --harness {{harness}} --detach
# start with <every>, and optionally <idle-ticks>
python3 "{{scripts}}/loop.py" --harness {{harness}} --detach --every <every> [--idle-ticks <idle-ticks>]
# stop
python3 "{{scripts}}/loop.py" --stop
# status
python3 "{{scripts}}/loop.py" --status
```

If the arguments don't fit the table, e.g. an interval without a unit or an
unknown word, say what's accepted and run nothing.

Report the result in one or two lines, using what the command printed. After a
start, add that `{{cmd:loop}} status` shows its progress, and that its log is at
`<workspace>/.state/logs/loop.log`. If it says a loop is **already running**,
report that; don't stop and restart it unless the user asks.
