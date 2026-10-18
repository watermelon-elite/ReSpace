"""Reconcile image discovery with measured RoomPlan identities and supports."""
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_dilation

from .associate_capture import associate_capture
from .association import label_family
from .discover_capture import discover_capture
from .geometry import masked_world_points
from .instances import InstanceSeed, SAM2Masks, RescanRequired, observations, room_objects


DECOR_FAMILIES = {"wall_art", "whiteboard", "bulletin_board", "clock", "mirror"}


def automatic_inventory(manifest, inputs, room, surfaces, working, check_budget):
    working.mkdir(parents=True, exist_ok=True)
    evidence = working/"discovery"
    check_budget()
    discovered = discover_capture(inputs.parent, evidence, limit=12)
    grouped = associate_capture(inputs.parent, evidence)
    check_budget()
    frames = {f.id: f for f in manifest.frames}
    proposals = {p["id"]: p for p in discovered["proposals"]}
    seeds = room_objects(room)
    groups, all_masks = [], []
    for group in grouped["instances"]:
        if not group["multi_view_supported"]: continue
        members, cloud = [], []
        for identifier in group["proposal_ids"]:
            record = proposals[identifier]
            frame = frames[record["frame_id"]]
            with np.load(evidence/record["mask_cache"], allow_pickle=False) as stored:
                mask = stored["mask"].astype(bool)
            points, fraction = masked_world_points(frame, mask, inputs)
            if fraction < .25 or len(points) < 16: continue
            members.append({"frame": frame, "mask": mask, "score": record["sam_score"],
                "mask_path": str((evidence/record["mask_cache"]).resolve()), "label": record["label"]})
            cloud.append(points)
        if len(members) < 2: continue
        groups.append((group, members, np.concatenate(cloud)))
    # RoomPlan remains a useful source of identity even when discovery calls the
    # same item a synonym. Masks still require measured depth and two views.
    provider = SAM2Masks()
    prior_masks = observations(manifest, inputs, seeds, working, provider, check_budget, require_all=False)
    for item in prior_masks:
        item["mask_path"] = str((working/"masks"/item["cache_filename"]).resolve())
    used, retained = set(), []
    kitchen = any(s.category in ("sink", "stove", "dishwasher", "oven") for s in seeds)
    for seed in seeds:
        candidates = []
        for index, (group, members, points) in enumerate(groups):
            if index in used or group["family"] in DECOR_FAMILIES: continue
            inverse = np.linalg.inv(seed.transform)
            local = points @ inverse[:3, :3].T+inverse[:3, 3]
            fraction = (np.abs(local) <= seed.dimensions/2+.05).all(axis=1).mean()
            family = label_family(seed.category)
            if fraction > .6 and (family == group["family"] or seed.category == "storage" and group["family"] == "storage"):
                candidates.append((fraction, index))
        masks = [m for m in prior_masks if m["entity_id"] == seed.id]
        if candidates:
            _, index = max(candidates)
            used.add(index)
            group, members, _ = groups[index]
            for m in members:
                if m["frame"].id not in {v["frame"].id for v in masks}:
                    masks.append(dict(m, entity_id=seed.id))
            labels = " ".join(m["label"] for m in members)
        else:
            labels = ""
            # Reject semantic hallucinations rather than manufacturing assets.
            if seed.category == "refrigerator": continue
        if len({m["frame"].id for m in masks}) < 2:
            if seed.kind == "furniture":
                raise RescanRequired("Capture overlapping views around the "+seed.label)
            continue
        if seed.kind == "unresolved_storage":
            if "dresser" in labels or "bookcase" in labels:
                seed.kind = "furniture"
            elif kitchen and labels and "cabinet" in labels:
                seed.kind = "fixed"
            else:
                raise RescanRequired("Capture clearer views of storage so built-ins can be distinguished from furniture")
        retained.append(seed)
        all_masks.extend(masks)
    decor = []
    for index, (group, members, points) in enumerate(groups):
        if index in used: continue
        lo, hi = points.min(axis=0), points.max(axis=0)
        transform = np.eye(4); transform[:3, 3] = (lo+hi)/2
        kind, support = "furniture", None
        if group["family"] in DECOR_FAMILIES or group["family"]=="rug":
            candidates = []
            for surface in surfaces:
                if surface.kind != ("floor" if group["family"]=="rug" else "wall"): continue
                inverse = np.linalg.inv(surface.transform)
                local = points @ inverse[:3, :3].T+inverse[:3, 3]
                distance = float(np.percentile(abs(local[:, 2]), 90))
                if distance < .10: candidates.append((distance, surface, local))
            if not candidates: continue
            _, support, local = min(candidates, key=lambda c: c[0])
            kind = "wall_decor"
            # Flat posters/boards use exact source rectification. Protruding
            # frames/trays remain real mesh geometry and use object completion.
            if np.ptp(np.percentile(local[:, 2], [5, 95])) < .025:
                decor.append({"id": group["id"], "support": support, "members": members,
                              "label": members[0]["label"], "points": points})
                for member in members: all_masks.append(dict(member, entity_id=group["id"]))
                continue
        if group["family"] == "storage":
            if kitchen and all("cabinet" in m["label"] for m in members): kind = "fixed"
            elif not any("dresser" in m["label"] or "bookcase" in m["label"] for m in members): continue
        # Do not duplicate a measured item because of a synonym or nested box.
        if any(np.all(np.abs(np.linalg.inv(s.transform)[:3, :3]@transform[:3, 3]+np.linalg.inv(s.transform)[:3, 3]) <= s.dimensions/2+.05) for s in retained):
            continue
        seed = InstanceSeed(group["id"], group["id"], group["family"], members[0]["label"], kind,
                            transform, np.maximum(hi-lo, .02))
        seed.support_id = support.id if support else None
        retained.append(seed)
        all_masks.extend(dict(m, entity_id=seed.id) for m in members)
    exclusions = {}
    for item in all_masks:
        frame = item["frame"]
        from PIL import Image
        target = (frame.metadata.depth_width, frame.metadata.depth_height)
        small = np.asarray(Image.fromarray(item["mask"]).resize(target, Image.Resampling.NEAREST)).copy()
        exclusions.setdefault(frame.id, np.zeros_like(small, dtype=bool))
        exclusions[frame.id] |= binary_dilation(small, iterations=1)
        item["mask"] = small
    check_budget()
    return retained, all_masks, decor, exclusions
