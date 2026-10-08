#!/usr/bin/env bash
# Convenience wrapper - run from the repo root:
#   ./dev.sh up
#   ./dev.sh down
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/backend/scripts/dev.sh" "$@"
