import json
import struct

import numpy as np
import pytest

from respace.geometry import normalize_room
from respace.glb_room import raw_room_from_glb


def write_glb(path, *, disconnected=False):
    # Local Z is up; the parent rotates it into Y, then the child scales by two.
    points = [[0, 0, 0], [3, 0, 0], [3, 2, 0], [0, 2, 0],
              [0, 0, 1], [3, 0, 1], [3, 2, 1], [0, 2, 1]]
    indices = [0, 1, 2, 0, 2, 3, 4, 5, 6, 4, 6, 7]
    if disconnected:
        points.extend([[4, 0, 0], [5, 0, 0], [5, 1, 0]])
        indices.extend([8, 9, 10])
    position_bytes = np.asarray(points, dtype="<f4").tobytes()
    index_bytes = np.asarray(indices, dtype="<u2").tobytes()
    binary = position_bytes + index_bytes
    parent = [1, 0, 0, 0, 0, 0, -1, 0, 0, 1, 0, 0, 10, -2, 20, 1]
    child = [2, 0, 0, 0, 0, 2, 0, 0, 0, 0, 2, 0, 0, 0, 0, 1]
    document = {"asset": {"version": "2.0", "extras": {"author": "Fixture artist"}},
                "scene": 0, "scenes": [{"nodes": [0]}],
                "nodes": [{"matrix": parent, "children": [1]}, {"matrix": child, "mesh": 0}],
                "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
                "buffers": [{"byteLength": len(binary)}],
                "bufferViews": [{"buffer": 0, "byteLength": len(position_bytes)},
                                {"buffer": 0, "byteOffset": len(position_bytes), "byteLength": len(index_bytes)}],
                "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(points), "type": "VEC3"},
                              {"bufferView": 1, "componentType": 5123, "count": len(indices), "type": "SCALAR"}]}
    encoded = json.dumps(document).encode()
    encoded += b" " * (-len(encoded) % 4)
    binary += b"\0" * (-len(binary) % 4)
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, 28 + len(encoded) + len(binary))
                     + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
                     + struct.pack("<II", len(binary), 0x004E4942) + binary)


def test_glb_floor_uses_parent_transform_scale_and_actual_faces(tmp_path):
    path = tmp_path / "room.glb"
    write_glb(path)
    raw, metadata = raw_room_from_glb(path, floor_meshes=(0,), meters_per_unit=.5)
    room = normalize_room(raw, "test-capture", "test-room")
    assert room["validity"]["usable"]
    assert room["height"] == pytest.approx(1)
    assert room["floor"]["area"] == pytest.approx(6)
    assert room["frame"]["room_from_world"][12:15] == pytest.approx([-5, 1, -8])
    assert metadata["source_floor_area_m2"] == pytest.approx(6)
    assert metadata["native_scan"] is False
    assert metadata["unit_scale_is_test_assumption"] is True
    assert metadata["asset"]["extras"]["author"] == "Fixture artist"
    assert raw["objects"] == raw["doors"] == raw["windows"] == []


def test_glb_disconnected_floors_are_rejected_without_bounding_box(tmp_path):
    path = tmp_path / "room.glb"
    write_glb(path, disconnected=True)
    with pytest.raises(ValueError, match="one connected floor"):
        raw_room_from_glb(path, floor_meshes=(0,), meters_per_unit=1)


def test_glb_explicit_mesh_selection_and_units_are_required(tmp_path):
    path = tmp_path / "room.glb"
    write_glb(path)
    with pytest.raises(ValueError, match="missing"):
        raw_room_from_glb(path, floor_meshes=(1,), meters_per_unit=1)
    with pytest.raises(ValueError, match="positive explicit"):
        raw_room_from_glb(path, floor_meshes=(0,), meters_per_unit=float("nan"))
