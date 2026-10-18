"""Diagnostic observed-surface decomposition; never a finished-room publisher.

An incomplete original mesh upload does not prevent studying the retained RGB-D
evidence. It still prevents the canonical reconstruction job from being queued.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from .benchmark import inspect_capture
from .instances import assign_surface_ownership, room_objects
from .models import SAFE_NAME
from .store import atomic_json, digest


def decompose_observed(capture: Path, evidence: Path, destination: Path):
    import open3d as o3d
    from .pipeline import fuse
    source, output = capture.resolve(), destination.resolve()
    if output == source or source in output.parents:
        raise ValueError("Derived geometry must remain outside the immutable capture")
    manifest, audit = inspect_capture(source)
    if audit["invalid_artifacts"] or any(a["type"] != "scene_mesh" for a in audit["missing_artifacts"]):
        raise ValueError("Complete verified RGB-D and RoomPlan evidence is required")
    records = json.loads((evidence / "segmentation-evidence.json").read_text())
    if records["capture_id"] != manifest.capture_id or records["manifest_sha256"] != audit["manifest_sha256"]:
        raise ValueError("Segmentation belongs to a different immutable capture")
    room = json.loads((source / "inputs" / manifest.room_export.filename).read_text())
    seeds = room_objects(room)
    frames = {f.id: f for f in manifest.frames}
    masks = []
    for instance in records["instances"]:
        for record in instance["observations"]:
            name = record["mask_cache"]
            if not SAFE_NAME.fullmatch(name) or ".." in name:
                raise ValueError("Invalid mask-cache reference")
            frame = frames[record["frame_id"]]
            with np.load(evidence / "masks" / name, allow_pickle=False) as data:
                mask = data["mask"].astype(bool)
                if mask.shape != (frame.metadata.depth_height, frame.metadata.depth_width):
                    raise ValueError("Mask dimensions disagree with calibrated depth")
                masks.append({"frame": frame, "entity_id": instance["id"], "mask": mask,
                              "score": float(data["score"])})
    output.mkdir(parents=True, exist_ok=True)
    signature = audit["manifest_sha256"]+"-observed-tsdf-15mm-v1"
    marker = output / "geometry-recipe.json"
    checkpoint = output / "observed.ply"
    if marker.is_file() and checkpoint.is_file() and json.loads(marker.read_text()).get("recipe") == signature:
        mesh = o3d.io.read_triangle_mesh(str(checkpoint))
    else:
        mesh, _ = fuse(manifest, source / "inputs", o3d)
        mesh.remove_degenerate_triangles()
        mesh.compute_vertex_normals()
        if not o3d.io.write_triangle_mesh(str(checkpoint), mesh):
            raise ValueError("Could not retain observed geometry")
        atomic_json(marker, {"recipe": signature})
    vertices, faces = np.asarray(mesh.vertices), np.asarray(mesh.triangles)
    ownership, summary = assign_surface_ownership(vertices, faces, seeds, masks, source / "inputs")
    with (output / "ownership.npz").open("wb") as f:
        np.savez_compressed(f, owner_index=ownership)
    objects = []
    for index, seed in enumerate(seeds):
        selected = np.flatnonzero(ownership == index)
        item = {"id": seed.id, "source_id": seed.source_id, "category": seed.category,
                "mobility": seed.kind, "face_count": len(selected),
                "local_to_scan_transform": seed.transform.flatten(order="F").tolist(),
                "complete": False}
        if len(selected):
            # Retain exactly owned faces; point selection would also include connecting faces.
            part = o3d.geometry.TriangleMesh(mesh)
            part.remove_triangles_by_mask(ownership != index)
            part.remove_unreferenced_vertices()
            part.transform(np.linalg.inv(seed.transform))
            part.compute_vertex_normals()
            filename = seed.id+".ply"
            if not o3d.io.write_triangle_mesh(str(output / filename), part):
                raise ValueError("Could not export observed instance")
            edges = np.sort(np.concatenate([np.asarray(part.triangles)[:, [0, 1]],
                                           np.asarray(part.triangles)[:, [1, 2]],
                                           np.asarray(part.triangles)[:, [2, 0]]]), axis=1)
            _, counts = np.unique(edges, axis=0, return_counts=True)
            item.update({"asset": filename, "sha256": digest(output / filename),
                         "open_boundary_edges": int(np.count_nonzero(counts == 1)),
                         "bounds_min": np.asarray(part.vertices).min(axis=0).tolist(),
                         "bounds_max": np.asarray(part.vertices).max(axis=0).tolist()})
        objects.append(item)
    background = o3d.geometry.TriangleMesh(mesh)
    background.remove_triangles_by_mask(ownership != -1)
    background.remove_unreferenced_vertices()
    if len(background.triangles):
        o3d.io.write_triangle_mesh(str(output / "room-observed.ply"), background)
    report = {"schema_version": 1, "capture_id": manifest.capture_id,
              "source_capture_complete": audit["complete"], "coordinate_system": "arkit_scan_meters_y_up",
              "source_mesh_sha256": digest(checkpoint), "ownership": summary, "instances": objects,
              "finished_room": False,
              "remaining_stages": ["class_agnostic_and_wall_decor_inventory", "complete_3d_ownership_boundaries",
                                   "object_hidden_surface_completion", "clean_background_completion",
                                   "source_photo_texture_baking", "navigation_and_mobile_acceptance"],
              "note": "Observed RGB-D diagnostic geometry only. Not the missing original mesh, not a product result, not a held-out quality benchmark."}
    atomic_json(output / "observed-instances.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = decompose_observed(args.capture, args.evidence, args.output)
    print(json.dumps({"objects": len(report["instances"]), "objects_with_owned_faces":
                      sum(i["face_count"] > 0 for i in report["instances"]), "finished_room": False}))


if __name__ == "__main__":
    main()
