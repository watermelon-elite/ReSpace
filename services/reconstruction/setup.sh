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

if [[ "$(uname -s)" == Darwin && "$(uname -m)" == arm64 && ! -x .tools/openmvs/RefineMesh ]]; then
  mkdir -p .tools
  curl -fL --retry 3 https://github.com/cdcseacave/openMVS/releases/download/v2.4.0/OpenMVS_macOS_arm64.zip -o .tools/openmvs.zip
  echo '3d4c616c97031b1ab6e2eecb0ddd5614fb99513c0782a32c9350602faf38799b  .tools/openmvs.zip' | shasum -a 256 -c -
  mkdir -p .tools/openmvs
  unzip -q -o .tools/openmvs.zip -d .tools/openmvs
elif [[ ! -x .tools/openmvs/RefineMesh && -z "${RESPACE_OPENMVS_BIN:-}" ]]; then
  echo 'Install OpenMVS and set RESPACE_OPENMVS_BIN to its executable directory.' >&2
fi

.venv/bin/python - <<'PY'
import os
from pathlib import Path
import secrets
env = Path('.env')
if not env.exists():
    env.write_text('RESPACE_RECONSTRUCTION_TOKEN=' + secrets.token_hex(32) + '\nRESPACE_RECONSTRUCTION_DATA=./data\n')
os.chmod(env, 0o600)
PY
echo 'Ready. Run ./run.sh; copy the token from .env into Configuration/Local.xcconfig.'
