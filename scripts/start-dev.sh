#!/usr/bin/env bash
# LitPilot 本地开发：后端 8000 + 前端 3002
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

start_backend() {
  cd "$ROOT/backend"
  if [[ ! -d .venv ]]; then
    python3 -m venv .venv
    .venv/bin/pip install -q -r requirements.txt
  fi
  export PYTHONPATH="$ROOT/backend"
  export LITPILOT_DATA_DIR="${LITPILOT_DATA_DIR:-$ROOT/data}"
  BACKEND_PORT="${BACKEND_PORT:-8001}"
  exec .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT"
}

start_frontend() {
  cd "$ROOT/frontend"
  if [[ ! -d node_modules ]]; then
    pnpm install
  fi
  exec pnpm dev
}

case "${1:-all}" in
  backend) start_backend ;;
  frontend) start_frontend ;;
  *)
    echo "LitPilot: backend http://127.0.0.1:${BACKEND_PORT:-8001}  |  frontend http://127.0.0.1:3002"
    trap 'kill 0' EXIT
    start_backend &
    sleep 1
    start_frontend &
    wait
    ;;
esac
