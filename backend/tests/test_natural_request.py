import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from respace.api import create_app
from respace.contracts import Generation
from respace.operations import OperationService
from respace.planning import PlanningController, stated_budget
from test_api import MemoryStorage, complete_room
from test_operations import room


class Model:
    def __init__(self, intent='add', budget=None, quote=None):
        self.intent, self.budget, self.quote = intent, budget, quote
        self.contexts = []

    async def act(self, context):
        self.contexts.append(context)
        if context.get('phase') == 'resolve_request':
            return {'action': 'resolve_request', 'payload': {'intent': self.intent, 'budget': self.budget, 'budget_quote': self.quote}}
        return {'action': 'finalize_selection', 'payload': {'selected': []}}


class Products:
    def __init__(self): self.searches = []
    def search(self, request, *args, **kwargs):
        self.searches.append(request)
        return {'state': 'no_match', 'displayed_choices': []}
    def verify_selection(self, selected, *args, **kwargs):
        assert selected == []
        return []


def setup(store, text, model):
    room(store)
    with store.transaction():
        store.put('captures', 'capture', {'capture_id': 'capture', 'room_id': 'room', 'state': 'complete', 'measured_context': {'objects': []}})
    ops = OperationService(store)
    ops.submit('device', 'room', 'generation', {'operation_id': 'op', 'capture_id': 'capture', 'planning_revision': 0,
        'expected_active_revision': 0, 'expected_active_design_id': None, 'intent': 'auto', 'text': text, 'budget': None})
    products = Products()
    async def spatial(operation_id, selection, **kwargs):
        ops.finish(operation_id, 'succeeded', {'result_kind': 'design', 'selected_intent': selection['approved_intent'], 'budget': selection['approved_ceiling']})
    return ops, products, PlanningController(store, ops, products, model, spatial)


@pytest.mark.parametrize('value,quote,text,expected', [
    ('1500', '$1,500', 'Please spend under $1,500 total.', '1500.00'),
    ('1500', '1.5k', 'My budget is 1.5k USD.', '1500.00'),
    ('0', '$0', 'Use what I have, $0.', '0.00'),
    ('500', '$500', 'Make this cozy.', None),
    ('500', '$50', 'My budget is $50.', None),
    ('-1', '-1', 'Budget -1', None),
    ('2000', '2.00', 'I can spend 2.00', None),
])
def test_budget_must_match_user_evidence(value, quote, text, expected):
    assert stated_budget(value, quote, [text]) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize('intent,text', [('add', 'Add a chair for under $200 total.'), ('redesign', 'Redesign everything for $200 total.')])
async def test_inferred_scope_is_durable_and_used_by_selection(store, intent, text):
    model = Model(intent, '200', '$200')
    ops, products, controller = setup(store, text, model)
    await controller.run('op', bounded=True)
    assert ops.get('device', 'op')['controller']['resolved_request'] == {'intent': intent, 'budget': '200.00', 'styles': ['Match what I have']}
    assert products.searches == []
    await controller.run('op')
    result = ops.get('device', 'op')
    assert result['state'] == 'succeeded', result
    assert result['outcome']['selected_intent'] == intent
    assert len([c for c in model.contexts if c.get('phase') == 'resolve_request']) == 1
    assert not result['question_history']


@pytest.mark.asyncio
async def test_missing_budget_waits_and_resumes_with_natural_answer(store):
    model = Model('redesign')
    ops, products, controller = setup(store, 'Make this room more comfortable.', model)
    await controller.run('op')
    pending = ops.get('device', 'op')
    assert pending['state'] == 'needs_clarification'
    assert products.searches == []
    await controller.run('op')
    assert len(model.contexts) == 1
    question = pending['pending_question']
    ops.answer('device', 'op', {'question_id': question['question_id'], 'reply_id': 'reply',
        'expected_decision_revision': 0, 'expected_question_revision': question['question_revision'], 'text': 'At most $800 total.'})
    model.budget, model.quote = '800', '$800'
    await controller.run('op')
    assert ops.get('device', 'op')['outcome']['budget'] == '800.00'
    assert model.contexts[1]['answers'][0]['request']['text'] == 'At most $800 total.'


@pytest.mark.asyncio
async def test_zero_budget_skips_product_discovery(store):
    ops, products, controller = setup(store, 'Move my chair, budget $0.', Model('redesign', '0', '$0'))
    await controller.run('op')
    assert ops.get('device', 'op')['state'] == 'succeeded'
    assert products.searches == []


def test_auto_api_does_not_require_old_form_fields(store):
    model = Model('redesign')
    api = TestClient(create_app(store, MemoryStorage(), products=Products(), model=model), headers={'X-Device-Id': 'device'})
    room_id, capture_id = complete_room(api)
    request = {'operation_id': 'natural', 'capture_id': capture_id, 'planning_revision': 0, 'expected_active_revision': 0,
               'intent': 'auto', 'text': 'Make it more welcoming.'}
    response = api.post(f'/v1/rooms/{room_id}/designs', json=request)
    assert response.status_code == 202, response.text
    operation = api.get('/v1/operations/natural').json()['operation']
    assert operation['pending_question']['kind'] == 'text'
    assert api.post(f'/v1/rooms/{room_id}/designs', json=request).json()['operation']['operation_id'] == 'natural'
    with pytest.raises(ValidationError):
        Generation.model_validate({**request, 'text': ' '})
    with pytest.raises(ValidationError):
        Generation.model_validate({**request, 'intent': 'add'})


def test_import_context_is_private_idempotent_and_does_not_fabricate_geometry(store):
    api = TestClient(create_app(store, MemoryStorage(), products=Products(), model=Model('add', '100', '$100')), headers={'X-Device-Id': 'device'})
    payload = {'operation_id': 'import', 'name': 'Kitchen', 'source_capture_id': 'original', 'source_scene_sha256': 'a'*64,
               'entities': [{'id': 'fridge', 'label': 'Fridge', 'kind': 'furniture', 'category': 'appliance', 'bounds_min': [0,0,0], 'bounds_max': [1,2,1]}]}
    response = api.post('/v1/rooms/imported', json=payload)
    assert response.status_code == 200, response.text
    detail = response.json()
    assert api.post('/v1/rooms/imported', json=payload).json() == detail
    assert detail['raw_export'] is None
    assert detail['measured_context']['source'] == 'imported_scene'
    room_id = detail['room']['room_id']
    assert api.get('/v1/rooms/'+room_id, headers={'X-Device-Id': 'other'}).status_code == 404
    request = {'operation_id': 'generate', 'capture_id': detail['room']['latest_capture_id'], 'planning_revision': 0,
        'expected_active_revision': 0, 'intent': 'auto', 'text': 'Improve storage for $100 total.', 'selected_object_id': 'fridge'}
    assert api.post(f'/v1/rooms/{room_id}/designs', json={**request, 'selected_object_id': 'foreign'}).status_code == 422
    assert api.post(f'/v1/rooms/{room_id}/designs', json=request).status_code == 202
    op = api.get('/v1/operations/generate').json()['operation']
    assert op['state'] == 'succeeded', op
    assert op['outcome']['result_kind'] == 'selection'
    assert store.list('designs', room_id) == []
    assert store.list('snapshots', room_id) == []
    assert api.delete('/v1/rooms/'+room_id, params={'operation_id': 'delete'}).json()['deletion']['state'] == 'deleted'


@pytest.mark.asyncio
async def test_zero_purchase_request_reaches_real_solver_and_atomic_publication(store):
    from test_spatial_pipeline import setup_pipeline
    ops, pipeline, selection, _, _, _ = setup_pipeline(store)
    with store.transaction():
        operation = store.get('operations', 'op')
        operation['request'].update(intent='auto', budget=None, text='Use only what I have.', selected_object_id='native-chair')
        operation.pop('controller')
        store.put('operations', 'op', operation)
        capture = store.get('captures', 'capture')
        capture['raw_export']['objects'] = [{'identifier': 'native-chair', 'category': {'chair': {}},
            'dimensions': [.4, .6, .3], 'transform': [1,0,0,0, 0,1,0,0, 0,0,1,0, 3,-.9,4,1]}]
        store.put('captures', 'capture', capture)
    class Layout:
        async def plan(self, snapshot, selections, instructions, photos, constraints):
            assert selections == {}
            assert constraints['intent'] == 'redesign'
            assert constraints['user_request']['text'] == 'Use only what I have.'
            assert constraints['user_request']['selected_object_id'] == snapshot['identity_map']['native-chair']['id']
            return {'plan': {'summary': 'Retain the existing room.', 'decision_revision': constraints['decision_revision'],
                            'base': constraints['base']}, 'hard_errors': [], 'diagnostics': []}
    pipeline.planner = Layout()
    controller = PlanningController(store, ops, Products(), Model('redesign', '0', 'Use only what I have'), pipeline)
    await controller.run('op')
    operation = ops.get('device', 'op')
    assert operation['state'] == 'succeeded', operation
    design = store.get('designs', operation['outcome']['design_id'])
    assert design['scene']['purchase_summary']['approved_ceiling'] == '0.00'
    assert design['scene']['purchase_summary']['total'] == '0.00'
    await controller.run('op')
    assert len(store.list('designs', 'room')) == 1
