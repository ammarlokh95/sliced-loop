---
description: Ask the research agent a question, or list what it has already answered
argument-hint: "[question, or a word to search past findings]"
---

**No argument** — list what has already been answered:

```bash
python3 "{{scripts}}/tasks.py" research
```

**A few words that look like a search** — check whether it is already answered
before spending a session on it:

```bash
python3 "{{scripts}}/tasks.py" research {{args}}
```

**An actual question** — hand it to the `research` agent. Pass the question
verbatim; do not rephrase it into a topic, since the sharpness of the question is
what makes the answer useful.

<!-- if:inproc -->
{{Spawn:research}} with it. Tell it to follow its brief: cite sources, argue the
other side, say where the evidence is thin, and write the finding to the
workspace's `research/` directory.

Relay its answer, its confidence, and the strongest reason it might be wrong.
<!-- endif -->
<!-- if:headless -->
Start it as its own headless session, so its scope is enforced:

```bash
python3 "{{scripts}}/dispatch.py" --harness {{harness}} research --question "<the question, verbatim>"
```

Its brief already tells it to cite sources, argue the other side, say where the
evidence is thin, and write the finding to the workspace's `research/`
directory. The session runs detached, so there is no answer to relay yet: tell
the user it is running and that `{{cmd:research}}` with no argument lists the
finding once it is written.
<!-- endif -->
