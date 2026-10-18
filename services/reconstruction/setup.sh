#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -x .venv/bin/python ]]; then
  task_python="${PYTHON_BIN:-}"
  if [[ -z "$task_python" ]]; then
    for candidate in python3.12 python3.11 python3; do
      if command -v "$candidate" >/dev/null && "$candidate" -c 'import sys; assert (3,11) <= sys.version_info[:2] < (3,13)' 2>/dev/null; then
        task_python="$(command -v "$candidate")"
        break
      fi
    done
  fi
  if [[ -z "$task_python" ]]; then
    echo 'Install Python 3.11/3.12 or set PYTHON_BIN to that executable.' >&2
    exit 1
  fi
  "$task_python" -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.lock -e '.[test]'

.venv/bin/python - <<'PY'
import os
from pathlib import Path
import secrets
env = Path('.env')
if not env.exists():
    env.write_text('RESPACE_RECONSTRUCTION_TOKEN=' + secrets.token_hex(32) + '\nRESPACE_RECONSTRUCTION_DATA=./data\nRESPACE_PIPELINE=astra\nOPENAI_API_KEY=\n')
os.chmod(env, 0o600)
PY
echo 'Set OPENAI_API_KEY in .env, run ./run.sh, and set the Mac endpoint/token in Configuration/Local.xcconfig.'
