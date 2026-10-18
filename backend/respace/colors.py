"""Observed camera RGB, with visibility evidence rather than material inference."""

import math

import numpy as np


def _runs(mask):
    runs: list[list[int]] = []
    for y, row in enumerate(mask):
        edges = np.flatnonzero(np.diff(np.r_[False, row, False]))
        runs.extend([y, int(start), int(end-start)] for start, end in zip(edges[::2], edges[1::2]))
    return runs


def native_samples(room, frame, camera, calibration, rgb, depth=None):
    """Ray-render a small optical-depth buffer of real walls and oriented bounds."""
    width, height = 160, max(1, round(160 * frame["h"] / frame["w"]))
    u: np.ndarray
    v: np.ndarray
    u, v = np.meshgrid((np.arange(width)+.5) * frame["w"] / width,
                       (np.arange(height)+.5) * frame["h"] / height)
    fx, fy, cx, cy = calibration
    rays = np.stack(((u-cx)/fx, -(v-cy)/fy, -np.ones_like(u)), axis=-1) @ camera[:3, :3].T
    origin = camera[:3, 3]
    nearest = np.full((height, width), np.inf)
    owners = np.full((height, width), -1)
    for wall in room["walls"]:
        if wall["virtual"]:
            continue
        normal = np.asarray(wall["inward_normal"])
        denominator = rays[:, :, [0, 2]] @ normal
        distance = float(np.dot(np.asarray(wall["a"])-origin[[0, 2]], normal))
        t = np.divide(distance, denominator, out=np.full_like(nearest, np.inf), where=np.abs(denominator) > 1e-9)
        with np.errstate(invalid="ignore"):
            point = origin + t[:, :, None] * rays
            axis = (np.asarray(wall["b"])-wall["a"]) / wall["length"]
            offset = (point[:, :, [0, 2]]-wall["a"]) @ axis
        hit = ((t > 1e-6) & (t < nearest) & (offset >= 0) & (offset <= wall["length"])
               & (point[:, :, 1] >= 0) & (point[:, :, 1] <= room["height"]))
        nearest[hit] = t[hit]
    objects = [obj for obj in room["objects"] if obj.get("source", "roomplan") != "mk1"]
    for index, obj in enumerate(objects):
        c, s = math.cos(obj["yaw"]), math.sin(obj["yaw"])
        rotation = np.array([[c, 0, -s], [0, 1, 0], [s, 0, c]])
        center = [obj["center"][0], obj["base_y"]+obj["size"][2]/2, obj["center"][1]]
        local_origin = rotation @ (origin-center)
        local_rays = rays @ rotation.T
        half = np.asarray(obj["size"])[[0, 2, 1]] / 2
        parallel = np.abs(local_rays) < 1e-9
        low = np.divide(-half-local_origin, local_rays, out=np.full_like(local_rays, -np.inf), where=~parallel)
        high = np.divide(half-local_origin, local_rays, out=np.full_like(local_rays, np.inf), where=~parallel)
        entry, exit = np.minimum(low, high).max(axis=2), np.maximum(low, high).min(axis=2)
        t = np.where(entry > 1e-6, entry, exit)
        hit = ((exit >= np.maximum(entry, 1e-6)) & (t < nearest)
               & ~np.any(parallel & (np.abs(local_origin) > half), axis=2))
        nearest[hit], owners[hit] = t[hit], index
    pixels = rgb[np.minimum(v.astype(int), frame["h"]-1), np.minimum(u.astype(int), frame["w"]-1)]
    qualified, agrees = np.zeros_like(owners, dtype=bool), np.ones_like(owners, dtype=bool)
    if depth is not None and depth["confidence"] is not None:
        dx = np.minimum((u * depth["width"] / frame["w"]).astype(int), depth["width"]-1)
        dy = np.minimum((v * depth["height"] / frame["h"]).astype(int), depth["height"]-1)
        measured = depth["depth"][dy, dx]
        qualified = ((depth["confidence"][dy, dx] == 2) & np.isfinite(measured) & (measured > 0) & (measured < 5))
        agrees = ~qualified | (np.abs(measured-nearest) <= .15+1e-9)
    samples, masks = [], []
    for index, obj in enumerate(objects):
        visible = owners == index
        padded = np.pad(visible, 2)
        eroded = np.logical_and.reduce([padded[y:y+height, x:x+width] for y in range(5) for x in range(5)])
        usable = eroded & agrees
        count = int(usable.sum())
        if count:
            samples.append({"reference": {"kind": "object", "id": obj["id"]},
                            "rgb": np.median(pixels[usable], axis=0).astype(int).tolist(),
                            "usable_pixels": count, "method": "native_visibility"})
        masks.append({"object_id": obj["id"], "visible_runs": _runs(visible), "usable_runs": _runs(usable),
                      "visible_pixels": int(visible.sum()), "usable_pixels": count,
                      "depth_rejected_pixels": int((eroded & qualified & ~agrees).sum())})
    return samples, {"width": width, "height": height, "erosion_px": 2, "masks": masks}


def detected_sample(reference, box, rgb):
    x1, y1, x2, y2 = box
    # Pixel centers inside the central half avoid border/background contamination.
    left, right = math.ceil(x1+(x2-x1)*.25-.5), math.ceil(x2-(x2-x1)*.25-.5)
    top, bottom = math.ceil(y1+(y2-y1)*.25-.5), math.ceil(y2-(y2-y1)*.25-.5)
    pixels = rgb[top:bottom, left:right].reshape(-1, 3)
    if not len(pixels):
        return None
    return {"reference": {"kind": "detection", "id": reference},
            "rgb": np.median(pixels, axis=0).astype(int).tolist(), "usable_pixels": len(pixels),
            "method": "detected_box"}


def merge_colors(room, lifts):
    for obj in room["objects"]:
        views = []
        for lift in lifts:
            samples = [sample for sample in lift.get("color_samples", []) if sample["usable_pixels"] > 0
                       and ((sample["reference"]["kind"] == "object" and sample["reference"]["id"] == obj["id"])
                            or room["identity_map"].get(sample["reference"]["id"]) == {"kind": "object", "id": obj["id"]})]
            if samples:
                sample = max(samples, key=lambda s: (s["usable_pixels"], s["reference"]["id"]))
                views.append({**sample, "frame_id": lift["frame_id"]})
        views = sorted(views, key=lambda s: (-s["usable_pixels"], s["frame_id"]))[:5]
        count = sum(view["usable_pixels"] for view in views)
        obj.setdefault("attrs", {}).pop("color", None)
        obj["color_evidence"] = {"kind": "observed_camera_rgb", "usable_pixels": count, "views": views}
        if count >= (1 if obj["source"] == "mk1" else 200):
            color = np.median([view["rgb"] for view in views], axis=0).astype(int)
            obj["attrs"]["color"] = "#" + "".join(f"{channel:02X}" for channel in color)
