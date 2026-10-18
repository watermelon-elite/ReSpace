from copy import deepcopy

from respace.geometry import normalize_room
from respace.solver import solve, validate_scene
from test_geometry import native_room
from test_solver import plan, selection


def test_partial_edit_moves_exact_base_item_and_failed_addition_has_no_demand():
    room = normalize_room(native_room(), 'capture', 'room')
    base = solve(room, plan(), {'sel': selection()}, {'intent': 'add'})['scene']
    before = deepcopy(base)
    changes = {'summary': 'Move desk and add oversized desk', 'moves': [
        {'action_id': 'move', 'target': {'kind': 'item', 'id': 'i_a_0'},
         'anchor': {'type': 'against_wall', 'wall_id': 'w_3', 'alignment': 'center'}, 'reason': 'Move'}],
        'adds': [{**plan()['adds'][0], 'add_id': 'large', 'action_id': 'large', 'selection_id': 'large'}]}
    result = solve(room, changes, {'sel': selection(), 'large': {**selection((10,10,1)), 'selection_id': 'large'}},
                   {'intent': 'redesign', 'allow_adjustments': False}, base)
    assert result['conflicts'] == []
    assert {o['action_id']: o['outcome'] for o in result['action_outcomes']} == {'move': 'applied', 'large': 'failed'}
    assert result['scene']['items'][0]['id'] == 'i_a_0'
    assert result['scene']['items'][0]['placement']['position'] == [2, 0, 2.7]
    assert result['placed_unit_demand'] == {'sel': 1, 'large': 0}
    assert base == before
    assert validate_scene(room, result['scene']) == []


def test_failed_move_keeps_current_saved_pose_and_failed_swap_keeps_product_and_purchase_snapshot():
    room = normalize_room(native_room(), 'capture', 'room')
    base = solve(room, plan(), {'sel': selection()}, {'intent': 'add'})['scene']
    move = {'summary': 'Move', 'moves': [{'action_id': 'm', 'target': {'kind': 'item', 'id': 'i_a_0'},
        'anchor': {'type': 'against_wall', 'wall_id': 'w_3', 'alignment': 'center'}, 'reason': 'move'}]}
    base = solve(room, move, {}, {'intent': 'redesign'}, base)['scene']
    base['purchase_summary'] = {'total': '100.00', 'immutable': 'prior evidence'}
    before = deepcopy(base)
    changes = {'summary': 'Failed edit', 'moves': [{'action_id': 'm', 'target': {'kind': 'item', 'id': 'i_a_0'},
        'anchor': {'type': 'on_top_of', 'target': {'kind': 'item', 'id': 'missing'}}, 'reason': 'move'}],
        'replaces': [{'action_id': 'r', 'target_item_id': 'i_a_0', 'selection_id': 'large', 'reason': 'swap'}]}
    large = {**selection((10,10,1)), 'selection_id': 'large'}
    result = solve(room, changes, {'large': large}, {'intent': 'redesign'}, base)
    assert all(o['outcome'] == 'failed' for o in result['action_outcomes'])
    assert result['scene']['items'] == before['items']
    assert result['scene']['products'] == before['products']
    assert result['scene']['purchase_summary'] == before['purchase_summary']
    assert result['conflicts'] == []
    assert base == before


def test_support_removal_cannot_leave_floating_item_and_ghost_is_not_present_support():
    room = normalize_room(native_room(), 'capture', 'room')
    request = plan({'type': 'room_center'})
    lamp = {**selection((.2,.2,.4), 'table_lamp'), 'selection_id': 'lamp'}
    request['adds'].append({**request['adds'][0], 'action_id': 'lamp', 'add_id': 'lamp', 'category': 'table_lamp', 'selection_id': 'lamp',
        'anchor': {'type': 'on_top_of', 'target': {'kind': 'addition_unit', 'id': 'a', 'unit_index': 0}}})
    base = solve(room, request, {'sel': selection(), 'lamp': lamp}, {'intent': 'add'})['scene']
    remove = {'summary': 'Remove support', 'removes': [{'action_id': 'r', 'target': {'kind': 'item', 'id': 'i_a_0'}, 'reason': 'remove'}]}
    failed = solve(room, remove, {}, {'intent': 'redesign'}, base)
    assert failed['scene']['items'] == base['items']
    assert failed['action_outcomes'][0]['outcome'] == 'failed'
    remove['removes'].append({'action_id': 'lamp-r', 'target': {'kind': 'item', 'id': 'i_lamp_0'}, 'reason': 'remove lamp'})
    removed = solve(room, remove, {}, {'intent': 'redesign'}, base)
    assert all(o['outcome'] == 'applied' for o in removed['action_outcomes'])
    assert all(i['status'] == 'removed' for i in removed['scene']['items'])
    assert validate_scene(room, removed['scene']) == []
    restore = {'summary': 'Restore lamp', 'restores': [{'action_id': 'restore', 'removed_item_id': 'i_lamp_0', 'reason': 'restore'}]}
    blocked = solve(room, restore, {}, {'intent': 'redesign'}, removed['scene'])
    assert blocked['action_outcomes'][0]['outcome'] == 'failed'
    assert blocked['scene']['items'] == removed['scene']['items']


def test_explicit_unlock_changes_only_target_instruction_and_permanent_fixture_remains_protected():
    room = normalize_room(native_room(), 'capture', 'room')
    room['objects'] = [{'id': 'obj', 'center': [2,.3], 'base_y': 0, 'yaw': 0,
        'size': [1,.5,.7], 'category': 'desk', 'mount': 'floor', 'fixed_in_place': False, 'attrs': {}}]
    base = solve(room, {'adds': []}, {}, {'intent': 'add', 'instructions': {'obj': 'keep'}})['scene']
    actions = {'summary': 'unlock and move', 'unlocks': [{'action_id': 'u', 'target': {'kind': 'object', 'id': 'obj'}, 'explicit_user_unlock_context': 'unlock desk', 'reason': 'user'}],
        'moves': [{'action_id': 'm', 'target': {'kind': 'object', 'id': 'obj'}, 'anchor': {'type': 'room_center'}, 'reason': 'user'}]}
    result = solve(room, actions, {}, {'intent': 'redesign', 'instructions': {'obj': 'keep'}, 'explicit_unlock_ids': ['obj']}, base)
    assert [o['outcome'] for o in result['action_outcomes']] == ['applied', 'applied']
    assert result['scene']['items'][0]['instruction'] == 'decide'
    assert base['items'][0]['instruction'] == 'keep'
    base['items'][0]['fixed_in_place'] = True
    protected = solve(room, actions, {}, {'intent': 'redesign', 'explicit_unlock_ids': ['obj']}, base)
    assert all(o['outcome'] == 'failed' for o in protected['action_outcomes'])
    assert protected['scene']['items'] == base['items']


def test_replacing_original_preserves_identity_and_records_exact_purchase_provenance():
    room = normalize_room(native_room(), 'capture', 'room')
    room['objects'] = [{'id': 'desk', 'center': [2,1.5], 'base_y': 0, 'yaw': 0,
        'size': [1,.5,.7], 'category': 'desk', 'mount': 'floor', 'fixed_in_place': False, 'attrs': {}}]
    base = solve(room, {'adds': []}, {}, {'intent': 'add'})['scene']
    replacement = {'summary': 'Replace original desk', 'replaces': [{'action_id':'r','target_item_id':'i_desk','selection_id':'sel','reason':'new desk'}]}
    result = solve(room, replacement, {'sel':selection((.8,.4,.7))}, {'intent':'redesign'}, base)
    assert not result['conflicts']
    item = result['scene']['items'][0]
    assert item['id'] == 'i_desk' and item['object_id'] == 'desk' and item['origin'] == 'existing'
    assert item['replacement_of_object_id'] == 'desk'
    assert item['original_placement'] == base['items'][0]['original_placement']
    assert item['placement']['position'] == base['items'][0]['placement']['position']
    assert item['selection_id'] == 'sel'
    remove = {'summary':'remove','removes':[{'action_id':'remove','target':{'kind':'item','id':'i_desk'},'reason':'remove'}]}
    removed = solve(room, remove, {}, {'intent':'redesign'}, result['scene'])
    restore = {'summary':'restore','restores':[{'action_id':'restore','removed_item_id':'i_desk','reason':'restore'}]}
    restored = solve(room, restore, {}, {'intent':'redesign'}, removed['scene'])
    assert restored['scene']['items'][0]['replacement_of_object_id'] == 'desk'
    assert restored['scene']['items'][0]['selection_id'] == 'sel'


def test_failed_support_move_revalidates_dependent_addition_against_surviving_base_pose():
    room = normalize_room(native_room(), 'capture', 'room')
    base = solve(room, plan(), {'sel':selection()}, {'intent':'add'})['scene']
    lamp = {**selection((.2,.2,.4), 'table_lamp'), 'selection_id':'lamp'}
    changes = {'summary':'Move table and add lamp', 'moves':[{'action_id':'move','target':{'kind':'item','id':'i_a_0'},
        'anchor':{'type':'against_wall','wall_id':'missing','alignment':'center'},'reason':'move'}],
        'adds':[{**plan()['adds'][0], 'add_id':'lamp','action_id':'lamp','category':'table_lamp','selection_id':'lamp',
        'anchor':{'type':'on_top_of','target':{'kind':'item','id':'i_a_0'}}}]}
    result = solve(room, changes, {'lamp':lamp}, {'intent':'redesign'}, base)
    outcomes = {o['action_id']:o['outcome'] for o in result['action_outcomes']}
    assert outcomes == {'move':'failed', 'lamp':'applied'}
    placed = next(i for i in result['scene']['items'] if i['id'] == 'i_lamp_0')
    assert placed['placement']['position'] == [2,.7,.3]
    assert not result['conflicts']


def test_targeting_new_addition_unit_waits_for_its_creation_before_move():
    room = normalize_room(native_room(), 'capture', 'room')
    request = plan()
    request['moves'] = [{'action_id':'move','target':{'kind':'addition_unit','id':'a','unit_index':0},
        'anchor':{'type':'room_center'},'reason':'move created desk'}]
    result = solve(room, request, {'sel':selection()}, {'intent':'redesign'})
    assert [o['action_id'] for o in result['action_outcomes']] == ['act','move']
    assert all(o['outcome'] == 'applied' for o in result['action_outcomes'])
    assert result['scene']['items'][0]['placement']['position'] == [2,0,1.5]


def test_restore_resolves_retained_support_before_tabletop_dependent_in_any_plan_order():
    room = normalize_room(native_room(), 'capture', 'room')
    request = plan({'type':'room_center'})
    lamp = {**selection((.2,.2,.4), 'table_lamp'), 'selection_id':'lamp'}
    request['adds'].append({**request['adds'][0], 'add_id':'lamp','action_id':'lamp','category':'table_lamp','selection_id':'lamp',
        'anchor':{'type':'on_top_of','target':{'kind':'addition_unit','id':'a','unit_index':0}}})
    base = solve(room, request, {'sel':selection(),'lamp':lamp}, {'intent':'add'})['scene']
    for item in base['items']:
        item['status'] = 'removed'
    restores = {'summary':'Restore arrangement', 'restores':[
        {'action_id':'lamp-r','removed_item_id':'i_lamp_0','reason':'restore'},
        {'action_id':'desk-r','removed_item_id':'i_a_0','reason':'restore'}]}
    result = solve(room, restores, {}, {'intent':'redesign'}, base)
    assert [o['action_id'] for o in result['action_outcomes']] == ['desk-r','lamp-r']
    assert all(o['outcome'] == 'applied' for o in result['action_outcomes'])
    assert not result['conflicts']


def test_move_to_measured_current_pose_is_no_op_despite_optional_null_fields():
    room = normalize_room(native_room(), 'capture', 'room')
    room['objects'] = [{'id':'desk','center':[2,.3],'base_y':0,'yaw':0,'size':[1,.5,.7],
        'category':'desk','mount':'floor','wall_id':'w_1','fixed_in_place':False,'attrs':{}}]
    base = solve(room, {'adds':[]}, {}, {'intent':'add'})['scene']
    changes = {'summary':'Already there','moves':[{'action_id':'move','target':{'kind':'object','id':'desk'},
        'anchor':{'type':'against_wall','wall_id':'w_1','alignment':'center'},'reason':'move'}]}
    result = solve(room, changes, {}, {'intent':'redesign'}, base)
    assert result['action_outcomes'][0]['outcome'] == 'no_op'
    assert result['scene']['items'] == base['items']
