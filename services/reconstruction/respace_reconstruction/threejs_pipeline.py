"""Fresh native capture -> pinned authoring workflow -> reviewed mobile scene."""
import json
import os
from pathlib import Path
import shutil

from .models import NativeManifest, parse_manifest
from .store import atomic_json, digest, generation_working_directory
from .astra_spending import Spending
from .threejs_tools import ROOT, source_module


def native_source(folder,manifest,output):
    output.mkdir(parents=True,exist_ok=True)
    declared=set()
    for item in manifest.files:
        source=folder/'inputs'/item.filename;target=output/item.relative_path
        if not source.is_file() or source.is_symlink() or source.stat().st_size!=item.byte_length or digest(source)!=item.sha256:raise ValueError('Native scan input failed integrity verification')
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists() and digest(target)!=item.sha256:raise ValueError('Retained native input changed')
        if not target.exists():os.link(source,target)
        declared.add(target.resolve())
    if declared!={p.resolve() for p in output.rglob('*') if p.is_file()}:raise ValueError('Native source has undeclared files')
    data=json.loads((output/'manifest.json').read_text())
    if data.get('format')!='house-capture/5' or data.get('integrityFile')!='integrity.json':raise ValueError('Fresh native source requires its sealed house-capture/5 manifest')
    # Original upstream validation checks the sealed inventory, poses, calibration,
    # photos, room index and layout; never convert back into the historical format.
    source_module().validate_bundle(output,None)
    return output


def process_threejs(folder,revision,generation_id=None):
    from .pipeline import progress
    from .threejs_agent import author
    folder=folder.resolve();manifest=parse_manifest((folder/'manifest.json').read_text())
    if not isinstance(manifest,NativeManifest):raise ValueError('This worker requires a fresh scan captured with Scan to Three.js. Capture a new Room to continue.')
    work=generation_working_directory(folder,generation_id)/'threejs';work.mkdir(parents=True,exist_ok=True)
    progress('preparing_scan')
    source=native_source(folder,manifest,work/'source')
    project=work/'project'
    if not project.exists():source_module().prepare(source,project,room_id='room')
    # Immutable measured source hash is also the restart/retry binding.
    binding=digest(folder/'manifest.json');record=work/'input-binding.json'
    if record.exists() and json.loads(record.read_text())['sha256']!=binding:raise ValueError('Authored project belongs to different source bytes')
    atomic_json(record,{'sha256':binding})
    if not (ROOT/'node_modules/typescript/bin/tsc').exists() or not (ROOT/'worker/node_modules/playwright').exists():raise RuntimeError('Install the Three.js worker runtime with services/reconstruction/setup.sh')
    if not (project/'node_modules').exists():(project/'node_modules').symlink_to(ROOT/'node_modules',target_is_directory=True)
    measurements=json.loads((project/'data/demos/room.json').read_text())
    spending=Spending(work/'spending.json')
    finished=author(project,work,spending,measurements,manifest.capture_id,revision,progress)
    progress('publishing')
    output=folder/'results'/f'{revision}.building'
    output.parent.mkdir(exist_ok=True)
    if output.exists():shutil.rmtree(output)
    shutil.copytree(finished['output'],output)
    result=dict(finished['result'],revision=revision)
    scene=json.loads((output/'scene.json').read_text());scene['reconstruction_revision']=revision;atomic_json(output/'scene.json',scene)
    for asset in result['assets']:
        path=output/asset['filename'];asset.update(byte_length=path.stat().st_size,sha256=digest(path))
    atomic_json(output/'completion.json',result)
    committed=folder/'results'/str(revision)
    if committed.exists():raise ValueError('Refusing to replace a published immutable revision')
    output.rename(committed)
    return result
