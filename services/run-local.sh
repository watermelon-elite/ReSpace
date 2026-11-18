#!/bin/bash
# Start both halves of the real scan/design/image pipeline. No sample imports.
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:---check}" in
  --check|--live) mode="${1:---check}" ;;
  *) echo 'Usage: bash services/run-local.sh [--check|--live]' >&2; exit 2 ;;
esac
set -a
[[ ! -f .env ]] || source .env
[[ ! -f services/reconstruction/.env ]] || source services/reconstruction/.env
set +a
planning_python="${RESPACE_PLANNING_PYTHON:-.local/venv/bin/python}"
reconstruction_python="${RESPACE_RECONSTRUCTION_PYTHON:-services/reconstruction/.venv/bin/python}"
missing=0
for executable in "$planning_python" "$reconstruction_python"; do
  if [[ ! -x "$executable" ]]; then echo "Missing Python environment: $executable" >&2; missing=1; fi
done
for name in SERPAPI_API_KEY GEMINI_PLANNING_MODEL GEMINI_EXTRACTION_MODEL GEMINI_SPATIAL_MODEL OPENAI_API_KEY RESPACE_RECONSTRUCTION_TOKEN; do
  if [[ -z "${!name:-}" ]]; then echo "Missing configuration: $name" >&2; missing=1; fi
done
if [[ -z "${GEMINI_API_KEY:-${GOOGLE_API_KEY:-}}" ]]; then echo 'Missing configuration: GEMINI_API_KEY or GOOGLE_API_KEY' >&2; missing=1; fi
if [[ ! -f services/scan-to-threejs/node_modules/typescript/bin/tsc || ! -d services/scan-to-threejs/worker/.browsers ]]; then
  echo 'Missing modeling runtime. Run services/reconstruction/setup.sh with Python 3.12.' >&2; missing=1
fi
[[ "$missing" == 0 ]] || exit 1
"$planning_python" -c 'import respace.api, playwright' || exit 1
"$reconstruction_python" -c 'import sys; assert (3,11) <= sys.version_info[:2] < (3,13); import respace_reconstruction.app, open3d, pxr' || exit 1
echo 'Planning and reconstruction configuration is ready. No provider calls made.'
[[ "$mode" == --live ]] || exit 0
export RESPACE_PIPELINE=threejs
# Anchor a relative reconstruction data directory to its own service, as run.sh does.
case "${RESPACE_RECONSTRUCTION_DATA:-./data}" in
  /*) ;;
  *) export RESPACE_RECONSTRUCTION_DATA="$PWD/services/reconstruction/${RESPACE_RECONSTRUCTION_DATA:-./data}" ;;
esac
pids=()
cleanup() { for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done; }
trap cleanup EXIT
trap 'exit 130' INT TERM
"$planning_python" -m respace.local --live-providers --host 0.0.0.0 --port 8000 &
pids+=("$!")
"$reconstruction_python" -m uvicorn respace_reconstruction.app:create_app --factory --host 0.0.0.0 --port 8008 &
pids+=("$!")
echo 'Planning :8000 / reconstruction :8008. Keep this Mac awake; Ctrl-C stops both.'
while kill -0 "${pids[0]}" 2>/dev/null && kill -0 "${pids[1]}" 2>/dev/null; do sleep 1; done
echo 'A service stopped. Stopping the other service; saved work is retained.' >&2
exit 1
