"""Deterministic candidate placement. Publication and purchase accounting are external."""

from copy import deepcopy
import math
from typing import Any

import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from .categories import CATEGORIES, SUPPORT_CATEGORIES
from .assets import render_descriptor


def _room(snapshot):
    return snapshot.get("room_model", snapshot.get("room", snapshot.get("model", snapshot)))


def footprint(placement):
    x, _, z = placement["position"]
    w, d, _ = placement["size"]
    yaw = placement["yaw"]
    c, s = math.cos(yaw), math.sin(yaw)
    return Polygon([(x+c*a+s*b, z-s*a+c*b) for a,b in
                    [(-w/2,-d/2), (w/2,-d/2), (w/2,d/2), (-w/2,d/2)]])


def _collision_class(item):
    mount = item["placement"]["mount"]
    if item["category"] == "rug":
        return "rug"
    if CATEGORIES[item["category"]]["collision_class"] == "none":
        return "none"
    return mount


def check_overlaps(room, scene, item_id):
    room = _room(room)
    items = {item["id"]: item for item in scene["items"] if item.get("status") != "removed"}
    item = items.get(item_id)
    if not item:
        return []
    placement, collisions = item["placement"], []
    bounds = footprint(placement)
    own_class = _collision_class(item)
    floor = Polygon(room["floor"]["polygon"])
    if own_class in ("floor", "rug", "tabletop", "ceiling") and not floor.buffer(1e-7).covers(bounds.buffer(.05)):
        collisions.append("wall")
    if own_class == "floor":
        for zone in room["zones"]:
            if bounds.buffer(.05).intersection(Polygon(zone["polygon"])).area > 1e-8:
                collisions.extend([f"keep_clear:{zone['id']}", f"door:{zone['opening_id']}"])
    for other in items.values():
        if other["id"] == item_id:
            continue
        other_class = _collision_class(other)
        relevant = ((own_class == other_class and own_class in ("floor", "rug")) or
                    (own_class == other_class == "tabletop" and placement.get("support_id") == other["placement"].get("support_id")))
        if relevant and bounds.buffer(.05).intersection(footprint(other["placement"])).area > 1e-8:
            collisions.append(other["id"])
        if "wall" in (own_class, other_class) and own_class in ("floor", "wall") and other_class in ("floor", "wall") and placement.get("wall_id") == other["placement"].get("wall_id"):
            op = other["placement"]
            if placement["position"][1] < op["position"][1] + op["size"][2] + .05 and op["position"][1] < placement["position"][1] + placement["size"][2] + .05:
                if bounds.buffer(.05).intersection(footprint(op)).area > 1e-8:
                    collisions.append(other["id"])
    if own_class == "wall":
        for opening in room["openings"]:
            if opening["wall_id"] != placement.get("wall_id"):
                continue
            if placement["position"][1] >= opening["bottom"] + opening["height"] + .05 or placement["position"][1]+placement["size"][2] <= opening["bottom"]-.05:
                continue
            wall = next(w for w in room["walls"] if w["id"] == opening["wall_id"])
            line = LineString([wall["a"], wall["b"]])
            center = line.project(Point(placement["position"][0], placement["position"][2]))
            if center + placement["size"][0]/2 + .05 > opening["offset"] and center - placement["size"][0]/2 - .05 < opening["offset"] + opening["width"]:
                collisions.append(f"opening:{opening['id']}")
    return sorted(set(collisions))


def validate_scene(snapshot, scene, constraints=None):
    room, conflicts = _room(snapshot), []
    if not room.get("validity", {}).get("usable"):
        return [{"code": "invalid_room", "reason": "Room boundary is not valid.", "target_ids": [], "action_ids": []}]
    active = {i["id"]: i for i in scene["items"] if i.get("status") != "removed"}
    represented = [i.get("object_id") for i in scene["items"] if i.get("origin") == "existing"]
    if set(represented) != {o["id"] for o in room["objects"]} or len(represented) != len(set(represented)):
        conflicts.append({"code": "missing_original_object", "reason": "Every original Object must remain represented exactly once.", "target_ids": [], "action_ids": []})
    if len({i["id"] for i in scene["items"]}) != len(scene["items"]):
        conflicts.append({"code": "duplicate_identity", "reason": "Scene Item IDs must be unique.", "target_ids": [], "action_ids": []})
    for item in active.values():
        placement = item["placement"]
        try:
            values = [*placement["position"], *placement["size"], placement["yaw"]]
            if len(placement["position"]) != 3 or len(placement["size"]) != 3 or not all(math.isfinite(v) for v in values) or min(placement["size"]) <= 0:
                raise ValueError("invalid placement numbers")
            mount = placement["mount"]
            if item["category"] not in CATEGORIES:
                raise ValueError("Unknown category")
            if mount == "ceiling" and abs(placement["position"][1] + placement["size"][2] - room["height"]) > .01:
                raise ValueError("Ceiling Item is not associated with the ceiling plane")
            if mount == "floor" and abs(placement["position"][1]) > 1e-6:
                raise ValueError("floor Item has a nonzero base")
            if mount not in ("floor", "wall", "tabletop", "ceiling"):
                raise ValueError("unsupported Mount")
            if placement["position"][1] < -.001 or placement["position"][1] + placement["size"][2] > room["height"] + .001:
                raise ValueError("Item extends outside room height")
            if mount == "wall":
                wall = next((w for w in room["walls"] if w["id"] == placement.get("wall_id") and not w["virtual"]), None)
                if not wall:
                    raise ValueError("wall Item lacks a valid real-wall association")
                direction = (np.asarray(wall["b"]) - wall["a"]) / wall["length"]
                relative = np.asarray([placement["position"][0], placement["position"][2]]) - wall["a"]
                inward = float(np.dot(relative, wall["inward_normal"]))
                corners = list(footprint(placement).exterior.coords)[:-1]
                projected = [float(np.dot(np.asarray(point) - wall["a"], direction)) for point in corners]
                if min(projected) < .05 - 1e-7 or max(projected) > wall["length"] - .05 + 1e-7 or not 0 <= inward <= placement["size"][1]/2 + .15:
                    raise ValueError("wall Item lies outside its associated real wall")
            if mount == "tabletop":
                support = active.get(placement.get("support_id"))
                if not support or support["category"] not in SUPPORT_CATEGORIES:
                    conflicts.append({"code": "missing_support", "target_ids": [item["id"]], "action_ids": [], "reason": "Required support is absent."})
                    continue
                sp = support["placement"]
                if abs(placement["position"][1] - sp["position"][1] - sp["size"][2]) > .01 or not footprint(sp).buffer(1e-7).covers(footprint(placement).buffer(.05)):
                    conflicts.append({"code": "invalid_support", "target_ids": [item["id"]], "action_ids": [], "reason": "Item does not fit on the measured support top."})
                seen, current = {item["id"]}, support
                while current["placement"].get("support_id") in active:
                    if current["id"] in seen:
                        conflicts.append({"code": "cyclic_support", "target_ids": [item["id"]], "action_ids": [], "reason": "Support relationships contain a cycle."})
                        break
                    seen.add(current["id"])
                    current = active[current["placement"]["support_id"]]
            collisions = check_overlaps(room, scene, item["id"])
            if collisions:
                conflicts.append({"code": "blocked_doorway" if any(c.startswith("keep_clear:") for c in collisions) else "collision",
                                  "target_ids": [item["id"]], "structure": collisions, "action_ids": [], "reason": "Item violates required placement clearance."})
        except (KeyError, TypeError, ValueError):
            conflicts.append({"code": "invalid_placement", "target_ids": [item["id"]], "action_ids": [], "reason": "Item geometry or Mount is invalid."})
    if constraints and constraints.get("intent") == "redesign":
        conflicts.extend(_access_conflicts(room, scene))
    return conflicts


def _access_conflicts(room, scene):
    if not room.get("zones"):
        return []
    obstacles = [footprint(i["placement"]).buffer(.05) for i in scene["items"]
                 if i.get("status") != "removed" and _collision_class(i) == "floor"]
    free = Polygon(room["floor"]["polygon"]).difference(unary_union(obstacles)).buffer(-.45, join_style=2)
    components = [free] if free.geom_type == "Polygon" else list(free.geoms) if free.geom_type == "MultiPolygon" else []
    zones = [Polygon(z["polygon"]) for z in room["zones"]]
    connected = any(all(component.intersection(zone).area > 1e-8 for zone in zones)
                    and component.difference(unary_union(zones)).area > .01 for component in components)
    if connected:
        return []
    return [{"code": "blocked_access", "reason": "Door access does not connect to usable free floor with the required 0.9 m passage.",
             "target_ids": [], "action_ids": [], "structure": [f"keep_clear:{z['id']}" for z in room["zones"]]}]


def _repair_access(room, scene, plan, constraints, result, hard, base_scene):
    if not constraints.get("allow_optional_access_removal", base_scene is None):
        return
    additions = {a["add_id"]: (index, a) for index, a in enumerate(plan.get("adds", []))}
    explicit = set(constraints.get("explicit_selection_ids", []))
    candidates = [i for i in scene["items"] if i.get("status") != "removed" and i.get("origin") == "new"
                  and i.get("add_id") in additions and i["add_id"] not in hard
                  and i.get("selection_id") not in explicit and not _protected(i, constraints) and _collision_class(i) == "floor"]
    candidates.sort(key=lambda i: (additions[i["add_id"]][1].get("priority") if additions[i["add_id"]][1].get("priority") is not None else additions[i["add_id"]][0], additions[i["add_id"]][0], i["id"]), reverse=True)
    while _access_conflicts(room, scene):
        item = next((i for i in candidates if not any(other.get("status") != "removed" and other["placement"].get("support_id") == i["id"] for other in scene["items"])), None)
        if item is None:
            return
        candidates.remove(item)
        scene["items"].remove(item)
        action = additions[item["add_id"]][1]
        result["omissions"].append({"add_id": item["add_id"], "action_id": action["action_id"], "units": [{"item_id": item["id"], "code": "access_omitted", "reason": "Optional Addition omitted to restore required access."}]})
        result["warnings"].append({"code": "access_omitted", "message": "Optional Addition omitted to restore required access.", "action_id": action["action_id"]})
        outcome = next(o for o in result["action_outcomes"] if o["action_id"] == action["action_id"])
        outcome["affected_item_ids"].remove(item["id"])
        outcome.update(outcome="applied" if outcome["affected_item_ids"] else "failed", code="partial_quantity" if outcome["affected_item_ids"] else "access_omitted", reason="Optional units omitted to restore required access.")


def _existing(room, constraints):
    items = []
    instructions = constraints.get("instructions", {})
    for obj in room["objects"]:
        placement = {"position": [obj["center"][0], obj["base_y"], obj["center"][1]], "yaw": obj["yaw"],
                     "size": obj["size"], "mount": obj["mount"], "wall_id": obj.get("wall_id"),
                     "support_id": f"i_{obj['support_id']}" if obj.get("support_id") else None}
        render = render_descriptor(obj["category"])
        render["tint"] = obj.get("attrs", {}).get("color", render["tint"])
        items.append({"id": f"i_{obj['id']}", "object_id": obj["id"], "add_id": None, "origin": "existing",
                      "status": "existing", "category": obj["category"], "label": obj["category"],
                      "placement": deepcopy(placement), "original_placement": deepcopy(placement),
                      "last_valid_placement": deepcopy(placement), "instruction": instructions.get(obj["id"], "decide"),
                      "fixed_in_place": obj["fixed_in_place"], "reason": "Measured original Object",
                      "render": render})
    return items


def _target_id(target):
    if not target:
        return None
    if isinstance(target, str):
        return target
    if target.get("kind") == "object":
        return f"i_{target['id']}"
    if target.get("kind") in ("addition_unit", "new_unit"):
        return f"i_{target.get('add_id', target.get('id'))}_{target['unit_index']}"
    return target.get("id")


def _anchor_target_ids(anchor):
    return {_target_id(choice.get("target")) for choice in [anchor, *anchor.get("alternatives", [])] if choice.get("target")}


def _anchor(room, anchor, size, category, items):
    kind = anchor["type"]
    w, d, h = size
    if category not in CATEGORIES:
        raise ValueError("Unknown category.")
    if CATEGORIES[category]["mount"] in ("wall", "ceiling") and kind not in ("on_wall", "on_top_of"):
        raise ValueError("Category requires a supported non-floor Mount Anchor.")
    if kind == "on_wall" and CATEGORIES[category]["mount"] != "wall":
        raise ValueError("Category does not support a wall Mount.")
    floor = Polygon(room["floor"]["polygon"])
    walls = {wall["id"]: wall for wall in room["walls"]}
    placement: dict[str, Any] = {"position": [0, 0, 0], "yaw": 0, "size": list(size), "mount": "floor"}
    if kind in ("against_wall", "on_wall", "in_front_of_window"):
        if kind == "in_front_of_window":
            opening = next((o for o in room["openings"] if o["id"] == anchor["opening_id"] and o["type"] == "window"), None)
            if not opening:
                raise ValueError("Unknown window Anchor.")
            wall = walls[opening["wall_id"]]
            along = opening["offset"] + opening["width"] / 2
        else:
            wall = walls[anchor["wall_id"]]
            alignment = anchor["alignment"]
            offset = anchor.get("offset") or 0
            # A->B runs right for an observer inside facing the wall.
            along = wall["length"] / 2 if alignment == "center" else w/2 + offset if alignment == "left" else wall["length"] - w/2 - offset
        if wall["virtual"]:
            raise ValueError("virtual wall cannot be an Anchor")
        direction = (np.asarray(wall["b"]) - wall["a"]) / wall["length"]
        normal = np.asarray(wall["inward_normal"])
        p = np.asarray(wall["a"]) + direction * along + normal * (d/2 + .05)
        placement.update(position=[float(p[0]), 0, float(p[1])], yaw=math.atan2(normal[0], normal[1]), wall_id=wall["id"])
        if kind == "on_wall":
            below = [i["placement"] for i in items if i.get("status") != "removed" and i["placement"].get("wall_id") == wall["id"] and _collision_class(i) == "floor" and abs(LineString([wall["a"], wall["b"]]).project(Point(i["placement"]["position"][0], i["placement"]["position"][2])) - along) <= (w+i["placement"]["size"][0])/2]
            center_y = anchor.get("height")
            if center_y is None:
                center_y = max([1.45, *(p["position"][1] + p["size"][2] + .25 + h/2 for p in below)])
            placement["position"][1] = center_y - h/2
            placement["mount"] = "wall"
    elif kind == "room_center":
        longest = max(room["walls"], key=lambda wall: (wall["length"], wall["id"]))
        normal = longest["inward_normal"]
        placement.update(position=[floor.centroid.x, 0, floor.centroid.y], yaw=math.atan2(normal[0], normal[1]))
    elif kind == "corner":
        corner = next((c for c in room["corners"] if c["id"] == anchor["corner_id"]), None)
        if not corner:
            raise ValueError("Unknown corner Anchor.")
        pair = [walls[key] for key in corner["wall_ids"]]
        if len(pair) != 2 or any(wall["virtual"] for wall in pair):
            raise ValueError("Corner requires two real walls.")
        normal = np.sum([wall["inward_normal"] for wall in pair], axis=0)
        normal = normal / np.linalg.norm(normal)
        facing = normal if category in ("sofa", "armchair", "chair", "stool") else max(pair, key=lambda wall: wall["length"])["inward_normal"]
        yaw = math.atan2(facing[0], facing[1])
        right, forward = np.array([math.cos(yaw), -math.sin(yaw)]), np.array([math.sin(yaw), math.cos(yaw)])
        distances = [.05 + abs(np.dot(wall["inward_normal"], right))*w/2 + abs(np.dot(wall["inward_normal"], forward))*d/2 for wall in pair]
        p = np.linalg.solve(np.asarray([wall["inward_normal"] for wall in pair]), np.asarray(distances)) + corner["position"]
        placement.update(position=[float(p[0]), 0, float(p[1])], yaw=yaw)
    else:
        target_id = _target_id(anchor.get("target"))
        target = next((i for i in items if i["id"] == target_id and i.get("status") != "removed"), None)
        if not target:
            raise ValueError("Required Anchor target is absent or removed.")
        tp = target["placement"]
        tx, ty, tz = tp["position"]
        tw, td, th = tp["size"]
        yaw = tp["yaw"]
        right, forward = np.array([math.cos(yaw), -math.sin(yaw)]), np.array([math.sin(yaw), math.cos(yaw)])
        p = np.array([tx, tz])
        if kind == "under":
            if category != "rug":
                raise ValueError("under is reserved for rugs")
        elif kind == "on_top_of":
            if target["category"] not in SUPPORT_CATEGORIES:
                raise ValueError("target has no supported top")
            placement.update(mount="tabletop", support_id=target_id)
            placement["position"][1] = ty + th
        elif kind == "next_to":
            side = anchor["side"]
            if side == "front":
                p += forward * (td/2 + d/2 + .10)
                yaw += math.pi
            else:
                p += right * (tw/2 + w/2 + .10) * (-1 if side == "left" else 1)
        elif kind == "facing":
            distance = anchor.get("distance")
            if distance is None:
                distance = .45 if category in SUPPORT_CATEGORIES else .8
            p += forward * (td/2 + d/2 + distance)
            yaw += math.pi
        else:
            raise ValueError("unsupported Anchor")
        placement["position"][0], placement["position"][2] = map(float, p)
        placement["yaw"] = yaw
    return placement


def _candidate_positions(room, anchor, size, category, items, constraints):
    placement = _anchor(room, anchor, size, category, items)
    yield placement
    if constraints.get("allow_adjustments", True):
        wall_id = placement.get("wall_id")
        if wall_id and placement["mount"] in ("floor", "wall"):
            wall = next(w for w in room["walls"] if w["id"] == wall_id)
            direction = (np.asarray(wall["b"]) - wall["a"]) / wall["length"]
            for step in range(1, 11):
                for sign in (1, -1):
                    candidate = deepcopy(placement)
                    candidate["position"][0] += float(direction[0] * step * .1 * sign)
                    candidate["position"][2] += float(direction[1] * step * .1 * sign)
                    yield candidate
        if placement["mount"] == "floor" and constraints.get("allow_rotation", True):
            rotated = deepcopy(placement)
            rotated["yaw"] += math.pi/2
            if wall_id:
                normal = next(w["inward_normal"] for w in room["walls"] if w["id"] == wall_id)
                rotated["position"][0] += normal[0] * (size[0]-size[1])/2
                rotated["position"][2] += normal[1] * (size[0]-size[1])/2
            yield rotated


def _candidates(room, anchor, size, category, items, constraints):
    anchors = [anchor]
    if constraints.get("allow_adjustments", True) and constraints.get("allow_alternative_anchors", True):
        anchors.extend(anchor.get("alternatives", []))
    for choice in anchors:
        attempts = constraints if choice is anchor else {**constraints, "allow_adjustments": False}
        for placement in _candidate_positions(room, choice, size, category, items, attempts):
            if choice["type"] == "in_front_of_window":
                opening = next(o for o in room["openings"] if o["id"] == choice["opening_id"])
                if placement["position"][1] + size[2] > opening["bottom"]:
                    wall = next(w for w in room["walls"] if w["id"] == opening["wall_id"])
                    direction = (np.asarray(wall["b"]) - wall["a"]) / wall["length"]
                    along = float(np.dot(np.asarray([placement["position"][0], placement["position"][2]]) - wall["a"], direction))
                    yaw = placement["yaw"]
                    half_width = abs(float(np.dot(direction, [math.cos(yaw), -math.sin(yaw)]))) * size[0]/2 + abs(float(np.dot(direction, [math.sin(yaw), math.cos(yaw)]))) * size[1]/2
                    if along + half_width + .05 > opening["offset"] and along - half_width - .05 < opening["offset"] + opening["width"]:
                        continue
            yield placement


def _verified_selection(selections, selection_id, category):
    selection = selections.get(selection_id)
    if not selection or selection.get("selection_id") != selection_id or selection.get("category") != category:
        raise ValueError("Action requires its exact verified selection.")
    size, evidence = selection["dimensions"], selection.get("dimension_evidence", {})
    if (evidence.get("outcome") != "verified" or evidence.get("variant_id") != selection["variant_id"]
            or evidence.get("dimensions", evidence.get("size_m")) != size or len(size) != 3
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v > 0 for v in size)):
        raise ValueError("Verified dimensions must match the selected exact variant.")
    return selection


def _protected(item, constraints):
    return item.get("fixed_in_place") or item.get("instruction") == "keep" or constraints.get("instructions", {}).get(item.get("object_id") or item["id"], item.get("instruction")) == "keep"


def _outcome(result, action, kind, outcome, code, reason, affected=None):
    result["action_outcomes"].append({"action_id": action["action_id"], "type": kind, "outcome": outcome,
        "code": code, "reason": reason, "affected_item_ids": affected or []})
    if outcome == "failed":
        result["warnings"].append({"code": code, "message": reason, "action_id": action["action_id"]})


def _find_placement(room, scene, item, anchor, constraints):
    issues = []
    target_id = _target_id(anchor.get("target"))
    if target_id and not any(i["id"] == target_id and i.get("status") != "removed" for i in scene["items"]):
        return None, [{"code": "missing_support" if anchor["type"] == "on_top_of" else "missing_target", "reason": "Required Anchor target is absent or removed."}]
    try:
        for placement in _candidates(room, anchor, item["placement"]["size"], item["category"], scene["items"], constraints):
            candidate = deepcopy(item)
            candidate["placement"] = placement
            trial = {**scene, "items": [i for i in scene["items"] if i["id"] != item["id"]] + [candidate]}
            issues = validate_scene(room, trial, constraints if constraints.get("_base_scene_edit") else None)
            if not issues:
                return placement, []
    except (KeyError, StopIteration, TypeError, ValueError, np.linalg.LinAlgError):
        issues = [{"code": "bad_anchor", "reason": "Anchor is unresolved or incompatible."}]
    return None, issues or [{"code": "collision", "reason": "No valid placement was found."}]


def _apply_edit(room, scene, action, kind, selections, constraints):
    target_id = action.get("target_item_id", action.get("removed_item_id", _target_id(action.get("target"))))
    item = next((i for i in scene["items"] if i["id"] == target_id), None)
    if not item:
        return "failed", "missing_target", "Target Item is absent from the base Scene.", []
    if kind == "unlock":
        explicit = constraints.get("explicit_unlock_ids", [])
        if item.get("fixed_in_place"):
            return "failed", "permanent_fixture", "Permanent fixtures cannot be unlocked.", []
        if not action.get("explicit_user_unlock_context") or not ({item["id"], item.get("object_id")} & set(explicit)):
            return "failed", "kept_object", "Unlock requires explicit user authorization for this target.", []
        if item.get("instruction") != "keep" and constraints.get("instructions", {}).get(item.get("object_id")) != "keep":
            return "no_op", "already_unlocked", "Target is already unlocked.", []
        item["instruction"] = "decide"
        constraints.setdefault("instructions", {})[item.get("object_id") or item["id"]] = "decide"
        return "applied", "unlocked", "Target unlocked.", [item["id"]]
    if _protected(item, constraints):
        return "failed", "permanent_fixture" if item.get("fixed_in_place") else "kept_object", "Protected target cannot be changed.", []
    if kind != "restore" and item.get("status") == "removed":
        return "failed", "missing_target", "Target is removed from this Scene.", []
    before = deepcopy(item)
    if kind == "move":
        placement, issues = _find_placement(room, scene, item, action["anchor"], constraints)
        if placement is None:
            return "failed", issues[0]["code"], issues[0]["reason"], []
        current = item["placement"]
        if (np.allclose(placement["position"], current["position"], rtol=0, atol=1e-7)
                and math.isclose(math.remainder(placement["yaw"] - current["yaw"], 2*math.pi), 0, abs_tol=1e-7)
                and all(placement.get(key) == current.get(key) for key in ("mount", "wall_id", "support_id"))):
            return "no_op", "unchanged_placement", "Target is already at the requested placement.", []
        item.update(placement=placement, anchor=deepcopy(action["anchor"]))
        if item["origin"] == "existing":
            item["status"] = "moved"
    elif kind == "remove":
        if item.get("add_id") in constraints.get("must_have_add_ids", []) or item.get("selection_id") in constraints.get("must_have_selection_ids", []) or item["category"] in constraints.get("must_have_categories", []):
            return "failed", "protected_requirement", "A required Item cannot be omitted.", []
        item["last_valid_placement"] = deepcopy(item["placement"])
        item["status"] = "removed"
    elif kind == "restore":
        if item.get("status") != "removed":
            return "no_op", "already_present", "Target is already present.", []
        item["placement"] = deepcopy(item.get("last_valid_placement") or item.get("original_placement"))
        item["status"] = "new" if item["origin"] == "new" else "existing" if item["placement"] == item.get("original_placement") else "moved"
    elif kind == "replace":
        try:
            selection = _verified_selection(selections, action["selection_id"], item["category"])
        except (KeyError, TypeError, ValueError) as exc:
            return "failed", "unverified_selection", str(exc), []
        if item.get("selection_id") == selection["selection_id"]:
            return "no_op", "unchanged_product", "This Product is already selected.", []
        if item["origin"] == "existing":
            item["replacement_of_object_id"] = item["object_id"]
        item["placement"]["size"] = deepcopy(selection["dimensions"])
        item.update(selection_id=selection["selection_id"], variant_id=selection["variant_id"],
            offer_id=selection["offer_id"], product=deepcopy(selection), render=deepcopy(selection.get("render", {})),
            label=selection.get("title", item["category"]))
    issues = validate_scene(room, scene, constraints if constraints.get("_base_scene_edit") else None)
    if issues:
        item.clear()
        item.update(before)
        return "failed", issues[0]["code"], issues[0]["reason"], []
    if kind != "remove":
        item["last_valid_placement"] = deepcopy(item["placement"])
    item["reason"] = action.get("reason", "")
    return "applied", "placed" if kind in ("move", "restore", "replace") else "removed", "Requested change applied.", [item["id"]]


def solve(room_snapshot, plan, selections, constraints, base_scene=None):
    room, constraints = _room(room_snapshot), deepcopy(constraints)
    constraints["_base_scene_edit"] = base_scene is not None
    scene = deepcopy(base_scene) if base_scene is not None else {"schema_version": 1, "room": deepcopy(room),
        "room_snapshot_id": room_snapshot.get("snapshot_id"), "items": _existing(room, constraints),
        "products": [], "purchase_summary": None, "summary": plan.get("summary", ""), "warnings": [],
        "design_id": None, "parent_id": None}
    result: dict[str, Any] = {"schema_version": 1, "scene": scene, "action_outcomes": [], "placements": [],
        "omissions": [], "warnings": [], "conflicts": []}
    if not room.get("validity", {}).get("usable"):
        result["conflicts"] = validate_scene(room, scene)
        return result
    if constraints.get("intent", "add") == "add" and any(plan.get(k) for k in ("moves", "removes", "replaces", "restores", "unlocks")):
        result["conflicts"].append({"code": "intent_conflict", "reason": "Add preserves every existing Object.", "action_ids": [], "target_ids": []})
        return result
    additions = plan.get("adds", [])
    requested = [a for group in ("adds", "moves", "removes", "replaces", "restores", "unlocks") for a in plan.get(group, [])]
    identities = [a.get("action_id") for a in requested]
    if (any(not identity for identity in identities) or len(identities) != len(set(identities))
            or len({a.get("add_id") for a in additions}) != len(additions)
            or any(not a.get("add_id") or not isinstance(a.get("quantity"), int) or isinstance(a.get("quantity"), bool) or not 0 < a["quantity"] <= 100 for a in additions)):
        result["conflicts"].append({"code": "invalid_plan", "reason": "Actions require unique identities and positive bounded physical quantities.", "target_ids": [], "action_ids": []})
        return result
    hard = set(constraints.get("must_have_add_ids", []))
    hard.update(a["add_id"] for a in additions if a.get("selection_id") in constraints.get("must_have_selection_ids", []) or a.get("category") in constraints.get("must_have_categories", []))
    if any(a.get("priority") is None for a in additions):
        result["warnings"].append({"code": "missing_priority", "message": "Missing Priority falls back to plan order."})
    actions = [(kind, action, index) for kind, group in (("unlock", "unlocks"), ("remove", "removes"), ("move", "moves"), ("restore", "restores"), ("replace", "replaces"), ("add", "adds")) for index, action in enumerate(plan.get(group, []))]
    producers = {f"i_{a['add_id']}_{unit}": a["action_id"] for a in additions for unit in range(a["quantity"])}
    new_units = dict(producers)
    producers.update({_target_id(a.get("target")): a["action_id"] for kind, a, _ in actions if kind == "move"})
    producers.update({a["removed_item_id"]: a["action_id"] for kind, a, _ in actions if kind == "restore"})
    unlocks = {_target_id(a["target"]): a["action_id"] for kind, a, _ in actions if kind == "unlock"}
    dependencies = {}
    for kind, action, _ in actions:
        target_id = _target_id(action.get("target")) if kind in ("move", "remove", "unlock") else action.get("target_item_id", action.get("removed_item_id"))
        required = {producers[target] for target in _anchor_target_ids(action.get("anchor", {})) if target in producers}
        if kind in ("move", "remove", "unlock") and target_id in new_units:
            required.add(new_units[target_id])
        if kind == "restore":
            retained: dict[str, Any] = next((i for i in scene["items"] if i["id"] == target_id), {})
            support_id = (retained.get("last_valid_placement") or retained.get("original_placement") or {}).get("support_id")
            if support_id in producers:
                required.add(producers[support_id])
        if kind not in ("unlock", "add") and target_id in unlocks:
            required.add(unlocks[target_id])
        # Explicit dependent moves/removals must finish before changing their support.
        if kind in ("move", "remove", "replace"):
            dependents = {i["id"] for i in scene["items"] if i.get("status") != "removed" and i.get("placement", {}).get("support_id") == target_id}
            required.update(a["action_id"] for k, a, _ in actions if k in ("move", "remove") and _target_id(a.get("target")) in dependents)
        dependencies[action["action_id"]] = required
    rank = {"unlock": 0, "remove": 1, "move": 2, "restore": 3, "replace": 3, "add": 4}
    def order(entry):
        kind, action, index = entry
        priority = action.get("priority")
        area = math.prod(selections.get(action.get("selection_id"), {}).get("dimensions", [0, 0])[:2])
        return (rank[kind], index if priority is None else priority, -area if priority is not None else 0, index, action["action_id"])
    pending = sorted(actions, key=order)
    completed: set[str] = set()
    while pending:
        ready = next((entry for entry in pending if dependencies[entry[1]["action_id"]] <= completed), None)
        if ready is None:
            for kind, action, _ in pending:
                _outcome(result, action, kind, "failed", "cyclic_reference", "Anchor/action dependencies contain a cycle.")
                if base_scene is None:
                    result["conflicts"].append({"code": "cyclic_reference", "reason": "Anchor/action dependencies contain a cycle.", "target_ids": [], "action_ids": [action["action_id"]]})
            break
        pending.remove(ready)
        kind, action, _ = ready
        if kind != "add":
            outcome, code, reason, affected = _apply_edit(room, scene, action, kind, selections, constraints)
            _outcome(result, action, kind, outcome, code, reason, affected)
            completed.add(action["action_id"])
            continue
        placed, failures = [], []
        try:
            selection = _verified_selection(selections, action["selection_id"], action["category"])
            if action["category"] in constraints.get("avoid_categories", []) or action["selection_id"] in constraints.get("avoid_selection_ids", []):
                raise ValueError("Addition violates an explicit avoid constraint.")
            quantity = action["quantity"]
            if not isinstance(quantity, int) or isinstance(quantity, bool) or not 0 < quantity <= 100:
                raise ValueError("Addition quantity must be a positive bounded integer.")
            for unit in range(quantity):
                item = {"id": f"i_{action['add_id']}_{unit}", "object_id": None, "add_id": action["add_id"],
                    "origin": "new", "status": "new", "category": action["category"], "label": selection.get("title", action["category"]),
                    "selection_id": selection["selection_id"], "variant_id": selection["variant_id"], "offer_id": selection["offer_id"],
                    "product": deepcopy(selection), "instruction": "decide", "anchor": deepcopy(action["anchor"]),
                    "render": deepcopy(selection.get("render", {})), "reason": action.get("reason", ""),
                    "original_placement": None, "fixed_in_place": False, "placement": {"size": selection["dimensions"]}}
                if any(i["id"] == item["id"] for i in scene["items"]):
                    raise ValueError("Addition unit identity already exists.")
                placement, issues = _find_placement(room, scene, item, action["anchor"], constraints)
                if placement is None:
                    failures.append({"unit_index": unit, "code": issues[0]["code"], "reason": issues[0]["reason"]})
                else:
                    item["placement"], item["last_valid_placement"] = placement, deepcopy(placement)
                    scene["items"].append(item)
                    placed.append(item["id"])
        except (KeyError, TypeError, ValueError) as exc:
            failures.append({"code": "unverified_selection", "reason": str(exc)})
        if failures:
            result["omissions"].append({"add_id": action["add_id"], "action_id": action["action_id"], "units": failures})
            result["warnings"].append({"code": "addition_unplaced", "message": failures[0]["reason"], "action_id": action["action_id"]})
            if action["add_id"] in hard:
                result["conflicts"].append({"code": "must_have_unplaced", "reason": "Required Addition could not be placed.", "target_ids": [action["add_id"]], "action_ids": [action["action_id"]], "permitted_recovery": "verified_equivalent_or_question"})
        outcome = "applied" if placed else "failed"
        _outcome(result, action, "add", outcome, "partial_quantity" if placed and failures else failures[0]["code"] if failures else "placed", failures[0]["reason"] if failures else "Addition placed.", placed)
        completed.add(action["action_id"])
    if constraints.get("intent") == "redesign":
        _repair_access(room, scene, plan, constraints, result, hard, base_scene)
    result["conflicts"].extend(validate_scene(room, scene, constraints))
    result["placed_unit_demand"] = {key: sum(i.get("selection_id") == key and i.get("status") != "removed" for i in scene["items"]) for key in set(selections) | {i["selection_id"] for i in scene["items"] if i.get("selection_id")}}
    # Historical base Product evidence stays unchanged even when a current lookup differs.
    products = {p["selection_id"]: deepcopy(p) for p in scene.get("products", [])}
    products.update({i["selection_id"]: deepcopy(i["product"]) for i in scene["items"] if i.get("product") and i.get("status") != "removed"})
    scene["products"] = [products[key] for key in sorted(products) if result["placed_unit_demand"].get(key)]
    result["placements"] = [{"item_id": i["id"], "selection_id": i.get("selection_id"), "placement": deepcopy(i["placement"])} for i in scene["items"] if i.get("status") != "removed" and any(i["id"] in o["affected_item_ids"] and o["outcome"] == "applied" for o in result["action_outcomes"])]
    scene["summary"], scene["action_outcomes"], scene["warnings"] = plan.get("summary", ""), deepcopy(result["action_outcomes"]), deepcopy(result["warnings"])
    return result
