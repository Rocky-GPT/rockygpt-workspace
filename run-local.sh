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
#   ./run-local.sh start --like-prod   the student UI as Vercel serves it (built, not dev mode)
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

# The Brain's Python and packages must be production's: the Dockerfile's Python and
# rockygpt-brain/requirements.lock. Packages are installed from the lock when they differ;
# a different Python stops the start, because only recreating .venv fixes it.
match_production_brain() {
  local check="$BRAIN_DIR/scripts/check_environment.py" py="$BRAIN_DIR/.venv/bin/python"
  [ -f "$check" ] || return 0   # a Brain checkout from before the lock
  "$py" "$check" >/dev/null 2>&1 && return 0
  if "$py" "$check" 2>/dev/null | grep -q '^Python '; then
    echo "  ${c_bad}✗${c_off} brain venv: $("$py" "$check" | grep '^Python ')"
    echo "    recreate it: cd rockygpt-brain && rm -rf .venv && python3.13 -m venv .venv && ../run-local.sh start"
    return 1
  fi
  echo "  ${c_dim}· brain packages differ from production; installing requirements.lock${c_off}"
  "$py" -m pip install -q --require-hashes -r "$BRAIN_DIR/requirements.lock" >"$LOGS/brain-install.log" 2>&1 \
    && "$py" "$check" >/dev/null 2>&1 && return 0
  echo "  ${c_bad}✗${c_off} brain packages still differ from production; see $LOGS/brain-install.log"
  "$py" "$check" | sed 's/^/    /'
  return 1
}

start() {
  local like_prod=0
  [ "${1:-}" = "--like-prod" ] && like_prod=1
  echo "starting RockyGPT local stack"
  match_production_brain || return 1
  # Read the Brain's secrets (its local file, else 1Password) before stopping a working stack.
  local brain_values
  brain_values="$("$BRAIN_DIR/.venv/bin/python" "$ROOT/local-env.py" --snapshot brain)" || return 1
  kill_ports

  # --- brain :8000 (read secrets once, then inherit values across reloads) ---
  if port_up 8000; then echo "  ${c_dim}· brain already up${c_off}"; else
    ( cd "$BRAIN_DIR"
      # Reload source and the prompt on edit, without watching .venv or .git.
      printf '%s' "$brain_values" | PYTHONPATH=src nohup .venv/bin/python -c '
import json, os, sys
os.environ.update(json.load(sys.stdin))
os.environ.pop("SERVICE_TOKEN", None)
os.environ.pop("STAGING_SERVICE_TOKEN", None)
os.environ.pop("OPENAI_CHAT_MODEL", None)
os.environ.pop("BRAIN_EXPECTED_CONFIG_HASH", None)
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.execv(sys.executable, [sys.executable, "-m", "uvicorn", *sys.argv[1:]])
' \
        rockygpt_brain.api.app:app --host 127.0.0.1 --port 8000 \
        --reload --reload-dir src --reload-include '*.md' \
        >"$LOGS/brain.log" 2>&1 & echo $! >"$PIDS/brain.pid" )
    wait_for 8000 brain 60 || return 1
  fi

  # --- ui :3000 (local Brain is bound to loopback without a staging token) ---
  # --like-prod builds and serves it the way Vercel does: production React, strict security
  # headers, the splash and saved chats. Without it, `next dev` reloads on every edit.
  if port_up 3000; then echo "  ${c_dim}· ui already up${c_off}"; else
    if [ "$like_prod" = 1 ]; then
      echo "  ${c_dim}· building the student ui as production does${c_off}"
      ( use_node22; cd "$UI_DIR" && BRAIN_URL=http://127.0.0.1:8000 npm run build >"$LOGS/ui-build.log" 2>&1 ) \
        || { echo "  ${c_bad}✗${c_off} ui build failed — see $LOGS/ui-build.log"; return 1; }
      ( use_node22; cd "$UI_DIR"
        export BRAIN_URL=http://127.0.0.1:8000 NODE_ENV=production
        unset SERVICE_TOKEN STAGING_SERVICE_TOKEN
        nohup "$UI_DIR/node_modules/.bin/next" start -p 3000 -H 127.0.0.1 >"$LOGS/ui.log" 2>&1 & echo $! >"$PIDS/ui.pid" )
    else
      ( use_node22; cd "$UI_DIR"
        export BRAIN_URL=http://127.0.0.1:8000
        unset SERVICE_TOKEN STAGING_SERVICE_TOKEN
        nohup npm run dev >"$LOGS/ui.log" 2>&1 & echo $! >"$PIDS/ui.pid" )
    fi
    wait_for 3000 ui 90 || return 1
  fi

  # --- dev ui :3100 (same local HTTP contract as the UI) ---
  if port_up 3100; then echo "  ${c_dim}· dev ui already up${c_off}"; else
    if [ -d "$DEV_DIR/node_modules" ]; then
      ( use_node22; cd "$DEV_DIR"
        export BRAIN_URL=http://127.0.0.1:8000
        unset SERVICE_TOKEN STAGING_SERVICE_TOKEN
        nohup npm run dev >"$LOGS/dev.log" 2>&1 & echo $! >"$PIDS/dev.pid" )
      wait_for 3100 dev 90 || return 1
    else
      echo "  ${c_dim}· dev ui skipped (run npm install in rockygpt-dev)${c_off}"
    fi
  fi

  echo
  echo "  ${c_ok}student  http://localhost:3000${c_off}$([ "$like_prod" = 1 ] && echo "  (production build)")"
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
preview() { start "${1:-}" && tail -f "$LOGS/ui.log"; }

case "${1:-start}" in
  start)   start "${2:-}" ;;
  stop)    stop ;;
  restart) start "${2:-}" ;;
  status)  status ;;
  logs)    logs "${2:-brain}" ;;
  preview) preview "${2:-}" ;;
  *) echo "usage: $0 {start|restart [--like-prod]|stop|status|logs [brain|ui|dev]|preview}"; exit 1 ;;
esac
