"""Deterministic candidate placement. Publication and purchase accounting are external."""

from copy import deepcopy
import math
from typing import Any

import numpy as np
from shapely.geometry import LineString, Point, Polygon

from .categories import CATEGORIES, SUPPORT_CATEGORIES


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
    if own_class in ("floor", "rug", "tabletop", "ceiling") and not floor.buffer(1e-7).covers(bounds.buffer(.05, join_style=2)):
        collisions.append("wall")
    if own_class == "floor":
        for zone in room["zones"]:
            if bounds.buffer(.05, join_style=2).intersection(Polygon(zone["polygon"])).area > 1e-8:
                collisions.extend([f"keep_clear:{zone['id']}", f"door:{zone['opening_id']}"])
    for other in items.values():
        if other["id"] == item_id:
            continue
        other_class = _collision_class(other)
        relevant = ((own_class == other_class and own_class in ("floor", "rug")) or
                    (own_class == other_class == "tabletop" and placement.get("support_id") == other["placement"].get("support_id")))
        if relevant and bounds.buffer(.05, join_style=2).intersection(footprint(other["placement"])).area > 1e-8:
            collisions.append(other["id"])
        if own_class == "wall" and placement.get("wall_id") == other["placement"].get("wall_id"):
            op = other["placement"]
            if other_class in ("floor", "wall") and placement["position"][1] < op["position"][1] + op["size"][2] + .05 and op["position"][1] < placement["position"][1] + placement["size"][2] + .05:
                if bounds.buffer(.05).intersects(footprint(op)):
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


def validate_scene(snapshot, scene):
    room, conflicts = _room(snapshot), []
    if not room.get("validity", {}).get("usable"):
        return [{"code": "invalid_room", "reason": "Room boundary is not valid.", "target_ids": [], "action_ids": []}]
    active = {i["id"]: i for i in scene["items"] if i.get("status") != "removed"}
    represented = [i.get("object_id") for i in scene["items"] if i.get("origin") == "existing"]
    if set(represented) != {o["id"] for o in room["objects"]} or len(represented) != len(set(represented)):
        conflicts.append({"code": "missing_original_object", "reason": "Every original Object must remain represented exactly once.", "target_ids": [], "action_ids": []})
    if len(active) != sum(i.get("status") != "removed" for i in scene["items"]):
        conflicts.append({"code": "duplicate_identity", "reason": "Scene Item IDs must be unique.", "target_ids": [], "action_ids": []})
    for item in active.values():
        placement = item["placement"]
        try:
            values = [*placement["position"], *placement["size"], placement["yaw"]]
            if len(placement["position"]) != 3 or len(placement["size"]) != 3 or not all(math.isfinite(v) for v in values) or min(placement["size"]) <= 0:
                raise ValueError("invalid placement numbers")
            mount = placement["mount"]
            if mount == "floor" and abs(placement["position"][1]) > 1e-6:
                raise ValueError("floor Item has a nonzero base")
            if mount not in ("floor", "wall", "tabletop", "ceiling"):
                raise ValueError("unsupported Mount")
            if placement["position"][1] < -.001 or placement["position"][1] + placement["size"][2] > room["height"] + .001:
                raise ValueError("Item extends outside room height")
            if mount == "wall":
                wall = next((w for w in room["walls"] if w["id"] == placement.get("wall_id") and not w["virtual"]), None)
                if not wall or LineString([wall["a"], wall["b"]]).distance(Point(placement["position"][0], placement["position"][2])) > .3:
                    raise ValueError("wall Item lacks a valid real-wall association")
            if mount == "tabletop":
                support = active.get(placement.get("support_id"))
                if not support or support["category"] not in SUPPORT_CATEGORIES:
                    conflicts.append({"code": "missing_support", "target_ids": [item["id"]], "action_ids": [], "reason": "Required support is absent."})
                    continue
                sp = support["placement"]
                if abs(placement["position"][1] - sp["position"][1] - sp["size"][2]) > .01 or not footprint(sp).buffer(1e-7).covers(footprint(placement).buffer(.05, join_style=2)):
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
    return conflicts


def _existing(room, constraints):
    items = []
    instructions = constraints.get("instructions", {})
    for obj in room["objects"]:
        placement = {"position": [obj["center"][0], obj["base_y"], obj["center"][1]], "yaw": obj["yaw"],
                     "size": obj["size"], "mount": obj["mount"], "wall_id": obj.get("wall_id"),
                     "support_id": f"i_{obj['support_id']}" if obj.get("support_id") else None}
        items.append({"id": f"i_{obj['id']}", "object_id": obj["id"], "add_id": None, "origin": "existing",
                      "status": "existing", "category": obj["category"], "label": obj["category"],
                      "placement": deepcopy(placement), "original_placement": deepcopy(placement),
                      "last_valid_placement": deepcopy(placement), "instruction": instructions.get(obj["id"], "decide"),
                      "fixed_in_place": obj["fixed_in_place"], "reason": "Measured original Object",
                      "render": {"kind": "standin", "category": obj["category"],
                                 "tint": obj.get("attrs", {}).get("color", CATEGORIES[obj["category"]]["default_tint"]),
                                 "scaling_mode": "normalized", "pivot": "bottom_center", "forward": "+Z"}})
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


def _anchor(room, anchor, size, category, items):
    kind = anchor["type"]
    w, d, h = size
    floor = Polygon(room["floor"]["polygon"])
    walls = {wall["id"]: wall for wall in room["walls"]}
    placement: dict[str, Any] = {"position": [0, 0, 0], "yaw": 0, "size": list(size), "mount": "floor"}
    if kind in ("against_wall", "on_wall", "in_front_of_window"):
        if kind == "in_front_of_window":
            opening = next(o for o in room["openings"] if o["id"] == anchor["opening_id"] and o["type"] == "window")
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
        if kind == "in_front_of_window" and h > opening["bottom"]:
            raise ValueError("Item obscures window above its sill")
    elif kind == "room_center":
        longest = max(room["walls"], key=lambda wall: (wall["length"], wall["id"]))
        normal = longest["inward_normal"]
        placement.update(position=[floor.centroid.x, 0, floor.centroid.y], yaw=math.atan2(normal[0], normal[1]))
    elif kind == "corner":
        corner = next(c for c in room["corners"] if c["id"] == anchor["corner_id"])
        pair = [walls[key] for key in corner["wall_ids"]]
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
        target = next(i for i in items if i["id"] == target_id and i.get("status") != "removed")
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


def _candidates(room, anchor, size, category, items, constraints):
    placement = _anchor(room, anchor, size, category, items)
    yield placement
    if constraints.get("allow_adjustments", True):
        wall_id = placement.get("wall_id")
        if wall_id and placement["mount"] == "floor":
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
        for alternative in anchor.get("alternatives", []):
            yield _anchor(room, alternative, size, category, items)


def solve(room_snapshot, plan, selections, constraints, base_scene=None):
    room = _room(room_snapshot)
    scene = deepcopy(base_scene) if base_scene else {"schema_version": 1, "room": deepcopy(room),
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
    # This initial floor-Addition seam leaves edit commands to the canonical edit controller.
    for kind in ("moves", "removes", "replaces", "restores", "unlocks"):
        for action in plan.get(kind, []):
            result["action_outcomes"].append({"action_id": action["action_id"], "type": kind.rstrip("s"),
                "outcome": "failed", "code": "unavailable_capability", "reason": "This placement operation accepts Additions only.", "affected_item_ids": []})
            result["conflicts"].append({"code": "unavailable_capability", "reason": "Existing-Item edits require their edit operation.", "action_ids": [action["action_id"]], "target_ids": []})
    additions = list(enumerate(plan.get("adds", [])))
    pending = sorted(additions, key=lambda pair: (pair[1].get("priority", pair[0]),
                     -math.prod(selections.get(pair[1].get("selection_id"), {}).get("dimensions", [0, 0])[:2]), pair[0]))
    if any("priority" not in addition for _, addition in additions):
        result["warnings"].append({"code": "missing_priority", "message": "Missing Priority falls back to plan order."})
    hard = set(constraints.get("must_have_add_ids", []))
    hard.update(a["add_id"] for _,a in additions if a.get("selection_id") in constraints.get("must_have_selection_ids", []) or a.get("category") in constraints.get("must_have_categories", []))
    while pending:
        progressed = False
        for index, addition in list(pending):
            target_id = _target_id(addition.get("anchor", {}).get("target"))
            if target_id and not any(i["id"] == target_id for i in scene["items"]):
                target_add = addition["anchor"]["target"].get("add_id")
                if any(other["add_id"] == target_add for _, other in pending if other is not addition):
                    continue
            pending.remove((index, addition))
            progressed = True
            selection = selections.get(addition.get("selection_id"))
            placed, failures = [], []
            try:
                if not selection or selection["selection_id"] != addition["selection_id"] or selection["category"] != addition["category"] or selection.get("dimension_evidence", {}).get("outcome") != "verified":
                    raise ValueError("Addition requires its exact verified selection.")
                size = selection["dimensions"]
                evidence = selection["dimension_evidence"]
                evidence_size = evidence.get("dimensions", evidence.get("size_m"))
                if evidence.get("variant_id") != selection["variant_id"] or evidence_size != size or len(size) != 3 or not all(math.isfinite(v) and v > 0 for v in size):
                    raise ValueError("Verified dimensions must match the selected exact variant.")
                quantity = addition["quantity"]
                if not isinstance(quantity, int) or isinstance(quantity, bool) or not 0 < quantity <= 100:
                    raise ValueError("Addition quantity must be a positive bounded integer.")
                for unit in range(quantity):
                    item = {"id": f"i_{addition['add_id']}_{unit}", "object_id": None, "add_id": addition["add_id"],
                            "origin": "new", "status": "new", "category": addition["category"], "label": selection.get("title", addition["category"]),
                            "selection_id": selection["selection_id"], "variant_id": selection["variant_id"], "offer_id": selection["offer_id"],
                            "product": deepcopy(selection), "instruction": "decide", "anchor": deepcopy(addition["anchor"]),
                            "render": deepcopy(selection.get("render", {})), "reason": addition.get("reason", ""),
                            "original_placement": None, "fixed_in_place": False}
                    if any(i["id"] == item["id"] for i in scene["items"]):
                        raise ValueError("Addition unit identity already exists.")
                    accepted = False
                    try:
                        for placement in _candidates(room, addition["anchor"], size, addition["category"], scene["items"], constraints):
                            item["placement"] = placement
                            candidate = {**scene, "items": [*scene["items"], item]}
                            issues = [c for c in validate_scene(room, candidate) if item["id"] in c["target_ids"]]
                            if not issues:
                                item["last_valid_placement"] = deepcopy(placement)
                                scene["items"].append(item)
                                placed.append(item["id"])
                                result["placements"].append({"item_id": item["id"], "selection_id": selection["selection_id"], "placement": deepcopy(placement)})
                                accepted = True
                                break
                    except (KeyError, StopIteration, TypeError, ValueError):
                        issues = [{"code": "bad_anchor", "reason": "Anchor is unresolved or incompatible."}]
                    if not accepted:
                        failures.append({"unit_index": unit, "reason": issues[0]["reason"] if issues else "No valid placement was found.", "code": issues[0]["code"] if issues else "collision"})
            except (KeyError, TypeError, ValueError) as exc:
                failures.append({"code": "unverified_selection", "reason": str(exc)})
            if failures:
                result["warnings"].append({"code":"addition_unplaced","message":f"{addition['category']}: {len(failures)} requested unit(s) could not be placed. {failures[0]['reason']}","action_id":addition["action_id"]})
                result["omissions"].append({"add_id": addition["add_id"], "action_id": addition["action_id"], "units": failures})
                if addition["add_id"] in hard:
                    result["conflicts"].append({"code": "must_have_unplaced", "reason": "Required Addition could not be placed.", "target_ids": [addition["add_id"]], "action_ids": [addition["action_id"]], "permitted_recovery": "verified_equivalent_or_question"})
            result["action_outcomes"].append({"action_id": addition["action_id"], "type": "add", "outcome": "applied" if placed else "failed", "affected_item_ids": placed,
                                             "code": "partial_quantity" if placed and failures else failures[0]["code"] if failures else "placed", "reason": failures[0]["reason"] if failures else "Addition placed."})
        if not progressed:
            for _, addition in pending:
                result["conflicts"].append({"code": "cyclic_reference", "reason": "Addition dependencies cannot be resolved.", "target_ids": [addition["add_id"]], "action_ids": [addition["action_id"]]})
                result["action_outcomes"].append({"action_id": addition["action_id"], "type": "add", "outcome": "failed", "code": "cyclic_reference", "reason": "Cyclic support references.", "affected_item_ids": []})
            break
    result["conflicts"].extend(validate_scene(room, scene))
    result["placed_unit_demand"] = {key: sum(i.get("selection_id") == key and i.get("status") != "removed" for i in scene["items"]) for key in selections}
    scene["products"] = [deepcopy(selections[key]) for key, count in result["placed_unit_demand"].items() if count]
    scene["action_outcomes"] = deepcopy(result["action_outcomes"])
    scene["warnings"] = deepcopy(result["warnings"])
    return result
