"""SAM 2 observations and visibility-tested 3D ownership in the original scan frame.

RoomPlan boxes are prompts/priors, never final furniture geometry. Unknown
ownership stays unknown; semantic category is not an instance identity.
"""
from dataclasses import dataclass
import hashlib
import json
from importlib import metadata as package_metadata
import os
from pathlib import Path

import numpy as np
from PIL import Image

from .geometry import camera_to_cv_world, depth_frame, masked_world_points
from .store import digest

SAM2_COMMIT = "2b90b9f5ceec907a1c18123530e92e794ad901a4"
SAM2_CONFIG = "configs/sam2.1/sam2.1_hiera_t.yaml"
SAM2_SHA256 = "7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69"


class ProviderUnavailable(RuntimeError):
    """Infrastructure/configuration failure; rescanning cannot fix it."""


class RescanRequired(ValueError):
    """Captured evidence cannot support a finished segmented room."""


@dataclass
class InstanceSeed:
    id: str
    source_id: str
    category: str
    label: str
    kind: str
    transform: np.ndarray
    dimensions: np.ndarray

    def corners(self):
        half = self.dimensions/2
        local = np.array([[x, y, z] for x in (-half[0], half[0]) for y in (-half[1], half[1]) for z in (-half[2], half[2])])
        return local @ self.transform[:3, :3].T+self.transform[:3, 3]


def stable_id(prefix, source_id):
    return prefix+"-"+hashlib.sha256(str(source_id).encode()).hexdigest()[:20]


def room_objects(room):
    from .pipeline import surface_transform, vector3
    wall_ids = {str(w.get("identifier")) for w in room.get("walls", [])}
    fixed = {"sink", "stove", "oven", "dishwasher", "washerDryer", "toilet", "bathtub", "fireplace", "stairs"}
    seeds = []
    for obj in room.get("objects", []):
        identifier = obj.get("identifier")
        if not identifier:
            raise RescanRequired("A detected room item has no source identity")
        category = obj.get("category", "unknown")
        if isinstance(category, dict):
            category = next(iter(category), "unknown")
        dimensions = vector3(obj["dimensions"])
        if np.any(dimensions <= 0) or np.max(dimensions) > 25:
            raise RescanRequired("A room item has invalid measured bounds")
        builtin = (obj.get("isBuiltIn") is True or str(obj.get("parentIdentifier")) in wall_ids
                   or category in fixed)
        # Unknown mobility is explicit; storage alone does not prove a built-in.
        if category == "storage" and not builtin:
            kind = "unresolved_storage"
        else:
            kind = "fixed" if builtin else "furniture"
        seeds.append(InstanceSeed(stable_id("item", identifier), str(identifier), str(category),
                                  str(category), kind, surface_transform(obj), dimensions))
    return seeds


def project(points, metadata):
    inverse = np.linalg.inv(camera_to_cv_world(metadata))
    camera = np.asarray(points) @ inverse[:3, :3].T+inverse[:3, 3]
    z = camera[:, 2]
    fx, fy, cx, cy = metadata.intrinsics
    uv = camera[:, :2]/np.maximum(z[:, None], 1e-8)*[fx, fy]+[cx, cy]
    return uv, z


def prompt_box(seed, metadata):
    uv, z = project(seed.corners(), metadata)
    if np.any(z <= .1):
        return None
    lo = np.maximum(uv.min(axis=0), 0)
    hi = np.minimum(uv.max(axis=0), [metadata.width-1, metadata.height-1])
    if np.any(hi-lo < 16):
        return None
    return np.r_[lo, hi]


def choose_observations(seed, frames, limit=4):
    candidates = []
    for frame in frames:
        box = prompt_box(seed, frame.metadata)
        if box is not None:
            area = np.prod(box[2:]-box[:2])/(frame.metadata.width*frame.metadata.height)
            position = camera_to_cv_world(frame.metadata)[:3, 3]
            direction = position-seed.transform[:3, 3]
            direction /= max(np.linalg.norm(direction), 1e-8)
            candidates.append((float(area), frame, box, direction))
    chosen = []
    for candidate in sorted(candidates, key=lambda value: value[0], reverse=True):
        if all(np.dot(candidate[3], previous[3]) < .94 for previous in chosen):
            chosen.append(candidate)
        if len(chosen) >= limit:
            break
    return [(f, box) for _, f, box, _ in chosen]


def mask_geometric_support(seed,frame,mask,inputs):
    points,valid_fraction=masked_world_points(frame,mask,inputs)
    if not len(points):
        return 0.,0
    inverse=np.linalg.inv(seed.transform)
    local=points@inverse[:3,:3].T+inverse[:3,3]
    inside=(np.abs(local)<=seed.dimensions/2+.035).all(axis=1)
    return float(inside.mean()),int(inside.sum())


class SAM2Masks:
    def __init__(self, checkpoint=None, device="cpu"):
        checkpoint = Path(checkpoint or os.environ.get("RESPACE_SAM2_CHECKPOINT", "") or
                          Path(__file__).resolve().parents[1] / ".tools/sam2/sam2.1_hiera_tiny.pt")
        if not checkpoint.is_file():
            raise ProviderUnavailable("SAM 2 checkpoint is unavailable; run setup-segmentation.sh")
        checksum = digest(checkpoint)
        if checksum != SAM2_SHA256:
            raise ProviderUnavailable("SAM 2 checkpoint differs from the pinned model")
        if device not in ("cpu", "mps", "cuda"):
            raise ProviderUnavailable("Unsupported segmentation device")
        try:
            import torch
            from sam2.build_sam import build_sam2
            from sam2.sam2_image_predictor import SAM2ImagePredictor
        except ImportError as exc:
            raise ProviderUnavailable("Install the pinned SAM 2 segmentation dependencies") from exc
        installed = json.loads(package_metadata.distribution("SAM-2").read_text("direct_url.json") or "{}")
        if installed.get("vcs_info", {}).get("commit_id") != SAM2_COMMIT:
            raise ProviderUnavailable("SAM 2 source differs from the verified revision; run setup-segmentation.sh")
        torch.set_num_threads(min(4, os.cpu_count() or 1))
        self.torch = torch
        self.model = build_sam2(SAM2_CONFIG, str(checkpoint), device=device)
        self.predictor = SAM2ImagePredictor(self.model, max_hole_area=0, max_sprinkle_area=0)
        self.recipe = {"sam2_commit": SAM2_COMMIT, "config": SAM2_CONFIG,
                       "checkpoint_sha256": checksum, "device": device, "torch_version": torch.__version__}

    def set_image(self, rgb):
        with self.torch.inference_mode():
            self.predictor.set_image(rgb)

    def mask(self, box, point=None):
        with self.torch.inference_mode():
            masks, scores, _ = self.predictor.predict(
                box=np.asarray(box, dtype=np.float32),
                point_coords=np.array([point], dtype=np.float32) if point is not None else None,
                point_labels=np.array([1]) if point is not None else None,
                multimask_output=True)
        best = int(np.argmax(scores))
        return masks[best].astype(bool), float(scores[best])

    def discover(self, rgb):
        from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator
        generator = SAM2AutomaticMaskGenerator(self.model, points_per_side=12, points_per_batch=16,
                                              pred_iou_thresh=.9, stability_score_thresh=.95,
                                              crop_n_layers=0, min_mask_region_area=0)
        with self.torch.inference_mode():
            return generator.generate(rgb)


def observations(manifest, inputs, seeds, working, provider, check_budget=lambda: None, views_per_object=4, require_all=True):
    """Return depth-grid masks; reuse image embeddings within each selected frame."""
    tasks = {}
    for seed in seeds:
        for frame, box in choose_observations(seed, manifest.frames, views_per_object):
            tasks.setdefault(frame.id, (frame, []))[1].append((seed, box))
    cache = working / "masks"
    cache.mkdir(parents=True, exist_ok=True)
    result = []
    for frame, entries in tasks.values():
        check_budget()
        photo = next(a for a in frame.artifacts if a.type == "jpeg")
        image = None
        for seed, box in entries:
            signature = hashlib.sha256(json.dumps({"image": photo.sha256, "box": box.tolist(),
                "target_dimensions": [frame.metadata.depth_width, frame.metadata.depth_height],
                "recipe": provider.recipe}, sort_keys=True).encode()).hexdigest()
            path = cache / (signature+".npz")
            if path.exists():
                with np.load(path, allow_pickle=False) as stored:
                    mask, score = stored["mask"].astype(bool), float(stored["score"])
            else:
                check_budget()
                if image is None:
                    with Image.open(inputs / photo.filename) as source:
                        image = np.asarray(source.convert("RGB")).copy()
                    provider.set_image(image)
                mask, score = provider.mask(box)
                if frame.metadata.depth_width and frame.metadata.depth_height:
                    mask = np.asarray(Image.fromarray(mask).resize((frame.metadata.depth_width,
                                      frame.metadata.depth_height), Image.Resampling.NEAREST)).copy()
                temporary = path.with_suffix(".tmp")
                with temporary.open("wb") as f:
                    np.savez_compressed(f, mask=mask, score=score)
                    f.flush()
                    os.fsync(f.fileno())
                temporary.replace(path)
            geometry_fraction,geometry_pixels=mask_geometric_support(seed,frame,mask,inputs)
            # A segmentation quality score is not semantic or geometric proof.
            # Reject masks predominantly covering a wall behind the prompt box.
            if score >= .7 and geometry_pixels >= 16 and geometry_fraction >= .25:
                result.append({"entity_id": seed.id, "frame": frame, "mask": mask, "score": score,
                               "cache_filename": path.name,"geometry_fraction":geometry_fraction})
        check_budget()
    supported = {r["entity_id"] for r in result}
    missing = [s.label for s in seeds if s.id not in supported]
    if missing and require_all:
        raise RescanRequired("Capture closer, clearer views of: "+", ".join(missing[:8]))
    return result


def assign_surface_ownership(vertices, triangles, seeds, masks, inputs, minimum_views=2):
    """Multi-view votes require measured visibility and membership in a real mask.

    Returns one seed index per source triangle, or -1 (room/unassigned). It never
    propagates labels across unknown neighbors merely to improve coverage.
    """
    centers = np.asarray(vertices)[np.asarray(triangles)].mean(axis=1)
    votes = np.zeros((len(centers), len(seeds)), dtype=np.float32)
    counts = np.zeros_like(votes, dtype=np.uint8)
    lookup = {s.id: i for i, s in enumerate(seeds)}
    by_frame = {}
    for item in masks:
        by_frame.setdefault(item["frame"].id, []).append(item)
    for items in by_frame.values():
        frame = items[0]["frame"]
        observation = depth_frame(frame, inputs)
        if observation is None:
            continue
        depth, _ = observation
        uv, z = project(centers, frame.metadata)
        x = np.floor(uv[:, 0]*depth.shape[1]/frame.metadata.width).astype(int)
        y = np.floor(uv[:, 1]*depth.shape[0]/frame.metadata.height).astype(int)
        valid = (z > .1) & (x >= 0) & (x < depth.shape[1]) & (y >= 0) & (y < depth.shape[0])
        ids = np.flatnonzero(valid)
        measured = depth[y[ids], x[ids]]
        ids = ids[(measured > 0) & (np.abs(measured-z[ids]) < np.maximum(.04, z[ids]*.02))]
        for item in items:
            index = lookup[item["entity_id"]]
            seed = seeds[index]
            inverse = np.linalg.inv(seed.transform)
            local = centers[ids] @ inverse[:3, :3].T+inverse[:3, 3]
            within = (np.abs(local) <= seed.dimensions/2+.035).all(axis=1)
            selected = ids[within & item["mask"][y[ids], x[ids]]]
            votes[selected, index] += item["score"]
            counts[selected, index] += 1
    if not seeds:
        return np.full(len(centers), -1, dtype=int), {"instances": []}
    winner = votes.argmax(axis=1)
    ordered = np.sort(votes, axis=1)
    best = ordered[:, -1]
    second = ordered[:, -2] if len(seeds) > 1 else np.zeros(len(centers))
    support = counts[np.arange(len(centers)), winner]
    confident = (support >= minimum_views) & (best >= .7*minimum_views) & ((best-second) >= .5)
    ownership = np.where(confident, winner, -1)
    summary = {"instances": [{"id": s.id, "triangles": int(np.count_nonzero(ownership == i)),
                              "observations": sum(m["entity_id"] == s.id for m in masks)}
                             for i, s in enumerate(seeds)],
               "unassigned_triangles": int(np.count_nonzero(ownership == -1)),
               "method": "depth_visible_multiview_sam2_votes_v1"}
    return ownership, summary
