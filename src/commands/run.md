---
description: Start one of this project's services and one of its UIs, wired to each other
argument-hint: "[--service NAME] [--ui NAME] [--api-port N] [--web-port N]"
---

```bash
"{{scripts}}/run.sh" {{args}}
```

Runs until stopped — start it in the background if the session needs to keep
working, and tell the user both URLs. Without `--service` and `--ui` it starts
the first of each role in `.sliced-loop.json`. To run a different pair, pass
the agents' names and a second pair of ports.

It sets `VITE_API_STUB=false` and `VITE_API_BASE_URL` so the UI talks to the
real server. **That matters:** a UI built by this workflow consumes a
stub of the published contract and defaults to it, so running its dev server
alone gives a convincing app that never touches the network, with no warning.

Assumes npm on both sides. If this project uses something else, say so rather
than pretending it worked — the two halves still start fine by hand.
