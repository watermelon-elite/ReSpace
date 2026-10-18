import copy
import json
import math

import numpy as np
import open3d as o3d
import pytest

from respace_reconstruction import astra_room
from respace_reconstruction.categories import category, CATEGORIES
from respace_reconstruction.instances import stable_id
from respace_reconstruction.room_document import RoomDocument, export_room, load_room
from respace_reconstruction.scene import SceneBundle
from respace_reconstruction.store import atomic_json
from test_astra_room import box, room_plan
from test_walkthrough import room_capture


@pytest.fixture
def exported_room(tmp_path):
    return build_room(tmp_path)


def build_room(tmp_path, extra_entities=()):
    manifest, _ = room_capture(tmp_path)
    room = json.loads((tmp_path/"inputs"/manifest.room_export.filename).read_text())
    door = copy.deepcopy(room["walls"][0])
    door.update(identifier="entry", dimensions=[.8, 2., 0.])
    door["transform"][12:15] = [1., 1., -2.]
    room["doors"] = [door]
    shell = astra_room.measured_structure({"roomplan": room})
    inventory = room_plan()
    counter = inventory["entities"][0]
    counter.update(id="counter", label="Gray countertop with backsplash", category="countertop", kind="fixed", yaw=.33,
        parts=[box([0., .86, -.4], [1.6, .1, .6]), box([0., 1., -.68], [1.6, .2, .04])])
    light = copy.deepcopy(counter)
    light.update(id="light", label="Undercabinet light", category="lighting_fixture", support_id="counter",
                 parts=[box([0., 1.47, -.4], [1.6, .1, .6])])
    inventory["entities"].append(light)
    inventory["entities"].extend(extra_entities)
    plan = astra_room.assemble_room(shell, astra_room.FurnishingPlan.model_validate(inventory))
    output = tmp_path/"export"; output.mkdir()
    entities, bindings, meshes, _, _ = astra_room.compile_room(plan, {"frame-0"}, output, o3d)
    nav = {
        "floor_polygons": [[[-2,-2],[2,-2],[2,2],[-2,2]]], "floor_height": 0.,
        "spawn_position": [1.,1.6,1.], "spawn_yaw": 0.}
    bundle = SceneBundle(capture_id=manifest.capture_id, scene_id="room", reconstruction_revision=1,
        entities=entities, materials=bindings, navigation=nav, ready=True)
    document = export_room(bundle, plan, room, meshes, output)
    atomic_json(output/"scene.json", bundle.model_dump())
    return output, bundle, document


def test_export_has_real_bottom_pivots_oriented_size_walls_openings_and_schema(exported_room):
    output, bundle, document = exported_room
    loaded = load_room(output)
    assert loaded.node_pivot == "bottom_center" and loaded.units == "meters"
    assert loaded.floor.polygon[0] == loaded.floor.polygon[-1]
    assert loaded.floor.area == 16 and loaded.height == 2.5
    assert len(loaded.walls) == 4 and len(loaded.openings) == len(loaded.zones) == 1
    counter = next(e for e in loaded.entities if e.id == "counter")
    assert counter.category == "counter" and counter.fixed_in_place
    assert counter.yaw == pytest.approx(.33)
    assert counter.size == pytest.approx([1.6, .6, .29])
    assert counter.base_y == pytest.approx(.81)
    assert len(counter.center) == 2
    assert loaded.openings[0].offset == pytest.approx(2.6)
    # The countertop work surface is below the backsplash's box top.
    surface = next(s for s in counter.surfaces if abs(s.top-.91) < .001)
    assert surface.clearance_above == pytest.approx(.51, abs=.001)
    assert surface.clearance_limited_by == "light"
    assert len(loaded.entities) == 2  # Structure has separate sections.
    assert (output/"room.schema.json").is_file()
    assert document.model_dump() == loaded.model_dump()
    encoded = json.loads((output/"room.json").read_text())
    assert all("position" not in item and "center" in item and "base_y" in item for item in encoded["entities"])
    assert "offset_from_a" not in encoded["openings"][0] and "offset" in encoded["openings"][0]
    schema = json.loads((output/"room.schema.json").read_text())
    assert {"center", "base_y"} <= set(schema["$defs"]["PlacementEntity"]["required"])
    assert schema["$defs"]["PlacementEntity"]["properties"]["collision_class"]["enum"] == ["floor", "wall", "tabletop", "ceiling", "none"]


@pytest.mark.parametrize("fault", ["pivot", "yaw", "size", "normal", "category", "support", "winding", "transform"])
def test_invalid_placement_contract_is_rejected_instead_of_guessed(exported_room, fault):
    output, bundle, document = exported_room
    data = document.model_dump()
    if fault == "pivot": data["entities"][0]["center"][0] += .02
    elif fault == "yaw": data["entities"][0]["yaw"] += math.pi/90
    elif fault == "size": data["entities"][0]["size"][0] += .02
    elif fault == "normal": data["walls"][0]["inward_normal"][0] += .1
    elif fault == "category": data["entities"][0]["category"] = "made_up"
    elif fault == "support": data["entities"][0].update(mount="tabletop", support_id=None)
    elif fault == "winding": data["floor"]["polygon"].reverse()
    else: data["room_from_world"][0] = 2.
    atomic_json(output/"room.json", data)
    with pytest.raises(ValueError):
        load_room(output)


def test_explicit_collision_class_preserves_unknown_items(exported_room):
    _, _, document = exported_room
    data = document.model_dump()
    data["entities"][0]["category"] = "other"
    assert RoomDocument.model_validate(data).entities[0].collision_class == "floor"


@pytest.mark.parametrize("identifier,label,expected", [
    ("appliance", "Refrigerator", "refrigerator"), ("functional_equipment", "Outlet", "outlet"),
    ("functional_equipment", "Switch", "light_switch"), ("countertop", "Countertop", "counter"),
    ("storage_furniture", "Cabinets", "cabinet"), ("curtain", "Window shades", "curtain"),
    ("lighting_fixture", "Ceiling light", "ceiling_light"), ("electronics", "Television", "tv"),
    ("appliance", "Kettle on countertop", "other"), ("faucet", "Faucet", "other"),
    ("appliance", "Grill", "other"), ("functional_equipment", "Thermostat", "other"),
    ("functional_equipment", "Sensor", "other"), ("appliance", "Microwave", "other"),
    ("electronics", "Desktop computer", "other"),
    ("faucet", "Chrome faucet above countertop", "other"),
    ("functional_equipment", "Thermostat beside light switch", "other"),
    ("seating", "Chair next to dining table", "chair"),
    ("table", "Dining table with chairs", "table"),
])
def test_categories_use_confirmed_backend_ids_and_other(identifier, label, expected):
    assert category(identifier, label) == expected
    assert not {"kettle", "faucet", "grill", "thermostat", "sensor", "microwave", "computer"} & CATEGORIES


def test_unsupported_items_keep_their_labels_and_mount_specific_collision_classes(tmp_path):
    def item(identifier, label, perception_category, kind, parts, support=None):
        entity = copy.deepcopy(room_plan()["entities"][0])
        entity.update(id=identifier, label=label, category=perception_category, kind=kind, parts=parts, support_id=support)
        return entity
    extras = [
        item("kettle", "Kettle on countertop", "appliance", "furniture", [box([0., 1.06, -.4], [.2, .3, .2])], "counter"),
        item("thermostat", "Thermostat", "functional_equipment", "fixed", [box([-.9, 1.1, -1.96], [.2, .2, .08])], stable_id("wall", "wall-0")),
        item("sensor", "Ceiling sensor", "functional_equipment", "fixed", [box([-.7, 2.45, 0.], [.1, .1, .1])]),
        item("grill", "Grill", "appliance", "furniture", [box([1.2, .3, 0.], [.4, .6, .4])]),
        item("rug", "Rug", "rug", "furniture", [box([1.2, .01, 1.], [.3, .02, .3])]),
    ]
    output, _, document = build_room(tmp_path, extras)
    entities = {e.id: e for e in document.entities}
    for identity, collision in (("kettle", "tabletop"), ("thermostat", "wall"), ("sensor", "ceiling"), ("grill", "floor")):
        assert entities[identity].category == "other"
        assert entities[identity].collision_class == entities[identity].mount == collision
        assert entities[identity].label == next(e["label"] for e in extras if e["id"] == identity)
    assert entities["kettle"].support_id == "counter"
    assert entities["kettle"].base_y == pytest.approx(.91)
    assert entities["thermostat"].wall_id == stable_id("wall", "wall-0")
    assert entities["rug"].collision_class == "none"
    assert load_room(output).model_dump() == document.model_dump()


def test_wall_protrusions_keep_separate_depths_at_each_height(tmp_path):
    trim = copy.deepcopy(room_plan()["entities"][0])
    trim.update(id="trim", label="Window sill and skirting", category="architectural_detail", kind="fixed",
        parts=[box([-.9, .05, -1.9875], [.8, .1, .025]), box([-.9, .808, -1.91], [.8, .07, .18])])
    _, _, document = build_room(tmp_path, [trim])
    wall = next(w for w in document.walls if w.id == stable_id("wall", "wall-0"))
    protrusions = [p for p in wall.protrusions if p.entity_id == "trim"]
    assert len(protrusions) == 2
    skirting, sill = sorted(protrusions, key=lambda p: p.bottom)
    assert (skirting.depth, skirting.bottom, skirting.top) == pytest.approx((.025, 0., .1))
    assert (sill.depth, sill.bottom, sill.top) == pytest.approx((.18, .773, .843))
    assert (sill.from_a, sill.to_a) == pytest.approx((.7, 1.5))
    # A placement consumer can apply the agreed 5cm from the deepest front at
    # the candidate's height, without incorrectly extending the sill to floor.
    def clearance(bottom, top):
        return .05+max((p.depth for p in protrusions if p.bottom < top and p.top > bottom), default=0.)
    assert clearance(0., .5) == pytest.approx(.075)
    assert clearance(0., 1.) == pytest.approx(.23)
    assert clearance(1., 1.5) == pytest.approx(.05)


@pytest.mark.parametrize("fault", ["position", "offset_from_a", "object_mount", "old_collision", "missing_collision"])
def test_proposed_names_and_unclassified_fallbacks_are_rejected(exported_room, fault):
    _, _, document = exported_room
    data = document.model_dump()
    if fault == "position": data["entities"][0]["position"] = [0., 0., 0.]
    elif fault == "offset_from_a": data["openings"][0]["offset_from_a"] = data["openings"][0].pop("offset")
    elif fault == "object_mount": data["entities"][0]["mount"] = "object"
    elif fault == "old_collision": data["entities"][0]["collision_class"] = "solid"
    else:
        data["entities"][0]["category"] = "other"
        data["entities"][0].pop("collision_class")
    with pytest.raises(ValueError):
        RoomDocument.model_validate(data)
