"""Repeatable multi-view Object assembly with retained planning identities."""

from copy import deepcopy
import math
from typing import Any

import numpy as np
from shapely.geometry import MultiPoint, Point

from .categories import CATEGORIES, PERMANENT_CATEGORIES, WALL_FEATURES
from .lifting import _footprint


def _compatible(a, b):
    return (a["mount"] == b["mount"] and a.get("wall_id") == b.get("wall_id")
            and a.get("support_id") == b.get("support_id"))


def _clusters(observations):
    clusters: list[list[dict[str, Any]]] = []
    for observation in sorted(observations, key=lambda d: (d["category"], *d["position"], d["id"])):
        threshold = .2 if observation["category"] in WALL_FEATURES else .4
        candidates = [c for c in clusters if c[0]["category"] == observation["category"]
                      and _compatible(c[0], observation) and all(
                          math.dist(d["position"], observation["position"]) <= threshold + 1e-9 for d in c)]
        if candidates:
            min(candidates, key=lambda c: (math.dist(np.mean([d["position"] for d in c], axis=0),
                                                   observation["position"]), c[0]["id"])).append(observation)
        else:
            clusters.append([observation])
    return clusters


def _counter(records, previous, key, prefix):
    numbers = [int(r["id"][len(prefix):]) for r in records
               if r["id"].startswith(prefix) and r["id"][len(prefix):].isdigit()]
    return max([previous.get("identity_counters", {}).get(key, 0), *numbers], default=0)


def _rug_bounds(cluster):
    points = [point for detection in cluster for point in detection.get("floor_points", [])]
    rectangle = MultiPoint(points).minimum_rotated_rectangle
    if rectangle.geom_type != "Polygon" or rectangle.area <= 1e-6:
        return None
    corners = np.asarray(rectangle.exterior.coords)[:4]
    edges = [(float(np.linalg.norm(corners[(i+1) % 4] - corners[i])),
              corners[(i+1) % 4] - corners[i]) for i in range(4)]
    width, axis = max(edges, key=lambda pair: (pair[0], abs(pair[1][0]), pair[1][0], pair[1][1]))
    depth = min(length for length, _ in edges)
    yaw = (-math.atan2(float(axis[1]), float(axis[0]))) % math.pi
    if abs(yaw - math.pi) < 1e-9:
        yaw = 0
    return np.mean(corners, axis=0).tolist(), [width, depth, CATEGORIES["rug"]["default_size"][2]], yaw


def _candidate(cluster):
    first = cluster[0]
    position = np.mean([d["position"] for d in cluster], axis=0)
    obj = {"category": first["category"], "center": position[[0, 2]].tolist(), "base_y": float(position[1]),
           "size": np.median([d["size"] for d in cluster], axis=0).tolist(), "yaw": first["yaw"],
           "source": "mk1", "mount": first["mount"], "wall_id": first.get("wall_id"),
           "support_id": first.get("support_id"), "fixed_in_place": first["category"] in PERMANENT_CATEGORIES,
           "source_ids": sorted(d["id"] for d in cluster), "attrs": {}, "observation_count": len(cluster),
           "evidence": [{"observation_id": d["id"], "frame_id": d["frame_id"], "idx": d["idx"],
                         "method": d["method"], "observation_point": d["observation_point"]} for d in cluster]}
    if obj["category"] == "rug":
        bounds = _rug_bounds(cluster)
        if bounds is None:
            return None
        obj["center"], obj["size"], obj["yaw"] = bounds
    return obj


def merge(base_room, lifts, previous=None):
    """Return a new RoomModel; missing prior identities remain explicit unresolved aliases."""
    previous = previous or {}
    if previous and (previous["capture_id"] != base_room["capture_id"] or previous["room_id"] != base_room["room_id"]):
        raise ValueError("Identity reuse requires the same Room and capture.")
    revisions = {lift["input_revision"] for lift in lifts}
    if len(revisions) > 1 or any(lift["capture_id"] != base_room["capture_id"] for lift in lifts):
        raise ValueError("Stored lifts must share the capture and input revision.")
    frame_ids = [lift["frame_id"] for lift in lifts]
    if len(set(frame_ids)) != len(frame_ids):
        raise ValueError("A stored keyframe cannot be counted twice.")
    room = deepcopy(base_room)
    warnings = room["validity"]["warnings"]
    old_objects = previous.get("objects", [])
    old_features = previous.get("wall_features", [])
    object_number = _counter([*old_objects, *room["objects"]], previous, "object", "o_")
    feature_number = _counter([*old_features, *room["wall_features"]], previous, "wall_feature", "wf_")
    used_ids = {obj["id"] for obj in room["objects"]}
    used_feature_ids = {feature["id"] for feature in room["wall_features"]}
    aliases = room["identity_map"]
    observations = [d for lift in sorted(lifts, key=lambda l: (l["idx"], l["frame_id"]))
                    if lift.get("state", "succeeded") == "succeeded" for d in lift["detections"]]
    if len({d["id"] for d in observations}) != len(observations):
        raise ValueError("Observation identities must be unique.")
    for cluster in _clusters(observations):
        category = cluster[0]["category"]
        if len({d["frame_id"] for d in cluster}) < 2 and category not in ("rug", "wall_art"):
            warnings.append({"code": "insufficient_observations", "observation_ids": sorted(d["id"] for d in cluster)})
            continue
        candidate = _candidate(cluster)
        if candidate is None:
            warnings.append({"code": "degenerate_rug", "observation_ids": sorted(d["id"] for d in cluster)})
            continue
        if category in WALL_FEATURES:
            point = np.mean([d["observation_point"] for d in cluster], axis=0)
            matches = []
            for wall in room["walls"]:
                if wall["virtual"]:
                    continue
                axis = (np.asarray(wall["b"]) - wall["a"]) / wall["length"]
                offset = float(np.dot(point[[0, 2]] - wall["a"], axis))
                distance = abs(float(np.dot(point[[0, 2]] - wall["a"], wall["inward_normal"])))
                if distance <= .15 + 1e-9 and 0 <= offset <= wall["length"] and 0 <= point[1] <= room["height"]:
                    matches.append((distance, wall["id"], offset))
            if not matches:
                warnings.append({"code": "feature_without_wall", "observation_ids": candidate["source_ids"]})
                continue
            _, wall_id, offset = min(matches)
            prior = [f for f in old_features if f["id"] not in used_feature_ids and f["type"] == category
                     and f["wall_id"] == wall_id and math.hypot(f["offset"]-offset, f["height"]-point[1]) <= .2 + 1e-9]
            if prior:
                identity = min(prior, key=lambda f: (math.hypot(f["offset"]-offset, f["height"]-point[1]), f["id"]))["id"]
            else:
                feature_number += 1
                identity = f"wf_{feature_number}"
            used_feature_ids.add(identity)
            room["wall_features"].append({"id": identity, "type": category, "wall_id": wall_id,
                "offset": offset, "height": float(point[1]), "source_ids": candidate["source_ids"],
                "observation_count": len(cluster), "evidence": candidate["evidence"]})
            for source_id in candidate["source_ids"]:
                aliases[source_id] = {"kind": "wall_feature", "id": identity}
            continue
        native = [obj for obj in room["objects"] if obj["source"] != "mk1"
                  and category in CATEGORIES[obj["category"]]["absorbs"] and _compatible(obj, candidate)
                  and _footprint(obj, .2).covers(Point(candidate["center"]))
                  and abs(obj["base_y"] - candidate["base_y"]) <= .4]
        if native:
            target = min(native, key=lambda o: (math.dist(o["center"], candidate["center"]), o["id"]))
            target["category"] = category
            target["source"] = "refined"
            target["source_ids"] = sorted(set(target["source_ids"] + candidate["source_ids"]))
            target["observation_count"] += len(cluster)
            target["evidence"] = target.get("evidence", []) + candidate["evidence"]
            identity = target["id"]
        else:
            prior = [obj for obj in old_objects if obj["id"] not in used_ids
                     and obj["category"] == category and _compatible(obj, candidate)
                     and math.dist([*obj["center"], obj["base_y"]], [*candidate["center"], candidate["base_y"]]) <= .4 + 1e-9]
            if prior:
                identity = min(prior, key=lambda o: (math.dist(o["center"], candidate["center"]), o["id"]))["id"]
            else:
                object_number += 1
                identity = f"o_{object_number}"
            candidate["id"] = identity
            room["objects"].append(candidate)
            used_ids.add(identity)
        for source_id in candidate["source_ids"]:
            aliases[source_id] = {"kind": "object", "id": identity}
    current_ids = {obj["id"] for obj in room["objects"]}
    current_features = {feature["id"] for feature in room["wall_features"]}
    for old in old_objects:
        if old["id"] in current_ids:
            continue
        absorbed = {aliases[source]["id"] for source in old.get("source_ids", []) if source in aliases
                    and aliases[source]["kind"] == "object"}
        if len(absorbed) == 1:
            aliases[old["id"]] = {"kind": "object", "id": absorbed.pop()}
        else:
            aliases[old["id"]] = {"kind": "unresolved_object", "id": old["id"], "reason": "not_observed"}
            warnings.append({"code": "unresolved_previous_object", "object_id": old["id"]})
    for source, reference in previous.get("identity_map", {}).items():
        if source in aliases:
            continue
        target = aliases.get(reference["id"])
        if target is not None:
            aliases[source] = deepcopy(target)
        elif reference["kind"] == "object" and reference["id"] in current_ids:
            aliases[source] = deepcopy(reference)
        elif reference["kind"] == "wall_feature" and reference["id"] in current_features:
            aliases[source] = deepcopy(reference)
        elif reference["kind"] == "unresolved_object":
            aliases[source] = deepcopy(reference)
            warning = {"code": "unresolved_previous_object", "object_id": reference["id"]}
            if warning not in warnings:
                warnings.append(warning)
    room["objects"].sort(key=lambda obj: int(obj["id"].split("_")[-1]))
    room["wall_features"].sort(key=lambda f: int(f["id"].split("_")[-1]))
    room["identity_counters"] = {"object": object_number, "wall_feature": feature_number}
    succeeded = sum(lift.get("state", "succeeded") == "succeeded" for lift in lifts)
    room["processing"] = {"expected_frames": len(lifts), "not_started": 0, "pending": 0,
                          "succeeded": succeeded, "failed": len(lifts)-succeeded,
                          "lifted": succeeded, "completed": succeeded}
    return room
