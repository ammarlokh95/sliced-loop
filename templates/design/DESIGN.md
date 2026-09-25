# Design sources — <project>

Where the UI's designs live, and how an agent reaches each one. The frontend
agent reads this before building anything a task links to a design. A design it
cannot open is a request for access, never a licence to guess.

Kept by the supervisor and the human. The frontend agent may add exports it
pulled (a frame as PNG, tokens as JSON) to this directory and list them below.

## Sources

One entry per source. `access` is how an agent opens it:

- `figma-mcp`: through a Figma MCP server connected to the agent's session.
- `artifact`: a Claude artifact, read with the Artifact tool, which Claude Code
  sessions have.
- `web`: a public URL a web fetch can read.
- `file`: an export saved in this directory.

`status` is `ok <date>` once an agent has actually opened the source, or
`needs-access` with what is missing.

<!-- Example — replace, do not keep:
### checkout-flow
- link: https://www.figma.com/design/AbC123/Shop?node-id=12-345
- covers: cart, checkout, order confirmation — desktop and mobile frames
- access: figma-mcp  (fallback: exports in design/checkout/)
- status: ok 2026-09-24
-->

_None recorded yet. Without a design, the frontend agent works from the task's
acceptance criteria and its own craft standards._

## Exports

Files in this directory and what they are. An export records one moment in the
design, so give each one the date it was taken. The link stays the source of
truth.
