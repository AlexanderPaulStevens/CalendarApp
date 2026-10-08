#!/usr/bin/env bash
# Start or stop the API (:8000) and frontend (:5173).
# Usage (from repo root):
#   ./dev.sh up
#   ./dev.sh down

set -euo pipefail

# Absolute Windows installs (Git Bash uses /c, WSL uses /mnt/c).
if [[ -d /c/Users/u0138175 ]]; then
  WIN_ROOT="/c"
elif [[ -d /mnt/c/Users/u0138175 ]]; then
  WIN_ROOT="/mnt/c"
else
  echo "Windows user dir not mounted" >&2
  exit 1
fi
UV="$WIN_ROOT/Users/u0138175/.local/bin/uv.exe"
NPM="$WIN_ROOT/Program Files/nodejs/npm.cmd"

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

if [[ ! -f "$UV" ]]; then
  echo "uv not found at $UV" >&2
  exit 1
fi
if [[ ! -f "$NPM" ]]; then
  echo "npm not found at $NPM" >&2
  exit 1
fi

echo "API  http://127.0.0.1:8000"
echo "UI   http://127.0.0.1:5173"

cleanup() {
  stop_servers
}
trap cleanup EXIT INT TERM

(
  cd "$BACKEND"
  "$UV" run python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
) &

# Health-check via Windows Python so WSL curl cannot miss Windows localhost.
api_ready() {
  (
    cd "$BACKEND"
    "$UV" run python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=1)"
  ) >/dev/null 2>&1
}

for _ in $(seq 1 60); do
  if api_ready; then
    echo "API ready"
    break
  fi
  sleep 0.5
done

if [[ ! -d "$FRONTEND/node_modules" ]]; then
  echo "Installing frontend dependencies..."
  "$NPM" install --prefix "$FRONTEND"
fi

"$NPM" run dev --prefix "$FRONTEND"
