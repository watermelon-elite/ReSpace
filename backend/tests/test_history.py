from copy import deepcopy

from fastapi.testclient import TestClient
from respace.api import create_app
from respace.operations import OperationService
from respace.publication import Publisher
from respace.solver import validate_scene
from test_api import MemoryStorage,EmptyProducts,QuestionModel,test_deferred_pipeline_publishes_once_and_reopens_saved_transport as seed_design


def lineage(store):
    seed_design(store)
    room=store.list('rooms')[0]
    parent=store.get('designs',room['active_design_id'])
    snapshot=deepcopy(store.get('snapshots',parent['snapshot_id']));snapshot.update(snapshot_id='new-snapshot',revision=2)
    with store.transaction():store.put('snapshots',snapshot['snapshot_id'],snapshot)
    ops=OperationService(store)
    ops.submit('device',room['room_id'],'generation',{'operation_id':'regen','capture_id':room['latest_capture_id'],'planning_revision':0,'expected_active_design_id':parent['design_id'],'expected_active_revision':room['active_revision']})
    candidate={'scene':deepcopy(parent['scene']),'action_outcomes':[],'conflicts':[]}
    candidate['scene']['summary']='A regenerated design'
    child_op=Publisher(store,ops,validate_scene).publish('regen',snapshot,parent['selection_snapshot'],{},candidate)
    child=store.get('designs',child_op['outcome']['design_id'])
    api=TestClient(create_app(store,MemoryStorage(),EmptyProducts(),QuestionModel(),lambda *args:None),headers={'X-Device-Id':'device'})
    return api,parent,child


def test_undo_replays_one_parent_and_reopen_uses_active_not_newest(store):
    api,parent,child=lineage(store)
    room=store.get('rooms',parent['room_id'])
    request={'operation_id':'undo','expected_active_design_id':child['design_id'],'expected_active_revision':room['active_revision']}
    response=api.post(f"/v1/rooms/{room['room_id']}/undo",json=request)
    assert response.status_code==200,response.text
    outcome=response.json()['operation']['outcome']
    assert outcome['design_id']==parent['design_id']
    assert api.post(f"/v1/rooms/{room['room_id']}/undo",json=request).json()==response.json()
    reopened=api.get(f"/v1/rooms/{room['room_id']}").json()['room']
    assert reopened['active_design_id']==parent['design_id']
    assert store.get('designs',parent['design_id'])==parent and store.get('designs',child['design_id'])==child
    assert len(store.list('designs',room['room_id']))==2
    entry=store.get('messages',outcome['message_ids'][0])
    assert entry['from_version_id']==child['design_id'] and entry['to_version_id']==parent['design_id']


def test_edit_after_undo_branches_and_root_cannot_undo(store):
    api,parent,child=lineage(store)
    room=store.get('rooms',parent['room_id'])
    request={'operation_id':'undo','expected_active_design_id':child['design_id'],'expected_active_revision':room['active_revision']}
    assert api.post(f"/v1/rooms/{room['room_id']}/undo",json=request).status_code==200
    root_request={'operation_id':'root-undo','expected_active_design_id':parent['design_id'],'expected_active_revision':room['active_revision']+1}
    rejected=api.post(f"/v1/rooms/{room['room_id']}/undo",json=root_request).json()['operation']
    assert rejected['state']=='rejected' and rejected['outcome']['result_kind']=='no_parent'
    ops=OperationService(store)
    ops.submit('device',room['room_id'],'generation',{'operation_id':'branch','capture_id':room['latest_capture_id'],'planning_revision':0,'expected_active_design_id':parent['design_id'],'expected_active_revision':room['active_revision']+1})
    result=Publisher(store,ops,validate_scene).publish('branch',store.get('snapshots',parent['snapshot_id']),parent['selection_snapshot'],{}, {'scene':deepcopy(parent['scene']),'action_outcomes':[],'conflicts':[]})
    branch=store.get('designs',result['outcome']['design_id'])
    assert branch['parent_id']==parent['design_id']
    assert child['design_id']!=branch['design_id'] and store.get('designs',child['design_id'])==child
