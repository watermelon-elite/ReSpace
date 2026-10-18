#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python || ! -f .env ]]; then
  echo 'Run ./setup.sh first.' >&2
  exit 1
fi
set -a
source .env
set +a
# One process owns the disk queue. Do not add --reload or --workers.
exec .venv/bin/python -m uvicorn respace_reconstruction.app:create_app --factory --host "${RESPACE_BIND_HOST:-0.0.0.0}" --port "${RESPACE_PORT:-8008}"
