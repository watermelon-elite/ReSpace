import copy
import json
import math

import numpy as np
import open3d as o3d
import pytest
from shapely import Polygon, union_all

from respace_reconstruction import astra_room
from respace_reconstruction.categories import category, CATEGORIES
from respace_reconstruction.instances import stable_id
from respace_reconstruction.room_document import RoomDocument, export_room, load_room, surface_shape
from respace_reconstruction.scene import SceneBundle
from respace_reconstruction.store import atomic_json
from test_astra_room import box, room_plan
from test_walkthrough import room_capture


@pytest.fixture
def exported_room(tmp_path):
    return build_room(tmp_path)


def build_room(tmp_path, extra_entities=(), configure=None, configure_room=None):
    manifest, _ = room_capture(tmp_path)
    room = json.loads((tmp_path/"inputs"/manifest.room_export.filename).read_text())
    door = copy.deepcopy(room["walls"][0])
    door.update(identifier="entry", dimensions=[.8, 2., 0.])
    door["transform"][12:15] = [1., 1., -2.]
    room["doors"] = [door]
    if configure_room is not None:
        configure_room(room)
    shell = astra_room.measured_structure({"roomplan": room})
    inventory = room_plan()
    counter = inventory["entities"][0]
    counter.update(id="counter", label="Gray countertop with backsplash", category="countertop", kind="fixed", yaw=.33,
        parts=[box([0., .405, -.4], [1.6, .81, .6]),
               box([0., .86, -.4], [1.6, .1, .6]), box([0., 1., -.68], [1.6, .2, .04])])
    light = copy.deepcopy(counter)
    light.update(id="light", label="Undercabinet light", category="lighting_fixture", support_id=stable_id("wall", "wall-0"),
                 parts=[box([0., 1.47, -.4], [1.6, .1, .6])])
    inventory["entities"].append(light)
    inventory["entities"].extend(extra_entities)
    if configure is not None:
        configure(inventory)
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
    assert counter.size == pytest.approx([1.6, .6, 1.1])
    assert counter.base_y == pytest.approx(0.)
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


@pytest.mark.parametrize("fault", ["position", "offset_from_a", "object_mount", "old_collision", "missing_collision",
                                   "null_node", "null_asset", "null_clearance"])
def test_proposed_names_and_unclassified_fallbacks_are_rejected(exported_room, fault):
    _, _, document = exported_room
    data = document.model_dump()
    if fault == "position": data["entities"][0]["position"] = [0., 0., 0.]
    elif fault == "offset_from_a": data["openings"][0]["offset_from_a"] = data["openings"][0].pop("offset")
    elif fault == "object_mount": data["entities"][0]["mount"] = "object"
    elif fault == "old_collision": data["entities"][0]["collision_class"] = "solid"
    elif fault == "null_node": data["entities"][0]["node_name"] = None
    elif fault == "null_asset": data["entities"][0]["asset"] = None
    elif fault == "null_clearance": data["entities"][0]["surfaces"][0]["clearance_above"] = None
    else:
        data["entities"][0]["category"] = "other"
        data["entities"][0].pop("collision_class")
    with pytest.raises(ValueError):
        RoomDocument.model_validate(data)


@pytest.mark.parametrize("fault", ["missing_pivot", "wall_order", "off_outline", "broken_join",
                                   "floating_floor", "ceiling_gap", "floating_tabletop", "wrong_support_position"])
def test_topology_and_mount_geometry_are_required(exported_room, fault):
    _, _, document = exported_room
    data = document.model_dump()
    if fault == "missing_pivot":
        data.pop("node_pivot")
    elif fault == "wall_order":
        data["walls"].reverse()
    elif fault == "off_outline":
        for wall in data["walls"]:
            for key in ("a", "b"):
                wall[key][0] += .03
    elif fault == "broken_join":
        wall = data["walls"][0]
        wall["b"] = (np.array(wall["b"])*.98+np.array(wall["a"])*.02).tolist()
        wall["length"] *= .98
    elif fault == "floating_floor":
        data["entities"][0]["base_y"] += .03
    else:
        entity = data["entities"][1]
        if fault == "ceiling_gap":
            entity.update(mount="ceiling", support_id=None)
        else:
            entity.update(mount="tabletop", support_id="counter", base_y=.94 if fault == "floating_tabletop" else .91)
            if fault == "wrong_support_position":
                entity["center"] = [20., 20.]
    with pytest.raises(ValueError):
        RoomDocument.model_validate(data)


def test_headroom_splits_covered_and_uncovered_stretches(tmp_path):
    def configure(inventory):
        inventory["entities"][1]["parts"] = [box([-.4, 1.47, -.4], [.8, .1, .6])]
    output, _, document = build_room(tmp_path, configure=configure)
    counter = next(e for e in document.entities if e.id == "counter")
    tops = [s for s in counter.surfaces if abs(s.top-.91) < .001]
    assert {s.clearance_limited_by for s in tops} == {"light", document.ceiling.node_name}
    covered = union_all([surface_shape(s) for s in tops if s.clearance_limited_by == "light"])
    uncovered = union_all([surface_shape(s) for s in tops if s.clearance_limited_by != "light"])
    assert covered.area == pytest.approx(.8*.56)
    assert uncovered.area == pytest.approx(.8*.56)
    assert covered.intersection(uncovered).area < 1e-8
    assert all(s.clearance_above == pytest.approx(.51 if s.clearance_limited_by == "light" else 1.59) for s in tops)
    assert load_room(output).model_dump() == document.model_dump()


def split_counter(inventory):
    counter = inventory["entities"][0]
    counter["parts"].pop(0)
    for index, x in enumerate((-1.6/3, 0., 1.6/3)):
        cabinet = copy.deepcopy(counter)
        cabinet.update(id="dishwasher" if index == 1 else f"cabinet-{index}",
                       category="appliance" if index == 1 else "cabinet",
                       label="Dishwasher" if index == 1 else f"Cabinet {index}",
                       parts=[box([x, .405, -.4], [1.6/3, .81, .6])])
        inventory["entities"].append(cabinet)


def test_counter_run_preserves_members_and_supports_appliances(tmp_path):
    kettle = copy.deepcopy(room_plan()["entities"][0])
    kettle.update(id="kettle", label="Kettle", category="appliance", support_id="counter", yaw=.33,
                  parts=[box([0., 1.01, -.4], [.2, .2, .2])])
    output, _, document = build_room(tmp_path, [kettle], configure=split_counter)
    entities = {e.id: e for e in document.entities}
    group = next(e for e in document.entities if e.member_ids)
    assert group.node_name is group.asset is None
    assert group.collision_class == "none" and group.mount == "floor" and group.base_y == pytest.approx(0.)
    assert set(group.member_ids) == {"counter", "cabinet-0", "cabinet-2", "dishwasher"}
    assert group.size == pytest.approx([1.6, .6, 1.1])
    assert all(entities[m].node_name and entities[m].asset for m in group.member_ids)
    assert entities["counter"].support_id in {"cabinet-0", "cabinet-2", "dishwasher"}
    assert entities["kettle"].support_id == group.id
    assert entities["kettle"].base_y == pytest.approx(.91)
    assert load_room(output).model_dump() == document.model_dump()

    data = document.model_dump()
    next(e for e in data["entities"] if e["id"] == group.id)["size"][0] += .03
    atomic_json(output/"room.json", data)
    with pytest.raises(ValueError, match="group bounds"):
        load_room(output)


def test_thin_countertop_retains_its_real_support_surface(tmp_path):
    def configure(inventory):
        split_counter(inventory)
        inventory["entities"][0]["parts"] = [box([0., .82, -.4], [1.6, .02, .6]),
                                                box([0., .925, -.68], [1.6, .19, .04])]
    output, _, document = build_room(tmp_path, configure=configure)
    group = next(e for e in document.entities if e.member_ids)
    assert any(s.top == pytest.approx(.83) and s.clearance_above == pytest.approx(.59) for s in group.surfaces)
    assert load_room(output).model_dump() == document.model_dump()


@pytest.mark.parametrize("fault", ["collidable", "asset", "unknown_member", "nested", "cycle", "unbacked_surface"])
def test_invalid_support_groups_are_rejected(tmp_path, fault):
    _, _, document = build_room(tmp_path, configure=split_counter)
    data = document.model_dump()
    group = next(e for e in data["entities"] if e["member_ids"])
    if fault == "collidable": group["collision_class"] = "floor"
    elif fault == "asset": group["asset"] = "duplicate.obj"
    elif fault == "unknown_member": group["member_ids"].append("missing")
    elif fault == "nested": group["member_ids"].append(group["id"])
    elif fault == "cycle":
        next(e for e in data["entities"] if e["id"] == "counter")["support_id"] = group["id"]
    else:
        group["surfaces"][0]["polygon"] = [[10, 10], [11, 10], [11, 11], [10, 11], [10, 10]]
    with pytest.raises(ValueError):
        RoomDocument.model_validate(data)


def test_inset_sink_keeps_its_mesh_but_excludes_its_footprint(tmp_path):
    sink = copy.deepcopy(room_plan()["entities"][0])
    sink.update(id="sink", label="Inset sink", category="sink", kind="fixed", support_id="counter", yaw=.33,
                parts=[box([0., .81, -.4], [.4, .22, .3])])
    output, _, document = build_room(tmp_path, [sink])
    entities = {e.id: e for e in document.entities}
    inset = entities["sink"]
    assert inset.mount == "inset" and inset.collision_class == "tabletop"
    assert inset.node_name == "sink" and (output/inset.asset).is_file()
    surfaces = [s for s in entities["counter"].surfaces if abs(s.top-.91) < .001]
    assert any(s.holes for s in surfaces)
    center = Polygon(surfaces[0].holes[0]).representative_point()
    assert not union_all([surface_shape(s) for s in surfaces]).covers(center)
    assert load_room(output).model_dump() == document.model_dump()


def test_floating_reconstruction_is_rejected_without_lowering_it(tmp_path):
    floating = copy.deepcopy(room_plan()["entities"][0])
    floating.update(id="floating", parts=[box([1., .5, 1.], [.2, .2, .2])])
    with pytest.raises(ValueError, match="Floor-mounted"):
        build_room(tmp_path, [floating])


def test_opening_past_wall_is_rejected_instead_of_shortened(tmp_path):
    def configure_room(room):
        room["doors"][0]["transform"][12] = 1.6
        room["doors"][0]["dimensions"][0] = .9
    with pytest.raises(ValueError, match="measured opening"):
        build_room(tmp_path, configure_room=configure_room)


def test_overlapping_overheads_use_the_lowest_limiter(tmp_path):
    lower = copy.deepcopy(room_plan()["entities"][0])
    lower.update(id="lower-light", category="lighting_fixture", kind="fixed", yaw=.33,
                 support_id=stable_id("wall", "wall-0"), parts=[box([0., 1.27, -.4], [.4, .1, .6])])
    def configure(inventory):
        inventory["entities"][1]["parts"] = [box([-.4, 1.47, -.4], [.8, .1, .6])]
    _, _, document = build_room(tmp_path, [lower], configure=configure)
    surfaces = next(e for e in document.entities if e.id == "counter").surfaces
    areas = {}
    for surface in surfaces:
        areas[surface.clearance_limited_by] = areas.get(surface.clearance_limited_by, 0.)+surface_shape(surface).area
    assert areas["lower-light"] == pytest.approx(.4*.56)
    assert areas["light"] == pytest.approx(.6*.56)
    assert areas[document.ceiling.node_name] == pytest.approx(.6*.56)
    assert all(s.clearance_above == pytest.approx(.31) for s in surfaces if s.clearance_limited_by == "lower-light")
