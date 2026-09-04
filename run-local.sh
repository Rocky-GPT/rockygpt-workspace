#!/usr/bin/env bash
# RockyGPT local stack.
#
#   Student UI  :3000  ->  brain :8000  ->  Neon
#   Dev UI      :3100  ->  brain :8000  ->  Neon
#
# Two products, one backend. The dev app is a separate interface, not a mode of
# the student one, so it is a separate process here too.
#
#   ./run-local.sh start     start everything, wait until healthy
#   ./run-local.sh stop      stop everything
#   ./run-local.sh restart
#   ./run-local.sh status    show what is up
#   ./run-local.sh logs [brain|ui|dev]    tail a log
#
set -uo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
ROOT="$(cd -P "$(dirname "$SOURCE")" && pwd)"
LOGS="$ROOT/.local-logs"
PIDS="$LOGS/pids"
mkdir -p "$LOGS" "$PIDS"

BRAIN_DIR="$ROOT/rockygpt-brain"
UI_DIR="$ROOT/rockygpt-ui"
DEV_DIR="$ROOT/rockygpt-dev"

c_ok=$'\033[32m'; c_bad=$'\033[31m'; c_dim=$'\033[2m'; c_off=$'\033[0m'

use_node22() {
  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
  # shellcheck disable=SC1091
  [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" && nvm use --delete-prefix 22 --silent
}

port_up() { nc -z -G 1 127.0.0.1 "$1" >/dev/null 2>&1; }

wait_for() { # wait_for <port> <label> <seconds>
  local port=$1 label=$2 max=${3:-60} i=0
  while [ $i -lt "$max" ]; do
    port_up "$port" && { echo "  ${c_ok}✓${c_off} $label (:$port)"; return 0; }
    sleep 1; i=$((i+1))
  done
  echo "  ${c_bad}✗${c_off} $label (:$port) did not come up — see $LOGS/$label.log"
  return 1
}

kill_ports() {
  local pids
  pids="$(lsof -ti:3000,3100,8000 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    echo "  ${c_dim}· clearing ports 3000, 3100 & 8000${c_off}"
    echo "$pids" | xargs kill -9 2>/dev/null || true
    sleep 0.5
  fi
}

start() {
  echo "starting RockyGPT local stack"
  kill_ports
  local shared_staging_token
  shared_staging_token="$("$BRAIN_DIR/.venv/bin/python" -c '
import os, sys
from dotenv import dotenv_values
print(dotenv_values(sys.argv[1]).get("STAGING_SERVICE_TOKEN", os.getenv("STAGING_SERVICE_TOKEN", "")) or "")
' "$BRAIN_DIR/.env")"

  # --- brain :8000 (reads its own .env) ---
  if port_up 8000; then echo "  ${c_dim}· brain already up${c_off}"; else
    ( cd "$BRAIN_DIR"
      set -a; . ./.env; set +a
      # Reload source and the prompt on edit, without watching .venv or .git.
      PYTHONPATH=src nohup .venv/bin/python -m uvicorn \
        rockygpt_brain.api.app:app --host 127.0.0.1 --port 8000 \
        --reload --reload-dir src --reload-include '*.md' \
        >"$LOGS/brain.log" 2>&1 & echo $! >"$PIDS/brain.pid" )
    wait_for 8000 brain 60 || return 1
  fi

  # --- ui :3000 (shares the optional environment token with the brain) ---
  if port_up 3000; then echo "  ${c_dim}· ui already up${c_off}"; else
    ( use_node22; cd "$UI_DIR"
      export BRAIN_URL=http://127.0.0.1:8000
      export STAGING_SERVICE_TOKEN="$shared_staging_token"
      nohup npm run dev >"$LOGS/ui.log" 2>&1 & echo $! >"$PIDS/ui.pid" )
    wait_for 3000 ui 90 || return 1
  fi

  # --- dev ui :3100 (same HTTP contract and environment token as the UI) ---
  if port_up 3100; then echo "  ${c_dim}· dev ui already up${c_off}"; else
    if [ -d "$DEV_DIR/node_modules" ]; then
      ( use_node22; cd "$DEV_DIR"
        export BRAIN_URL=http://127.0.0.1:8000
        export STAGING_SERVICE_TOKEN="$shared_staging_token"
        nohup npm run dev >"$LOGS/dev.log" 2>&1 & echo $! >"$PIDS/dev.pid" )
      wait_for 3100 dev 90 || return 1
    else
      echo "  ${c_dim}· dev ui skipped (run npm install in rockygpt-dev)${c_off}"
    fi
  fi

  echo
  echo "  ${c_ok}student  http://localhost:3000${c_off}"
  echo "  ${c_ok}dev      http://localhost:3100${c_off}"
  echo "  ${c_dim}logs: ./run-local.sh logs brain|ui|dev${c_off}"
}

stop() {
  echo "stopping RockyGPT local stack"
  pkill -f "uvicorn rockygpt_brain.api.app:app" 2>/dev/null && echo "  · brain stopped"
  pkill -f "$UI_DIR/node_modules/.bin/next"     2>/dev/null && echo "  · ui stopped"
  pkill -f "$DEV_DIR/node_modules/.bin/next"    2>/dev/null && echo "  · dev ui stopped"
  rm -f "$PIDS"/*.pid
  echo "done"
}

status() {
  printf "%-10s %-6s %s\n" SERVICE PORT STATE
  for row in "brain 8000" "ui 3000" "dev 3100"; do
    set -- $row
    if port_up "$2"; then printf "%-10s %-6s ${c_ok}up${c_off}\n" "$1" "$2"
    else printf "%-10s %-6s ${c_bad}down${c_off}\n" "$1" "$2"; fi
  done
  echo
  for u in "http://127.0.0.1:8000/readiness brain" "http://127.0.0.1:3000/api/readiness ui" "http://127.0.0.1:3100/api/health dev"; do
    set -- $u
    code=$(curl -s -m 5 -o /dev/null -w '%{http_code}' "$1" 2>/dev/null)
    printf "  %-6s readiness -> %s\n" "$2" "${code:-no response}"
  done
}

logs() { tail -f "$LOGS/${1:-brain}.log"; }

# Used by .claude/launch.json. Brings the stack up (skipping whatever is
# already up), then stays in the foreground streaming the UI log, so the
# preview pane has a live process to own and its logs to show.
preview() { start && tail -f "$LOGS/ui.log"; }

case "${1:-start}" in
  start)   start ;;
  stop)    stop ;;
  restart) stop; sleep 2; start ;;
  status)  status ;;
  logs)    logs "${2:-brain}" ;;
  preview) preview ;;
  *) echo "usage: $0 {start|stop|restart|status|logs [brain|ui]|preview}"; exit 1 ;;
esac
