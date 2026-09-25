#!/usr/bin/env bash
#
# Start this project's backend and frontend together, wired to each other.
#
#   run.sh [--api-port N] [--web-port N] [--no-install]
#
# A frontend built this way consumes a stub of the backend's published contract
# and defaults to that stub — so running its dev server alone gives a convincing
# app that never touches the network. This starts the real server and points the
# frontend at it.
#
# Directory names come from .sliced-loop.json.
#
# Ctrl-C stops both.

set -uo pipefail


PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
while [ ! -f "$ROOT/.sliced-loop.json" ] && [ "$ROOT" != "/" ]; do ROOT=$(dirname "$ROOT"); done

if [ -t 1 ]; then B=$'\033[1m'; C=$'\033[36m'; D=$'\033[2m'; R=$'\033[31m'; X=$'\033[0m'
else B=""; C=""; D=""; R=""; X=""; fi

die() { printf '%serror:%s %s\n' "$R" "$X" "$1" >&2; exit 1; }
note() { printf '%s%s%s\n' "$D" "$1" "$X"; }

API_PORT=3000
WEB_PORT=5173
INSTALL=1

while [ $# -gt 0 ]; do
  case "$1" in
    --api-port) API_PORT="${2-}"; shift 2 || die "--api-port needs a number" ;;
    --web-port) WEB_PORT="${2-}"; shift 2 || die "--web-port needs a number" ;;
    --no-install) INSTALL=0; shift ;;
    -h|--help) sed -n '3,16p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) die "unknown option $1" ;;
    *) die "unexpected argument $1" ;;
  esac
done

[ -f "$ROOT/.sliced-loop.json" ] || die "no .sliced-loop.json found — run /sliced-loop:init first"

cfg_get() {
  command jq -r --arg k "$1" --arg d "$2" '(.[$k] // $d) | rtrimstr("/")' \
    "$ROOT/.sliced-loop.json" 2>/dev/null || printf '%s' "$2"
}
FE_DIR=$(cfg_get frontend frontend)
BE_DIR=$(cfg_get backend backend)
PROJECT=$(basename "$ROOT")

BACKEND="$ROOT/$BE_DIR"
FRONTEND="$ROOT/$FE_DIR"
[ -d "$BACKEND" ]  || die "no backend at $BE_DIR/"
[ -d "$FRONTEND" ] || die "no frontend at $FE_DIR/"
[ -f "$BACKEND/package.json" ]  || die "$BE_DIR/ has no package.json — this runner expects npm on both sides"
[ -f "$FRONTEND/package.json" ] || die "$FE_DIR/ has no package.json — this runner expects npm on both sides"

# Try both stacks: vite binds ::1 by default, the backend binds 127.0.0.1, and
# a probe of the wrong one reads as "not listening yet" forever.
port_busy() {
  local port=$1 host
  for host in 127.0.0.1 ::1; do
    # `exec` with only redirections applies them to this shell for good, so the
    # fd close is grouped — `exec 3>&- 2>/dev/null` would mute stderr forever.
    (exec 3<>"/dev/tcp/$host/$port") 2>/dev/null && { { exec 3>&-; } 2>/dev/null; return 0; }
  done
  return 1
}
port_busy "$API_PORT" && die "port $API_PORT is already in use (--api-port to change)"
port_busy "$WEB_PORT" && die "port $WEB_PORT is already in use (--web-port to change)"

API_PID=""; WEB_PID=""
CLEANED=0

# `npm start` becomes npm -> node, and the pid we hold is only the subshell.
# Signalling that pid leaves the server running and the port bound, so walk the
# real process tree instead and signal children before their parents (a parent
# npm will happily respawn a child it outlives).
descendants() {
  local pid=$1 child
  for child in $(pgrep -P "$pid" 2>/dev/null); do
    descendants "$child"
    printf '%s\n' "$child"
  done
}

kill_tree() {
  local pid=$1 sig=$2 target
  [ -n "$pid" ] || return 0
  for target in $(descendants "$pid") "$pid"; do
    kill "-$sig" "$target" 2>/dev/null
  done
}

tree_alive() {
  local pid=$1
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null && return 0
  [ -n "$(descendants "$pid")" ]
}

cleanup() {
  [ "$CLEANED" = 1 ] && return
  CLEANED=1
  trap - INT TERM EXIT
  printf '\n'
  note "stopping…"

  kill_tree "$WEB_PID" TERM
  kill_tree "$API_PID" TERM

  # The backend drains on SIGTERM by design; give it a moment before forcing.
  for _ in $(seq 1 20); do
    tree_alive "$API_PID" || tree_alive "$WEB_PID" || break
    sleep 0.25
  done

  kill_tree "$WEB_PID" KILL
  kill_tree "$API_PID" KILL
  wait 2>/dev/null
  note "stopped."
}
trap 'cleanup; exit 130' INT
trap 'cleanup; exit 143' TERM
trap cleanup EXIT

# --- frontend dependencies -------------------------------------------------
# The backend in this workspace is deliberately dependency-free; the frontend
# is not, so only it may need installing.
if [ "$INSTALL" = 1 ] && [ ! -d "$FRONTEND/node_modules" ]; then
  note "installing frontend dependencies (first run)…"
  if [ -f "$FRONTEND/package-lock.json" ]; then
    (cd "$FRONTEND" && npm ci) || die "npm ci failed in frontend/$PROJECT"
  else
    (cd "$FRONTEND" && npm install) || die "npm install failed in frontend/$PROJECT"
  fi
fi

printf '%s%s%s  backend + frontend, wired together\n\n' "$B" "$PROJECT" "$X"

# --- backend ---------------------------------------------------------------
( cd "$BACKEND" && PORT="$API_PORT" npm start 2>&1 | sed "s/^/$(printf '%s' "${C}api ${X}")/" ) &
API_PID=$!

printf 'waiting for the api on %s' "$API_PORT"
for _ in $(seq 1 60); do
  port_busy "$API_PORT" && break
  [ "$CLEANED" = 1 ] && exit 130
  kill -0 "$API_PID" 2>/dev/null || { printf '\n'; die "the backend exited before it listened — see the api output above"; }
  printf '.'; sleep 0.5
done
printf '\n'
port_busy "$API_PORT" || die "the backend never listened on $API_PORT"

# --- frontend --------------------------------------------------------------
# Point the client at the real server. A frontend that does not read these is
# unaffected by them, so this stays correct for projects wired differently.
API_URL="http://127.0.0.1:$API_PORT"
(
  cd "$FRONTEND" \
    && VITE_API_STUB=false VITE_API_BASE_URL="$API_URL" \
       npm run dev -- --host 127.0.0.1 --port "$WEB_PORT" --strictPort 2>&1 \
    | sed "s/^/$(printf '%s' "${C}web ${X}")/"
) &
WEB_PID=$!

for _ in $(seq 1 60); do
  port_busy "$WEB_PORT" && break
  [ "$CLEANED" = 1 ] && exit 130
  kill -0 "$WEB_PID" 2>/dev/null || { printf '\n'; die "the frontend exited before it listened — see the web output above"; }
  sleep 0.5
done

printf '\n  %sapp%s  http://127.0.0.1:%s\n' "$B" "$X" "$WEB_PORT"
printf '  %sapi%s  %s\n' "$B" "$X" "$API_URL"
if grep -rqs 'VITE_API_STUB' "$FRONTEND/src" 2>/dev/null; then
  note "  the frontend is on the real api, not its stub (VITE_API_STUB=false)"
fi
printf '\n%sctrl-c to stop both%s\n\n' "$D" "$X"

wait
