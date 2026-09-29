---
description: Add a source tree to the project, with its own agent
argument-hint: "[name] [dir] [ui|service] [focus] [model]"
---

Add a new source tree to this project and give it its own agent: its own
brief, scope, memory file, task-ID prefix, git repository and, optionally, its
own model.

## 1. Pin down the agent

`$ARGUMENTS` may already give some of this. Ask for whatever is missing, and
confirm the whole agent before writing anything:

- **name**: lowercase letters, digits and dashes, e.g. `mobile`, `billing`,
  `admin`. It can't be `supervisor`, `research`, or a name already in use.
- **dir**: the tree, relative to the project root. It must not sit inside
  another agent's tree or the workspace. If it doesn't exist, ask whether to
  create it.
- **role**: `ui` builds an interface and consumes the services' contracts.
  `service` builds a server and publishes its own contract in
  `<workspace>/capabilities/<name>/`.
- **focus**, optional but worth asking: what kind of code the tree holds, e.g.
  "React Native app for iOS and Android" or "Go worker that settles invoices".
  It goes into the agent's brief, and the supervisor uses it to place work.
- **model**, optional: the LLM that runs this agent. Leave it out for the
  harness's default. It can be one per harness:
  `{"claude": "sonnet", "opencode": "anthropic/claude-sonnet-5"}`.
- **prefix**, optional: 2-4 capitals for its task IDs. It's derived from the
  name if not given.

See who exists already:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/agents.py" list
```

## 2. Add it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/agents.py" add <name> --path <dir> --role <ui|service> \
    [--focus "<focus>"] [--model <model>] [--prefix <XX>] [--create] --harness claude
```

It records the agent in `.sliced-loop.json`. It then creates the agent's memory
file and, for a service, its contract. It gives the tree its own git repository
and writes the agent's definition for every harness this project uses.

If it says the tree is **tracked by the root repository**, it left the tree
alone. Splitting it into its own repository removes it from the root
repository's index, so ask the user first, as `init` does. Then run
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/repos.py" init <name> --split-tracked`.

## 3. Tell the user what happens next

- The new agent owns nothing yet. `/sliced-loop:plan` with a brief for this tree
  seeds its tasks, sequenced behind what is already there. So does the
  supervisor on its next tick, if `PROJECT.md` already covers this tree.
- Its scope is enforced from its first tool call.
- Restart Claude Code before the next tick. Agents load at startup, so this
  session can't spawn the new one; `claude --continue` keeps this conversation.
