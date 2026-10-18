import asyncio
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
from respace.api import create_app
from respace.operations import OperationService
from respace.spatial import SpatialPipeline
from test_api import MemoryStorage,EmptyProducts,QuestionModel


def test_stored_frames_are_lifted_persisted_reused_and_exposed_as_authorized_snapshot(store):
    fixture=json.loads((Path(__file__).parent/'fixtures/lifting/calibrated_observations_v1.json').read_text())
    room_id,capture_id=fixture['room_id'],fixture['capture_id']
    storage=MemoryStorage();operations=OperationService(store)
    buffer=BytesIO();Image.new('RGB',(800,600)).save(buffer,'JPEG');jpeg=buffer.getvalue()
    with store.transaction():
        store.put('rooms',room_id,{'room_id':room_id,'device_id':'device','latest_capture_id':capture_id,'latest_snapshot_id':None,'active_design_id':None,'active_revision':0,'planning_revision':0,'current_operation_id':None})
        store.put('captures',capture_id,{'capture_id':capture_id,'room_id':room_id,'state':'complete','raw_export':fixture['raw_export']})
        for frame in fixture['frames']:
            meta=deepcopy(frame['meta']);meta['room_id']=room_id
            meta.update(depth_w=8,depth_h=6,depth_format='float32_le_m',confidence_format='uint8',artifacts=[])
            for kind,data in [('jpeg',jpeg),('depth',bytes.fromhex(fixture['depth_hex'])),('confidence',bytes.fromhex(fixture['confidence_hex']))]:
                artifact_id=meta['frame_id']+kind;key=f'rooms/{room_id}/{artifact_id}'
                meta['artifacts'].append({'kind':kind,'artifact_id':artifact_id})
                store.put('artifacts',artifact_id,{'artifact_id':artifact_id,'room_id':room_id,'storage_key':key})
                storage.put(key,data,'application/octet-stream')
            store.put('keyframes',meta['frame_id'],meta)
            store.put('detection_outcomes',meta['frame_id'],{**frame['outcome'],'room_id':room_id,'capture_id':capture_id})
    operations.submit('device',room_id,'generation',{'operation_id':'process','capture_id':capture_id,'planning_revision':0,'expected_active_revision':0})
    pipeline=SpatialPipeline(store,operations,storage)
    # Bounded redelivery progresses one stored frame at a time without calling a detector.
    while True:
        snapshot=asyncio.run(pipeline.process_snapshot('process',bounded=True))
        if snapshot is not None:break
    assert [obj['category'] for obj in snapshot['room']['objects']]==fixture['expected_object_categories']
    assert len(store.list('keyframe_lifts',room_id))==len(fixture['frames'])
    original=deepcopy(snapshot)
    with store.transaction():
        room=store.get('rooms',room_id);room['latest_snapshot_id']=snapshot['snapshot_id'];store.put('rooms',room_id,room)
    reused=asyncio.run(pipeline.process_snapshot('process'))
    assert reused==original and len(store.list('snapshots',room_id))==1
    api=TestClient(create_app(store,storage,EmptyProducts(),QuestionModel(),pipeline),headers={'X-Device-Id':'device'})
    path=f'/v1/rooms/{room_id}/snapshots/{snapshot["snapshot_id"]}'
    assert api.get(path).json()['snapshot']==original
    frame_id=fixture['frames'][0]['meta']['frame_id']
    overlay=api.get(path+'/overlays/'+frame_id)
    assert overlay.status_code==200 and 'viewBox="0 0 800 600"' in overlay.text
    assert api.get(path+'/overlays/'+frame_id,headers={'X-Device-Id':'other'}).status_code==404
    assert api.get(path+'/overlays/foreign').status_code==404
    # Reprocessing changed evidence creates a distinct snapshot; the old one stays byte-for-byte stable.
    with store.transaction():
        outcome=store.get('detection_outcomes',frame_id);outcome['detections']=[];store.put('detection_outcomes',frame_id,outcome)
    changed=asyncio.run(pipeline.process_snapshot('process'))
    assert changed['snapshot_id']!=original['snapshot_id']
    assert changed['revision']==original['revision']+1
    assert store.get('snapshots',original['snapshot_id'])==original
    assert len(store.list('snapshots',room_id))==2
