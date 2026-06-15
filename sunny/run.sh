#!/usr/bin/env bash
# Load .env (if present) and start Sunny.
# Usage: ./run.sh [chat|serve|ping]   (defaults to chat)
set -euo pipefail
cd "$(dirname "$0")"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

exec python -m sunny.main "${1:-chat}"
