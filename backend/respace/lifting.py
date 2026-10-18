"""Pure calibrated lifting of stored, native sensor-orientation observations."""

import math

import numpy as np
from shapely.geometry import Point, Polygon

from .categories import CATEGORIES, SUPPORT_CATEGORIES
from .geometry import _matrix


def decode_depth(depth_bytes, confidence_bytes, width, height, *,
                 depth_format="float32_le_m", confidence_format="uint8"):
    if (type(width) is not int or type(height) is not int or not 0 < width <= 4096
            or not 0 < height <= 4096 or depth_format != "float32_le_m"
            or len(depth_bytes) != width * height * 4):
        raise ValueError("Depth dimensions, format and byte count must agree.")
    confidence = None
    if confidence_bytes is not None:
        if confidence_format != "uint8" or len(confidence_bytes) != width * height:
            raise ValueError("Confidence must match the depth observation.")
        confidence = np.frombuffer(confidence_bytes, dtype=np.uint8).reshape(height, width)
        if np.any(confidence > 2):
            raise ValueError("Unknown depth confidence level.")
    return {"depth": np.frombuffer(depth_bytes, dtype="<f4").reshape(height, width),
            "confidence": confidence, "width": width, "height": height, "units": "m"}


def _calibration(room, frame, rgb=None, depth=None):
    width, height = frame["w"], frame["h"]
    if (type(width) is not int or type(height) is not int or min(width, height) <= 0
            or frame.get("orientation") != "sensor_landscape"
            or frame["capture_id"] != room["capture_id"]):
        raise ValueError("Capture, dimensions and native sensor orientation must agree.")
    intrinsics = frame["intrinsics"]
    values = [float(intrinsics[k]) for k in ("fx", "fy", "cx", "cy")]
    if not all(math.isfinite(v) for v in values) or min(values[:2]) <= 0:
        raise ValueError("Finite calibrated intrinsics with positive focal lengths are required.")
    if rgb is not None and (np.asarray(rgb).shape != (height, width, 3)
                            or np.asarray(rgb).dtype != np.uint8):
        raise ValueError("RGB must match uploaded sensor-orientation pixels.")
    if depth is not None:
        dw, dh = depth["width"], depth["height"]
        if (dw * height != dh * width or np.asarray(depth["depth"]).shape != (dh, dw)
                or depth.get("units") != "m" or (depth["confidence"] is not None
                and np.asarray(depth["confidence"]).shape != (dh, dw))):
            raise ValueError("Depth pixels must share the image aspect, orientation and observation.")
    camera = _matrix(room["frame"]["room_from_world"]) @ _matrix(frame["transform"])
    if np.linalg.det(camera[:3, :3]) < 0:
        raise ValueError("Reflected camera axes are not a calibrated camera pose.")
    return camera, values


def _ray(camera, calibration, pixel):
    fx, fy, cx, cy = calibration
    u, v = pixel
    return camera[:3, :3] @ [(u - cx) / fx, -(v - cy) / fy, -1]


def _footprint(obj, expansion=0):
    x, z = obj["center"]
    width, depth, _ = obj["size"]
    c, s = math.cos(obj["yaw"]), math.sin(obj["yaw"])
    return Polygon([(x + c * a + s * b, z - s * a + c * b)
                    for a, b in [(-width/2, -depth/2), (width/2, -depth/2),
                                 (width/2, depth/2), (-width/2, depth/2)]]).buffer(expansion)


def _plane_hit(origin, direction, y):
    if abs(direction[1]) < 1e-9:
        return None
    t = (y - origin[1]) / direction[1]
    return (float(t), origin + t * direction) if t > 1e-6 else None


def _wall_hits(room, origin, direction):
    hits = []
    for wall in room["walls"]:
        if wall["virtual"]:
            continue
        normal = np.asarray(wall["inward_normal"])
        denominator = float(np.dot(direction[[0, 2]], normal))
        if abs(denominator) < 1e-9:
            continue
        t = float(np.dot(np.asarray(wall["a"]) - origin[[0, 2]], normal) / denominator)
        point = origin + t * direction
        axis = (np.asarray(wall["b"]) - wall["a"]) / wall["length"]
        offset = float(np.dot(point[[0, 2]] - wall["a"], axis))
        if t > 1e-6 and -1e-6 <= offset <= wall["length"] + 1e-6 and 0 <= point[1] <= room["height"]:
            hits.append((t, point, wall, offset))
    return sorted(hits, key=lambda h: (h[0], h[2]["id"]))


def _surface_hit(room, origin, direction, category):
    if CATEGORIES[category]["mount"] == "wall":
        hits = _wall_hits(room, origin, direction)
        if not hits:
            return None
        t, point, wall, _ = hits[0]
        return t, point, "wall", wall["id"], None
    if category == "ceiling_light":
        hit = _plane_hit(origin, direction, room["height"])
        return (*hit, "ceiling", None, None) if hit else None
    if category in ("table_lamp", "plant", "decor"):
        supports = []
        for obj in room["objects"]:
            if obj["category"] not in SUPPORT_CATEGORIES:
                continue
            hit = _plane_hit(origin, direction, obj["base_y"] + obj["size"][2])
            if hit and _footprint(obj).covers(Point(hit[1][[0, 2]])):
                supports.append((*hit, "tabletop", None, obj["id"]))
        if supports:
            return min(supports, key=lambda h: (h[0], h[4]))
    hit = _plane_hit(origin, direction, 0)
    return (*hit, "floor", None, None) if hit else None


def _qualified_depth(depth, frame, pixel, origin, direction, hit):
    if depth is None or depth["confidence"] is None:
        return None, {"state": "unavailable" if depth is None else "confidence_missing"}
    u = min(depth["width"] - 1, max(0, int(pixel[0] * depth["width"] / frame["w"])))
    v = min(depth["height"] - 1, max(0, int(pixel[1] * depth["height"] / frame["h"])))
    value = float(depth["depth"][v, u])
    if depth["confidence"][v, u] != 2:
        return None, {"state": "low_confidence"}
    if not math.isfinite(value) or not 0 < value < 5:
        return None, {"state": "invalid_range"}
    point = origin + value * direction
    disagreement = float(np.linalg.norm(point - hit))
    evidence = {"state": "accepted" if disagreement <= .3 + 1e-9 else "disagrees",
                "optical_depth_m": value, "disagreement_m": disagreement, "pixel": [u, v]}
    return (point if disagreement <= .3 + 1e-9 else None), evidence


def _rejection(room, origin, direction, hit, category):
    t, point, mount, wall_id, support_id = hit
    if mount != "wall":
        if not Polygon(room["floor"]["polygon"]).buffer(-.05).covers(Point(point[[0, 2]])):
            return "outside_floor"
        walls = _wall_hits(room, origin, direction)
        if walls and walls[0][0] < t - 1e-5:
            return "ray_exits_room"
        if mount == "tabletop":
            support = next(obj for obj in room["objects"] if obj["id"] == support_id)
            if not _footprint(support).covers(Point(point[[0, 2]])):
                return "outside_support"
        return None
    wall = next(w for w in room["walls"] if w["id"] == wall_id)
    axis = (np.asarray(wall["b"]) - wall["a"]) / wall["length"]
    offset = float(np.dot(point[[0, 2]] - wall["a"], axis))
    distance = abs(float(np.dot(point[[0, 2]] - wall["a"], wall["inward_normal"])))
    if distance > .15 + 1e-9 or not 0 <= offset <= wall["length"]:
        return "outside_wall"
    for opening in room["openings"]:
        if (opening["wall_id"] == wall_id and opening["offset"] <= offset <= opening["offset"] + opening["width"]
                and opening["bottom"] <= point[1] <= opening["bottom"] + opening["height"]
                and not (category == "curtain" and opening["type"] == "window")):
            return "opening_reflection"
    for obj in room["objects"]:
        if (category != "mirror" and obj["category"] == "mirror" and obj.get("wall_id") == wall_id
                and np.linalg.norm(point[[0, 2]] - obj["center"]) <= obj["size"][0] / 2
                and obj["base_y"] <= point[1] <= obj["base_y"] + obj["size"][2]):
            return "mirror_reflection"
    return None


def lift_keyframe(base_room, keyframe, detections, rgb, depth=None):
    """Raycasts establish Mount/elevation; qualified optical depth only refines X/Z."""
    from .colors import detected_sample, native_samples

    camera, calibration = _calibration(base_room, keyframe, rgb, depth)
    origin = camera[:3, 3]
    result = {"schema_version": 1, "capture_id": keyframe["capture_id"], "frame_id": keyframe["frame_id"],
              "input_revision": keyframe.get("input_revision", 1), "idx": keyframe["idx"],
              "state": "succeeded", "detections": [], "color_samples": [], "rejected": [], "diagnostics": []}
    result["color_samples"], result["color_diagnostics"] = native_samples(
        base_room, keyframe, camera, calibration, rgb, depth)
    for index, detection in enumerate(detections):
        category = detection["category"]
        evidence = {"id": f"det:{keyframe['frame_id']}:{index}", "category": category,
                    "frame_id": keyframe["frame_id"], "idx": keyframe["idx"], "box_px": detection["box_px"]}
        try:
            x1, y1, x2, y2 = map(float, detection["box_px"])
            if (category not in CATEGORIES or not all(math.isfinite(v) for v in (x1, y1, x2, y2))
                    or not 0 <= x1 < x2 <= keyframe["w"] or not 0 <= y1 < y2 <= keyframe["h"]):
                raise ValueError("invalid_detection")
            if category == "rug":
                pixels = [(x1, y2), (x2, y2), ((x1 + x2)/2, y1)]
            elif CATEGORIES[category]["mount"] == "wall":
                pixels = [((x1 + x2)/2, (y1 + y2)/2)]
            else:
                pixels = [((x1 + x2)/2, y1 if category == "ceiling_light" else y2)]
            points, methods, depth_evidence = [], [], []
            hit = None
            for pixel in pixels:
                direction = _ray(camera, calibration, pixel)
                hit = _surface_hit(base_room, origin, direction, category)
                if hit is None:
                    raise ValueError("no_allowed_surface")
                reason = _rejection(base_room, origin, direction, hit, category)
                if reason:
                    raise ValueError(reason)
                refined, diagnostic = _qualified_depth(depth, keyframe, pixel, origin, direction, hit[1])
                point = hit[1].copy()
                if refined is not None:
                    point[[0, 2]] = refined[[0, 2]]
                    refined_hit = (hit[0], point, *hit[2:])
                    if _rejection(base_room, origin, direction, refined_hit, category):
                        diagnostic["state"] = "outside_surface"
                        point = hit[1].copy()
                        refined = None
                points.append(point)
                methods.append("raycast+depth" if refined is not None else "raycast")
                depth_evidence.append(diagnostic)
            assert hit is not None
            point = np.mean(points, axis=0)
            size = list(CATEGORIES[category]["default_size"])
            estimate = [(x2-x1) * hit[0] / calibration[0], size[1], (y2-y1) * hit[0] / calibration[1]]
            bounds = CATEGORIES[category]["plausible_range"]
            if all(low <= value <= high for value, low, high in zip(estimate, bounds["min"], bounds["max"])):
                size = estimate
            bottom = point.copy()
            if hit[2] == "wall":
                bottom[1] -= size[2] / 2
            elif hit[2] == "ceiling":
                bottom[1] -= size[2]
            if bottom[1] < -1e-6 or bottom[1] + size[2] > base_room["height"] + 1e-6:
                raise ValueError("outside_vertical_bounds")
            yaw = 0.0
            if hit[3]:
                wall = next(w for w in base_room["walls"] if w["id"] == hit[3])
                yaw = math.atan2(*wall["inward_normal"])
            result["detections"].append({**evidence, "position": bottom.tolist(), "observation_point": point.tolist(),
                "sample_pixels": [list(p) for p in pixels], "size": size, "mount": hit[2],
                "wall_id": hit[3], "support_id": hit[4], "yaw": yaw,
                "floor_points": [p[[0, 2]].tolist() for p in points] if category == "rug" else [],
                "method": "raycast+depth" if all(m == "raycast+depth" for m in methods) else "raycast",
                "depth_evidence": depth_evidence})
            sample = detected_sample(evidence["id"], (x1, y1, x2, y2), rgb)
            if sample is not None:
                result["color_samples"].append(sample)
        except (ValueError, TypeError) as exc:
            result["rejected"].append({**evidence, "reason": str(exc)})
    result["diagnostics"] = [{"id": d["id"], "method": d["method"], "depth": d["depth_evidence"]}
                             for d in result["detections"]]
    return result


def project_room_points(room, keyframe, points):
    """Project room coordinates into the exact uploaded image; points behind return None."""
    camera, (fx, fy, cx, cy) = _calibration(room, keyframe)
    inverse = np.linalg.inv(camera)
    pixels = []
    for point in points:
        x, y, z, _ = inverse @ [*point, 1]
        pixels.append([float(cx + fx*x/-z), float(cy - fy*y/-z)] if z < -1e-6 else None)
    return pixels


def calibrated_overlay_svg(room, keyframe, lift):
    """Transparent native-box/wall/lift projection to layer on the retained JPEG."""
    from html import escape

    elements = []
    masks = lift.get("color_diagnostics", {})
    for mask in masks.get("masks", []):
        for kind, color, alpha in (("visible", "#ffb347", .15), ("usable", "#00bb88", .3)):
            for y, x, length in mask[kind+"_runs"]:
                sx, sy = keyframe["w"]/masks["width"], keyframe["h"]/masks["height"]
                elements.append(f'<rect data-mask="{kind}" data-object="{escape(mask["object_id"])}" '
                                f'x="{x*sx:.3f}" y="{y*sy:.3f}" width="{length*sx:.3f}" height="{sy:.3f}" '
                                f'fill="{color}" fill-opacity="{alpha}"/>')
    def wireframe(points, edges, attribute, identity, color):
        pixels = project_room_points(room, keyframe, points)
        for a, b in edges:
            if pixels[a] is not None and pixels[b] is not None:
                x1, y1 = pixels[a]
                x2, y2 = pixels[b]
                elements.append(f'<line data-{attribute}="{escape(identity)}" x1="{x1:.3f}" y1="{y1:.3f}" '
                                f'x2="{x2:.3f}" y2="{y2:.3f}" stroke="{color}" stroke-width="1"/>')
    for wall in room["walls"]:
        points = [[x, y, z] for y in (0, room["height"]) for x, z in (wall["a"], wall["b"])]
        wireframe(points, [(0, 1), (1, 3), (3, 2), (2, 0)], "wall", wall["id"], "#64a8ff")
    for obj in room["objects"]:
        footprint = list(_footprint(obj).exterior.coords)[:4]
        points = [[x, y, z] for y in (obj["base_y"], obj["base_y"] + obj["size"][2]) for x, z in footprint]
        edges = [(i, (i+1) % 4) for i in range(4)] + [(i+4, (i+1) % 4+4) for i in range(4)] + [(i, i+4) for i in range(4)]
        wireframe(points, edges, "object", obj["id"], "#ffc766")
    for detection in lift["detections"]:
        pixel = project_room_points(room, keyframe, [detection["observation_point"]])[0]
        if pixel is not None:
            x, y = pixel
            elements.append(f'<circle data-observation="{escape(detection["id"])}" cx="{x:.3f}" cy="{y:.3f}" '
                            f'r="4" fill="#00bb88"/><text x="{x+5:.3f}" y="{y:.3f}" fill="#00bb88">'
                            f'{escape(detection["category"])} · {escape(detection["method"])}</text>')
    for rejection in lift["rejected"]:
        x1, y1, x2, y2 = rejection["box_px"]
        elements.append(f'<rect x="{x1}" y="{y1}" width="{x2-x1}" height="{y2-y1}" fill="none" stroke="#d44"/>'
                        f'<text x="{x1}" y="{y1}" fill="#d44">{escape(rejection["reason"])}</text>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {keyframe["w"]} {keyframe["h"]}">' + "".join(elements) + '</svg>'
