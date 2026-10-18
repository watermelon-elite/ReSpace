from copy import deepcopy

import pytest

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
                      'idx': i, 'w': 100, 'h': 100, 'artifacts': [{'kind': 'jpeg', 'artifact_id': f'jpeg{i}'}]})
            store.put('artifacts', f'jpeg{i}', {'storage_key': f'jpeg{i}'})
    class Storage:
        def get(self, key): return key.encode()
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
