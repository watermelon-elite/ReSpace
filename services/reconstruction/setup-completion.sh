#!/usr/bin/env bash
# Isolated CPU completion experiment; leaves the working SAM/Open3D environment intact.
set -euo pipefail
cd "$(dirname "$0")"
task_root="$PWD/.tools/triposr"
mkdir -p "$task_root"
[[ -x .venv/bin/python ]] || { echo 'Run setup.sh first.' >&2; exit 1; }
[[ -x "$task_root/env/bin/python" ]] || .venv/bin/python -m venv "$task_root/env"
if [[ ! -d "$task_root/source/.git" ]]; then
  git clone --filter=blob:none --no-checkout https://github.com/VAST-AI-Research/TripoSR.git "$task_root/source"
fi
git -C "$task_root/source" checkout --detach 107cefdc244c39106fa830359024f6a2f1c78871
"$task_root/env/bin/python" -m pip install \
  'torch==2.5.1' 'numpy==1.26.4' 'Pillow==10.1.0' 'omegaconf==2.3.0' \
  'einops==0.7.0' 'transformers==4.46.3' 'trimesh==4.0.5' 'rembg==2.0.59' \
  'onnxruntime==1.20.1' 'imageio==2.36.0' 'huggingface-hub==0.26.5' \
  'scikit-build-core==1.1.1' 'pybind11==2.13.6' cmake ninja
"$task_root/env/bin/python" -m pip install --no-build-isolation \
  'git+https://github.com/tatsy/torchmcubes.git@879926d0ef58e6ce0ac2630fdecb5e53af7ed3ff'
HF_HOME="$task_root/cache" "$task_root/env/bin/python" - "$task_root" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.request
from huggingface_hub import hf_hub_download

root=Path(sys.argv[1])
weights=root/'weights'
weights.mkdir(exist_ok=True)
revision='5b521936b01fbe1890f6f9baed0254ab6351c04a'
expected='429e2c6b22a0923967459de24d67f05962b235f79cde6b032aa7ed2ffcd970ee'
for name in ['config.yaml','model.ckpt']:
    destination=weights/name
    if not destination.exists():
        temporary=destination.with_suffix('.download')
        url=f'https://huggingface.co/stabilityai/TripoSR/resolve/{revision}/{name}?download=true'
        print('Downloading pinned '+name,flush=True)
        with urllib.request.urlopen(url,timeout=120) as response, temporary.open('wb') as stream:
            while block:=response.read(1024*1024): stream.write(block)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(destination)
with (weights/'model.ckpt').open('rb') as stream:
    actual=hashlib.file_digest(stream,'sha256').hexdigest()
if actual != expected:
    raise SystemExit('TripoSR model checksum mismatch')
config=(weights/'config.yaml').read_bytes()
assert hashlib.sha1(b'blob '+str(len(config)).encode()+b'\0'+config).hexdigest()=='fa3e59a701f02679bd1dca02fbaf97306174d291', 'Model config mismatch'
dino=Path(hf_hub_download('facebook/dino-vitb16','config.json',revision='f205d5d8e640a89a2b8ef0369670dfc37cc07fc2'))
recipe={'source_commit':'107cefdc244c39106fa830359024f6a2f1c78871','model_revision':revision,
        'model_sha256':actual,'dino_config_revision':dino.parent.name,
        'dino_config_sha256':hashlib.sha256(dino.read_bytes()).hexdigest(),
        'torchmcubes_commit':'879926d0ef58e6ce0ac2630fdecb5e53af7ed3ff'}
(root/'recipe.json').write_text(json.dumps(recipe,sort_keys=True))
print('TripoSR CPU candidate stage installed. No model inference or room publication performed.')
PY
