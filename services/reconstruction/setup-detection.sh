#!/usr/bin/env bash
# Public detector weights; inference remains local and source captures immutable.
set -euo pipefail
cd "$(dirname "$0")"
[[ -x .venv/bin/python ]] || { echo 'Run setup.sh first.' >&2; exit 1; }
.venv/bin/python -m pip install 'torch==2.5.1' 'torchvision==0.20.1' \
  'transformers==4.46.3' 'huggingface-hub==0.26.5' 'safetensors==0.4.5'
.venv/bin/python - <<'PY'
import hashlib
import json
import os
from pathlib import Path
import urllib.request

root=Path('.tools/grounding-dino')
root.mkdir(parents=True,exist_ok=True)
revision='a2bb814dd30d776dcf7e30523b00659f4f141c71'
files=['config.json','preprocessor_config.json','tokenizer.json','tokenizer_config.json',
       'special_tokens_map.json','added_tokens.json','vocab.txt','model.safetensors','README.md']
hashes={}
for name in files:
    path=root/name
    if not path.is_file():
        print('Downloading pinned '+name,flush=True)
        temporary=path.with_suffix('.download')
        url=f'https://huggingface.co/IDEA-Research/grounding-dino-tiny/resolve/{revision}/{name}?download=true'
        with urllib.request.urlopen(url,timeout=120) as response,temporary.open('wb') as stream:
            while block:=response.read(1024*1024): stream.write(block)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    with path.open('rb') as stream: hashes[name]=hashlib.file_digest(stream,'sha256').hexdigest()
if hashes['model.safetensors'] != '1a2412ef99bd74bcd3c2a246fa1e48581f8889a1300c9051974741314fc042f3':
    raise SystemExit('Grounding DINO checkpoint checksum mismatch')
(root/'recipe.json').write_text(json.dumps({'model':'IDEA-Research/grounding-dino-tiny',
    'revision':revision,'file_sha256':hashes,'transformers':'4.46.3'},sort_keys=True))
print('Grounding DINO installed; no inference or room publication performed.')
PY
