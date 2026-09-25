---
description: Ask the research agent a question, or list what it has already answered
argument-hint: "[question, or a word to search past findings]"
---

**No argument** — list what has already been answered:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tasks.py" research
```

**A few words that look like a search** — check whether it is already answered
before spending a session on it:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tasks.py" research $ARGUMENTS
```

**An actual question** — hand it to the `research` agent. Pass the question
verbatim; do not rephrase it into a topic, since the sharpness of the question is
what makes the answer useful.

Spawn the `research` agent with it. Tell it to follow its brief: cite sources, argue the
other side, say where the evidence is thin, and write the finding to the
workspace's `research/` directory.

Relay its answer, its confidence, and the strongest reason it might be wrong.
