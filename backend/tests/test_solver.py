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
