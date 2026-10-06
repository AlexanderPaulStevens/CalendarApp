#!/usr/bin/env bash
# Start or stop the API (:8000) and frontend (:5173).
# Usage (from repo root or backend/):
#   ./backend/scripts/dev.sh up
#   ./backend/scripts/dev.sh down

set -euo pipefail

ACTION="${1:-}"
if [[ "$ACTION" != "up" && "$ACTION" != "down" ]]; then
  echo "Usage: $0 {up|down}" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND="$(cd "$BACKEND/../frontend" && pwd)"

stop_servers() {
  pkill -f "uvicorn app.main:app" 2>/dev/null || true
  pkill -f "vite" 2>/dev/null || true
}

if [[ "$ACTION" == "down" ]]; then
  stop_servers
  echo "Stopped API and frontend"
  exit 0
fi

command -v uv >/dev/null || { echo "uv not found. Install: https://docs.astral.sh/uv/" >&2; exit 1; }
command -v npm >/dev/null || { echo "npm not found. Install Node.js." >&2; exit 1; }

echo "API  http://127.0.0.1:8000"
echo "UI   http://127.0.0.1:5173"

cleanup() {
  stop_servers
}
trap cleanup EXIT INT TERM

(
  cd "$BACKEND"
  uv run python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
) &

for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:8000/api/health" >/dev/null 2>&1; then
    echo "API ready"
    break
  fi
  sleep 0.5
done

if [[ ! -d "$FRONTEND/node_modules" ]]; then
  echo "Installing frontend dependencies..."
  npm install --prefix "$FRONTEND"
fi

npm run dev --prefix "$FRONTEND"
