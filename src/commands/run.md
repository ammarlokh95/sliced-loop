---
description: Start this project's backend and frontend together, wired to each other
argument-hint: "[--api-port N] [--web-port N]"
---

```bash
"{{scripts}}/run.sh" {{args}}
```

Runs until stopped — start it in the background if the session needs to keep
working, and tell the user both URLs.

It sets `VITE_API_STUB=false` and `VITE_API_BASE_URL` so the frontend talks to
the real server. **That matters:** a frontend built by this workflow consumes a
stub of the published contract and defaults to it, so running its dev server
alone gives a convincing app that never touches the network, with no warning.

Assumes npm on both sides. If this project uses something else, say so rather
than pretending it worked — the two halves still start fine by hand.
