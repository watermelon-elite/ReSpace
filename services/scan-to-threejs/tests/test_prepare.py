import hashlib
import json
from pathlib import Path
import stat
import zipfile

import numpy as np
from PIL import Image
import pytest

import prepare
from fixtures import native_bundle, room_plan


def test_every_vendored_source_matches_pinned_git_blob():
    provenance = json.loads((prepare.ROOT/'UPSTREAM.json').read_text())
    assert provenance['revision']=='31b2dc9da3fb541e501f2f0936e55b32afb70ee8'
    assert provenance['assets_copied'] is False
    for entry in provenance['source_files']:
        contents = (prepare.ROOT/entry['path']).read_bytes()
        assert hashlib.sha1(b'blob '+str(len(contents)).encode()+b'\0'+contents).hexdigest()==entry['git_blob'],entry['path']


def test_native_capture_core_matches_the_same_pinned_revision():
    pin=json.loads((prepare.ROOT/'UPSTREAM_CAPTURE.json').read_text())
    assert pin['revision']=='31b2dc9da3fb541e501f2f0936e55b32afb70ee8'
    for entry in pin['unchanged']:
        contents=(prepare.ROOT.parents[1]/entry['path']).read_bytes()
        assert hashlib.sha1(b'blob '+str(len(contents)).encode()+b'\0'+contents).hexdigest()==entry['git_blob']


def test_native_original_index_photo_order_upright_pixels_and_common_frame(tmp_path):
    source,out = tmp_path/'capture',tmp_path/'project'
    world,photos = native_bundle(source,mesh=False)
    original = {str(p.relative_to(source)):prepare.digest(p) for p in source.rglob('*') if p.is_file()}
    state = prepare.prepare(source,out,room_id='synthetic',reconstruct=False)
    converted = json.loads((out/'data/demos/synthetic.json').read_text())
    assert state['original_room_index']==7 and state['photo_count']==2
    assert state['ready'] is False and state['stage']=='awaiting_modeling'
    assert converted['objects']==[]  # no public-room furniture or guessed Objects
    assert [p['file'] for p in converted['photos']]==['photos/0009.jpg','photos/0002.jpg']
    transform = np.array(converted['transform']['worldToRoom']).reshape(4,4,order='F')
    for view,photo in zip(converted['photos'],[photos[0],photos[2]]):
        pose = transform@np.array(photo['transform']).reshape(4,4,order='F')
        np.testing.assert_allclose(view['position'],pose[:3,3],atol=1e-4)
        np.testing.assert_allclose(view['forward'],-pose[:3,2],atol=1e-5)
        np.testing.assert_allclose(view['up'],-pose[:3,0],atol=1e-5)
        assert view['aspect']==.75
    # One global rigid transform must remove the source heading and translation
    # for both the walls and the cameras without changing the 4x3 metre room.
    np.testing.assert_allclose(transform@world,np.eye(4),atol=1e-8)
    assert sorted(w['length'] for w in converted['walls'])==[3,3,4,4]
    with Image.open(source/'photos/0009.jpg') as image,Image.open(out/'data/web-assets/synthetic/photos/0000.jpg') as upright:
        expected = np.asarray(image.transpose(Image.Transpose.ROTATE_270)).astype(float)
        assert upright.size==(480,640)
        assert np.abs(expected-np.asarray(upright)).mean()<2
    assert original=={str(p.relative_to(source)):prepare.digest(p) for p in source.rglob('*') if p.is_file()}
    assert 'import.meta.glob<AuthoredPart>' in (out/'demos/synthetic/index.ts').read_text()
    assert 'data/\n' in (out/'.gitignore').read_text()


def test_reference_mesh_uses_same_alignment_as_photos(tmp_path):
    source,out=tmp_path/'capture',tmp_path/'project'
    native_bundle(source)
    state=prepare.prepare(source,out,room_id='synthetic')
    import open3d as o3d
    mesh=o3d.io.read_triangle_mesh(str(out/'data/scans/synthetic/scan_room.ply'))
    vertices=np.asarray(mesh.vertices)
    assert state['reference_kind']=='scan' and len(mesh.triangles)>0
    np.testing.assert_allclose(vertices.min(axis=0),[-2,0,-1.5],atol=1e-5)
    np.testing.assert_allclose(vertices.max(axis=0),[2,2.6,-1.5],atol=1e-5)
    assert (out/'data/web-assets/synthetic/scan.glb').stat().st_size>1000


def test_respace_preserves_calibration_depth_and_source_checksums(tmp_path,capture):
    manifest,payloads=capture
    room=manifest.room_export
    payload=json.dumps(room_plan()).encode()
    payloads[room.filename]=payload
    record=manifest.model_dump(mode='json')
    record['room_export'].update(byte_length=len(payload),sha256=hashlib.sha256(payload).hexdigest())
    source,out=tmp_path/'saved',tmp_path/'project'
    (source/'inputs').mkdir(parents=True)
    (source/'manifest.json').write_text(json.dumps(record))
    for name,contents in payloads.items(): (source/'inputs'/name).write_bytes(contents)
    prepare.prepare(source,out,reconstruct=False,legacy_capture=True)
    bundle=out/'data/captures-in/room'
    photos=json.loads((bundle/'photos/photos.json').read_text())
    depths=json.loads((bundle/'depth/frames.json').read_text())
    frame=manifest.frames[0]
    jpeg=next(a for a in frame.artifacts if a.type=='jpeg')
    assert (bundle/photos[0]['file']).read_bytes()==payloads[jpeg.filename]
    assert photos[0]['transform']==frame.metadata.camera_to_scan_transform
    assert photos[0]['intrinsics']==[480,0,0,0,480,0,320,240,1]
    assert photos[0]['blurPixels'] is None
    assert depths[0]['intrinsics']==[120,0,0,0,120,0,80,60,1]
    original_depth=next(a for a in frame.artifacts if a.type=='depth')
    assert (bundle/depths[0]['file']).read_bytes()==payloads[original_depth.filename]
    # ReSpace's declared raw-artifact hashes remain mandatory.
    (source/'inputs'/jpeg.filename).write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='verify'):
        prepare.prepare(source,tmp_path/'corrupt-project',reconstruct=False,legacy_capture=True)
    assert not (tmp_path/'corrupt-project').exists()


@pytest.mark.parametrize('problem',['image_dimensions','pose_scale','escaping_photo','no_photos','missing_walls','bad_index'])
def test_malformed_evidence_never_becomes_a_prepared_project(tmp_path,problem):
    source=tmp_path/'capture'; native_bundle(source,mesh=False)
    photos=json.loads((source/'photos/photos.json').read_text())
    if problem=='image_dimensions': photos[0]['width']=1
    if problem=='pose_scale': photos[0]['transform'][0]=4
    if problem=='escaping_photo': photos[0]['file']='../../outside.jpg'
    if problem=='no_photos': photos=[]
    if problem=='missing_walls': (source/'rooms/room-7.json').write_text('{"walls":[]}')
    if problem=='bad_index':
        manifest=json.loads((source/'manifest.json').read_text()); manifest['rooms'][0]['index']='7'
        (source/'manifest.json').write_text(json.dumps(manifest))
    (source/'photos/photos.json').write_text(json.dumps(photos))
    with pytest.raises(ValueError): prepare.prepare(source,tmp_path/'project',reconstruct=False)
    assert not (tmp_path/'project').exists()


@pytest.mark.parametrize('entry',['../escape','/absolute'])
def test_zip_paths_cannot_escape_private_workspace(tmp_path,entry):
    source=tmp_path/'capture.zip'
    with zipfile.ZipFile(source,'w') as archive: archive.writestr(entry,b'bad')
    with pytest.raises(ValueError): prepare.prepare(source,tmp_path/'project')


def test_zip_symlink_rejected(tmp_path):
    source=tmp_path/'capture.zip'
    with zipfile.ZipFile(source,'w') as archive:
        info=zipfile.ZipInfo('capture/linked'); info.external_attr=(stat.S_IFLNK|0o777)<<16
        archive.writestr(info,b'../../private')
    with pytest.raises(ValueError,match='symlinks'): prepare.prepare(source,tmp_path/'project')


def test_shared_room_zip_preserves_its_original_index(tmp_path):
    source=tmp_path/'capture'; native_bundle(source,mesh=False)
    archive_path=tmp_path/'capture.zip'
    with zipfile.ZipFile(archive_path,'w') as archive:
        for path in source.rglob('*'):
            if path.is_file(): archive.write(path,'Shared Room/'+str(path.relative_to(source)))
    result=prepare.prepare(archive_path,tmp_path/'project',reconstruct=False)
    assert result['original_room_index']==7 and result['ready'] is False


def test_missing_saved_mesh_fuses_recorded_depth_with_original_upstream_tool(tmp_path):
    source=tmp_path/'capture'; _,photos=native_bundle(source,mesh=False)
    frames=[]
    for i,photo in enumerate([photos[0],photos[2]]):
        file,confidence=f'depth/{i:05d}.f16',f'depth/{i:05d}.conf'
        (source/file).write_bytes(np.full((60,80),2.5,dtype='<f2').tobytes())
        (source/confidence).write_bytes(np.full((60,80),2,dtype='u1').tobytes())
        frames.append({'file':file,'confidence':confidence,'width':80,'height':60,
            'transform':photo['transform'],'intrinsics':[75,0,0,0,75,0,40,30,1]})
    (source/'depth/frames.json').write_text(json.dumps(frames))
    out=tmp_path/'project'; result=prepare.prepare(source,out)
    report=json.loads((out/'data/scans/room/reconstruction.json').read_text())
    assert result['reference_kind']=='scan'
    assert report['sourceMesh'] is None and report['depthFrames']==2 and report['triangles']>100


def test_multiple_rooms_require_explicit_original_index(tmp_path):
    source=tmp_path/'capture'; native_bundle(source,mesh=False)
    manifest=json.loads((source/'manifest.json').read_text())
    manifest['rooms'].append({'index':8,'file':'rooms/room-8.json'})
    (source/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='original room index'):
        prepare.prepare(source,tmp_path/'no-selection',reconstruct=False)
    assert prepare.prepare(source,tmp_path/'selected',room=7,reconstruct=False)['original_room_index']==7


def seal_native(bundle):
    manifest=json.loads((bundle/'manifest.json').read_text())
    manifest.update(state='completed',integrityFile='integrity.json')
    (bundle/'manifest.json').write_text(json.dumps(manifest))
    files=[{'path':str(p.relative_to(bundle)),'byteLength':p.stat().st_size,'sha256':prepare.digest(p)}
           for p in sorted(bundle.rglob('*')) if p.is_file() and p.name!='integrity.json']
    (bundle/'integrity.json').write_text(json.dumps({'format':'respace-source-integrity/1','files':files}))


def test_fresh_managed_capture_uses_native_metadata_without_legacy_adapter(tmp_path,monkeypatch):
    source=tmp_path/'managed'; bundle=source/'house-capture'
    native_bundle(bundle,mesh=False)
    photos=json.loads((bundle/'photos/photos.json').read_text())
    photos[0].update(highRes=True,manual=False,exposure=.008,
        camera={'iso':80,'shutter':.008,'whiteBalance':[1.8,1,1.6],'whiteBalanceLocked':True})
    (bundle/'photos/photos.json').write_text(json.dumps(photos))
    seal_native(bundle)
    (source/'manifest.json').write_text(json.dumps({'schema_version':1,'state':'local_saved',
        'source_bundle_format':'house-capture/5','frames':[]}))
    def obsolete_adapter(*args): raise AssertionError('Fresh captures must never enter the legacy adapter')
    monkeypatch.setattr(prepare,'respace_bundle',obsolete_adapter)
    out=tmp_path/'project'; prepare.prepare(source,out,reconstruct=False)
    copied=out/'data/captures-in/room'
    assert (copied/'photos/photos.json').read_bytes()==(bundle/'photos/photos.json').read_bytes()
    saved=json.loads((copied/'photos/photos.json').read_text())[0]
    assert saved['highRes'] and saved['camera']['whiteBalanceLocked']
    assert saved['exposure']==.008 and saved['blurPixels']==.2
    (bundle/'photos/0009.jpg').write_bytes(b'changed')
    with pytest.raises(ValueError,match='integrity'):
        prepare.prepare(source,tmp_path/'corrupt',reconstruct=False)


def test_old_adapter_is_disabled_unless_explicitly_requested(tmp_path):
    source=tmp_path/'legacy'; source.mkdir()
    (source/'manifest.json').write_text('{"schema_version":1,"scene_mesh":{}}')
    with pytest.raises(ValueError,match='old ReSpace capture'):
        prepare.prepare(source,tmp_path/'project',reconstruct=False)


def test_incomplete_native_source_cannot_be_prepared_as_a_finished_capture(tmp_path):
    source=tmp_path/'capture'; native_bundle(source,mesh=False)
    manifest=json.loads((source/'manifest.json').read_text()); manifest['state']='recording'
    (source/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='incomplete'):
        prepare.prepare(source,tmp_path/'project',reconstruct=False)


def test_saved_capture_without_roomplan_layout_reports_recovery_without_faking_a_model(tmp_path):
    source=tmp_path/'capture'; native_bundle(source)
    manifest=json.loads((source/'manifest.json').read_text())
    manifest['rooms'][0]['file']=''
    manifest['layoutError']='RoomBuilder could not finish'
    (source/'manifest.json').write_text(json.dumps(manifest))
    (source/'rooms/room-7.json').unlink()
    seal_native(source)
    before={str(p.relative_to(source)):prepare.digest(p) for p in source.rglob('*') if p.is_file()}
    with pytest.raises(ValueError,match='layout is unavailable'):
        prepare.prepare(source,tmp_path/'project',reconstruct=False)
    assert not (tmp_path/'project').exists()
    assert before=={str(p.relative_to(source)):prepare.digest(p) for p in source.rglob('*') if p.is_file()}
