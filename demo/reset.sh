#!/usr/bin/env bash
# One-command demo reset. Wipes imports, candidates, approvals and conversations.
set -e
cd "$(dirname "$0")/.."
if curl -sf -XPOST localhost:8420/api/reset -d '{}' >/dev/null 2>&1; then
  echo "reset via running server"
else
  rm -f var/resipi.db && echo "reset by removing var/resipi.db"
fi
