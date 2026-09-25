---
description: Open the drag-and-drop task board in a browser
argument-hint: "[--port N]"
---

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/board/serve.py" $ARGUMENTS
```

Runs until stopped, so start it in the background if the session needs to keep
working, and tell the user the URL.

Every task in six columns for the lifecycle, filterable by owner. Dragging a
card rewrites that task's `status:` and `updated:` in the file and appends a
`board: <from> -> <to> (manual override)` line to its `## Thread`. A human move
outranks the lifecycle rules — the board can put a task in any column, including
ones only the supervisor normally sets.
