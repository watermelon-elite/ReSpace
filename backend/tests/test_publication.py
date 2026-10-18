import pytest
from respace.operations import OperationService, DomainError
from respace.publication import Publisher
from test_operations import room


def test_publication_is_atomic_replay_with_immutable_evidence(store):
    room(store)
    ops=OperationService(store)
    ops.submit('device','room','generation',{'operation_id':'op','capture_id':'capture','planning_revision':0,'expected_active_revision':0})
    snapshot={'snapshot_id':'snapshot','room_id':'room','capture_id':'capture','room':{'validity':{'usable':True}}}
    with store.transaction(): store.put('snapshots','snapshot',snapshot)
    candidate={'scene':{'items':[],'purchases':{'total':'0.00'},'summary':'Keep the room open'},'action_outcomes':[],'conflicts':[]}
    publisher=Publisher(store,ops,lambda room,scene:[])
    saved=publisher.publish('op',snapshot,{}, {}, candidate)
    same=publisher.publish('op',snapshot,{}, {}, candidate)
    assert saved==same
    assert len(store.list('designs','room'))==1
    assert len([entry for entry in store.list('messages','room') if entry['event_kind']=='outcome'])==1
    assert store.get('rooms','room')['active_revision']==1
    assert saved['outcome']['message_ids']==[entry['message_id'] for entry in store.list('messages','room') if entry['event_kind']=='outcome']
    design=store.get('designs',saved['outcome']['design_id'])
    candidate['scene']['summary']='changed later'
    assert store.get('designs',design['design_id'])['scene']['summary']=='Keep the room open'


def test_cancelled_and_invalid_candidates_never_publish(store):
    room(store)
    ops=OperationService(store)
    ops.submit('device','room','generation',{'operation_id':'op','capture_id':'capture','planning_revision':0,'expected_active_revision':0})
    publisher=Publisher(store,ops,lambda room,scene:[{'code':'collision'}])
    with pytest.raises(DomainError): publisher.publish('op',{'room':{'validity':{'usable':True}}},{},{},{'scene':{'items':[]},'conflicts':[]})
    assert store.list('designs','room')==[]
    ops.cancel('device','op','cancel')
    with pytest.raises(DomainError): publisher.publish('op',{'room':{'validity':{'usable':True}}},{},{},{'scene':{},'conflicts':[]})
