---
description: What changed in the task files since the last check
---

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tasks.py" changes
```

Only what is new since the previous call — it advances a snapshot each time, so
anything it prints is genuinely new. Pass `--peek` to look without advancing.
