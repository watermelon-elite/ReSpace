from copy import deepcopy
import pytest

from respace.geometry import normalize_room
from respace.solver import solve, validate_scene
from test_geometry import native_room
from test_solver import plan, selection


def supported_scene():
    room = normalize_room(native_room(), 'capture', 'room')
    request = plan({'type': 'room_center'})
    choices = {'sel': selection((1.6, 1.2, .7))}
    for identity, category, size, target in [('top', 'side_table', (.8, .8, .4), 'i_a_0'), ('lamp', 'table_lamp', (.2, .2, .3), 'i_top_0')]:
        choices[identity] = {**selection(size, category), 'selection_id': identity}
        request['adds'].append({**request['adds'][0], 'action_id': identity, 'add_id': identity, 'category': category,
            'selection_id': identity, 'anchor': {'type': 'on_top_of', 'target': {'kind': 'item', 'id': target}}})
    base = solve(room, request, choices, {'intent': 'add'})['scene']
    assert validate_scene(room, base) == []
    return room, choices, base


def removal():
    return {'summary': 'Remove desk', 'removes': [{'action_id': 'remove', 'target': {'kind': 'item', 'id': 'i_a_0'}, 'reason': 'Requested removal'}]}


def test_remove_support_omits_permitted_optional_chain_as_one_valid_action():
    room, choices, base = supported_scene()
    before = deepcopy(base)
    result = solve(room, removal(), choices, {'intent': 'redesign', 'allow_dependent_omission': True}, base)
    assert [i['status'] for i in result['scene']['items']] == ['removed', 'removed', 'removed']
    assert result['action_outcomes'][0]['affected_item_ids'] == ['i_a_0', 'i_top_0', 'i_lamp_0']
    assert [w['code'] for w in result['warnings']] == ['dependent_omitted', 'dependent_omitted']
    assert result['placed_unit_demand'] == {'sel': 0, 'top': 0, 'lamp': 0}
    assert result['conflicts'] == []
    assert base == before


def test_remove_support_relocates_optional_dependents_to_their_saved_alternative():
    room, choices, base = supported_scene()
    top = next(i for i in base['items'] if i['id'] == 'i_top_0')
    top['anchor']['alternatives'] = [{'type': 'against_wall', 'wall_id': 'w_3', 'alignment': 'center'}]
    result = solve(room, removal(), choices, {'intent': 'redesign', 'allow_dependent_omission': True,
                   'allow_dependent_relocation': True}, base)
    items = {i['id']: i for i in result['scene']['items']}
    assert items['i_a_0']['status'] == 'removed'
    assert items['i_top_0']['status'] == 'new'
    assert items['i_top_0']['placement']['mount'] == 'floor'
    assert items['i_top_0']['anchor']['type'] == 'against_wall'
    assert items['i_lamp_0']['status'] == 'new'
    assert items['i_lamp_0']['placement']['position'][1] == .4
    assert validate_scene(room, result['scene']) == []


def test_support_removal_preserves_a_protected_dependent():
    room, choices, base = supported_scene()
    next(i for i in base['items'] if i['id'] == 'i_lamp_0')['instruction'] = 'keep'
    result = solve(room, removal(), choices, {'intent': 'redesign', 'allow_dependent_omission': True}, base)
    assert result['scene']['items'] == base['items']
    assert result['action_outcomes'][0]['code'] == 'protected_dependent'


def test_requested_anchor_dependent_move_finishes_before_its_target_is_removed():
    room = normalize_room(native_room(), 'capture', 'room')
    choices = {'sel': selection(), 'chair': {**selection((.4, .4, .8), 'chair'), 'selection_id': 'chair'}}
    request = plan({'type': 'room_center'})
    request['adds'].append({**request['adds'][0], 'action_id': 'chair', 'add_id': 'chair', 'category': 'chair',
        'selection_id': 'chair', 'anchor': {'type': 'next_to', 'target': {'kind': 'item', 'id': 'i_a_0'}, 'side': 'left'}})
    base = solve(room, request, choices, {'intent': 'add'})['scene']
    changes = removal()
    changes['moves'] = [{'action_id': 'move-chair', 'target': {'kind': 'item', 'id': 'i_chair_0'},
        'anchor': {'type': 'against_wall', 'wall_id': 'w_3', 'alignment': 'center'}, 'reason': 'Requested move'}]
    result = solve(room, changes, choices, {'intent': 'redesign', 'allow_dependent_omission': True,
        'allow_dependent_relocation': True, 'allow_adjustments': False}, base)
    assert {o['action_id']: o['outcome'] for o in result['action_outcomes']} == {'move-chair': 'applied', 'remove': 'applied'}
    assert next(i for i in result['scene']['items'] if i['id'] == 'i_chair_0')['status'] == 'new'
    assert validate_scene(room, result['scene']) == []


def test_replacement_relocates_the_complete_support_chain_to_the_new_height():
    room, choices, base = supported_scene()
    choices['replacement'] = {**selection((1.6, 1.2, .9)), 'selection_id': 'replacement'}
    request = {'summary': 'Replace support', 'replaces': [{'action_id': 'replace', 'target_item_id': 'i_a_0',
                'selection_id': 'replacement', 'reason': 'Requested replacement'}]}
    result = solve(room, request, choices, {'intent': 'redesign', 'allow_dependent_relocation': True}, base)
    items = {i['id']: i for i in result['scene']['items']}
    assert result['action_outcomes'][0]['outcome'] == 'applied'
    assert items['i_top_0']['placement']['position'][1] == .9
    assert items['i_lamp_0']['placement']['position'][1] == 1.3
    assert validate_scene(room, result['scene']) == []


def test_same_pose_swap_rejects_incompatible_required_support_without_offering_unavailable_changes():
    room, choices, base = supported_scene()
    base['items'] = [i for i in base['items'] if i['id'] != 'i_top_0']
    lamp = next(i for i in base['items'] if i['id'] == 'i_lamp_0')
    lamp['placement'].update(position=[2, .7, 1.5], support_id='i_a_0')
    lamp['anchor']['target']['id'] = 'i_a_0'
    choices['replacement'] = {**selection((1.6, 1.2, .9)), 'selection_id': 'replacement'}
    request = {'replaces': [{'action_id': 'swap', 'target_item_id': 'i_a_0', 'selection_id': 'replacement', 'reason': 'Swap'}]}
    result = solve(room, request, choices, {'intent': 'redesign', 'must_have_selection_ids': ['lamp']}, base)
    assert result['scene']['items'] == base['items']
    assert result['action_outcomes'][0]['outcome'] == 'failed'
    assert not result.get('required_questions')


def test_occupied_restore_preserves_removal_while_an_unrelated_move_succeeds():
    room, choices, base = supported_scene()
    removed = solve(room, removal(), choices, {'intent': 'redesign', 'allow_dependent_omission': True}, base)['scene']
    choices['small'] = {**selection((.4, .4, .5)), 'selection_id': 'small'}
    occupied = solve(room, {'adds': [
        {**plan({'type': 'room_center'})['adds'][0], 'action_id': 'blocker', 'add_id': 'blocker'},
        {**plan()['adds'][0], 'action_id': 'other', 'add_id': 'other', 'selection_id': 'small'}]}, choices,
        {'intent': 'redesign'}, removed)['scene']
    result = solve(room, {'restores': [{'action_id': 'restore', 'removed_item_id': 'i_a_0', 'reason': 'Restore desk'}],
        'moves': [{'action_id': 'move', 'target': {'kind': 'item', 'id': 'i_other_0'},
                   'anchor': {'type': 'against_wall', 'wall_id': 'w_3', 'alignment': 'center'}, 'reason': 'Move other desk'}]},
        choices, {'intent': 'redesign'}, occupied)
    outcomes = {o['action_id']: o for o in result['action_outcomes']}
    assert outcomes['restore']['outcome'] == 'failed' and outcomes['restore']['code'] == 'collision'
    assert outcomes['move']['outcome'] == 'applied'
    assert next(i for i in result['scene']['items'] if i['id'] == 'i_a_0')['status'] == 'removed'
    assert validate_scene(room, result['scene']) == []


@pytest.mark.parametrize('protection,reason', [('keep', 'Kept target requires an explicit unlock.'), ('fixed', 'Permanent fixture cannot be changed or unlocked.')])
def test_direct_remove_cannot_override_protection(store, protection, reason):
    from test_edits import setup_edit, base_request
    api, _, _ = setup_edit(store, {})
    with store.transaction():
        parent = store.get('designs', 'parent')
        item = parent['scene']['items'][0]
        if protection == 'keep':
            item['instruction'] = 'keep'
        else:
            item['fixed_in_place'] = True
        store.put('designs', 'parent', parent)
    api.post('/v1/designs/parent/remove', json={**base_request(), 'item_id': 'i_a_0'})
    operation = api.get('/v1/operations/edit').json()['operation']
    assert operation['state'] == 'rejected'
    assert operation['outcome']['action_outcomes'][0]['reason'] == reason
    assert api.get('/v1/designs/parent').json()['design'] == parent
    assert len(store.list('designs', 'room')) == 1


def test_direct_remove_one_unit_preserves_a_pack_still_needed_by_another_unit(store):
    from test_edits import setup_edit, base_request
    from test_products import offer
    from respace.products import calculate_purchases
    api, _, _ = setup_edit(store, {})
    with store.transaction():
        parent = store.get('designs', 'parent')
        selected = parent['scene']['selections']['sel']
        selected['offer'] = offer('v', '100.00', 2)
        selected['offer']['pack_contents']['components'][0]['dimensions'] = selected['dimensions']
        room = parent['scene']['room']
        request = plan()
        request['adds'].append({**plan()['adds'][0], 'action_id': 'second', 'add_id': 'second',
                                'anchor': {'type': 'against_wall', 'wall_id': 'w_3', 'alignment': 'center'}})
        scene = solve(room, request, {'sel': selected}, {'intent': 'add'})['scene']
        assert len(scene['items']) == 2
        scene.update(design_id='parent', selections={'sel': selected}, purchase_summary=calculate_purchases(scene['items'], {'o_v': selected['offer']}, '200.00'))
        parent['scene'] = scene
        store.put('designs', 'parent', parent)
    api.post('/v1/designs/parent/remove', json={**base_request(), 'item_id': 'i_a_0'})
    operation = api.get('/v1/operations/edit').json()['operation']
    assert operation['state'] == 'succeeded'
    scene = api.get('/v1/designs/' + operation['outcome']['design_id']).json()['design']['scene']
    assert scene['purchase_summary']['total'] == '100.00'
    assert scene['purchase_summary']['lines'][0]['placed_unit_count'] == 1
    assert scene['purchase_summary']['lines'][0]['paid_surplus_count'] == 1


def test_direct_remove_replays_one_child_and_restore_this_preserves_product_and_pose(store):
    from test_edits import setup_edit, base_request
    restored = {'action': 'execute_plan', 'payload': {'plan': {'summary': 'Restore desk', 'restores': [
        {'action_id': 'restore', 'removed_item_id': 'i_a_0', 'reason': 'Requested restore'}]}}}
    api, _, parent = setup_edit(store, restored)
    request = {**base_request('direct-remove'), 'item_id': 'i_a_0'}
    response = api.post('/v1/designs/parent/remove', json=request)
    assert response.status_code == 202, response.text
    operation = api.get('/v1/operations/direct-remove').json()['operation']
    assert operation['state'] == 'succeeded', operation
    removed_id = operation['outcome']['design_id']
    removed = api.get('/v1/designs/' + removed_id).json()['design']
    item = removed['scene']['items'][0]
    assert item['status'] == 'removed' and item['pre_removal_status'] == 'new'
    assert item['product'] == parent['scene']['items'][0]['product']
    assert removed['scene']['purchase_summary']['total'] == '0.00'
    assert api.post('/v1/designs/parent/remove', json=request).json()['operation']['outcome'] == operation['outcome']
    restore = {**base_request('restore'), 'expected_active_design_id': removed_id, 'expected_active_revision': 2,
               'text': 'Restore this', 'selected_item_id': 'i_a_0'}
    api.post('/v1/designs/' + removed_id + '/chat', json=restore)
    operation = api.get('/v1/operations/restore').json()['operation']
    assert operation['state'] == 'succeeded', operation
    child = api.get('/v1/designs/' + operation['outcome']['design_id']).json()['design']
    assert child['scene']['items'][0]['placement'] == parent['scene']['items'][0]['placement']
    assert child['scene']['purchase_summary']['total'] == '50.00'


def setup_supported_api(store, *, must_have=False, result=None):
    from respace.products import calculate_purchases
    from test_edits import setup_edit
    from test_products import offer
    api, model, _ = setup_edit(store, result or {})
    room, choices, _ = supported_scene()
    request = plan({'type': 'room_center'})
    for key in ('top', 'lamp'):
        category = choices[key]['category']
        request['adds'].append({**request['adds'][0], 'action_id': key, 'add_id': key, 'category': category,
            'selection_id': key, 'anchor': {'type': 'on_top_of', 'target': {'kind': 'item', 'id': 'i_a_0' if key == 'top' else 'i_top_0'}}})
    for key, choice in choices.items():
        choice.update(variant_id=key, offer_id='o_' + key, offer=offer(key, '20.00', 1), quantity=1,
                      variant={'variant_id': key, 'title': key, 'category': choice['category'], 'image_references': []})
        choice['dimension_evidence'].update(variant_id=key, dimensions=choice['dimensions'])
        choice['offer']['pack_contents']['components'][0]['dimensions'] = choice['dimensions']
    choices['lamp']['must_have'] = must_have
    scene = solve(room, request, choices, {'intent': 'add'})['scene']
    scene.update(design_id='parent', parent_id=None, selections=choices,
                 purchase_summary=calculate_purchases(scene['items'], {s['offer_id']: s['offer'] for s in choices.values()}, '200.00'))
    with store.transaction():
        store.put('captures', 'capture', {'capture_id': 'capture', 'room_id': 'room', 'state': 'complete'})
        design = store.get('designs', 'parent')
        design.update(scene=scene, selection_snapshot={'selected': list(choices.values())})
        snapshot = store.get('snapshots', 'snapshot')
        snapshot.update(room=room, identity_map=room['identity_map'])
        store.put('snapshots', 'snapshot', snapshot)
        store.put('designs', 'parent', design)
    return api, model, design


def test_must_have_dependent_waits_for_explicit_answer_and_commits_one_undoable_result(store):
    from test_edits import base_request
    api, _, parent = setup_supported_api(store, must_have=True)
    response = api.post('/v1/designs/parent/remove', json={**base_request('remove-support'), 'item_id': 'i_a_0'})
    assert response.status_code == 202
    operation = api.get('/v1/operations/remove-support').json()['operation']
    assert operation['state'] == 'needs_clarification', operation
    question = operation['pending_question']
    assert question['consequence_item_ids'] == ['i_lamp_0']
    assert api.get('/v1/rooms/room').json()['room']['active_design_id'] == 'parent'
    answer = {'operation_id': 'remove-support', 'reply_id': 'approve', 'question_id': question['question_id'],
              'expected_decision_revision': question['decision_revision'], 'expected_question_revision': question['question_revision'],
              'action': 'answer', 'choice_ids': ['allow_consequences']}
    response = api.post('/v1/operations/remove-support/answers', json=answer)
    assert response.status_code == 200, response.text
    operation = api.get('/v1/operations/remove-support').json()['operation']
    assert operation['state'] == 'succeeded', operation
    child = api.get('/v1/designs/' + operation['outcome']['design_id']).json()['design']
    assert all(i['status'] == 'removed' for i in child['scene']['items'])
    assert child['scene']['purchase_summary']['total'] == '0.00'
    assert child['parent_id'] == 'parent'
    undo = {**base_request('undo'), 'expected_active_design_id': child['design_id'], 'expected_active_revision': 2}
    assert api.post('/v1/rooms/room/undo', json=undo).status_code == 200
    assert api.get('/v1/designs/parent').json()['design'] == parent
    assert api.get('/v1/rooms/room').json()['room']['active_design_id'] == 'parent'
