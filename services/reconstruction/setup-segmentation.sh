#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[[ -x .venv/bin/python ]] || { echo 'Run setup.sh first.' >&2; exit 1; }
if [[ "$(uname -s)" == Linux ]]; then
  .venv/bin/python -m pip install 'torch==2.5.1' 'torchvision==0.20.1' --index-url https://download.pytorch.org/whl/cpu
else
  .venv/bin/python -m pip install 'torch==2.5.1' 'torchvision==0.20.1'
fi
SAM2_BUILD_CUDA=0 .venv/bin/python -m pip install --no-build-isolation \
  'git+https://github.com/facebookresearch/sam2.git@2b90b9f5ceec907a1c18123530e92e794ad901a4'
mkdir -p .tools/sam2
task_checkpoint='.tools/sam2/sam2.1_hiera_tiny.pt'
if [[ ! -f "$task_checkpoint" ]]; then
  curl --fail --location --retry 2 \
    'https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_tiny.pt' \
    --output "$task_checkpoint.download"
  .venv/bin/python - "$task_checkpoint.download" <<'PY'
import hashlib
from pathlib import Path
import sys
p=Path(sys.argv[1])
expected='7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69'
with p.open('rb') as f:
    actual=hashlib.file_digest(f,'sha256').hexdigest()
if actual != expected:
    p.unlink()
    raise SystemExit('Checkpoint checksum differs from the verified official download')
PY
  mv "$task_checkpoint.download" "$task_checkpoint"
fi
.venv/bin/python - "$task_checkpoint" <<'PY'
from pathlib import Path
import sys
from respace_reconstruction.store import digest
assert digest(Path(sys.argv[1])) == '7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69', 'Checkpoint integrity failure'
print('SAM 2.1 tiny ready. CPU is the verified baseline; MPS is experimental.')
PY
