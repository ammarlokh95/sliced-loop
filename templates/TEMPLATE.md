---
id: FE-000                # the owner's prefix — agents.py list shows them
title: short imperative summary
owner: frontend          # any agent in .sliced-loop.json
status: proposed         # proposed | ready | in-progress | blocked | review | done
priority: P2             # P0 urgent · P1 next · P2 normal · P3 someday
created: 2026-09-20
updated: 2026-09-20
requested_by: supervisor # supervisor | research | any agent
depends_on: []           # e.g. [BE-004]
---

## Goal

What this task is for, in a sentence or two. The user-visible or system-visible
outcome — not the implementation.

## Acceptance criteria

- [ ] Specific, checkable statements. The owner ticks these.
- [ ] Include the failure and edge cases, not just the happy path.

## Contract

Only for cross-boundary work. The exact interface: method, path, auth, request
schema, response schema with field types, status codes, error shape.

## Design

Frontend tasks only, when a design exists. Which entry in `design/DESIGN.md`
this implements, and the exact frame, page or section, e.g.
`checkout-flow — "Cart / mobile" (node-id=12-345)`. Leave it out when there is
no design. The UI agent then works from the acceptance criteria.

## Context

Links to other tasks, the capabilities file, prior decisions, constraints.

## Thread

- 2026-09-20 supervisor: created
