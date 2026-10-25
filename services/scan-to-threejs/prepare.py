#!/usr/bin/env python3
"""Prepare a private Scan to Three.js authoring project from a saved scan.

Uses the pinned upstream converters/viewer/skill unchanged. Fresh ReSpace scans
already contain house-capture/5; historical conversion is explicit. It does not model the room, judge
visual similarity, invoke a paid API or mark a baseline as a finished room.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent
SCRIPTS = Path('.agents/skills/scan-to-threejs/scripts')
LIMIT = 8*1024**3


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, allow_nan=False, indent=2)+'\n')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checked(root, relative):
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError('Expected a relative capture path')
    path = (root/relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Capture path escapes its bundle')
    return path


def rigid(values):
    import numpy as np
    m = np.asarray(values, dtype=float).reshape((4,4), order='F')
    if (not np.isfinite(m).all() or not np.allclose(m[3],[0,0,0,1],atol=1e-4)
        or not np.allclose(m[:3,:3].T@m[:3,:3],np.eye(3),atol=.01)
        or abs(np.linalg.det(m[:3,:3])-1)>.01):
        raise ValueError('Capture pose is not a finite rigid transform')


def unpack(source, out):
    total = 0
    with zipfile.ZipFile(source) as archive:
        if len(archive.infolist()) > 30000:
            raise ValueError('Capture archive has too many entries')
        for member in archive.infolist():
            total += member.file_size
            if total > LIMIT or stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError('Capture archive exceeds size limit or contains symlinks')
            destination = checked(out, member.filename)
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as stream, destination.open('wb') as target:
                    shutil.copyfileobj(stream, target)
    manifests = list(out.rglob('manifest.json'))
    if len(manifests) != 1:
        raise ValueError('Select a single room/session bundle containing one manifest.json')
    return manifests[0].parent


def intrinsics(fx, fy, cx, cy):
    return [fx,0,0,0,fy,0,cx,cy,1]


def respace_bundle(source, output):
    # Reuse the actual saved-capture contract and integrity checker, not a second
    # permissive parser for private native artifacts.
    sys.path.insert(0, str(ROOT.parent/'reconstruction'))
    from respace_reconstruction.benchmark import inspect_capture
    from respace_reconstruction.geometry import read_scan
    import open3d as o3d
    from PIL import Image
    manifest, audit = inspect_capture(source)
    if not audit['complete']:
        raise ValueError('Complete and verify all original capture artifacts before conversion')
    for sub in ('rooms','photos','depth','mesh'):
        (output/sub).mkdir(parents=True, exist_ok=True)
    inputs = source/'inputs'
    shutil.copyfile(inputs/manifest.room_export.filename, output/'rooms/room-0.json')
    shutil.copyfile(inputs/manifest.scene_mesh.filename, output/'mesh/original-respace.mesh')
    shutil.copyfile(source/'manifest.json', output/'original-respace-manifest.json')
    mesh = read_scan(inputs/manifest.scene_mesh.filename, manifest.capture_id, o3d)
    if not o3d.io.write_triangle_mesh(str(output/'mesh/room-0.ply'), mesh, write_ascii=False):
        raise ValueError('Could not export the measured reference mesh')
    photos, depths, associations = [], [], []
    previous = -math.inf
    for i, frame in enumerate(manifest.frames):
        m = frame.metadata
        if m.timestamp <= previous:
            raise ValueError('Capture frames are not in strictly chronological array order')
        previous = m.timestamp
        artifacts = {a.type: a for a in frame.artifacts}
        photo = f'photos/{i:04d}.jpg'
        shutil.copyfile(inputs/artifacts['jpeg'].filename, output/photo)
        fx,fy,cx,cy = m.intrinsics
        photos.append({'file':photo, 'room':0, 'timestamp':m.timestamp, 'width':m.width, 'height':m.height,
            'transform':m.camera_to_scan_transform, 'intrinsics':intrinsics(fx,fy,cx,cy),
            'tracking':'not_recorded', 'manual':False, 'highRes':False, 'blurPixels':None})
        associations.append({'frame_id':frame.id, 'photo':photo, 'source_photo_sha256':artifacts['jpeg'].sha256,
                             'source_artifact_ids':{k:a.id for k,a in artifacts.items()}})
        if 'depth' not in artifacts:
            continue
        if 'confidence' in artifacts and (m.depth_width,m.depth_height)!=(m.confidence_width,m.confidence_height):
            raise ValueError('Depth/confidence dimensions differ; retain the original scan for diagnosis')
        depth = f'depth/{i:05d}.f16'
        confidence = f'depth/{i:05d}.conf'
        rgb = f'depth/{i:05d}.jpg'
        shutil.copyfile(inputs/artifacts['depth'].filename, output/depth)
        if 'confidence' in artifacts:
            shutil.copyfile(inputs/artifacts['confidence'].filename, output/confidence)
        with Image.open(output/photo) as image:
            image = image.convert('RGB'); image.thumbnail((640,640))
            image.save(output/rgb, quality=90)
            rx,ry = image.width/m.width, image.height/m.height
        sx,sy = m.depth_width/m.width, m.depth_height/m.height
        depths.append({'file':depth, 'confidence':confidence, 'rgb':rgb, 'room':0, 'timestamp':m.timestamp,
            'width':m.depth_width, 'height':m.depth_height, 'transform':m.camera_to_scan_transform,
            'intrinsics':intrinsics(fx*sx,fy*sy,cx*sx,cy*sy),
            'rgbIntrinsics':intrinsics(fx*rx,fy*ry,cx*rx,cy*ry)})
    write_json(output/'photos/photos.json', photos)
    write_json(output/'depth/frames.json', depths)
    write_json(output/'respace-associations.json', {'source_capture_id':manifest.capture_id,
        'source_manifest_sha256':audit['manifest_sha256'], 'frames':associations,
        'notes':['Regular sensor frames; native high-resolution still capture and blur metadata were not recorded.',
                 'A missing confidence file remains absent; no confidence values were fabricated.']})
    write_json(output/'manifest.json', {'format':'house-capture/5', 'sourceFormat':'respace-capture/1',
        'rooms':[{'index':0,'name':manifest.capture_id,'file':'rooms/room-0.json',
                  'mesh':{'file':'mesh/room-0.ply'}}], 'photos':'photos/photos.json','depthFrames':'depth/frames.json'})
    return 0


def validate_bundle(bundle, room):
    from PIL import Image
    manifest = json.loads((bundle/'manifest.json').read_text())
    if manifest.get('format') not in {f'house-capture/{n}' for n in range(1,6)}:
        raise ValueError('Expected a supported house-capture session bundle')
    if manifest.get('state') not in (None,'completed'):
        raise ValueError('This source capture is incomplete; keep recording or finish saving it first')
    if manifest.get('integrityFile'):
        seal_path = checked(bundle,manifest['integrityFile'])
        seal = json.loads(seal_path.read_text())
        if seal.get('format')!='respace-source-integrity/1' or not seal.get('files'):
            raise ValueError('Invalid native capture integrity record')
        expected = set()
        for artifact in seal['files']:
            path = checked(bundle,artifact['path'])
            if path in expected or not path.is_file() or path.stat().st_size!=artifact['byteLength'] or digest(path)!=artifact['sha256']:
                raise ValueError('Native source capture integrity verification failed')
            expected.add(path)
        actual = {p.resolve() for p in bundle.rglob('*') if p.is_file() and p.resolve()!=seal_path}
        if actual != expected:
            raise ValueError('Native source capture files disagree with their integrity record')
    matches = [r for r in manifest['rooms'] if room is None or r['index']==room]
    if len(matches)!=1:
        raise ValueError('Select the original room index with --room; do not assume room zero')
    index = matches[0]['index']
    if type(index) is not int or index<0:
        raise ValueError('The original room index must be a nonnegative integer')
    if not matches[0].get('file'):
        raise ValueError('RoomPlan layout is unavailable. Raw capture, mesh and photographs are retained; rebuild the layout or use the upstream mesh measurement tools before authoring')
    room_path = checked(bundle, matches[0]['file'])
    if room_path != bundle/f'rooms/room-{index}.json' or not room_path.is_file():
        raise ValueError('Bundle is missing its original indexed RoomPlan JSON')
    plan = json.loads(room_path.read_text())
    if not plan.get('walls'):
        raise ValueError('RoomPlan walls are missing; a measured baseline cannot be inferred')
    for collection in ('walls','floors','doors','windows','openings','objects'):
        for part in plan.get(collection,[]):
            rigid(part['transform'])
            if not all(math.isfinite(v) and v>=0 for v in part['dimensions']):
                raise ValueError('Invalid RoomPlan dimensions')
    if manifest.get('photos','photos/photos.json')!='photos/photos.json':
        raise ValueError('Upstream tools require photos/photos.json; normalize the original export first')
    photos = json.loads(checked(bundle,manifest.get('photos','photos/photos.json')).read_text())
    for photo in photos:
        rigid(photo['transform'])
        k = photo['intrinsics']
        if len(k)!=9 or not all(math.isfinite(x) for x in k) or min(k[0],k[4])<=0:
            raise ValueError('Invalid source photo intrinsics')
        with Image.open(checked(bundle,photo['file'])) as image:
            if image.size!=(photo['width'],photo['height']):
                raise ValueError('Source photo dimensions disagree with calibration')
    if not any(p['room']==index for p in photos):
        raise ValueError('The selected room has no posed photographs')
    frames_path = checked(bundle,manifest.get('depthFrames') or 'depth/frames.json')
    if frames_path.is_file():
        for frame in json.loads(frames_path.read_text()):
            rigid(frame['transform'])
            checked(bundle,frame['file'])
            checked(bundle,frame['confidence'])
            if frame.get('rgb'):
                checked(bundle,frame['rgb'])
    return index


def copy_bundle(source, out):
    total = 0
    out.mkdir(parents=True, exist_ok=True)
    for path in source.rglob('*'):
        if path.is_symlink():
            raise ValueError('Resolve capture symlinks before importing')
        if path.is_file():
            total += path.stat().st_size
            if total > LIMIT:
                raise ValueError('Capture exceeds the private workspace size limit')
            destination = out/path.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path,destination)


def template(output):
    manifest = json.loads((ROOT/'UPSTREAM.json').read_text())
    paths = [f['path'] for f in manifest['source_files']]+[
        'UPSTREAM.json','UPSTREAM_CAPTURE.json','package.json','demos/index.ts','reconstruction.ts',
        'scan-viewer.config.ts','tsconfig.scan.json','runtime-export.ts',
        'apps/room-viewer/tools/worker.html','apps/room-viewer/tools/worker.ts',
        'apps/room-viewer/tools/native.html','apps/room-viewer/tools/native.ts']
    for name in paths:
        destination = output/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name,destination)
        if name.endswith('.sh'):
            destination.chmod(0o755)
    (output/'data/web-assets').mkdir(parents=True, exist_ok=True)
    # Every personal input, authored model, texture and comparison stays private.
    (output/'.gitignore').write_text('data/\ndemos/\nnode_modules/\napps/room-viewer/dist/\n.env*\n')


def prepare(source, output, *, room=None, room_id='room', reconstruct=True, legacy_capture=False):
    import re
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,47}', room_id):
        raise ValueError('Room id must be a short lowercase slug')
    source,output = source.resolve(),output.resolve()
    if output.exists() or output.is_relative_to(source):
        raise ValueError('Choose a new output directory outside the source capture')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.scan-to-threejs-',dir=output.parent) as temporary:
        stage = Path(temporary)/'project'; stage.mkdir()
        template(stage)
        bundle = stage/'data/captures-in'/room_id
        if source.is_file() and zipfile.is_zipfile(source):
            unpacked = Path(temporary)/'unpacked'; unpacked.mkdir()
            source = unpack(source,unpacked)
        manifest = json.loads((source/'manifest.json').read_text())
        if manifest.get('source_bundle_format')=='house-capture/5':
            if manifest.get('state') not in ('completed','local_saved'):
                raise ValueError('Finish saving the native capture before preparing it')
            copy_bundle(checked(source,'house-capture'),bundle)
        elif manifest.get('schema_version')==1 and 'scene_mesh' in manifest:
            if not legacy_capture:
                raise ValueError('This is an old ReSpace capture. Record a fresh native capture; historical conversion requires --legacy-capture')
            index = respace_bundle(source,bundle)
            if room not in (None,0):
                raise ValueError('A ReSpace capture contains one room at index zero')
        else:
            copy_bundle(source,bundle)
        index = validate_bundle(bundle,room)
        measurements = stage/'data/demos'/f'{room_id}.json'
        measurements.parent.mkdir(parents=True,exist_ok=True)
        script = stage/SCRIPTS
        subprocess.run([sys.executable,str(script/'bundle_to_room.py'),str(bundle),'--room',str(index),
            '-o',str(measurements),'--plan',str(measurements.with_suffix('.png'))],check=True,capture_output=True,text=True)
        photos = stage/'data/web-assets'/room_id/'photos'
        subprocess.run([sys.executable,str(script/'prepare_photos.py'),str(bundle),str(measurements),str(photos)],
                       check=True,capture_output=True,text=True)
        data = json.loads(measurements.read_text())
        for field in ('walls','objects','photos'):
            if not isinstance(data[field],list):
                raise ValueError('Unexpected upstream measurement output')
        has_mesh = False
        mesh = bundle/f'mesh/room-{index}.ply'
        depth_path = bundle/'depth/frames.json'
        has_depth = depth_path.is_file() and bool(json.loads(depth_path.read_text()))
        if reconstruct and (mesh.is_file() or has_depth):
            result = stage/'data/scans'/room_id
            result.mkdir(parents=True,exist_ok=True)
            reference_command = [sys.executable,str(script/'reconstruct_bundle.py'),str(bundle)]
            if mesh.is_file():
                reference_command.extend(['--mesh',str(mesh)])
            log = subprocess.run(reference_command+['--room',str(measurements),'-o',str(result)],
                                 check=True,capture_output=True,text=True)
            (result/'conversion.log').write_text(log.stdout)
            report = json.loads((result/'reconstruction.json').read_text())
            if report['triangles']<=0 or not (result/'scan_room.glb').is_file():
                raise ValueError('The upstream reference conversion produced no mesh; inspect its source or explicitly use --layout-reference')
            shutil.copyfile(result/'scan_room.glb',photos.parent/'scan.glb')
            has_mesh = True
        author = stage/'demos'/room_id
        (author/'items').mkdir(parents=True); (author/'parts').mkdir()
        (author/'index.ts').write_text("import { captureRoom } from '../../reconstruction';\n"
            "import data from '../../data/demos/"+room_id+".json';\n"
            "import type { AuthoredPart } from '../../reconstruction';\n"
            "const parts = import.meta.glob<AuthoredPart>('./parts/*.ts', { eager: true });\n"
            "const items = import.meta.glob<AuthoredPart>('./items/*.ts', { eager: true });\n"
            f"export default captureRoom({json.dumps(room_id)}, {json.dumps(room_id+' — measured baseline')}, data, parts, items, {str(has_mesh).lower()});\n")
        plan = {'format':'respace-scan-to-threejs/1', 'upstream':json.loads((stage/'UPSTREAM.json').read_text())['revision'],
            'room_id':room_id, 'original_room_index':index, 'stage':'awaiting_modeling', 'ready':False,
            'photo_count':len(data['photos']), 'reference_kind':'scan' if has_mesh else 'layout',
            'world_to_room':data['transform']['worldToRoom'],
            'baseline_assumptions':['10 cm wall thickness','neutral materials and authoring fill lighting',
                                    'flat ceiling at maximum recorded wall top; inspect mesh/photos for steps'],
            'source_manifest_sha256':digest(bundle/'manifest.json')}
        write_json(stage/'workflow.json',plan)
        (author/'BRIEF.md').write_text(brief(room_id,index,len(data['photos']),has_mesh))
        (stage/'START_HERE.txt').write_text(f'Use scan-to-threejs with demos/{room_id}/BRIEF.md. This project is a measured baseline, not a finished reconstruction.\n')
        stage.rename(output)
    return plan


def brief(room_id,index,photo_count,has_mesh):
    return f'''# Reconstruct this captured Room

Use `.agents/skills/scan-to-threejs/SKILL.md` and ALL four linked references.
Upstream is pinned in UPSTREAM.json. Follow its measure → model → compare workflow.
The source is data/captures-in/{room_id}, original room index {index}. There are
{photo_count} posed photographs in data/demos/{room_id}.json array order. Original
sensor JPEGs remain in the bundle; prepared upright photos are under
data/web-assets/{room_id}/photos. Do not rotate those prepared images again.

First inspect the plan, reference geometry and photo contact sheet. Establish
layout, dimensions, ceiling steps and uncertainties before detailing. RoomPlan
boxes are bounds, not finished furniture. The starting shell is explicitly a
schematic baseline. Reference kind: {'measured mesh' if has_mesh else 'RoomPlan layout only'}.

Author actual Objects in items/*.ts and areas in parts/*.ts, exporting build(ctx).
PartContext is in ../../reconstruction.ts. Match all useful views, distinctive
silhouettes, layered construction, hardware, organized contents and source graphics.
Use custom extrude/lathe/tube/rounded geometry as needed, without the earlier JSON
worker's fixed part count or three-attempt limit. Retain measured coordinate
transforms for geometry, cameras, reference layers and lights.

Use rectified photo crops for graphics/screens/artwork and suitable PBR maps for
surfaces. Inspect repeats, seams, baked shadows and alternate views. Match the
captured wood, fabric and flooring rather than assigning a default texture family.
Use the upstream fetch_textures.py for CC0 materials where suitable; retain their
source and license. Do not borrow the public office's dimensions, product shapes,
personal graphics or assets. Place lights from photo evidence and review full PBR
renders. Do not stretch a whole-object photograph across unrelated geometry.

Run npm ci and npm run dev. Set S=$PWD/.agents/skills/scan-to-threejs/scripts and
CAP_URL=http://localhost:5188. Use cmp.sh for orthographic scan/model evidence and
cmp_photo.sh {room_id} PHOTO_INDICES for original vs exact-camera model images.
The helpers only capture comparisons: inspect them, record concrete discrepancies,
fix the largest, and repeat until significant discrepancies are resolved. Inspect
closeups and translated views, not only the starting camera. Keep uncropped source
frames; black/empty scan areas are evidence. No automatic similarity verdict is
provided by upstream. Functionality and appearance are separate acceptance checks.

Completion requires production build success, working viewer/capture modes and no
browser errors, matched-camera evidence covering all modeled Object groups, and
a written comparison review describing measured, modeled and approximate details.
Record remaining uncertainty honestly. Keep workflow.json ready=false until that
evidence has been reviewed. A passing build or a converted baseline is insufficient.
All private captures, textures, generated source and comparisons remain ignored.
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--room',type=int)
    parser.add_argument('--id',default='room')
    parser.add_argument('--layout-reference',action='store_true',help='explicitly skip mesh coloring; reference is schematic only')
    parser.add_argument('--legacy-capture',action='store_true',help='explicit archival conversion only; never used for fresh native scans')
    args = parser.parse_args()
    try:
        result = prepare(args.capture,args.output,room=args.room,room_id=args.id,reconstruct=not args.layout_reference,legacy_capture=args.legacy_capture)
    except (OSError,ValueError,KeyError,subprocess.CalledProcessError) as exc:
        detail = exc.stderr[-2000:] if isinstance(exc,subprocess.CalledProcessError) and exc.stderr else str(exc)
        parser.exit(1,f'Preparation failed: {detail}\n')
    print(json.dumps({'project':str(args.output.resolve()),**result},indent=2))


if __name__=='__main__':
    main()
