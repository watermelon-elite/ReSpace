"""Room reconstruction JSON, version 2, read into the processed RoomModel.

The reconstruction exporter ships a modelled room (a USDZ) with a JSON record
of what is in it. This reads that record into the same RoomModel that
`geometry.normalize_room` builds from native RoomPlan evidence, so the solver
and planning need no second room shape. Format and rationale:
specs/room-reconstruction-json.md.

Invalid evidence stays explicitly invalid: a record that cannot be read is
returned with `validity.usable` false and the reasons, never guessed into a
usable room.
"""

import math
from typing import Any

import numpy as np
from shapely.geometry import LineString, Point, Polygon

from .categories import CATEGORY_VERSION, CATEGORIES, PERMANENT_CATEGORIES, SUPPORT_CATEGORIES, WALL_FEATURES
from .geometry import _matrix, _numbers, corners, keep_clear

SCHEMA_VERSION = 2
NODE_PIVOTS = ("bottom_center", "box_center")
MOUNTS = ("floor", "wall", "tabletop", "ceiling")
COLLISION_CLASSES = ("floor", "wall", "tabletop", "ceiling", "none")
# Endpoints, lengths and elevations written by an exporter are rounded; anything
# looser than this is a disagreement, not rounding.
TOLERANCE = .02


class _Invalid(ValueError):
    def __init__(self, code, message, **detail):
        super().__init__(message)
        self.reason = {"code": code, "message": message, **detail}


def room_from_reconstruction(document, room_id):
    """Read a version 2 room reconstruction record. Never raises on bad evidence."""
    reasons: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    room: dict[str, Any] = {
        "schema_version": 1, "category_version": CATEGORY_VERSION, "room_id": room_id,
        "capture_id": None, "height": 0, "frame": {"room_from_world": np.eye(4).ravel().tolist()},
        "floor": {"polygon": [], "area": 0}, "walls": [], "corners": [], "openings": [],
        "objects": [], "wall_features": [], "obstacles": [], "zones": [], "style_hints": {},
        "identity_map": {}, "render": {"node_pivot": None, "nodes": {}},
        "processing": {"expected_frames": 0, "not_started": 0, "pending": 0, "succeeded": 0,
                       "failed": 0, "lifted": 0, "completed": 0},
        "validity": {"usable": False, "reasons": reasons, "warnings": warnings}}
    try:
        _frame(document, room)
        _walls(document, room)
        _openings(document, room)
        _entities(document, room, reasons, warnings)
    except _Invalid as exc:
        reasons.append(exc.reason)
    except (KeyError, TypeError, ValueError) as exc:
        reasons.append({"code": "unsupported_reconstruction_shape", "message": str(exc) or type(exc).__name__})
    room["validity"]["usable"] = not reasons
    return room


def _frame(document, room):
    if not isinstance(document, dict) or document.get("schema_version") != SCHEMA_VERSION:
        raise _Invalid("unsupported_schema_version", f"Expected a version {SCHEMA_VERSION} room reconstruction record.")
    if document.get("units") != "meters" or document.get("up_axis") != "+Y":
        raise _Invalid("unsupported_frame", "Units must be meters and up must be +Y.")
    if document.get("node_pivot") not in NODE_PIVOTS:
        raise _Invalid("unknown_node_pivot", "node_pivot must say where USD entity nodes are positioned.")
    matrix = _matrix(document["room_from_world"])
    if np.linalg.det(matrix[:3, :3]) <= 0:
        raise _Invalid("unsupported_frame", "room_from_world must be a rigid transform.")
    height = float(document["height"])
    if not math.isfinite(height) or height <= 0:
        raise _Invalid("invalid_height", "Room height must be positive.")
    points = [_numbers(p, 2) for p in document["floor"]["polygon"]]
    floor = Polygon(points)
    if len(points) < 3 or not floor.is_valid or floor.area <= .1:
        raise _Invalid("invalid_boundary", "Floor polygon must be a simple outline with positive area.")
    # Shapely reads X/Z as its X/Y, where counter-clockwise is positive area.
    if not floor.exterior.is_ccw:
        raise _Invalid("invalid_boundary", "Floor polygon must be ordered with positive signed area.")
    room.update(capture_id=document.get("capture_id"), height=height,
                frame={"room_from_world": [float(v) for v in document["room_from_world"]]},
                floor={"polygon": points, "area": float(floor.area)})
    room["render"]["node_pivot"] = document["node_pivot"]


def _walls(document, room):
    floor = Polygon(room["floor"]["polygon"])
    walls = []
    for record in document["walls"]:
        a, b = np.asarray(_numbers(record["a"], 2)), np.asarray(_numbers(record["b"], 2))
        delta = b - a
        length = float(np.linalg.norm(delta))
        if length < .01:
            raise _Invalid("degenerate_wall", "Wall endpoints coincide.", source_id=record["id"])
        if abs(length - float(record["length"])) > TOLERANCE:
            raise _Invalid("wall_length_mismatch", "Wall length disagrees with its endpoints.", source_id=record["id"])
        normal = np.array([-delta[1], delta[0]]) / length
        if np.linalg.norm(normal - _numbers(record["inward_normal"], 2)) > .01:
            raise _Invalid("wall_normal_mismatch", "Inward normal disagrees with the endpoints and winding.",
                           source_id=record["id"])
        if floor.exterior.distance(Point(a)) > TOLERANCE or floor.exterior.distance(Point(b)) > TOLERANCE:
            raise _Invalid("wall_off_boundary", "Wall endpoints must lie on the floor outline.", source_id=record["id"])
        protrusions = []
        for p in record.get("protrusions", []):
            depth, bottom, top = float(p["depth"]), float(p["bottom"]), float(p["top"])
            start, end = float(p["from_a"]), float(p["to_a"])
            if not (0 < depth < 1 and 0 <= bottom < top and -TOLERANCE <= start < end <= length + TOLERANCE):
                raise _Invalid("invalid_protrusion", "Protrusion needs positive depth, a height band and a span along the wall.",
                               source_id=record["id"])
            protrusions.append({"depth": depth, "bottom": bottom, "top": top, "from_a": max(0., start),
                                "to_a": min(length, end), "source_id": p.get("entity_id")})
        walls.append({"a": a.tolist(), "b": b.tolist(), "length": length, "inward_normal": normal.tolist(),
                      "virtual": bool(record.get("virtual", False)), "source_ids": [record["id"]],
                      "protrusions": protrusions, "node_name": record.get("node_name")})
    # Chain the walls end to start, so numbering and corners follow the winding.
    chain, remaining = [walls[0]], walls[1:]
    while remaining:
        end = np.asarray(chain[-1]["b"])
        following = min(remaining, key=lambda w: float(np.linalg.norm(np.asarray(w["a"]) - end)))
        if np.linalg.norm(np.asarray(following["a"]) - end) > TOLERANCE:
            raise _Invalid("walls_not_closed", "Walls must join end to start in one closed loop.")
        chain.append(following)
        remaining.remove(following)
    if len(chain) < 3 or np.linalg.norm(np.asarray(chain[0]["a"]) - chain[-1]["b"]) > TOLERANCE:
        raise _Invalid("walls_not_closed", "Walls must join end to start in one closed loop.")
    first = min(range(len(chain)), key=lambda i: (math.hypot(*chain[i]["a"]), chain[i]["a"]))
    for number, wall in enumerate(chain[first:] + chain[:first], start=1):
        wall["id"] = f"w_{number}"
        node = wall.pop("node_name")
        if node:
            room["render"]["nodes"][wall["id"]] = node
        room["identity_map"][wall["source_ids"][0]] = {"kind": "wall", "id": wall["id"]}
        room["walls"].append(wall)
    room["corners"] = corners(room["walls"])


def _wall(room, source_id, real=True):
    mapped = room["identity_map"].get(source_id, {})
    wall = next((w for w in room["walls"] if mapped.get("kind") == "wall" and w["id"] == mapped["id"]), None)
    if wall is None or (real and wall["virtual"]):
        raise _Invalid("missing_real_wall", "Reference must name a real wall.", source_id=source_id)
    return wall


def _openings(document, room):
    floor = Polygon(room["floor"]["polygon"])
    for kind in ("door", "window", "opening"):
        records = sorted((r for r in document.get("openings", []) if r["type"] == kind), key=lambda r: r["id"])
        for record in records:
            wall = _wall(room, record["wall_id"])
            offset, width = float(record["offset"]), float(record["width"])
            bottom, height = float(record["bottom"]), float(record["height"])
            if min(width, height) <= 0 or bottom < -TOLERANCE or offset < -TOLERANCE or offset + width > wall["length"] + TOLERANCE:
                raise _Invalid("invalid_opening", "Opening must lie within its wall with positive size.", source_id=record["id"])
            opening = {"id": f"{kind}_{len(room['openings']) + 1}", "type": kind, "wall_id": wall["id"],
                       "offset": max(0., offset), "width": width, "bottom": max(0., bottom), "height": height,
                       "source_ids": [record["id"]]}
            room["openings"].append(opening)
            room["identity_map"][record["id"]] = {"kind": "opening", "id": opening["id"]}
            if record.get("node_name"):
                room["render"]["nodes"][opening["id"]] = record["node_name"]
            if kind != "window":
                zone = keep_clear(wall, opening, floor)
                if zone:
                    room["zones"].append(zone)
    unknown = {r["type"] for r in document.get("openings", [])} - {"door", "window", "opening"}
    if unknown:
        raise _Invalid("invalid_opening", f"Unknown opening type {sorted(unknown)[0]!r}.")


def _entities(document, room, reasons, warnings):
    objects, obstacles, features = [], [], []
    for record in document.get("entities", []):
        try:
            entity = _entity(record, room, warnings)
        except _Invalid as exc:
            reasons.append(exc.reason)
            continue
        except (KeyError, TypeError, ValueError):
            reasons.append({"code": "invalid_entity", "source_id": record.get("id") if isinstance(record, dict) else None})
            continue
        if entity["category"] in WALL_FEATURES:
            features.append(entity)
        elif entity["category"] == "other":
            obstacles.append(entity)
        else:
            objects.append(entity)

    order = lambda e: (e["category"], *e["center"], e["source_ids"][0])  # noqa: E731
    for prefix, kind, group in (("o_", "object", objects), ("x_", "obstacle", obstacles)):
        for number, entity in enumerate(sorted(group, key=order), start=1):
            entity["id"] = f"{prefix}{number}"
            room["identity_map"][entity["source_ids"][0]] = {"kind": kind, "id": entity["id"]}
    for number, entity in enumerate(sorted(features, key=order), start=1):
        wall = next(w for w in room["walls"] if w["id"] == entity["wall_id"])
        offset = LineString([wall["a"], wall["b"]]).project(Point(entity["center"]))
        room["wall_features"].append({"id": f"wf_{number}", "type": entity["category"], "wall_id": wall["id"],
                                      "offset": float(offset), "height": entity["base_y"] + entity["size"][2] / 2,
                                      "source_ids": entity["source_ids"]})
        room["identity_map"][entity["source_ids"][0]] = {"kind": "wall_feature", "id": f"wf_{number}"}

    supports = {e["source_ids"][0]: e for e in objects}
    for entity in [*objects, *obstacles]:
        node = entity.pop("node_name")
        if node:
            room["render"]["nodes"][entity["id"]] = node
        source = entity.pop("support_source")
        if entity["mount"] != "tabletop":
            continue
        support = supports.get(source)
        if support is None or support["category"] not in SUPPORT_CATEGORIES:
            reasons.append({"code": "missing_support", "source_id": entity["source_ids"][0],
                            "message": "A tabletop entity must rest on a support Object."})
            continue
        entity["support_id"] = support["id"]
        top = _support_top(support, entity["center"])
        if abs(entity["base_y"] - top) > TOLERANCE:
            reasons.append({"code": "invalid_support", "source_id": entity["source_ids"][0],
                            "message": "A tabletop entity must sit on its support's top surface."})
        entity["base_y"] = top
    room["objects"] = sorted(objects, key=lambda e: int(e["id"][2:]))
    room["obstacles"] = sorted(obstacles, key=lambda e: int(e["id"][2:]))


def _support_top(support, center):
    for surface in support.get("surfaces", []):
        if not surface.get("polygon") or Polygon(surface["polygon"], surface["holes"]).buffer(TOLERANCE).covers(Point(center)):
            return surface["top"]
    return support["base_y"] + support["size"][2]


def _entity(record, room, warnings):
    source_id = record["id"]
    category = record["category"]
    collision = record.get("collision_class")
    if category == "other":
        if collision not in COLLISION_CLASSES:
            raise _Invalid("unknown_category", "An 'other' entity needs a collision_class.", source_id=source_id)
    elif category not in CATEGORIES:
        raise _Invalid("unknown_category", "Category must come from the shared registry, or be 'other'.",
                       source_id=source_id)
    center = _numbers(record["center"], 2)
    base_y = float(record["base_y"])
    yaw = float(record["yaw"])
    size = _numbers(record["size"], 3)
    mount = record["mount"]
    if not math.isfinite(base_y) or not math.isfinite(yaw) or min(size) <= 0 or mount not in MOUNTS:
        raise _Invalid("invalid_entity", "Entity needs a finite pose, positive size and a known Mount.", source_id=source_id)
    # Floor and ceiling contact is exact in the RoomModel; exporters round.
    if mount == "floor":
        if abs(base_y) > TOLERANCE:
            raise _Invalid("missing_support", "A floor entity must stand on the floor.", source_id=source_id)
        base_y = 0.
    if mount == "ceiling":
        if abs(base_y + size[2] - room["height"]) > TOLERANCE:
            raise _Invalid("invalid_entity", "A ceiling entity must reach the ceiling.", source_id=source_id)
        base_y = room["height"] - size[2]
    if not Polygon(room["floor"]["polygon"]).buffer(TOLERANCE).covers(Point(center)):
        raise _Invalid("outside_boundary", "Entity centre lies outside the floor outline.", source_id=source_id)
    wall_id = None
    if mount == "wall" or category in WALL_FEATURES:
        if not record.get("wall_id"):
            raise _Invalid("missing_wall_association", "A wall entity must name its wall.", source_id=source_id)
        wall_id = _wall(room, record["wall_id"])["id"]
    if mount == "tabletop" and not record.get("support_id"):
        raise _Invalid("missing_support", "A tabletop entity must name its support.", source_id=source_id)
    surfaces = []
    for surface in record.get("surfaces", []):
        top = float(surface["top"])
        if not base_y - TOLERANCE <= top <= base_y + size[2] + TOLERANCE:
            raise _Invalid("invalid_surface", "A surface top must lie within its entity's height.", source_id=source_id)
        clearance = surface.get("clearance_above")
        if clearance is not None and (not math.isfinite(float(clearance)) or float(clearance) <= 0):
            raise _Invalid("invalid_surface", "Clearance above a surface must be positive.", source_id=source_id)
        polygon = [_numbers(p, 2) for p in surface.get("polygon") or []]
        holes = [[_numbers(p, 2) for p in hole] for hole in surface.get("holes") or []]
        if polygon and (len(polygon) < 3 or not Polygon(polygon, holes).is_valid):
            raise _Invalid("invalid_surface", "A surface outline must be a simple polygon.", source_id=source_id)
        surfaces.append({"top": top, "polygon": polygon or None, "holes": holes if polygon else [],
                         "clearance_above": float(clearance) if clearance is not None else None,
                         "clearance_limited_by": surface.get("clearance_limited_by")})
    entity = {"source_ids": [source_id], "category": category, "label": record.get("label", category),
              "source": record.get("source", "reconstruction"), "center": center, "base_y": base_y,
              "yaw": yaw, "size": size, "mount": mount, "wall_id": wall_id, "support_id": None,
              "fixed_in_place": bool(record.get("fixed_in_place", category in PERMANENT_CATEGORIES)),
              "attrs": {}, "observation_count": 0, "node_name": record.get("node_name"),
              "support_source": record.get("support_id")}
    if surfaces:
        entity["surfaces"] = surfaces
    if category == "other":
        entity["collision_class"] = collision
    if mount == "floor":
        # Same rule as native normalization (SPEC 9.4): facing parallel, back within 0.3 m.
        forward = np.array([math.sin(yaw), math.cos(yaw)])
        for wall in room["walls"]:
            if wall["virtual"] or abs(abs(float(np.dot(forward, wall["inward_normal"]))) - 1) >= .04:
                continue
            line = LineString([wall["a"], wall["b"]])
            if line.distance(Point(center)) - size[1] / 2 <= .3 and float(np.dot(np.asarray(center) - wall["a"], wall["inward_normal"])) > 0:
                entity["against_wall"] = wall["id"]
                break
    return entity
