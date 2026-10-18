#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
bash setup.sh
bash setup-segmentation.sh
bash setup-detection.sh
.venv/bin/python - <<'PY'
from respace_reconstruction.instances import SAM2Masks
from respace_reconstruction.detection import GroundingDINO
sam=SAM2Masks()
del sam
detector=GroundingDINO()
print('Walkthrough geometry, segmentation and detection dependencies verified. Gemini is not required.')
PY
