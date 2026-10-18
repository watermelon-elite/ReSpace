"""Actual SAM observations, without fabricating inputs or publishing a room."""
import argparse
import json
from pathlib import Path
import time

from .benchmark import inspect_capture
from .instances import SAM2Masks, observations, room_objects
from .store import atomic_json


def segment_capture(capture: Path, destination: Path, device="cpu", views_per_object=4):
    source, output = capture.resolve(), destination.resolve()
    if output == source or source in output.parents:
        raise ValueError("Segmentation output must be outside the immutable capture")
    manifest, audit = inspect_capture(source)
    if audit["invalid_artifacts"]:
        raise ValueError("Capture integrity failed")
    missing_frames = [a for a in audit["missing_artifacts"] if a["type"] in ("jpeg", "depth", "confidence", "metadata", "roomplan")]
    if missing_frames:
        raise ValueError("Upload complete RGB-D frames and RoomPlan before segmentation")
    room = json.loads((source / "inputs" / manifest.room_export.filename).read_text())
    seeds = room_objects(room)
    if not seeds:
        raise ValueError("No semantic object seeds; class-agnostic discovery is required")
    output.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    print(json.dumps({"stage": "loading_sam2", "objects": len(seeds)}), flush=True)
    provider = SAM2Masks(device=device)
    evidence = observations(manifest, source / "inputs", seeds, output, provider,
                            views_per_object=views_per_object)
    report = {"schema_version": 1, "capture_id": manifest.capture_id,
              "manifest_sha256": audit["manifest_sha256"], "recipe": dict(provider.recipe,acceptance="measured_seed_support_v2"),
              "source_capture_complete": audit["complete"],
              "missing_artifact_types": [a["type"] for a in audit["missing_artifacts"]],
              "seconds": time.monotonic()-start,
              "instances": [{"id": s.id, "source_id": s.source_id, "category": s.category,
                             "mobility": s.kind, "observations": [
                  {"frame_id": item["frame"].id, "mask_cache": item["cache_filename"],
                   "score": item["score"], "foreground_pixels": int(item["mask"].sum()),
                   "seed_geometry_fraction":item["geometry_fraction"]}
                  for item in evidence if item["entity_id"] == s.id]} for s in seeds],
              "stage": "observations_only", "finished_room": False,
              "note": "Actual model masks, not yet verified full 3D ownership, decor inventory or completed surfaces."}
    atomic_json(output / "segmentation-evidence.json", report)
    print(json.dumps({"stage": "observations_complete", "objects": len(seeds),
                      "masks": len(evidence), "seconds": round(report["seconds"], 2),
                      "source_capture_complete": audit["complete"], "finished_room": False}), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", choices=["cpu", "mps", "cuda"], default="cpu")
    parser.add_argument("--views-per-object", type=int, choices=range(2, 9), default=4)
    args = parser.parse_args()
    segment_capture(args.capture, args.output, args.device, args.views_per_object)


if __name__ == "__main__":
    main()
