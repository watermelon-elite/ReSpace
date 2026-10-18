from copy import deepcopy

import pytest
from respace.operations import OperationService,DomainError
from test_operations import room


def interview(store):
    room(store)
    service=OperationService(store)
    service.submit('device','room','generation',{'operation_id':'op','capture_id':'capture','planning_revision':0,'expected_active_revision':0,'budget':'100.00','intent':'add'})
    original=service.ask('op',{'kind':'single_choice','topic':'activity','text':'What matters most?','choices':[{'choice_id':'work','label':'Working'},{'choice_id':'relax','label':'Relaxation'}]})
    service.answer('device','op',{'question_id':original['question_id'],'reply_id':'first','expected_decision_revision':0,'expected_question_revision':1,'choice_ids':['work'],'action':'answer'})
    pending=service.ask('op',{'kind':'numeric','topic':'occupants','text':'How many occupants?','numeric_min':1,'numeric_max':8,'numeric_step':1,'choices':[]})
    return service,original,pending


def test_intentional_answer_revision_appends_once_and_invalidates_unfinished_decisions(store):
    service,original,pending=interview(store)
    before=service.get('device','op')
    with store.transaction():
        operation=store.get('operations','op')
        operation['controller']={'initial_products':{'state':'completed'},'actions':[{'action':'search_products','result':{'search_id':'old'}}]}
        store.put('operations','op',operation)
    request={'question_id':original['question_id'],'reply_id':'revision','expected_decision_revision':1,'expected_question_revision':1,'choice_ids':['relax'],'action':'answer','revision_of_answer_id':before['answer_history'][0]['answer_id']}
    revised=service.answer('device','op',request)
    assert revised['decision_revision']==2 and revised['pending_question'] is None
    assert revised['answer_history'][0]==before['answer_history'][0]
    assert revised['answer_history'][1]['revision_of_answer_id']==request['revision_of_answer_id']
    assert revised['controller']=={}
    assert revised['decision_history'][0]['pending_question']==pending
    assert service.answer('device','op',request)['answer_history']==revised['answer_history']
    with pytest.raises(DomainError):
        service.answer('device','op',{**request,'reply_id':'accidental','revision_of_answer_id':None})


def test_revision_waits_for_boundary_and_requires_latest_answer_revision(store):
    service,original,pending=interview(store)
    first=service.get('device','op')['answer_history'][0]
    request={'question_id':original['question_id'],'reply_id':'revision','expected_decision_revision':1,'expected_question_revision':1,'choice_ids':['relax'],'revision_of_answer_id':first['answer_id']}
    with store.transaction():
        operation=store.get('operations','op');operation.update(state='running',phase='searching_products');operation['pending_question']=None;store.put('operations','op',operation)
    with pytest.raises(DomainError) as error:service.answer('device','op',request)
    assert error.value.code=='revision_boundary_required'
    with store.transaction():
        operation=store.get('operations','op');operation.update(state='needs_clarification',phase='awaiting_answer',pending_question=pending);store.put('operations','op',operation)
    service.answer('device','op',request)
    service.ask('op',{'kind':'single_choice','topic':'new','text':'Choose one','choices':[{'choice_id':'a','label':'A'}]})
    with pytest.raises(DomainError): service.answer('device','op',{**request,'reply_id':'obsolete','expected_decision_revision':2})


def test_revision_does_not_race_an_active_worker_or_reuse_old_effective_answers(store):
    from respace.planning import PlanningController
    service,original,_=interview(store)
    first=service.get('device','op')['answer_history'][0]
    request={'question_id':original['question_id'],'reply_id':'revision','expected_decision_revision':1,'expected_question_revision':1,'choice_ids':['relax'],'revision_of_answer_id':first['answer_id']}
    with store.transaction():
        operation=store.get('operations','op');operation['worker_lease']={'expires_at':'2099-01-01T00:00:00+00:00'};store.put('operations','op',operation)
    with pytest.raises(DomainError) as error:service.answer('device','op',request)
    assert error.value.code=='revision_boundary_required'
    with store.transaction():
        operation=store.get('operations','op');operation.pop('worker_lease');store.put('operations','op',operation)
    revised=service.answer('device','op',request)
    assert OperationService.effective_answers(revised)[0]['request']['choice_ids']==['relax']
    assert len(revised['answer_history'])==2 and PlanningController.approved_budget(revised)=='100.00'


@pytest.mark.asyncio
async def test_next_controller_question_uses_revision_and_replay_does_not_repeat_model_work(store):
    from respace.planning import PlanningController
    service,original,pending=interview(store)
    first=service.get('device','op')['answer_history'][0]
    request={'question_id':original['question_id'],'reply_id':'revision','expected_decision_revision':1,'expected_question_revision':1,'choice_ids':['relax'],'revision_of_answer_id':first['answer_id']}
    service.answer('device','op',request)
    with store.transaction():store.put('captures','capture',{'capture_id':'capture','room_id':'room','state':'complete','measured_context':{}})
    class Model:
        calls=0
        async def act(self,context):
            self.calls+=1
            assert len(context['answers'])==1 and context['answers'][0]['request']['choice_ids']==['relax']
            return {'action':'ask_user','payload':{'kind':'numeric','topic':'occupants','text':'How many people will relax here?','choices':[],'numeric_min':1,'numeric_max':8,'numeric_step':1}}
    model=Model();controller=PlanningController(store,service,None,model,None)
    await controller.run('op')
    resumed=service.get('device','op')
    assert resumed['pending_question']['text']=='How many people will relax here?'
    assert resumed['pending_question']['question_id']!=pending['question_id']
    assert resumed['question_revision']==3 and resumed['decision_revision']==2
    service.answer('device','op',request)
    await controller.run('op')
    assert model.calls==1 and len(service.get('device','op')['answer_history'])==2
