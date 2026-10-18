import pytest

from respace.operations import OperationService, DomainError


def room(store, room_id='room'):
    with store.transaction():
        store.put('rooms', room_id, {'room_id':room_id, 'device_id':'device', 'capture_id':'capture', 'latest_capture_id':'capture', 'capture_state':'complete','planning_revision':0,'active_revision':0,'active_design_id':None,'current_operation_id':None,'metadata_revision':0})


def test_request_replay_and_room_lock_survive_reopen(store):
    room(store)
    service = OperationService(store)
    payload = {'operation_id':'op', 'capture_id':'capture','planning_revision':0,'expected_active_revision':0}
    first = service.submit('device', 'room', 'generation', payload)
    assert OperationService(store).submit('device','room','generation',payload) == first
    with pytest.raises(DomainError, match='payload'):
        service.submit('device','room','generation',{**payload,'text':'changed'})
    with pytest.raises(DomainError) as error:
        service.submit('device','room','find_more',{**payload,'operation_id':'second'})
    assert error.value.code == 'room_busy'
    service.cancel('device','op','cancel')
    assert service.get('device','op')['state'] == 'cancelled'
    assert store.get('rooms','room')['current_operation_id'] is None


def test_answer_replay_restores_exact_question_and_prohibits_competing_work(store):
    room(store)
    service=OperationService(store)
    service.submit('device','room','generation',{'operation_id':'op','capture_id':'capture','planning_revision':0,'expected_active_revision':0})
    question={'kind':'single_choice','text':'What matters most?','choices':[{'choice_id':'relax','label':'Relaxation'},{'choice_id':'work','label':'Work'}],'allow_skip':True,'allow_delegate':True}
    frozen=service.ask('op',question)
    assert OperationService(store).get('device','op')['pending_question'] == frozen
    answer={'operation_id':'op','question_id':frozen['question_id'],'reply_id':'reply','expected_decision_revision':0,'expected_question_revision':1,'choice_ids':['work'],'action':'answer'}
    with pytest.raises(DomainError):
        service.answer('device','op',{**answer,'choice_ids':['foreign']})
    accepted=service.answer('device','op',answer)
    assert accepted['decision_revision'] == 1
    assert accepted['pending_question'] is None
    assert service.answer('device','op',answer) == accepted
    assert len(service.get('device','op')['answer_history']) == 1


def test_deletion_blocks_late_publication_and_retries_cleanup(store):
    room(store)
    service=OperationService(store)
    service.submit('device','room','generation',{'operation_id':'op','capture_id':'capture','planning_revision':0,'expected_active_revision':0})
    with store.transaction():
        store.put('artifacts','photo',{'room_id':'room','storage_key':'private/photo'})
        store.put('messages','message',{'room_id':'room','text':'private'})
        for kind in ('captures','keyframes','snapshots','planning','designs','selections','searches','comparisons','budget_proposals','receipts'):
            store.put(kind,'related-'+kind,{'room_id':'room','private':'capture-specific content'})
        store.put('candidates','shared',{'candidate_id':'shared','title':'Reusable public Product'})
    class Cleanup:
        def __init__(self): self.fail=True
        def delete_prefix(self, prefix):
            if self.fail: raise OSError('storage unavailable')
    cleanup=Cleanup()
    pending=service.delete_room('device','room','deletion',cleanup)
    assert pending['state'] == 'pending'
    with pytest.raises(DomainError):
        service.guard('op')
    cleanup.fail=False
    assert service.delete_room('device','room','deletion',cleanup)['state'] == 'deleted'
    assert store.get('rooms','room') is None
    assert store.list('messages','room') == []
    assert store.list('operations','room') == []
    for kind in ('captures','keyframes','snapshots','planning','designs','selections','searches','comparisons','budget_proposals','receipts'):
        assert store.list(kind,'room')==[]
    assert store.get('candidates','shared')['title']=='Reusable public Product'
    assert store.get('deletions','room') == {'room_id':'room','device_id':'device','deletion_id':'deletion','state':'deleted'}


def test_budget_approval_is_exact_and_skip_does_not_authorize_money(store):
    room(store)
    service=OperationService(store)
    service.submit('device','room','generation',{'operation_id':'op','capture_id':'capture','planning_revision':0,'expected_active_revision':0,'budget':'100.00'})
    proposal={'old_ceiling':'100.00','new_ceiling':'150.00','resulting_total':'150.00','affected_purchases':[]}
    question=service.ask('op',{'kind':'budget','text':'Approve the complete purchase set?','choices':[],'budget_proposal':proposal,'allow_skip':True,'allow_delegate':True})
    request={'operation_id':'op','question_id':question['question_id'],'reply_id':'reply','expected_decision_revision':0,'expected_question_revision':1,'action':'skip'}
    with pytest.raises(DomainError): service.answer('device','op',request)
    with pytest.raises(DomainError): service.answer('device','op',{**request,'action':'answer','budget_approval':{**proposal,'new_ceiling':'200.00'}})
    assert service.answer('device','op',{**request,'action':'answer','budget_approval':proposal})['state']=='queued'


def test_ordinary_answer_cannot_smuggle_budget_approval(store):
    room(store)
    service=OperationService(store)
    service.submit('device','room','generation',{'operation_id':'op','capture_id':'capture','planning_revision':0,'expected_active_revision':0,'budget':'100.00'})
    question=service.ask('op',{'kind':'single_choice','text':'Which style?','choices':[{'choice_id':'minimal','label':'Minimal'}]})
    request={'operation_id':'op','question_id':question['question_id'],'reply_id':'reply','expected_decision_revision':0,'expected_question_revision':1,'action':'answer','choice_ids':['minimal'],'budget_approval':{'new_ceiling':'999999.00'}}
    with pytest.raises(DomainError) as error: service.answer('device','op',request)
    assert error.value.code=='unexpected_budget_approval'
    assert service.get('device','op')['answer_history']==[]
