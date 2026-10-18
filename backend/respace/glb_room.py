"""Explicitly selected GLB floor geometry for local tests, never native scan evidence."""

import hashlib
import json
import math
from pathlib import Path
import struct

import numpy as np
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union


def _accessor(document, binary, index):
    accessor = document["accessors"][index]
    if accessor.get("sparse") or accessor.get("normalized"):
        raise ValueError("Sparse and normalized GLB accessors are unsupported for this test import")
    view = document["bufferViews"][accessor["bufferView"]]
    if view.get("buffer", 0) != 0:
        raise ValueError("Test geometry must use the embedded GLB buffer")
    dtype = np.dtype({5126: "<f4", 5125: "<u4", 5123: "<u2", 5121: "u1"}[accessor["componentType"]])
    columns = {"VEC3": 3, "SCALAR": 1}[accessor["type"]]
    stride = view.get("byteStride", columns * dtype.itemsize)
    start = accessor.get("byteOffset", 0)
    count = accessor["count"]
    required = start + (count - 1) * stride + columns * dtype.itemsize
    if count < 1 or stride < columns * dtype.itemsize or required > view["byteLength"]:
        raise ValueError("GLB accessor extends beyond its buffer view")
    return np.ndarray((count, columns), dtype=dtype, buffer=binary,
                      offset=view.get("byteOffset", 0) + start,
                      strides=(stride, dtype.itemsize))


def raw_room_from_glb(path, *, floor_meshes=(140, 141), meters_per_unit=10):
    """Build RoomPlan-shaped test walls from selected floor triangles and model height.

    Defaults describe the supplied room.glb only. The caller must verify its SHA
    before using this profile. Its scale override is an explicit test assumption.
    """
    if not math.isfinite(meters_per_unit) or meters_per_unit <= 0 or not floor_meshes:
        raise ValueError("Selected floor meshes and a positive explicit unit scale are required")
    data = Path(path).read_bytes()
    if len(data) < 28 or struct.unpack_from("<4sII", data) != (b"glTF", 2, len(data)):
        raise ValueError("Expected a complete glTF 2 GLB")
    json_length, kind = struct.unpack_from("<II", data, 12)
    binary_header = 20 + json_length
    if kind != 0x4E4F534A or binary_header + 8 > len(data):
        raise ValueError("GLB JSON chunk is missing or truncated")
    document = json.loads(data[20:binary_header])
    binary_length, kind = struct.unpack_from("<II", data, binary_header)
    binary = data[binary_header + 8:]
    if kind != 0x004E4942 or binary_length != len(binary):
        raise ValueError("GLB embedded binary chunk is missing or truncated")
    selected = []
    all_bounds: list[np.ndarray] = []
    found_meshes = set()

    def visit(index, parent, ancestors):
        if index in ancestors:
            raise ValueError("GLB scene graph contains a cycle")
        node = document["nodes"][index]
        # The supplied models use matrices; reject other transforms instead of ignoring them.
        if any(key in node for key in ("rotation", "translation", "scale")):
            raise ValueError("This test importer requires matrix-based GLB node transforms")
        local = np.asarray(node.get("matrix", np.eye(4).T.ravel()), dtype=float).reshape(4, 4).T
        if not np.isfinite(local).all() or not np.allclose(local[3], [0, 0, 0, 1]):
            raise ValueError("GLB node transform must be finite and affine")
        world = parent @ local
        if "mesh" in node:
            for primitive in document["meshes"][node["mesh"]]["primitives"]:
                vertices = _accessor(document, binary, primitive["attributes"]["POSITION"])
                if vertices.shape[1] != 3 or not np.isfinite(vertices).all():
                    raise ValueError("GLB positions must be finite VEC3 values")
                vertices = (np.column_stack((vertices, np.ones(len(vertices)))) @ world.T)[:, :3]
                vertices *= meters_per_unit
                all_bounds.extend((vertices.min(axis=0), vertices.max(axis=0)))
                if node["mesh"] in floor_meshes:
                    if primitive.get("mode", 4) != 4:
                        raise ValueError("Selected floor meshes must use triangle primitives")
                    indices = (_accessor(document, binary, primitive["indices"]).ravel()
                               if "indices" in primitive else np.arange(len(vertices)))
                    if len(indices) % 3 or indices.min() < 0 or indices.max() >= len(vertices):
                        raise ValueError("GLB floor indices are invalid")
                    selected.append(vertices[indices.reshape(-1, 3)])
                    found_meshes.add(node["mesh"])
        for child in node.get("children", []):
            visit(child, world, ancestors | {index})

    for index in document["scenes"][document.get("scene", 0)]["nodes"]:
        visit(index, np.eye(4), set())
    if found_meshes != set(floor_meshes):
        raise ValueError("Selected floor meshes are missing from the active GLB scene")
    triangles = np.concatenate(selected)
    floor_y = float(triangles[:, :, 1].min())
    at_floor = np.max(np.abs(triangles[:, :, 1] - floor_y), axis=1) <= 1e-5
    floor = unary_union([polygon for triangle in triangles[at_floor]
                         if (polygon := Polygon(triangle[:, [0, 2]])).area > 1e-8])
    if not isinstance(floor, Polygon) or not floor.is_valid or floor.interiors or floor.area <= .1:
        raise ValueError("Selected meshes must form one connected floor without holes")
    # Match the native normalizer's 0.3 m endpoint precision; retain exact source contour below.
    boundary = orient(floor.simplify(.3, preserve_topology=True), sign=1)
    points = list(boundary.exterior.coords)[:-1]
    if len(points) < 3 or any(math.dist(a, b) <= .3 for a, b in zip(points, points[1:] + points[:1])):
        raise ValueError("Selected floor has edges below supported room precision")
    bounds = np.asarray(all_bounds)
    height = float(bounds[:, 1].max() - floor_y)
    if not math.isfinite(height) or height <= 0:
        raise ValueError("GLB has no usable vertical extent above the selected floor")
    digest = hashlib.sha256(data).hexdigest()
    identifier = f"test-glb-{digest[:12]}"
    walls = []
    for index, (a, b) in enumerate(zip(points, points[1:] + points[:1])):
        dx, dz = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dz)
        walls.append({"identifier": f"{identifier}-wall-{index}", "category": {"wall": {}},
                      "dimensions": [length, height, 0],
                      "transform": [dx / length, 0, dz / length, 0, 0, 1, 0, 0,
                                    -dz / length, 0, dx / length, 0,
                                    (a[0] + b[0]) / 2, floor_y + height / 2,
                                    (a[1] + b[1]) / 2, 1]})
    raw = {"identifier": identifier, "version": 1, "walls": walls, "floors": [],
           "objects": [], "doors": [], "windows": [], "openings": []}
    metadata = {"kind": "glb_local_test", "filename": Path(path).name, "sha256": digest,
                "asset": document.get("asset", {}), "floor_meshes": list(floor_meshes),
                "meters_per_unit": meters_per_unit, "unit_scale_is_test_assumption": True,
                "floor_y_m": floor_y, "floor_polygon_m": [list(point) for point in floor.exterior.coords[:-1]],
                "source_floor_area_m2": floor.area, "test_floor_area_m2": boundary.area,
                "contour_simplification_m": .3, "test_wall_height_m": height,
                "height_source": "maximum_model_vertex_y_minus_selected_floor_y",
                "native_scan": False, "keyframes": 0,
                "limitations": ["Walls are synthesized from selected floor contours for testing.",
                                "Object categories and door/window geometry were not imported.",
                                "No camera, LiDAR, depth or detector observations are present."]}
    return raw, metadata
