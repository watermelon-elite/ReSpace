from copy import deepcopy

import pytest

from respace.geometry import normalize_room
from respace.solver import solve, validate_scene
from test_geometry import native_room


def selection(size=(1, .5, .7), category="desk"):
    return {"selection_id": "sel", "category": category, "variant_id": "v", "offer_id": "o",
            "title": "Measured desk", "dimensions": list(size),
            "dimension_evidence": {"outcome": "verified", "variant_id": "v", "size_m": list(size)},
            "offer": {"offer_id": "o", "variant_id": "v", "price": "100.00", "currency": "USD"},
            "render": {"kind": "standin", "category": category}}


def plan(anchor=None, quantity=1):
    return {"summary": "Add a desk", "adds": [{"add_id": "a", "action_id": "act", "category": "desk",
            "priority": 1, "quantity": quantity, "anchor": anchor or {"type": "against_wall", "wall_id": "w_1", "alignment": "center"},
            "selection_id": "sel", "reason": "Workspace"}], "moves": [], "removes": [], "replaces": [], "restores": [], "unlocks": []}


def test_floor_addition_uses_verified_dimensions_and_deterministic_unit_identity():
    room = normalize_room(native_room(), "capture", "room")
    result = solve(room, plan(), {"sel": selection()}, {"intent": "add"})
    assert result["conflicts"] == []
    item = result["scene"]["items"][0]
    assert item["id"] == "i_a_0"
    assert item["placement"]["position"] == pytest.approx([2, 0, .3])
    assert item["placement"]["size"] == [1, .5, .7]
    assert item["selection_id"] == "sel"
    assert result == solve(room, plan(), {"sel": selection()}, {"intent": "add"})
    assert validate_scene(room, result["scene"]) == []


def test_optional_does_not_fit_is_omitted_and_required_fit_remains_a_conflict():
    room = normalize_room(native_room(), "capture", "room")
    choices = {"sel": selection((10,10,1))}
    optional = solve(room, plan(), choices, {"intent": "add"})
    assert optional["scene"]["items"] == []
    assert optional["placed_unit_demand"] == {"sel": 0}
    assert optional["omissions"][0]["add_id"] == "a"
    assert optional["conflicts"] == []
    required = solve(room, plan(), choices, {"intent": "add", "must_have_add_ids": ["a"]})
    assert required["conflicts"][0]["code"] == "must_have_unplaced"


def test_nonconvex_centroid_cannot_place_in_missing_floor_and_unverified_size_is_rejected():
    room = normalize_room(native_room(((2,3),(6,3),(6,4),(3,4),(3,7),(2,7))), "capture", "room")
    result = solve(room, plan({"type": "room_center"}), {"sel": selection((.6,.6,.7))}, {"intent": "add"})
    assert result["scene"]["items"] == []
    assert result["warnings"][0]["code"] == "addition_unplaced"
    assert result["omissions"]
    choices = {"sel": selection()}
    choices["sel"]["dimension_evidence"]["outcome"] = "unverified"
    result = solve(room, plan(), choices, {"intent": "add"})
    assert result["action_outcomes"][0]["code"] == "unverified_selection"


def test_fixed_original_blocking_door_is_reported_without_mutating_it():
    room = normalize_room(native_room(), "capture", "room")
    room["zones"] = [{"id": "z", "opening_id": "door", "polygon": [[1,0],[3,0],[3,1],[1,1]]}]
    room["objects"] = [{"id": "obj", "center": [2,.5], "base_y": 0, "yaw": 0,
                        "size": [.6,.4,.7], "category": "radiator", "mount": "floor",
                        "fixed_in_place": True, "attrs": {}}]
    before = deepcopy(room)
    result = solve(room, {"adds": []}, {}, {"intent": "add"})
    assert result["conflicts"][0]["code"] == "blocked_doorway"
    assert result["scene"]["items"][0]["placement"]["position"] == [2,0,.5]
    assert room == before


def test_wall_slide_is_bounded_deterministic_and_units_do_not_overlap():
    room = normalize_room(native_room(), "capture", "room")
    result = solve(room, plan(quantity=2), {"sel": selection((.8,.5,.7))}, {"intent": "add"})
    assert [i["id"] for i in result["scene"]["items"]] == ["i_a_0", "i_a_1"]
    assert result["placed_unit_demand"] == {"sel": 2}
    assert validate_scene(room, result["scene"]) == []


def test_virtual_wall_is_not_an_anchor_and_add_preserves_existing_objects():
    room = normalize_room(native_room(), "capture", "room")
    room["walls"][0]["virtual"] = True
    result = solve(room, plan(), {"sel": selection()}, {"intent": "add"})
    assert result["omissions"][0]["units"][0]["code"] == "bad_anchor"
    changed = plan()
    changed["removes"] = [{"action_id": "remove", "target": {"kind": "object", "id": "o_1"}}]
    assert solve(room, changed, {"sel": selection()}, {"intent": "add"})["conflicts"][0]["code"] == "intent_conflict"


def test_cross_action_dependencies_place_new_support_before_existing_item_move():
    room = normalize_room(native_room(), 'capture', 'room')
    lamp = selection((.2,.2,.4), 'table_lamp')
    base_plan = plan({'type': 'room_center'})
    base_plan['adds'][0].update(category='table_lamp')
    base = solve(room, base_plan, {'sel': lamp}, {'intent': 'add'})['scene']
    support = selection((1.2,.8,.7), 'desk')
    support['selection_id'] = 'desk'
    request = plan()
    request['adds'][0].update(selection_id='desk', priority=99, add_id='support')
    request['moves'] = [{'action_id': 'move', 'target': {'kind': 'item', 'id': 'i_a_0'}, 'anchor':
        {'type': 'on_top_of', 'target': {'kind': 'addition_unit', 'id': 'support', 'add_id': 'support', 'unit_index': 0}}, 'reason': 'on desk'}]
    result = solve(room, request, {'desk': support}, {'intent': 'redesign'}, base)
    assert [o['action_id'] for o in result['action_outcomes']] == ['act', 'move']
    lamp_item = next(i for i in result['scene']['items'] if i['id'] == 'i_a_0')
    assert lamp_item['placement']['position'] == pytest.approx([2, .7, .45])
    assert lamp_item['placement']['support_id'] == 'i_support_0'
    assert result['conflicts'] == []


def test_wall_item_blocks_same_wall_furniture_in_both_overlap_directions():
    from respace.solver import check_overlaps

    room = normalize_room(native_room(), 'capture', 'room')
    room['objects'] = [{'id': 'art', 'center': [2,.07], 'base_y': .8, 'yaw': 0,
        'size': [1,.04,.5], 'category': 'wall_art', 'mount': 'wall', 'wall_id': 'w_1',
        'fixed_in_place': False, 'attrs': {}}]
    result = solve(room, plan(), {'sel': selection((1,.5,1.2))}, {'intent': 'add', 'allow_adjustments': False})
    assert len(result['scene']['items']) == 1
    assert result['action_outcomes'][0]['outcome'] == 'failed'
    scene = deepcopy(result['scene'])
    scene['items'].append({'id': 'desk', 'category': 'desk', 'placement':
        {'position': [2,0,.3], 'yaw': 0, 'size': [1,.5,1.2], 'mount': 'floor', 'wall_id': 'w_1'}})
    assert check_overlaps(room, scene, 'desk') == ['i_art']
    assert check_overlaps(room, scene, 'i_art') == ['desk']


def test_full_redesign_access_omits_only_permitted_optional_additions_and_recomputes_demand():
    room = normalize_room(native_room(((0,0),(6,0),(6,4),(0,4))), 'capture', 'room')
    room['zones'] = [{'id': 'front', 'opening_id': 'front', 'polygon': [[2.5,0],[3.5,0],[3.5,1],[2.5,1]]},
                     {'id': 'back', 'opening_id': 'back', 'polygon': [[2.5,3],[3.5,3],[3.5,4],[2.5,4]]}]
    request = plan({'type': 'room_center'})
    request['adds'][0]['category'] = 'shelf'
    selected = selection((5.6,.3,1.8), 'shelf')
    optional = solve(room, request, {'sel': selected}, {'intent': 'redesign', 'allow_adjustments': False})
    assert optional['conflicts'] == []
    assert optional['scene']['items'] == []
    assert optional['placed_unit_demand'] == {'sel': 0}
    assert optional['action_outcomes'][0]['outcome'] == 'failed'
    assert optional['action_outcomes'][0]['code'] == 'access_omitted'
    required = solve(room, request, {'sel': selected}, {'intent': 'redesign', 'allow_adjustments': False, 'must_have_add_ids': ['a']})
    assert len(required['scene']['items']) == 1
    assert any(c['code'] == 'blocked_access' for c in required['conflicts'])
    prohibited = solve(room, request, {'sel': selected}, {'intent': 'redesign', 'allow_adjustments': False, 'allow_optional_access_removal': False})
    assert any(c['code'] == 'blocked_access' for c in prohibited['conflicts'])


def test_window_anchor_nudges_tall_item_only_when_adjustments_are_allowed():
    room = normalize_room(native_room(), 'capture', 'room')
    room['openings'] = [{'id': 'window', 'wall_id': 'w_1', 'type': 'window', 'offset': 1.5, 'width': 1, 'bottom': .5, 'height': 1}]
    request = plan({'type': 'in_front_of_window', 'opening_id': 'window'})
    nudged = solve(room, request, {'sel': selection((.6,.4,.7))}, {'intent': 'add', 'allow_rotation': False})
    assert nudged['conflicts'] == []
    assert nudged['scene']['items'][0]['placement']['position'] == pytest.approx([2.9,0,.25])
    blocked = solve(room, request, {'sel': selection((.6,.4,.7))}, {'intent': 'add', 'allow_adjustments': False})
    assert blocked['scene']['items'] == []


def test_rug_under_and_tabletop_support_use_current_typed_target_pose():
    room = normalize_room(native_room(), 'capture', 'room')
    request = plan({'type': 'room_center'})
    lamp = selection((.2,.2,.4), 'table_lamp')
    lamp['selection_id'] = 'lamp'
    rug = selection((1.8,1,.02), 'rug')
    rug['selection_id'] = 'rug'
    target = {'kind': 'addition_unit', 'id': 'a', 'add_id': 'a', 'unit_index': 0}
    request['adds'].extend([{**request['adds'][0], 'action_id': 'lamp', 'add_id': 'lamp', 'category': 'table_lamp', 'selection_id': 'lamp', 'priority': 0, 'anchor': {'type': 'on_top_of', 'target': target}},
        {**request['adds'][0], 'action_id': 'rug', 'add_id': 'rug', 'category': 'rug', 'selection_id': 'rug', 'priority': 0, 'anchor': {'type': 'under', 'target': target}}])
    result = solve(room, request, {'sel': selection(), 'lamp': lamp, 'rug': rug}, {'intent': 'add'})
    assert result['conflicts'] == []
    items = {i['id']: i for i in result['scene']['items']}
    assert items['i_lamp_0']['placement']['position'] == [2,.7,1.5]
    assert items['i_rug_0']['placement']['position'] == [2,0,1.5]
    assert items['i_rug_0']['placement']['yaw'] == items['i_a_0']['placement']['yaw']
    oversize = deepcopy(lamp)
    oversize['dimensions'] = [2,2,.4]
    oversize['dimension_evidence']['size_m'] = [2,2,.4]
    failed = solve(room, request, {'sel': selection(), 'lamp': oversize, 'rug': rug}, {'intent': 'add'})
    assert next(o for o in failed['action_outcomes'] if o['action_id'] == 'lamp')['code'] == 'invalid_support'


@pytest.mark.parametrize(('anchor', 'category', 'expected_position', 'expected_yaw'), [
    ({'type': 'next_to', 'side': 'left'}, 'side_table', [1.2,0,.45], 0),
    ({'type': 'next_to', 'side': 'right'}, 'side_table', [2.8,0,.45], 0),
    ({'type': 'next_to', 'side': 'front'}, 'side_table', [2,0,1.15], 3.141592653589793),
    ({'type': 'facing'}, 'side_table', [2,0,1.5], 3.141592653589793),
    ({'type': 'facing'}, 'chair', [2,0,1.85], 3.141592653589793),
])
def test_relative_anchor_orientation_and_specified_gaps(anchor, category, expected_position, expected_yaw):
    room = normalize_room(native_room(), 'capture', 'room')
    room['objects'] = [{'id': 'desk', 'center': [2,.45], 'base_y': 0, 'yaw': 0,
        'size': [1,.8,.7], 'category': 'desk', 'mount': 'floor', 'fixed_in_place': False, 'attrs': {}}]
    anchor = {**anchor, 'target': {'kind': 'object', 'id': 'desk'}}
    request = plan(anchor)
    request['adds'][0]['category'] = category
    result = solve(room, request, {'sel': selection((.4,.4,.5), category)}, {'intent': 'add', 'allow_adjustments': False})
    placed = next(i for i in result['scene']['items'] if i['origin'] == 'new')
    assert placed['placement']['position'] == pytest.approx(expected_position)
    assert placed['placement']['yaw'] == pytest.approx(expected_yaw)
    assert result['conflicts'] == []


def test_on_wall_default_bottom_elevation_clears_tall_furniture_and_explicit_height_is_enforced():
    room = normalize_room(native_room(), 'capture', 'room')
    room['objects'] = [{'id': 'dresser', 'center': [2,.3], 'base_y': 0, 'yaw': 0,
        'size': [1,.5,1.5], 'category': 'dresser', 'mount': 'floor', 'wall_id': 'w_1', 'fixed_in_place': False, 'attrs': {}}]
    request = plan({'type': 'on_wall', 'wall_id': 'w_1', 'alignment': 'center'})
    request['adds'][0]['category'] = 'wall_art'
    result = solve(room, request, {'sel': selection((.6,.04,.5), 'wall_art')}, {'intent': 'add'})
    art = next(i for i in result['scene']['items'] if i['origin'] == 'new')
    assert art['placement']['position'] == pytest.approx([2,1.75,.07])
    assert art['placement']['mount'] == 'wall'
    request['adds'][0]['anchor']['height'] = 1
    blocked = solve(room, request, {'sel': selection((.6,.04,.5), 'wall_art')}, {'intent': 'add', 'allow_adjustments': False})
    assert all(i['origin'] == 'existing' for i in blocked['scene']['items'])


def test_rugs_collide_with_each_other_but_ceiling_and_informational_features_do_not_obstruct_floor():
    room = normalize_room(native_room(), 'capture', 'room')
    room['objects'] = [{'id': 'light', 'center': [2,1.5], 'base_y': 2.3, 'yaw': 0, 'size': [.4,.4,.3],
        'category': 'ceiling_light', 'mount': 'ceiling', 'fixed_in_place': True, 'attrs': {}},
        {'id': 'outlet', 'center': [2,.06], 'base_y': .1, 'yaw': 0, 'size': [.08,.02,.08],
        'category': 'outlet', 'mount': 'wall', 'wall_id': 'w_1', 'fixed_in_place': True, 'attrs': {}}]
    floor = solve(room, plan({'type': 'room_center'}), {'sel': selection()}, {'intent': 'add'})
    assert floor['conflicts'] == []
    request = plan({'type': 'room_center'}, quantity=2)
    request['adds'][0]['category'] = 'rug'
    rugs = solve(room, request, {'sel': selection((1,1,.02), 'rug')}, {'intent': 'add', 'allow_adjustments': False})
    assert rugs['placed_unit_demand']['sel'] == 1
    assert rugs['action_outcomes'][0]['code'] == 'partial_quantity'


def test_versioned_relation_transport_replays_solver_and_purchase_evidence():
    import json
    from pathlib import Path
    from respace.products import calculate_purchases
    from respace.spatial_planning import validate_plan

    fixture = json.loads((Path(__file__).parent/'fixtures/spatial-relations-v1.json').read_text())
    assert fixture['schema_version'] == 1
    validation = validate_plan(fixture['plan'], fixture['snapshot'], fixture['selections'], fixture['constraints'])
    assert not validation['diagnostics'] and not validation['hard_errors']
    result = solve(fixture['snapshot'], fixture['plan'], fixture['selections'], fixture['constraints'])
    assert result == fixture['solve_result']
    assert not validate_scene(fixture['snapshot'], fixture['design_envelope']['design']['scene'])
    purchases = calculate_purchases(result['scene']['items'], {s['offer_id']:s['offer'] for s in fixture['selections'].values()}, '500.00')
    assert purchases == fixture['design_envelope']['design']['scene']['purchase_summary']
    assert purchases['total'] == '400.00'


@pytest.mark.parametrize(('category', 'size', 'expected_position', 'expected_yaw'), [
    ('chair', [.5,.5,.9], [.4035533905932738,0,.4035533905932738], .7853981633974483),
    ('desk', [1,.5,.7], [.55,0,.3], 0),
])
def test_corner_uses_real_wall_gaps_and_category_orientation(category, size, expected_position, expected_yaw):
    room = normalize_room(native_room(), 'capture', 'room')
    request = plan({'type':'corner','corner_id':'c_1'})
    request['adds'][0]['category'] = category
    result = solve(room, request, {'sel':selection(size, category)}, {'intent':'add','allow_adjustments':False})
    assert not result['conflicts']
    item = result['scene']['items'][0]
    assert item['placement']['position'] == pytest.approx(expected_position)
    assert item['placement']['yaw'] == pytest.approx(expected_yaw)


def test_priorities_apply_only_after_dependencies_and_missing_priority_reports_plan_order():
    room = normalize_room(native_room(), 'capture', 'room')
    request = plan({'type':'room_center'})
    request['adds'][0].pop('priority')
    second = {**request['adds'][0], 'action_id':'second','add_id':'second','priority':1}
    request['adds'].append(second)
    result = solve(room, request, {'sel':selection()}, {'intent':'add','allow_adjustments':False})
    assert [o['action_id'] for o in result['action_outcomes']] == ['act','second']
    assert any(w['code'] == 'missing_priority' for w in result['warnings'])
    assert result['scene']['items'][0]['add_id'] == 'a'
