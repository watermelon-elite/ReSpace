import math
from copy import deepcopy

import pytest

from respace.reconstruction import room_from_reconstruction
from respace.solver import solve, validate_scene


def reconstruction():
    """A 4 x 3 m kitchen: window wall with sill and skirting, door, counter, fridge, kettle."""
    def wall(id_, a, b, protrusions=()):
        length = math.dist(a, b)
        return {"id": id_, "node_name": f"scan_{id_}", "a": list(a), "b": list(b), "length": length,
                "inward_normal": [-(b[1] - a[1]) / length, (b[0] - a[0]) / length],
                "virtual": False, "protrusions": list(protrusions)}

    def entity(id_, category, center, base_y, yaw, size, mount, **extra):
        return {"id": id_, "label": id_, "node_name": f"scan_{id_}", "category": category, "center": list(center),
                "base_y": base_y, "yaw": yaw, "size": list(size), "mount": mount, "fixed_in_place": True, **extra}

    return {
        "schema_version": 2, "room_id": "kitchen", "capture_id": "capture", "units": "meters", "up_axis": "+Y",
        "node_pivot": "box_center", "room_from_world": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 1, 1.5, 5, 1],
        "height": 2.6, "floor": {"polygon": [[0, 0], [4, 0], [4, 3], [0, 3]]},
        # Out of winding order on purpose; the reader chains them.
        "walls": [wall("north", (4, 3), (0, 3)), wall("west", (0, 3), (0, 0)),
                  wall("south", (0, 0), (4, 0), [
                      {"entity_id": "sill", "depth": .18, "bottom": .8, "top": .88, "from_a": .9, "to_a": 3.1},
                      {"entity_id": "skirting", "depth": .02, "bottom": 0, "top": .1, "from_a": 0, "to_a": 4}]),
                  wall("east", (4, 0), (4, 3))],
        "openings": [{"id": "window", "type": "window", "wall_id": "south", "offset": 1, "width": 2, "bottom": .9, "height": 1.2},
                     {"id": "door", "type": "door", "wall_id": "north", "offset": 1.5, "width": .9, "bottom": 0, "height": 2.1}],
        "entities": [
            # Flush with the west wall and with the fridge: measured fact, not a conflict.
            entity("counter", "counter", (.3, 1.5), .002, math.pi / 2, (2, .6, .95), "floor",
                   surfaces=[{"top": .9, "clearance_above": .5, "clearance_limited_by": "upper-cabinets"}]),
            entity("fridge", "refrigerator", (.35, 2.75), 0, math.pi / 2, (.5, .7, 1.8), "floor"),
            entity("kettle", "other", (.3, 1.5), .905, math.pi / 2, (.2, .2, .25), "tabletop",
                   collision_class="tabletop", support_id="counter"),
            entity("outlet", "outlet", (.01, 1), .3, math.pi / 2, (.08, .02, .08), "wall", wall_id="west"),
        ],
    }


def chair(size=(.45, .5, .76), category="chair", key="sel"):
    return {"selection_id": key, "category": category, "variant_id": key, "offer_id": key, "title": key,
            "dimensions": list(size), "dimension_evidence": {"outcome": "verified", "variant_id": key, "size_m": list(size)},
            "render": {"kind": "catalog", "category": category, "asset_id": f"asset-{key}", "asset_revision": "1",
                       "authored_bounds": list(size), "scaling_mode": "dimensioned"}}


def add(anchor, category="chair"):
    return {"summary": "", "moves": [], "removes": [], "replaces": [], "restores": [], "unlocks": [],
            "adds": [{"add_id": "a", "action_id": "act", "category": category, "priority": 1, "quantity": 1,
                      "selection_id": "sel", "anchor": anchor}]}


def test_reader_builds_the_solver_room_model_with_stable_ids_and_derived_structure():
    room = room_from_reconstruction(reconstruction(), "room")
    assert room["validity"] == {"usable": True, "reasons": [], "warnings": []}
    assert [w["source_ids"][0] for w in room["walls"]] == ["south", "east", "north", "west"]
    assert room["walls"][0]["inward_normal"] == pytest.approx([0, 1])
    assert [p["source_id"] for p in room["walls"][0]["protrusions"]] == ["sill", "skirting"]
    assert [(o["id"], o["type"], o["wall_id"]) for o in room["openings"]] == [("door_1", "door", "w_3"), ("window_2", "window", "w_1")]
    assert [z["opening_id"] for z in room["zones"]] == ["door_1"]
    assert len(room["corners"]) == 4
    counter, fridge = room["objects"]
    assert (counter["id"], counter["category"], counter["base_y"], counter["against_wall"]) == ("o_1", "counter", 0, "w_4")
    assert fridge["category"] == "refrigerator"
    kettle, = room["obstacles"]
    assert (kettle["support_id"], kettle["collision_class"], kettle["base_y"]) == ("o_1", "tabletop", .9)
    outlet, = room["wall_features"]
    assert (outlet["type"], outlet["wall_id"], outlet["offset"]) == ("outlet", "w_4", pytest.approx(2))
    assert room["render"] == {"node_pivot": "box_center", "nodes": {
        "w_1": "scan_south", "w_2": "scan_east", "w_3": "scan_north", "w_4": "scan_west",
        "o_1": "scan_counter", "o_2": "scan_fridge", "x_1": "scan_kettle"}}
    assert room["identity_map"]["kettle"] == {"kind": "obstacle", "id": "x_1"}


@pytest.mark.parametrize("change, code", [
    (lambda d: d.update(schema_version=1), "unsupported_schema_version"),
    (lambda d: d.update(node_pivot=None), "unknown_node_pivot"),
    (lambda d: d["floor"].update(polygon=d["floor"]["polygon"][::-1]), "invalid_boundary"),
    (lambda d: d["walls"][0].update(inward_normal=[0, 1]), "wall_normal_mismatch"),
    (lambda d: d["walls"][1].update(a=[0, 2.5]), "wall_length_mismatch"),
    (lambda d: d["walls"].pop(), "walls_not_closed"),
    (lambda d: d["openings"][0].update(width=3.5), "invalid_opening"),
    (lambda d: d["entities"][2].pop("collision_class"), "unknown_category"),
    (lambda d: d["entities"][2].update(category="kettle"), "unknown_category"),
    (lambda d: d["entities"][2].update(base_y=1.2), "invalid_support"),
    (lambda d: d["entities"][1].update(base_y=.3), "missing_support"),
    (lambda d: d["entities"][3].pop("wall_id"), "missing_wall_association"),
    (lambda d: d["entities"][0]["surfaces"][0].update(top=1.5), "invalid_surface"),
])
def test_reader_rejects_evidence_it_would_otherwise_have_to_guess(change, code):
    document = reconstruction()
    change(document)
    room = room_from_reconstruction(document, "room")
    assert not room["validity"]["usable"]
    assert code in [reason["code"] for reason in room["validity"]["reasons"]]


@pytest.mark.parametrize("height, gap", [(.76, .02 + .05), (1.8, .18 + .05)])
def test_against_wall_stands_off_the_deepest_protrusion_at_the_items_height(height, gap):
    room = room_from_reconstruction(reconstruction(), "room")
    result = solve(room, add({"type": "against_wall", "wall_id": "w_1", "alignment": "center"}),
                   {"sel": chair((.45, .5, height))}, {"intent": "add"})
    assert result["conflicts"] == []
    assert result["scene"]["items"][-1]["placement"]["position"] == pytest.approx([2, 0, .25 + gap])


def test_protrusions_block_items_that_reach_them():
    room = room_from_reconstruction(reconstruction(), "room")
    sofa = {"type": "room_center"}
    result = solve(room, add(sofa), {"sel": chair((.45, .5, 1.8))}, {"intent": "add"})
    item = result["scene"]["items"][-1]
    # A tall item pressed against the bare wall under the sill collides with it.
    item["placement"]["position"] = [2, 0, .25 + .02 + .05]
    assert {"code": "collision", "target_ids": [item["id"]], "structure": ["wall"], "action_ids": [],
            "reason": "Item violates required placement clearance."} in validate_scene(room, result["scene"])


def test_on_top_of_uses_the_recorded_surface_slides_past_clutter_and_respects_headroom():
    room = room_from_reconstruction(reconstruction(), "room")
    anchor = {"type": "on_top_of", "target": {"kind": "object", "id": "o_1"}}
    result = solve(room, add(anchor, "table_lamp"), {"sel": chair((.25, .25, .4), "table_lamp")}, {"intent": "add"})
    assert result["conflicts"] == []
    x, y, z = result["scene"]["items"][-1]["placement"]["position"]
    # The work surface, not the 0.95 m box top; moved 0.3 m along the counter, clear of the kettle.
    assert (x, y, abs(z - 1.5)) == pytest.approx((.3, .9, .3))
    tall = solve(room, add(anchor, "table_lamp"), {"sel": chair((.25, .25, .6), "table_lamp")}, {"intent": "add"})
    assert tall["omissions"][0]["units"][0]["code"] == "no_headroom"


def test_a_measured_conflict_is_reported_without_blocking_unrelated_placement():
    document = reconstruction()
    document["entities"].append({"id": "bin", "label": "bin", "node_name": None, "category": "cabinet",
                                 "center": [2, 2.75], "base_y": 0, "yaw": math.pi, "size": [.5, .4, .8],
                                 "mount": "floor", "fixed_in_place": False})
    room = room_from_reconstruction(document, "room")
    result = solve(room, add({"type": "against_wall", "wall_id": "w_1", "alignment": "center"}),
                   {"sel": chair()}, {"intent": "add"})
    assert result["action_outcomes"][0]["outcome"] == "applied"
    assert [c["code"] for c in result["conflicts"]] == ["blocked_doorway"]
    assert result["conflicts"][0]["target_ids"] == ["i_o_1"]


def test_moving_a_measured_object_checks_it_like_any_placement():
    room = room_from_reconstruction(reconstruction(), "room")
    result = solve(room, {"adds": []}, {}, {"intent": "add"})
    assert result["conflicts"] == []
    fridge = next(i for i in result["scene"]["items"] if i["object_id"] == "o_2")
    fridge["placement"] = deepcopy(fridge["placement"])
    fridge["placement"]["position"][0] = .34  # 1 cm into the wall, but moved: no measurement slack
    assert any(c["target_ids"] == [fridge["id"]] for c in validate_scene(room, result["scene"]))
