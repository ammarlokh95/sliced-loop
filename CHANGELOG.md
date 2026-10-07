# Changelog

Notable changes to sliced-loop, newest first. Versions follow
`.claude-plugin/plugin.json`.

## 1.3.0 — 2026-10-07

Cuts the token cost of each task. Nearly all of a run's tokens are spent in
the tree agents' sessions, and most of that is earlier tool output resent on
every later call.

### Added

- **Context budget in the tree-agent briefs** (`ui` and `service` roles). It
  explains that every tool result is paid for again on each later call, and
  sets the rules:
  - search first, then read just a range of the file
  - don't re-read what is already in context
  - batch independent calls
  - while iterating, run only the relevant tests, showing failures and the
    summary; run the full suite once, before `review`
  - send noisy output to a file
  - ask web fetches a narrow question
  - (`ui` agents only) take screenshots sparingly and near the end
- **Workers can split an oversized task.** A task that proves bigger than it
  looked can be handed in as a working, tested part. The criteria not reached
  move into a follow-up `proposed` task the agent opens in its own prefix,
  which depends on the original. The supervisor accepts the part when the
  criteria that stayed are met, then triages the follow-up.
- **Task sizing guidance** for the supervisor and `plan`: one focused session
  per task, split only where the halves can each be reviewed on their own.

### Changed

- **Memory files are also measured in characters.** `status` warns at 10k
  characters and asks for compaction at 12k, alongside the 80/100-line limits.
  Files of long lines used to slip past the line count. The memory-file
  guidance now asks for short lines.
- **Smaller startup reads for tree agents.** They no longer read
  `<workspace>/README.md` at the start of every session; the brief already
  carries the protocol. They scan `memory/decisions.md` by its headings and
  read the sections their task touches.

### Upgrading

Update the plugin, then run `agents.py sync` (the `status` command prints `SYNC`
when it's needed) to regenerate each project's tree-agent files. Restart the
harness so the new briefs load.
