import math
import json
from pathlib import Path

import pytest

from respace.geometry import normalize_room


def native_room(points=((2, 3), (6, 3), (6, 6), (2, 6)), floor_y=-1.2):
    walls = []
    for i, (a, b) in enumerate(zip(points, (*points[1:], points[0]))):
        dx, dz = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dz)
        walls.append({"identifier": f"native-wall-{i}", "category": {"wall": {}},
                      "dimensions": [length, 2.6, 0],
                      "transform": [dx / length, 0, dz / length, 0, 0, 1, 0, 0,
                                    -dz / length, 0, dx / length, 0,
                                    (a[0] + b[0]) / 2, floor_y + 1.3, (a[1] + b[1]) / 2, 1]})
    return {"identifier": "native-room", "walls": walls, "objects": [], "doors": [],
            "windows": [], "openings": [], "floors": [], "version": 1}


def test_native_column_major_room_translates_without_rotation_or_invented_floor():
    room = normalize_room(native_room(), "capture", "room")
    assert room["validity"]["usable"]
    assert room["floor"]["area"] == pytest.approx(12)
    assert room["floor"]["polygon"] == [[0, 0], [4, 0], [4, 3], [0, 3]]
    assert room["frame"]["room_from_world"][12:15] == pytest.approx([-2, 1.2, -3])
    assert room["identity_map"]["native-wall-0"]["id"] == "w_1"
    assert room["walls"][0]["inward_normal"] == pytest.approx([0, 1])


def test_l_shape_stays_nonconvex_and_native_ids_survive_export_order():
    raw = native_room(((2, 3), (6, 3), (6, 4), (4, 4), (4, 6), (2, 6)))
    first = normalize_room(raw, "capture", "room")
    raw["walls"].reverse()
    assert normalize_room(raw, "capture", "room") == first
    assert first["floor"]["area"] == 8
    assert len(first["floor"]["polygon"]) == 6
    assert len(first["corners"]) == 5


def test_unsupported_or_sparse_boundary_is_never_a_guessed_rectangle():
    raw = native_room()
    raw["walls"] = raw["walls"][:2]
    assert not normalize_room(raw, "capture", "room")["validity"]["usable"]


def test_duplicate_native_id_cannot_redirect_keep_to_another_object_or_wall():
    raw = native_room()
    raw["walls"][1]["identifier"] = raw["walls"][0]["identifier"]
    room = normalize_room(raw, "capture", "room")
    assert not room["validity"]["usable"]
    assert room["validity"]["reasons"][0]["code"] == "invalid_native_identity"
    raw = native_room()
    raw["walls"][0]["transform"] = [[1, 0, 0, 0]] * 4
    assert not normalize_room(raw, "capture", "room")["validity"]["usable"]


def test_openings_keep_real_elevation_and_clip_access_zones():
    raw = native_room()
    raw["doors"] = [{"identifier": "door-a", "parentIdentifier": "native-wall-0",
                     "dimensions": [1, 2, 0], "category": {"door": {"isOpen": False}},
                     "transform": [1,0,0,0, 0,1,0,0, 0,0,1,0, 3,-.2,3,1]}]
    raw["windows"] = [{"identifier": "window-a", "parentIdentifier": "native-wall-2",
                       "dimensions": [1.2, 1, 0],
                       "transform": [1,0,0,0, 0,1,0,0, 0,0,1,0, 4,.3,6,1]}]
    room = normalize_room(raw, "capture", "room")
    assert room["validity"]["usable"]
    assert room["openings"][0]["bottom"] == pytest.approx(0)
    assert room["openings"][1]["bottom"] == pytest.approx(1)
    assert room["openings"][0]["offset"] == pytest.approx(.5)
    assert len(room["zones"]) == 1
    assert max(p[1] for p in room["zones"][0]["polygon"]) == 1.2


def test_object_axis_order_bottom_center_and_stool_attribute():
    raw = native_room()
    raw["objects"] = [{"identifier": "native-chair", "category": {"chair": {}},
                       "attributes": [{"chairType": {"stool": {}}}], "dimensions": [.4,.6,.3],
                       "transform": [0,0,-1,0, 0,1,0,0, 1,0,0,0, 3,-.9,4,1]}]
    obj = normalize_room(raw, "capture", "room")["objects"][0]
    assert obj["category"] == "stool"
    assert obj["size"] == [.4,.3,.6]
    assert obj["base_y"] == pytest.approx(0)
    assert obj["yaw"] == pytest.approx(math.pi / 2)
    assert obj["center"] == [1,1]


@pytest.mark.parametrize("path", sorted((Path(__file__).parent / "fixtures" / "spatial").glob("*_v1.json")), ids=lambda p: p.stem)
def test_versioned_transport_fixture_replays_exact_native_mapping_and_diagnostics(path):
    fixture = json.loads(path.read_text())
    assert fixture["schema_version"] == 1
    actual = normalize_room(fixture["raw_export"], "capture-fixture", "room-fixture")
    if "snapshot" in fixture:
        assert actual == fixture["snapshot"]["room"]
    else:
        assert not actual["validity"]["usable"]


def test_door_clearance_matches_reconstruction_exporter():
    from shapely.geometry import Polygon
    from respace.geometry import keep_clear
    wall = {"a": [0, 0], "b": [4, 0], "length": 4, "inward_normal": [0, 1]}
    floor = Polygon([[0, 0], [4, 0], [4, 3], [0, 3]])
    for kind in ("door", "opening"):
        zone = keep_clear(wall, {"id": "entrance", "type": kind, "offset": 1, "width": .9}, floor)
        assert Polygon(zone["polygon"]).bounds == pytest.approx((.55, 0, 2.35, 1.2))
    edge = keep_clear(wall, {"id": "edge", "type": "door", "offset": 0, "width": .9}, floor)
    assert Polygon(edge["polygon"]).bounds == pytest.approx((0, 0, 1.35, 1.2))
