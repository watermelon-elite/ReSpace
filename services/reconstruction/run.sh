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
# This branch always uses direct Astra, even with a retained older .env file.
export RESPACE_PIPELINE=astra
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo 'Set OPENAI_API_KEY in the private .env before starting the Astra service.' >&2
  exit 1
fi
# One process owns the disk queue. Do not add --reload or --workers.
exec .venv/bin/python -m uvicorn respace_reconstruction.app:create_app --factory --host "${RESPACE_BIND_HOST:-0.0.0.0}" --port "${RESPACE_PORT:-8008}"
