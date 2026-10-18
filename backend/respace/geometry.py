"""Pure translation-only native RoomPlan normalization and diagnostics."""

from copy import deepcopy
import math
from typing import Any

import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import polygonize, unary_union

from .categories import CATEGORY_VERSION, CATEGORIES, PERMANENT_CATEGORIES, native_category


def _numbers(values, count):
    if not isinstance(values, (list, tuple)) or len(values) != count:
        raise ValueError(f"expected {count} finite numbers")
    result = [float(v) for v in values]
    if not all(math.isfinite(v) for v in result):
        raise ValueError("nonfinite geometry")
    return result


def _matrix(values):
    matrix = np.asarray(_numbers(values, 16)).reshape(4, 4).T
    if not np.allclose(matrix[3], [0, 0, 0, 1], atol=1e-5):
        raise ValueError("unsupported transform; require affine column-major Matrix4")
    if not np.allclose(matrix[:3, :3].T @ matrix[:3, :3], np.eye(3), atol=.02):
        raise ValueError("native transform axes must be orthonormal")
    return matrix


def _surface_segments(surface, warnings):
    matrix = _matrix(surface["transform"])
    width, height, _ = _numbers(surface["dimensions"], 3)
    if width <= 0 or height <= 0:
        raise ValueError("nonpositive wall size")
    center, axis = matrix[[0, 2], 3], matrix[[0, 2], 0]
    a, b = center - axis * width / 2, center + axis * width / 2
    curve = surface.get("curve")
    if curve:
        try:
            def angle(value):
                if isinstance(value, dict):
                    number = float(value["value"])
                    symbol = value.get("unit", {}).get("symbol")
                    if symbol not in ("rad", "°", "deg"):
                        raise ValueError("unknown curve angle unit")
                    return math.radians(number) if symbol != "rad" else number
                return float(value)
            start, end = angle(curve["startAngle"]), angle(curve["endAngle"])
            radius = float(curve["radius"])
            cx, cz = _numbers(curve["center"], 2)
            if not all(math.isfinite(v) for v in (start, end, radius)) or radius <= 0:
                raise ValueError("invalid curve")
            count = min(8, max(1, math.ceil(abs(end - start) * radius / .5)))
            points = []
            for theta in np.linspace(start, end, count + 1):
                world = matrix @ [cx + radius * math.cos(theta), 0,
                                  cz + radius * math.sin(theta), 1]
                points.append(world[[0, 2]])
            warnings.append({"code": "curve_approximated", "source_id": surface["identifier"]})
            return list(zip(points, points[1:])), height, matrix[1, 3] - height / 2
        except (KeyError, TypeError, ValueError):
            warnings.append({"code": "curve_metadata_unsupported", "source_id": surface["identifier"]})
    return [(a, b)], height, matrix[1, 3] - height / 2


def normalize_room(raw, capture_id, room_id):
    """Normalize supported native evidence; invalid evidence remains explicitly invalid."""
    warnings: list[dict[str, Any]] = []
    reasons: list[dict[str, Any]] = []
    segments: list[dict[str, Any]] = []
    heights, floor_ys = [], []
    room: dict[str, Any] = {"schema_version": 1, "category_version": CATEGORY_VERSION, "room_id": room_id,
            "capture_id": capture_id, "height": 0, "frame": {"room_from_world": np.eye(4).T.ravel().tolist()},
            "floor": {"polygon": [], "area": 0}, "walls": [], "corners": [], "openings": [],
            "objects": [], "wall_features": [], "zones": [], "style_hints": {}, "identity_map": {},
            "processing": {"expected_frames": 0, "not_started": 0, "pending": 0, "succeeded": 0,
                           "failed": 0, "lifted": 0, "completed": 0},
            "validity": {"usable": False, "reasons": reasons, "warnings": warnings}}
    if not isinstance(raw, dict) or not isinstance(raw.get("walls"), list):
        reasons.append({"code": "unsupported_native_shape", "message": "Native walls array is required."})
        return room
    source_ids = set()
    for group in ("walls", "doors", "windows", "openings", "objects", "floors"):
        entries = raw.get(group, [])
        if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
            reasons.append({"code": "unsupported_native_shape", "field": group})
            return room
        for entry in entries:
            source_id = entry.get("identifier")
            if not isinstance(source_id, str) or not source_id or source_id in source_ids:
                reasons.append({"code": "invalid_native_identity", "field": group})
                return room
            source_ids.add(source_id)
    for wall in raw["walls"]:
        try:
            pairs, height, floor_y = _surface_segments(wall, warnings)
            heights.append(height)
            floor_ys.append(floor_y)
            segments.extend({"a": np.asarray(a), "b": np.asarray(b), "source": wall["identifier"],
                             "virtual": False} for a, b in pairs)
        except (KeyError, TypeError, ValueError):
            reasons.append({"code": "invalid_wall", "source_id": wall.get("identifier")})
    if len(segments) < 3:
        reasons.append({"code": "insufficient_boundary", "message": "At least three measured wall segments are required."})
        return room
    # Union close endpoints before averaging, independent of native export ordering.
    endpoints = [s[key] for s in segments for key in ("a", "b")]
    parents = list(range(len(endpoints)))
    def root(i):
        while parents[i] != i:
            i = parents[i]
        return i
    for i, a in enumerate(endpoints):
        for j in range(i):
            if np.linalg.norm(a - endpoints[j]) <= .3:
                parents[root(i)] = root(j)
    for i in range(len(endpoints)):
        cluster_points = [point for j, point in enumerate(endpoints) if root(j) == root(i)]
        segments[i // 2]["a" if i % 2 == 0 else "b"] = np.mean(cluster_points, axis=0)
    if any(np.linalg.norm(s["b"] - s["a"]) < .01 for s in segments):
        reasons.append({"code": "degenerate_wall"})
        return room
    lines = [LineString([s["a"], s["b"]]) for s in segments]
    polygons = list(polygonize(unary_union(lines)))
    if not polygons:
        degree: dict[tuple[float, float], int] = {}
        for s in segments:
            for key in ("a", "b"):
                p = tuple(s[key])
                degree[p] = degree.get(p, 0) + 1
        loose = sorted(p for p, n in degree.items() if n == 1)
        if len(loose) == 2:
            gap = math.dist(*loose)
            measured = sum(line.length for line in lines)
            if gap <= 1.2 and gap <= measured / 3:
                segments.append({"a": np.asarray(loose[0]), "b": np.asarray(loose[1]),
                                 "source": None, "virtual": True})
                polygons = list(polygonize(unary_union(lines + [LineString(loose)])))
                warnings.append({"code": "virtual_gap", "length": gap})
    if not polygons:
        reasons.append({"code": "invalid_boundary", "message": "Measured walls do not form a supported closed floor."})
        return room
    polygon = orient(max(polygons, key=lambda p: p.area), sign=1)
    if len(polygons) > 1:
        warnings.append({"code": "largest_section_only"})
    if not polygon.is_valid or polygon.area <= .1 or polygon.interiors:
        reasons.append({"code": "invalid_boundary"})
        return room
    floor_y = float(np.median(floor_ys))
    floors = raw.get("floors", [])
    if floors:
        try:
            floor = max(floors, key=lambda f: float(f.get("dimensions", [0, 0, 0])[0]) *
                        max(float(f.get("dimensions", [0, 0, 0])[1]), float(f.get("dimensions", [0, 0, 0])[2])))
            floor_y = float(_matrix(floor["transform"])[1, 3])
            warnings.append({"code": "native_floor_axes_unverified", "message": "Floor polygon uses measured walls; native floor is elevation evidence only."})
        except (KeyError, TypeError, ValueError):
            warnings.append({"code": "invalid_native_floor"})
    minx, minz, _, _ = polygon.bounds
    translation = np.array([-minx, -floor_y, -minz])
    matrix = np.eye(4)
    matrix[:3, 3] = translation
    room["frame"]["room_from_world"] = matrix.T.ravel().tolist()
    room["height"] = float(np.median(heights))
    coords = list(polygon.exterior.coords)[:-1]
    first = min(range(len(coords)), key=lambda i: (math.hypot(*np.asarray(coords[i]) + translation[[0, 2]]), coords[i]))
    coords = coords[first:] + coords[:first]
    normalized = [list(np.asarray(p) + translation[[0, 2]]) for p in coords]
    room["floor"] = {"polygon": normalized, "area": float(polygon.area)}
    for i, (a, b) in enumerate(zip(coords, coords[1:] + coords[:1])):
        midpoint = Point((np.asarray(a) + np.asarray(b)) / 2)
        segment = min(segments, key=lambda s: LineString([s["a"], s["b"]]).distance(midpoint))
        delta = np.asarray(b) - a
        length = float(np.linalg.norm(delta))
        wall = {"id": f"w_{i + 1}", "a": normalized[i], "b": normalized[(i + 1) % len(coords)],
                "length": length, "inward_normal": [-float(delta[1]) / length, float(delta[0]) / length],
                "virtual": segment["virtual"], "source_ids": [segment["source"]] if segment["source"] else []}
        room["walls"].append(wall)
        if segment["source"]:
            old = room["identity_map"].get(segment["source"])
            room["identity_map"][segment["source"]] = {"kind": "wall", "id": wall["id"],
                "ids": [*(old.get("ids", [old["id"]]) if old else []), wall["id"]]}
    room["corners"] = corners(room["walls"])
    _openings(raw, room, translation, reasons, warnings)
    _objects(raw, room, translation, reasons, warnings)
    room["validity"]["usable"] = not reasons
    return room


def corners(walls):
    """Corner Anchors where two real walls, in closed winding order, meet at 45-135 degrees."""
    result = []
    for i, wall in enumerate(walls):
        previous = walls[i - 1]
        if wall["virtual"] or previous["virtual"]:
            continue
        u = np.asarray(previous["a"]) - previous["b"]
        v = np.asarray(wall["b"]) - wall["a"]
        angle = math.degrees(math.acos(float(np.clip(np.dot(u, v) / np.linalg.norm(u) / np.linalg.norm(v), -1, 1))))
        convex = -u[0] * v[1] + u[1] * v[0] > 0
        if convex and 45 <= angle <= 135:
            result.append({"id": f"c_{i + 1}", "position": wall["a"], "wall_ids": [previous["id"], wall["id"]]})
    return result


def keep_clear(wall, opening, floor):
    """The room-side access zone in front of a door or doorless opening, or None."""
    direction = (np.asarray(wall["b"]) - wall["a"]) / wall["length"]
    start = np.asarray(wall["a"]) + direction * max(0., opening["offset"] - .45)
    end = np.asarray(wall["a"]) + direction * min(wall["length"], opening["offset"] + opening["width"] + .45)
    depth = 1.2
    normal = np.asarray(wall["inward_normal"]) * depth
    zone = Polygon([start, end, end + normal, start + normal]).intersection(floor)
    if not isinstance(zone, Polygon) or zone.is_empty:
        return None
    return {"id": f"z_{opening['id']}", "type": "keep_clear", "reason": opening["type"],
            "opening_id": opening["id"], "polygon": [list(p) for p in zone.exterior.coords[:-1]]}


def _openings(raw, room, translation, reasons, warnings):
    floor = Polygon(room["floor"]["polygon"])
    for group, kind in (("doors", "door"), ("windows", "window"), ("openings", "opening")):
        entries = sorted(raw.get(group, []), key=lambda e: str(e.get("identifier", "")))
        for entry in entries:
            try:
                matrix = _matrix(entry["transform"])
                width, height, _ = _numbers(entry["dimensions"], 3)
                if min(width, height) <= 0:
                    raise ValueError("invalid opening dimensions")
                position = matrix[:3, 3] + translation
                parent = room["identity_map"].get(entry.get("parentIdentifier"), {})
                candidates = [w for w in room["walls"] if not w["virtual"] and
                              (not parent or w["id"] in parent.get("ids", [parent.get("id")]))]
                if not candidates:
                    raise ValueError("missing real wall")
                wall = min(candidates, key=lambda w: LineString([w["a"], w["b"]]).distance(Point(position[[0, 2]])))
                line = LineString([wall["a"], wall["b"]])
                if line.distance(Point(position[[0, 2]])) > .3:
                    raise ValueError("opening detached from wall")
                offset = line.project(Point(position[[0, 2]])) - width / 2
                if offset < -.3 or offset + width > wall["length"] + .3:
                    raise ValueError("opening extends beyond wall")
                opening = {"id": f"{kind}_{len(room['openings']) + 1}", "type": kind,
                           "wall_id": wall["id"], "offset": float(max(0, offset)), "width": width,
                           "bottom": float(position[1] - height / 2), "height": height,
                           "source_ids": [entry["identifier"]]}
                room["openings"].append(opening)
                room["identity_map"][entry["identifier"]] = {"kind": "opening", "id": opening["id"]}
                if kind != "window":
                    zone = keep_clear(wall, opening, floor)
                    if zone:
                        room["zones"].append(zone)
            except (KeyError, TypeError, ValueError):
                reasons.append({"code": "invalid_opening", "source_id": entry.get("identifier")})


def _objects(raw, room, translation, reasons, warnings):
    pending = []
    for entry in raw.get("objects", []):
        try:
            category = native_category(entry.get("category"), entry.get("attributes"))
            if category is None:
                reasons.append({"code": "unsupported_object_category", "source_id": entry.get("identifier")})
                continue
            matrix = _matrix(entry["transform"])
            w, h, d = _numbers(entry["dimensions"], 3)
            if min(w, h, d) <= 0:
                raise ValueError("invalid object bounds")
            position = matrix[:3, 3] + translation
            yaw = math.atan2(float(matrix[0, 2]), float(matrix[2, 2]))
            registry = CATEGORIES[category]
            mount = registry["mount"]
            wall = min((w for w in room["walls"] if not w["virtual"]),
                       key=lambda w: LineString([w["a"], w["b"]]).distance(Point(position[[0, 2]])))
            base_y = float(position[1] - h / 2)
            if mount == "wall" and LineString([wall["a"], wall["b"]]).distance(Point(position[[0, 2]])) > .3:
                if abs(base_y) <= .15:
                    mount = "floor"
                elif not entry.get("parentIdentifier"):
                    reasons.append({"code": "missing_wall_association", "source_id": entry["identifier"]})
            obj = {"source_ids": [entry["identifier"]], "category": category, "source": "roomplan",
                   "center": position[[0, 2]].tolist(), "base_y": base_y, "yaw": yaw,
                   "size": [w, d, h], "mount": mount, "wall_id": wall["id"] if mount == "wall" else None,
                   "support_id": None, "fixed_in_place": category in PERMANENT_CATEGORIES,
                   "attrs": {}, "native_attributes": deepcopy(entry.get("attributes", [])), "observation_count": 0}
            wall_distance = abs(float(np.dot(position[[0, 2]] - wall["a"], wall["inward_normal"])))
            forward = np.array([math.sin(yaw), math.cos(yaw)])
            if abs(abs(float(np.dot(forward, wall["inward_normal"]))) - 1) < .04 and wall_distance - d / 2 <= .3:
                obj["against_wall"] = wall["id"]
            pending.append((obj, entry.get("parentIdentifier")))
        except (KeyError, TypeError, ValueError):
            reasons.append({"code": "invalid_object", "source_id": entry.get("identifier")})
    pending.sort(key=lambda pair: (pair[0]["category"], *pair[0]["center"], pair[0]["source_ids"][0]))
    for i, (obj, _) in enumerate(pending):
        obj["id"] = f"o_{i + 1}"
        room["objects"].append(obj)
        room["identity_map"][obj["source_ids"][0]] = {"kind": "object", "id": obj["id"]}
    for obj, parent in pending:
        mapped = room["identity_map"].get(parent, {})
        if mapped.get("kind") == "object":
            obj["mount"], obj["support_id"] = "tabletop", mapped["id"]
        elif obj["mount"] == "floor" and abs(obj["base_y"]) > .15:
            reasons.append({"code": "missing_support", "object_id": obj["id"], "message": "Elevated Object needs explicit support evidence."})


def top_down_svg(room, scene=None):
    """Offline diagnostic of the exact boundary, zones and oriented placement bounds."""
    from html import escape

    points = room.get("floor", {}).get("polygon", [])
    if not points:
        return '<svg xmlns="http://www.w3.org/2000/svg"><text x="4" y="20">Invalid room boundary</text></svg>'
    maxx, maxz = np.max(np.asarray(points), axis=0)
    def poly(points, color, opacity=1):
        return f'<polygon points="{" ".join(f"{x*100:.3f},{z*100:.3f}" for x,z in points)}" fill="{color}" fill-opacity="{opacity}" stroke="#333" stroke-width="1"/>'
    result = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-20 -20 {maxx*100+40} {maxz*100+40}">', poly(points, "#f4ede3")]
    for zone in room.get("zones", []):
        result.append(poly(zone["polygon"], "#ed7777", .4))
    objects = scene["items"] if scene else room.get("objects", [])
    for obj in objects:
        if obj.get("status") == "removed":
            continue
        placement = obj.get("placement")
        if placement:
            x, _, z = placement["position"]
            w, d, _ = placement["size"]
            yaw = placement["yaw"]
        else:
            x, z = obj["center"]
            w, d, _ = obj["size"]
            yaw = obj["yaw"]
        c, s = math.cos(yaw), math.sin(yaw)
        corners = [[x + c * a + s * b, z - s * a + c * b] for a,b in [(-w/2,-d/2),(w/2,-d/2),(w/2,d/2),(-w/2,d/2)]]
        result.extend([poly(corners, "#b8c6d6", .7), f'<text x="{x*100}" y="{z*100}" font-size="8">{escape(obj["id"])}</text>'])
    result.append("</svg>")
    return "".join(result)
