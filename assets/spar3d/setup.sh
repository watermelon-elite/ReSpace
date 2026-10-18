#!/usr/bin/env bash
# Build the SPAR3D image-to-mesh runtime on Apple Silicon. Idempotent.
#
# Code lives in the repository; the runtime, weights and generated meshes live
# in a lab directory outside it ($SPAR3D_LAB, default ~/spar3d-lab) because they
# are large and reproducible. Never place the lab under /tmp: a reboot clears it.
#
# Five upstream packaging problems are worked around here, each marked WORKAROUND.
set -euo pipefail

LAB="${SPAR3D_LAB:-$HOME/spar3d-lab}"
PY="$LAB/.venv/bin/python"

TORCH_VERSION="${TORCH_VERSION:-2.14.1}"
TORCHVISION_VERSION="${TORCHVISION_VERSION:-0.29.1}"

mkdir -p "$LAB"/{images,out}
cd "$LAB"

echo "== 1/7 source =="
[ -d "$LAB/repo/.git" ] || git clone --depth 1 \
  https://github.com/Stability-AI/stable-point-aware-3d.git "$LAB/repo"

echo "== 2/7 interpreter =="
# SPAR3D pins numpy 1.26 and transformers 4.42, which have no builds for 3.13+.
[ -x "$PY" ] || uv venv --python 3.11 "$LAB/.venv"
"$PY" -m ensurepip --upgrade >/dev/null
# WORKAROUND 1: setuptools 81+ removed pkg_resources, which AlphaCLIP's setup.py
# still imports. Pin below that line, and install AlphaCLIP with real pip --
# uv re-resolves build dependencies and silently upgrades setuptools back.
"$PY" -m pip install -q "setuptools==69.5.1" wheel

echo "== 3/7 openmp =="
# WORKAROUND 2: uv_unwrapper compiles with -fopenmp; Apple clang ships no libomp.
brew list libomp >/dev/null 2>&1 || brew install libomp

echo "== 4/7 torch ${TORCH_VERSION} =="
# WORKAROUND 3: do not downgrade torch to chase the MPS deadlock (see README).
# torch <=2.6 ships a c10 header specializing std::is_arithmetic, which current
# Apple clang rejects, so neither native extension can compile against it.
uv pip install --python "$PY" -q \
  "torch==${TORCH_VERSION}" "torchvision==${TORCHVISION_VERSION}"

echo "== 5/7 core requirements =="
# WORKAROUND 4: requirements.txt lists ./texture_baker/ and ./uv_unwrapper/ by
# relative path, so it resolves only from inside repo/. Both import torch in
# setup.py, so they need --no-build-isolation and are installed in step 7.
grep -v -E "^\./(texture_baker|uv_unwrapper)/|AlphaCLIP" \
  "$LAB/repo/requirements.txt" > "$LAB/.core-requirements.txt"
uv pip install --python "$PY" -q -r "$LAB/.core-requirements.txt"
"$PY" -m pip install -q "setuptools==69.5.1"
"$PY" -m pip install -q --no-build-isolation --no-deps \
  "git+https://github.com/SunzeY/AlphaCLIP.git"

echo "== 6/7 flet pin =="
# WORKAROUND 5: transparent-background imports a GUI module at package import,
# and current flet renamed the controls it expects. 0.24.1 still has them and
# satisfies the declared >=0.23.1 floor.
"$PY" -m pip install -q "flet==0.24.1"

echo "== 7/7 native extensions =="
export USE_METAL=1 USE_CUDA=0
export CPATH="/opt/homebrew/opt/libomp/include${CPATH:+:$CPATH}"
export LIBRARY_PATH="/opt/homebrew/opt/libomp/lib${LIBRARY_PATH:+:$LIBRARY_PATH}"
(cd "$LAB/repo" && "$PY" -m pip install -q --no-build-isolation --no-deps \
  ./texture_baker/ ./uv_unwrapper/)

echo
PYTHONPATH="$LAB/repo" NO_ALBUMENTATIONS_UPDATE=1 "$PY" - <<'EOF'
import torch, texture_baker, uv_unwrapper, alpha_clip, trimesh  # noqa: F401
from spar3d.system import SPAR3D  # noqa: F401
print(f"OK  torch {torch.__version__}  mps={torch.backends.mps.is_available()}")
EOF

echo "== preparation env =="
# A second venv, because the two halves of the pipeline disagree about trimesh:
# the SPAR3D extensions are built against 4.4.1 and assets/requirements.txt
# pins 5.1.1 for prepare.py. Installing either into the other's venv breaks it.
PREP="$LAB/.venv-prepare"
[ -x "$PREP/bin/python" ] || uv venv --python 3.11 -q "$PREP"
VIRTUAL_ENV="$PREP" uv pip install -q -r "$(dirname "$0")/../requirements.txt"
"$PREP/bin/python" - <<'EOF'
import trimesh, PIL  # noqa: F401
from pxr import Usd
print(f"OK  trimesh {trimesh.__version__}  usd {'.'.join(map(str, Usd.GetVersion()))}")
EOF

echo "lab ready at $LAB"
