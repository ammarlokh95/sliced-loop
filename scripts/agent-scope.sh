#!/usr/bin/env bash
# PreToolUse hook: confine each specialist agent to the directories it owns.
#
# Hook payloads carry `agent_type` (the subagent's name), so scope is enforced
# per-agent -- something plain permission rules cannot express. The main thread,
# the supervisor, and any agent not listed below pass through untouched.
#
#   frontend  read+write  <frontend>/ <workspace>/
#                         read-only: <workspace>/capabilities/, memory/backend.md
#   backend   read+write  <backend>/  <workspace>/
#                         read-only: memory/frontend.md
#   research  read        <workspace>/   write only <workspace>/research/
#
# Directory names come from .sliced-loop.json, so this works whatever the
# project calls its two trees.
#
# File tools are enforced exactly. Bash is checked by pattern only: a shell has
# routes a text check cannot see, so this is a guard rail, not a jail.

set -uo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

payload=$(cat)
field() { printf '%s' "$payload" | command jq -r "$1" 2>/dev/null; }

agent=$(field '.agent_type // ""')
case "$agent" in
  frontend|backend|research) ;;
  *) exit 0 ;;
esac

root="${CLAUDE_PROJECT_DIR:-$(field '.cwd // ""')}"
[ -n "$root" ] || exit 0
[ -f "$root/.sliced-loop.json" ] || exit 0   # not a sliced-loop project; stay out of the way

cfg_get() {
  command jq -r --arg k "$1" --arg d "$2" '(.[$k] // $d) | rtrimstr("/")' \
    "$root/.sliced-loop.json" 2>/dev/null || printf '%s' "$2"
}
FRONTEND=$(cfg_get frontend frontend)
BACKEND=$(cfg_get backend backend)
WORKSPACE=$(cfg_get workspace .claude/sliced-loop)

case "$agent" in
  frontend)
    read_ok=("$FRONTEND" "$WORKSPACE")
    write_ok=("$FRONTEND" "$WORKSPACE")
    write_deny_re="^${WORKSPACE}/(capabilities(/|$)|memory/backend\.md$)"
    write_deny_why="the published API contract in $WORKSPACE/capabilities/ and the backend's memory file"
    bash_deny="$BACKEND"
    ;;
  backend)
    read_ok=("$BACKEND" "$WORKSPACE")
    write_ok=("$BACKEND" "$WORKSPACE")
    write_deny_re="^${WORKSPACE}/memory/frontend\.md$"
    write_deny_why="the frontend's memory file"
    bash_deny="$FRONTEND"
    ;;
  research)
    read_ok=("$WORKSPACE")
    write_ok=("$WORKSPACE/research")
    write_deny_re=''
    write_deny_why=""
    bash_deny="$FRONTEND|$BACKEND"
    ;;
esac

cwd=$(field '.cwd // ""'); [ -n "$cwd" ] || cwd="$root"
tool=$(field '.tool_name // ""')

deny() {
  printf '%s' "$1" | command jq -R --slurp '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: .
    }
  }'
  exit 0
}

under() {
  local abs=$1 rel dir; shift
  for rel in "$@"; do
    dir=$(realpath -m "$root/$rel")
    case "$abs" in "$dir"|"$dir"/*) return 0 ;; esac
  done
  return 1
}

list() { local out="" x; for x in "$@"; do out+="${out:+, }$x/"; done; printf '%s' "$out"; }

case "$tool" in
  Read|Glob|Grep|Edit|Write|NotebookEdit)
    target=$(field '.tool_input.file_path // .tool_input.notebook_path // .tool_input.path // ""')
    [ -n "$target" ] || exit 0
    case "$target" in
      /*) abs=$(realpath -m "$target") ;;
      *)  abs=$(realpath -m "$cwd/$target") ;;
    esac

    case "$tool" in
      Read|Glob|Grep) mode=read; allowed=("${read_ok[@]}") ;;
      *)              mode=write; allowed=("${write_ok[@]}") ;;
    esac

    if ! under "$abs" "${allowed[@]}"; then
      deny "Out of scope: the $agent agent may $mode only within $(list "${allowed[@]}"). Blocked: $abs. If this needs work outside your scope, open a task in $WORKSPACE/tasks/ for the agent that owns it and mark yourself blocked on it."
    fi

    if [ "$mode" = write ] && [ -n "$write_deny_re" ]; then
      rel=${abs#"$root"/}
      if printf '%s' "$rel" | grep -qE "$write_deny_re"; then
        deny "Read-only for the $agent agent: $write_deny_why. Blocked write: $rel. If it is wrong, raise it in a task rather than editing it."
      fi
    fi
    ;;

  Bash)
    cmd=$(field '.tool_input.command // ""')
    if printf '%s' "$cmd" | grep -qE "(^|[^A-Za-z0-9_.-])\.{0,2}/?(${bash_deny})(/|\$)"; then
      deny "Out of scope: the $agent agent must not touch ${bash_deny//|/ or }/. Command referenced it: $cmd"
    fi
    ;;
esac

exit 0
