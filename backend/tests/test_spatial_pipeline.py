from copy import deepcopy
from io import BytesIO

import pytest
from PIL import Image

from respace.operations import OperationService
from respace.spatial import SpatialPipeline
from test_geometry import native_room
from test_operations import room
from test_products import offer
from test_solver import plan, selection


def setup_pipeline(store, *, known_equivalent=True, explicit=True):
    room(store)
    chosen = selection((10, 10, 1))
    chosen.update(quantity=1, must_have=True, explicit_choice=explicit)
    chosen['offer'] = offer('v', '100.00', 1)
    chosen['offer_id'] = chosen['offer']['offer_id']
    alternative = selection()
    alternative.update(selection_id='small', variant_id='small-v', offer_id='o_small-v', quantity=1)
    alternative['dimension_evidence']['variant_id'] = 'small-v'
    alternative['offer'] = offer('small-v', '100.00', 1)
    selection_snapshot = {'schema_version': 1, 'selection_snapshot_id': 'selected', 'room_id': 'room',
                          'capture_id': 'capture', 'decision_revision': 0, 'selected': [chosen], 'approved_ceiling': '200.00'}
    ops = OperationService(store)
    ops.submit('device', 'room', 'generation', {'operation_id': 'op', 'capture_id': 'capture',
               'planning_revision': 0, 'expected_active_revision': 0, 'intent': 'add', 'budget': '200.00'})
    with store.transaction():
        store.put('captures', 'capture', {'capture_id': 'capture', 'room_id': 'room', 'state': 'complete', 'raw_export': native_room()})
        store.put('planning', 'room', {'instructions': []})
        operation = store.get('operations', 'op')
        operation['controller'] = {'selection': selection_snapshot, 'initial_products': {'displayed_choices': [alternative] if known_equivalent else []}, 'actions': []}
        store.put('operations', 'op', operation)
        for i in range(2):
            store.put('keyframes', f'f{i}', {'room_id': 'room', 'capture_id': 'capture', 'frame_id': f'f{i}',
                      'idx': i, 'w': 100, 'h': 100,'orientation':'sensor_landscape','intrinsics':{'fx':100,'fy':100,'cx':50,'cy':50},'transform':[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1], 'artifacts': [{'kind': 'jpeg', 'artifact_id': f'jpeg{i}'}]})
            store.put('artifacts', f'jpeg{i}', {'storage_key': f'jpeg{i}'})
    class Storage:
        def get(self, key):
            buffer=BytesIO();Image.new('RGB',(100,100)).save(buffer,'JPEG');return buffer.getvalue()
    class Detector:
        calls = 0
        async def detect(self, jpeg, w, h, frame_id):
            self.calls += 1
            return {'frame_id': frame_id, 'state': 'succeeded', 'detections': [], 'attempts': []}
    class Planner:
        calls = 0
        async def plan(self, snapshot, selections, instructions, photos, constraints):
            self.calls += 1
            candidate = plan()
            candidate.update(decision_revision=constraints['decision_revision'], base=constraints['base'])
            return {'plan': candidate, 'hard_errors': [], 'diagnostics': []}
    class Products:
        calls = 0
        def verify_selection(self, choices, ceiling):
            self.calls += 1
            result = deepcopy(alternative)
            result.update(selection_id=choices[0]['selection_id'], quantity=choices[0]['quantity'])
            return [result]
    detector, planner, products = Detector(), Planner(), Products()
    pipeline = SpatialPipeline(store, ops, Storage(), detector, planner, products=products)
    return ops, pipeline, selection_snapshot, detector, planner, products


def answer(ops, choice_id):
    operation = ops.get('device', 'op')
    question = operation['pending_question']
    return ops.answer('device', 'op', {'question_id': question['question_id'], 'reply_id': 'reply-' + choice_id,
                       'expected_decision_revision': operation['decision_revision'],
                       'expected_question_revision': question['question_revision'], 'choice_ids': [choice_id]})


@pytest.mark.asyncio
async def test_protected_fit_repair_uses_verified_retained_equivalent_and_resumes_without_reprocessing(store):
    ops, pipeline, selected, detector, planner, products = setup_pipeline(store)
    await pipeline('op', selected)
    operation = ops.get('device', 'op')
    assert operation['state'] == 'needs_clarification'
    assert store.list('designs', 'room') == []
    choice_id = next(c['choice_id'] for c in operation['pending_question']['choices'] if c['choice_id'] != 'cancel_generation')
    answer(ops, choice_id)
    await pipeline('op', selected)
    operation = ops.get('device', 'op')
    assert operation['state'] == 'succeeded'
    assert detector.calls == 2
    assert planner.calls == 1
    assert products.calls == 1
    design = store.get('designs', operation['outcome']['design_id'])
    assert design['scene']['purchase_summary']['total'] == '100.00'
    assert design['plan']['decision_revision'] == 1
    assert design['scene']['items'][0]['variant_id'] == 'small-v'
    assert len(store.list('snapshots', 'room')) == 1


@pytest.mark.asyncio
async def test_delegated_equivalent_can_fit_without_question_and_budget_is_recomputed(store):
    ops, pipeline, selected, detector, planner, products = setup_pipeline(store, explicit=False)
    await pipeline('op', selected)
    operation = ops.get('device', 'op')
    assert operation['state'] == 'succeeded'
    assert operation['question_history'] == []
    design = store.get('designs', operation['outcome']['design_id'])
    assert design['scene']['items'][0]['variant_id'] == 'small-v'
    assert design['scene']['purchase_summary']['total'] == '100.00'


@pytest.mark.asyncio
async def test_unfit_requirement_can_be_explicitly_omitted_without_repeating_the_question(store):
    ops, pipeline, selected, detector, planner, products = setup_pipeline(store, known_equivalent=False)
    await pipeline('op', selected)
    operation = ops.get('device', 'op')
    assert operation['state'] == 'needs_clarification'
    assert store.list('designs', 'room') == []
    assert {c['choice_id'] for c in operation['pending_question']['choices']} == {'omit_requirement', 'cancel_generation'}
    answer(ops, 'omit_requirement')
    await pipeline('op', selected)
    operation = ops.get('device', 'op')
    assert operation['state'] == 'succeeded'
    assert len(operation['question_history']) == 1
    design = store.get('designs', operation['outcome']['design_id'])
    assert design['scene']['items'] == []
    assert design['scene']['purchase_summary']['total'] == '0.00'
    assert design['scene']['action_outcomes'][0]['code'] == 'user_approved_omission'
    assert design['selection_snapshot']['selected'] == []


@pytest.mark.asyncio
async def test_required_fit_question_can_cancel_without_ever_publishing(store):
    ops, pipeline, selected, detector, planner, products = setup_pipeline(store, known_equivalent=False)
    await pipeline('op', selected)
    answer(ops, 'cancel_generation')
    await pipeline('op', selected)
    assert ops.get('device', 'op')['state'] == 'cancelled'
    assert store.list('designs', 'room') == []
    assert len(store.list('snapshots', 'room')) == 1


def test_generation_reuses_requested_snapshot_and_preserves_parents_across_snapshot_versions(tmp_path):
    from fastapi.testclient import TestClient
    from test_api import complete_room
    from test_local_acceptance import generate, local_app, operation

    app = local_app(tmp_path)
    with TestClient(app, headers={'X-Device-Id': 'device'}) as api:
        room_id, capture_id = complete_room(api)
        completed = generate(api, room_id, capture_id)
        original = api.get('/v1/designs/' + completed['outcome']['design_id']).json()['design']
        snapshot = app.state.store.get('snapshots', original['snapshot_id'])
        legacy_request = app.state.store.get('operations', 'generate')['request']
        assert 'snapshot_id' not in legacy_request
        assert api.post(f'/v1/rooms/{room_id}/designs', json={**legacy_request, 'snapshot_id': None}).status_code == 200

        async def no_processing(*args, **kwargs):
            pytest.fail('An explicitly reused snapshot must not repeat room processing.')
        app.state.controller.spatial.process_snapshot = no_processing
        request = {'operation_id': 'reuse', 'capture_id': capture_id, 'snapshot_id': snapshot['snapshot_id'],
                   'planning_revision': 0, 'expected_active_design_id': original['design_id'],
                   'expected_active_revision': 1, 'intent': 'redesign', 'budget': '500.00'}
        assert api.post(f'/v1/rooms/{room_id}/designs', json=request).status_code == 202
        reused = operation(api, 'reuse')
        assert reused['state'] == 'succeeded', reused
        child = api.get('/v1/designs/' + reused['outcome']['design_id']).json()['design']
        assert child['parent_id'] == original['design_id']
        assert child['snapshot_id'] == original['snapshot_id']
        assert len(app.state.store.list('snapshots', room_id)) == 1

        # This stored context is an upstream fixture; no scan/reconstruction path is changed.
        newer = {**deepcopy(snapshot), 'snapshot_id': 'recorded-snapshot-v2', 'revision': 2,
                 'input_fingerprint': 'recorded-test-input-v2'}
        with app.state.store.transaction():
            app.state.store.put('snapshots', newer['snapshot_id'], newer)
        request.update(operation_id='new-snapshot', snapshot_id=newer['snapshot_id'],
                       expected_active_design_id=child['design_id'], expected_active_revision=2)
        assert api.post(f'/v1/rooms/{room_id}/designs', json=request).status_code == 202
        regenerated = operation(api, 'new-snapshot')
        assert regenerated['state'] == 'succeeded', regenerated
        latest = api.get('/v1/designs/' + regenerated['outcome']['design_id']).json()['design']
        assert latest['parent_id'] == child['design_id'] and latest['snapshot_id'] == newer['snapshot_id']
        assert api.post(f'/v1/rooms/{room_id}/designs', json=request).json()['operation']['outcome'] == regenerated['outcome']
        undo = {'operation_id': 'undo-generation', 'expected_active_design_id': latest['design_id'],
                'expected_active_revision': 3}
        assert api.post(f'/v1/rooms/{room_id}/undo', json=undo).json()['operation']['outcome']['design_id'] == child['design_id']
        assert app.state.store.get('snapshots', snapshot['snapshot_id']) == snapshot
        assert len(app.state.store.list('designs', room_id)) == 3

    with TestClient(local_app(tmp_path), headers={'X-Device-Id': 'device'}) as api:
        assert api.get(f'/v1/rooms/{room_id}').json()['room']['active_design_id'] == child['design_id']
        for saved in (original, child, latest):
            assert api.get('/v1/designs/' + saved['design_id']).json()['design'] == saved


@pytest.mark.parametrize('invalid', ['unknown', 'other_room', 'other_capture', 'unusable'])
def test_generation_rejects_invalid_requested_snapshot_without_processing_or_publication(tmp_path, invalid):
    from fastapi.testclient import TestClient
    from test_api import complete_room
    from test_local_acceptance import generate, local_app, operation

    app = local_app(tmp_path)
    with TestClient(app, headers={'X-Device-Id': 'device'}) as api:
        room_id, capture_id = complete_room(api)
        completed = generate(api, room_id, capture_id)
        original = api.get('/v1/designs/' + completed['outcome']['design_id']).json()['design']
        snapshot = deepcopy(app.state.store.get('snapshots', original['snapshot_id']))
        snapshot['snapshot_id'] = 'invalid-snapshot'
        if invalid == 'other_room':
            snapshot['room_id'] = 'another-room'
        elif invalid == 'other_capture':
            snapshot['capture_id'] = 'another-capture'
        elif invalid == 'unusable':
            snapshot['room']['validity']['usable'] = False
        if invalid != 'unknown':
            with app.state.store.transaction():
                app.state.store.put('snapshots', snapshot['snapshot_id'], snapshot)

        async def no_processing(*args, **kwargs):
            pytest.fail('A rejected snapshot must not start room processing.')
        app.state.controller.spatial.process_snapshot = no_processing
        request = {'operation_id': 'invalid-reuse', 'capture_id': capture_id, 'snapshot_id': snapshot['snapshot_id'],
                   'planning_revision': 0, 'expected_active_design_id': original['design_id'],
                   'expected_active_revision': 1, 'intent': 'add', 'budget': '500.00'}
        assert api.post(f'/v1/rooms/{room_id}/designs', json=request).status_code == 202
        rejected = operation(api, 'invalid-reuse')
        assert rejected['state'] == 'rejected', rejected
        assert rejected['failure']['code'] == ('invalid_room' if invalid == 'unusable' else 'invalid_snapshot')
        assert app.state.store.list('designs', room_id) == [original]
        assert api.get(f'/v1/rooms/{room_id}').json()['room']['active_design_id'] == original['design_id']
