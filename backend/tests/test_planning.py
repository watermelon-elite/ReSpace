import pytest
from types import SimpleNamespace
from respace.planning import GeminiPlanningModel
from respace.operations import OperationService
from respace.planning import PlanningController
from test_operations import room


@pytest.mark.asyncio
async def test_search_tool_rejects_prose_in_one_attempt_and_preserves_axis_limits_on_retry():
    import json
    payloads = [
        {'category': 'side_table', 'function': 'coffee and a book', 'must_have': 'wood, maximum width 50 cm'},
        {'category': 'side_table', 'function': 'coffee and a book', 'must_have': {},
         'avoid': {'material': 'glass'}, 'max_dimensions': [0.5, None, None]},
    ]
    calls = []
    async def generate(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text=json.dumps({'action': 'search_products', 'payload': payloads[len(calls)-1]}))
    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    from respace.operations import DomainError
    model = GeminiPlanningModel(client=client, model='configured-model')
    with pytest.raises(DomainError) as failure:
        await model.act({})
    assert failure.value.retryable and len(calls) == 1
    action = await model.act({})
    assert len(calls) == 2
    reference = json.loads(calls[0]['contents'].split('\n', 1)[1])['layout_reference']
    assert 'Optional reference' in reference['usage']
    assert '# ReSpace layout reasoning context' in reference['content']
    controller = PlanningController(None, None, None, None, None)
    operation = {'room_id': 'r', 'operation_id': 'op', 'request': {'budget': '300'}, 'base_context': {}, 'answer_history': []}
    request = controller._search_request(operation, action['payload'])
    assert request['avoid'] == {'material': 'glass'}
    assert request['max_dimensions'] == [0.5, None, None]


@pytest.mark.asyncio
@pytest.mark.parametrize('code,phrase', [(404, 'not available'), (429, 'quota')])
async def test_planning_reports_unavailable_model_or_quota_without_immediate_retry(code, phrase):
    calls = []
    async def generate(**kwargs):
        calls.append(kwargs)
        error = RuntimeError('Provider detail must remain in private logs')
        error.code = code
        raise error
    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    from respace.operations import DomainError
    with pytest.raises(DomainError) as failure:
        await GeminiPlanningModel(client=client, model='configured-model').act({})
    assert phrase in str(failure.value)
    assert failure.value.retryable is False
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('text,category', [('Add a side table', 'side_table'), ('Add a coffee table', 'coffee_table'),
                                         ('Add an armchair', 'armchair'), ('Add a table lamp', 'table_lamp')])
async def test_initial_discovery_uses_the_specific_requested_category(store, text, category):
    room(store)
    with store.transaction():
        store.put('captures', 'capture', {'state': 'complete', 'measured_context': {}, 'room_id': 'room'})
    operations = OperationService(store)
    operations.submit('device', 'room', 'generation', {'operation_id': 'op', 'capture_id': 'capture',
        'planning_revision': 0, 'expected_active_revision': 0, 'budget': '300.00', 'intent': 'add', 'text': text})
    calls = []
    class Products:
        def search(self, request, *args, **kwargs):
            calls.append(request)
            return {'state': 'no_match', 'displayed_choices': []}
    await PlanningController(store, operations, Products(), None, None).run('op', bounded=True)
    assert calls[0]['category'] == category


@pytest.mark.asyncio
async def test_model_question_releases_work_and_resume_uses_persisted_answers(store):
    room(store)
    with store.transaction():
        store.put('captures','capture',{'capture_id':'capture','room_id':'room','state':'complete','measured_context':{'objects':[],'units':'meters'}})
        store.put('planning','room',{'room_id':'room','planning_revision':0,'instructions':[]})
    ops=OperationService(store)
    ops.submit('device','room','generation',{'operation_id':'op','capture_id':'capture','planning_revision':0,'expected_active_revision':0,'budget':'100.00','intent':'add','styles':['Minimal']})
    class Model:
        calls=[]
        async def act(self, context):
            self.calls.append(context)
            return {'action':'ask_user','payload':{'kind':'single_choice','topic':'activity','text':'What do you do here?','choices':[{'choice_id':'read','label':'Read'}],'allow_delegate':True,'allow_skip':True}}
    class Products:
        def search(self,*args): raise AssertionError('No requested category yet')
    model=Model()
    controller=PlanningController(store,ops,Products(),model,None)
    await controller.run('op')
    operation=ops.get('device','op')
    assert operation['state']=='needs_clarification'
    assert model.calls[0]['measured_context']['units']=='meters'
    assert model.calls[0]['initial_products']['state']=='empty'
    await controller.run('op')
    assert len(model.calls)==1
    assert store.get('rooms','room')['current_operation_id']=='op'


@pytest.mark.asyncio
async def test_unrecognized_model_actions_fail_without_executing_any_tool(store):
    room(store)
    with store.transaction(): store.put('captures','capture',{'state':'complete','measured_context':{},'room_id':'room'})
    ops=OperationService(store)
    ops.submit('device','room','generation',{'operation_id':'op','capture_id':'capture','planning_revision':0,'expected_active_revision':0,'budget':'100.00','intent':'add'})
    class Model:
        async def act(self,context): return {'action':'execute_shell','payload':{'command':'anything'}}
    controller=PlanningController(store,ops,None,Model(),None)
    await controller.run('op')
    assert ops.get('device','op')['state']=='failed'
    assert store.list('designs','room')==[]


def test_budget_proposal_verifies_evidence_above_old_ceiling_without_approving_it(store):
    from test_discovery import service,hit
    products,_,_=service(store,[[hit(1)],[],[]])
    known=products.search({'category':'chair','room_id':'r'},'initial')['displayed_choices'][0]
    room(store,'r')
    operations=OperationService(store)
    operation=operations.submit('device','r','generation',{'operation_id':'op','capture_id':'capture','planning_revision':0,'expected_active_revision':0,'budget':'90.00'})
    operation['controller']={'initial_products':{'displayed_choices':[known]},'actions':[]}
    with store.transaction(): store.put('operations','op',operation)
    controller=PlanningController(store,operations,products,None,None)
    question=controller._verified_question(operation,{'kind':'budget','text':'Approve the verified required chair?','proposed_selected':[{'variant_id':known['variant_id'],'offer_id':known['offer_id'],'quantity':1}],'alternative_sets':[],'functional_consequences':['Adds one required chair'],'reason':'No verified required chair was found within this ceiling'})
    assert question['budget_proposal']['old_ceiling']=='90.00'
    assert question['budget_proposal']['new_ceiling']=='100.00'
    assert controller.approved_budget(operations.get('device','op'))=='90.00'
    assert store.get('budget_proposals',question['budget_proposal']['proposal_id'])==question['budget_proposal']


def test_budget_proposal_uses_refreshed_price_without_requiring_prior_approval(store):
    from datetime import datetime,timedelta,timezone
    from test_discovery import service,hit
    products,_,verifier=service(store,[[hit(1)],[],[]])
    known=products.search({'category':'chair','room_id':'r'},'initial')['displayed_choices'][0]
    with store.transaction():
        offer=store.get('offers',known['offer_id'])
        offer['checked_at']=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
        store.put('offers',offer['offer_id'],offer)
    original_verify=verifier.verify
    def refreshed(candidate):
        result=original_verify(candidate)
        result['offers'][0]['price']='125.00'
        return result
    verifier.verify=refreshed
    room(store,'r')
    operations=OperationService(store)
    operation=operations.submit('device','r','generation',{'operation_id':'op','capture_id':'capture','planning_revision':0,'expected_active_revision':0,'budget':'90.00'})
    operation['controller']={'initial_products':{'displayed_choices':[known]},'actions':[]}
    with store.transaction(): store.put('operations','op',operation)
    controller=PlanningController(store,operations,products,None,None)
    question=controller._verified_question(operation,{'kind':'budget','text':'Approve the refreshed required chair?','proposed_selected':[{'variant_id':known['variant_id'],'offer_id':known['offer_id'],'quantity':1}],'alternative_sets':[],'functional_consequences':['Adds one required chair'],'reason':'No verified required chair was found within this ceiling'})
    assert question['budget_proposal']['new_ceiling']=='125.00'
    assert controller.approved_budget(operations.get('device','op'))=='90.00'
    from respace.products import ProductError
    with pytest.raises(ProductError): products.verify_selection([known],'90.00')


@pytest.mark.asyncio
async def test_conflicting_add_request_requires_explicit_intent_answer(store):
    room(store)
    with store.transaction():
        store.put('captures','capture',{'capture_id':'capture','room_id':'room','state':'complete','measured_context':{'objects':[]}})
    operations=OperationService(store)
    operations.submit('device','room','generation',{'operation_id':'op','capture_id':'capture','planning_revision':0,'expected_active_revision':0,'budget':'100.00','intent':'add','text':'replace everything'})
    class Model:
        calls=[]
        async def act(self,context):
            self.calls.append(context)
            return {'action':'ask_user','payload':{'kind':'single_choice','topic':'activity','text':'What matters most?','choices':[{'choice_id':'work','label':'Working'}],'allow_skip':True,'allow_delegate':True}}
    model=Model()
    controller=PlanningController(store,operations,None,model,None)
    await controller.run('op')
    operation=operations.get('device','op');question=operation['pending_question']
    assert question['topic']=='intent_conflict' and model.calls==[]
    operations.answer('device','op',{'operation_id':'op','question_id':question['question_id'],'reply_id':'reply','expected_decision_revision':0,'expected_question_revision':1,'choice_ids':['redesign'],'action':'answer'})
    await controller.run('op')
    assert model.calls[0]['request']['intent']=='redesign'
    assert operations.get('device','op')['request']['intent']=='add'
