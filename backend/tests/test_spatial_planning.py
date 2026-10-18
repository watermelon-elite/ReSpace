import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from respace.geometry import normalize_room
from respace.spatial_planning import GeminiSpatialPlanner, PlanningFailure, validate_plan
from test_geometry import native_room
from test_solver import plan, selection


def test_plan_filters_unknown_optional_ids_and_rejects_metric_anchor_fields():
    room = normalize_room(native_room(), "capture", "room")
    raw = plan()
    bad = deepcopy(raw["adds"][0])
    bad.update(add_id="bad", action_id="bad", anchor={"type": "room_center", "x": 2, "z": 3})
    raw["adds"].append(bad)
    result = validate_plan(raw, room, {"sel": selection()}, {"intent": "add"})
    assert len(result["plan"]["adds"]) == 1
    assert result["invalid_count"] == 1
    assert not result["retry_malformed"]
    assert result["diagnostics"][0]["action_id"] == "bad"


def test_missing_cyclic_and_rejected_addition_references_are_filtered_without_losing_hard_requirement():
    room = normalize_room(native_room(), "capture", "room")
    raw = plan()
    raw["adds"][0]["anchor"] = {"type": "next_to", "target": {"kind": "addition_unit", "id": "b", "add_id": "b", "unit_index": 0}, "side": "left"}
    second = deepcopy(raw["adds"][0])
    second.update(add_id="b", action_id="b", anchor={"type": "next_to", "target": {"kind": "addition_unit", "id": "a", "add_id": "a", "unit_index": 0}, "side": "left"})
    raw["adds"].append(second)
    result = validate_plan(raw, room, {"sel": selection()}, {"intent": "add", "must_have_add_ids": ["a"]})
    assert result["plan"]["adds"] == []
    assert result["retry_malformed"]
    assert result["hard_errors"][0]["code"] == "missing_must_have"


def test_kept_permanent_and_add_intent_cannot_be_overridden_by_model():
    room = normalize_room(native_room(), "capture", "room")
    room["objects"] = [{"id": "obj", "category": "desk", "fixed_in_place": False}]
    raw = {"summary": "Remove", "removes": [{"action_id": "r", "target": {"kind": "object", "id": "obj"}, "reason": "space"}]}
    result = validate_plan(raw, room, {}, {"intent": "redesign", "instructions": {"obj": "keep"}})
    assert result["plan"]["removes"] == []
    result = validate_plan(raw, room, {}, {"intent": "add"})
    assert result["plan"]["removes"] == []


def test_real_adapter_sends_room_selections_and_photos_and_retries_malformed_once():
    calls = []
    responses = [{"summary": "bad", "adds": [{"x": 3}]}, plan()]
    async def generate(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text=json.dumps(responses.pop(0)), usage_metadata=None)
    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    room = normalize_room(native_room(), "capture", "room")
    result = asyncio.run(GeminiSpatialPlanner(client=client, model="configured-model").plan(room, {"sel": selection()}, {}, [b"photo1", b"photo2"], {"intent": "add"}))
    assert result["plan"]["adds"][0]["selection_id"] == "sel"
    assert len(calls) == 2
    assert calls[0]["model"] == "configured-model"
    assert calls[0]["contents"][1].inline_data.data == b"photo1"
    assert '"w_1"' in calls[0]["contents"][0].text
    assert 'Optional reference' in calls[0]['contents'][0].text
    assert '# ReSpace layout reasoning context' in calls[0]['contents'][0].text


def test_geometry_only_local_mode_is_explicit_and_preserves_normal_photo_requirement():
    calls = []
    async def generate(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text=json.dumps(plan()), usage_metadata=None)
    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    room = normalize_room(native_room(), 'capture', 'room')
    for photos in ([], [b'only-one-photo']):
        with pytest.raises(PlanningFailure) as failure:
            asyncio.run(GeminiSpatialPlanner(client=client, model='model').plan(room, {'sel': selection()}, {}, photos, {'intent': 'add'}))
        assert failure.value.code == 'missing_planning_photos'
    assert calls == []
    planner = GeminiSpatialPlanner(client=client, model='model', allow_geometry_only=True)
    result = asyncio.run(planner.plan(room, {'sel': selection()}, {}, [], {'intent': 'add'}))
    assert result['plan']['adds'][0]['selection_id'] == 'sel'
    assert len(calls[0]['contents']) == 1
    assert 'geometry-only test with no room photos' in calls[0]['contents'][0].text


def test_provider_failures_are_bounded_and_hard_requirement_cannot_publish():
    calls = []
    async def generate(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("provider unavailable")
    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    room = normalize_room(native_room(), "capture", "room")
    with pytest.raises(PlanningFailure) as failure:
        asyncio.run(GeminiSpatialPlanner(client=client, model="model").plan(room, {}, {}, [b"p1", b"p2"], {"intent": "add"}))
    assert failure.value.code == "provider_error"
    assert len(calls) == 2


def test_verified_equivalent_question_preserves_private_candidate_and_resumes_same_evidence():
    from respace.solver import solve
    from respace.spatial_planning import repair_candidate
    from test_products import offer

    room = normalize_room(native_room(), "capture", "room")
    original = selection((10,10,1))
    alternative = selection()
    alternative.update(selection_id="small", variant_id="small-v", offer_id="o_small-v")
    alternative["dimension_evidence"]["variant_id"] = "small-v"
    alternative["offer"] = offer("small-v", "100.00", 1)
    original["offer"] = offer("v", "100.00", 1)
    original["offer_id"] = original["offer"]["offer_id"]
    constraints = {"intent": "add", "must_have_add_ids": ["a"], "explicit_selection_ids": ["sel"], "approved_ceiling": "200.00"}
    original_plan = plan()
    result = solve(room, original_plan, {"sel": original}, constraints)
    pending = repair_candidate(room, original_plan, {"sel": original}, constraints, result, {"sel": [alternative]})
    assert pending["state"] == "awaiting_question"
    assert pending["plan"] == original_plan
    assert pending["solve_result"] == result
    assert pending["question"]["choices"][0]["id"] == "small"
    resumed = repair_candidate(room, pending["plan"], pending["selections"], constraints,
                               pending["solve_result"], {"sel": [alternative]}, approved_repair={"add_id": "a", "selection_id": "small"})
    assert resumed["state"] == "complete"
    assert resumed["solve_result"]["scene"]["purchase_summary"]["total"] == "100.00"
    assert resumed["solve_result"]["scene"]["items"][0]["id"] == "i_a_0"
    assert resumed["solve_result"]["scene"]["room"] == room


def test_explicit_unlock_allows_same_command_move_and_cross_action_cycles_are_rejected():
    room = normalize_room(native_room(), 'capture', 'room')
    room['objects'] = [{'id': 'obj', 'category': 'desk', 'fixed_in_place': False}]
    raw = {'summary': 'Unlock and move', 'unlocks': [{'action_id': 'u', 'target': {'kind': 'object', 'id': 'obj'},
        'explicit_user_unlock_context': 'unlock and move the desk', 'reason': 'user'}],
        'moves': [{'action_id': 'm', 'target': {'kind': 'object', 'id': 'obj'},
        'anchor': {'type': 'room_center'}, 'reason': 'move'}]}
    result = validate_plan(raw, room, {}, {'intent': 'redesign', 'instructions': {'obj': 'keep'}, 'explicit_unlock_ids': ['obj']})
    assert result['invalid_count'] == 0
    assert len(result['plan']['moves']) == 1
    raw['adds'] = plan()['adds']
    raw['adds'][0]['anchor'] = {'type': 'next_to', 'target': {'kind': 'object', 'id': 'obj'}, 'side': 'left'}
    raw['moves'][0]['anchor'] = {'type': 'next_to', 'target': {'kind': 'addition_unit', 'id': 'a', 'add_id': 'a', 'unit_index': 0}, 'side': 'right'}
    result = validate_plan(raw, room, {'sel': selection()}, {'intent': 'redesign', 'explicit_unlock_ids': ['obj']})
    assert result['plan']['moves'] == []
    assert result['plan']['adds'] == []
    assert sum(d['code'] == 'invalid_dependency' for d in result['diagnostics']) == 2


def test_typed_alternative_anchors_are_validated_and_respect_repair_permissions():
    from respace.solver import solve

    room = normalize_room(native_room(), 'capture', 'room')
    room['zones'] = [{'id':'z', 'opening_id':'door', 'polygon':[[1,0],[3,0],[3,1],[1,1]]}]
    request = plan({'type':'against_wall','wall_id':'w_1','alignment':'center',
        'alternatives':[{'type':'against_wall','wall_id':'w_3','alignment':'center'}]})
    validation = validate_plan(request, room, {'sel':selection()}, {'intent':'add'})
    assert not validation['invalid_count']
    allowed = solve(room, validation['plan'], {'sel':selection()}, {'intent':'add','allow_rotation':False})
    assert allowed['scene']['items'][0]['placement']['position'] == [2,0,2.7]
    denied = solve(room, validation['plan'], {'sel':selection()}, {'intent':'add','allow_rotation':False,'allow_alternative_anchors':False})
    assert denied['scene']['items'] == []


def test_alternative_window_anchor_cannot_bypass_sill_clearance():
    from respace.solver import solve

    room = normalize_room(native_room(), 'capture', 'room')
    room['zones'] = [{'id':'z', 'opening_id':'door', 'polygon':[[0,0],[4,0],[4,1],[0,1]]}]
    room['openings'] = [{'id':'window','type':'window','wall_id':'w_3','offset':0,'width':4,'bottom':.4,'height':1}]
    request = plan({'type':'against_wall','wall_id':'w_1','alignment':'center',
        'alternatives':[{'type':'in_front_of_window','opening_id':'window'}]})
    result = solve(room, request, {'sel':selection()}, {'intent':'add','allow_rotation':False})
    assert result['scene']['items'] == []


def test_addition_can_depend_on_accepted_restore_but_cannot_target_an_unrestored_ghost():
    from respace.solver import solve

    room = normalize_room(native_room(), 'capture', 'room')
    base = solve(room, plan(), {'sel':selection()}, {'intent':'add'})['scene']
    base['items'][0]['status'] = 'removed'
    lamp = {**selection((.2,.2,.4), 'table_lamp'), 'selection_id':'lamp'}
    request = {'summary':'Bring back desk and lamp', 'restores':[{'action_id':'restore','removed_item_id':'i_a_0','reason':'restore'}],
        'adds':[{**plan()['adds'][0], 'action_id':'lamp','add_id':'lamp','category':'table_lamp','selection_id':'lamp',
        'anchor':{'type':'on_top_of','target':{'kind':'item','id':'i_a_0'}}}]}
    validation = validate_plan(request, room, {'lamp':lamp}, {'intent':'redesign'}, base)
    assert not validation['diagnostics']
    result = solve(room, validation['plan'], {'lamp':lamp}, {'intent':'redesign'}, base)
    assert [o['outcome'] for o in result['action_outcomes']] == ['applied','applied']
    request['restores'] = []
    rejected = validate_plan(request, room, {'lamp':lamp}, {'intent':'redesign'}, base)
    assert rejected['plan']['adds'] == []
