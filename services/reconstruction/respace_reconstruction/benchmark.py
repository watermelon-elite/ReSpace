"""Read-only capture audit and deterministic, spatially separated evaluation split.

Never edits the source capture or relaxes its declared artifact contract. Reports
an incomplete upload before fitting, rather than substituting a fabricated mesh.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from .geometry import camera_to_cv_world, depth_frame
from .models import Manifest, Metadata
from .store import atomic_json, digest


def inspect_capture(folder: Path) -> tuple[Manifest, dict]:
    folder = folder.resolve()
    manifest = Manifest.model_validate_json((folder / "manifest.json").read_text())
    inputs = folder / "inputs"
    missing, invalid, frames = [], [], []
    for artifact in manifest.artifacts:
        path = inputs / artifact.filename
        if not path.is_file():
            missing.append({"id": artifact.id, "type": artifact.type, "filename": artifact.filename})
        elif path.stat().st_size != artifact.byte_length or digest(path) != artifact.sha256:
            invalid.append({"id": artifact.id, "reason": "integrity"})
    unavailable = {a["id"] for a in missing + invalid}
    for frame in manifest.frames:
        if any(a.id in unavailable for a in frame.artifacts):
            continue
        metadata = next(a for a in frame.artifacts if a.type == "metadata")
        if Metadata.model_validate_json((inputs / metadata.filename).read_text()) != frame.metadata:
            invalid.append({"id": metadata.id, "reason": "calibration_disagreement"})
            continue
        photo = next(a for a in frame.artifacts if a.type == "jpeg")
        with Image.open(inputs / photo.filename) as image:
            if image.size != (frame.metadata.width, frame.metadata.height):
                invalid.append({"id": photo.id, "reason": "image_dimensions"})
                continue
            image.thumbnail((512, 512))
            gray = np.asarray(image.convert("L"), dtype=np.float32)
        laplace = (-4 * gray[1:-1, 1:-1] + gray[:-2, 1:-1] + gray[2:, 1:-1]
                   + gray[1:-1, :-2] + gray[1:-1, 2:])
        observation = depth_frame(frame, inputs)
        camera = camera_to_cv_world(frame.metadata)
        frames.append({"id": frame.id, "timestamp": frame.metadata.timestamp,
                       "sharpness_laplacian_variance": float(laplace.var()) if laplace.size else 0.,
                       "valid_depth_fraction": float(np.count_nonzero(observation[0]) / observation[0].size) if observation else 0.,
                       "position": camera[:3, 3].tolist(), "forward": camera[:3, 2].tolist()})
    return manifest, {"schema_version": 1, "capture_id": manifest.capture_id,
                      "manifest_sha256": digest(folder / "manifest.json"),
                      "complete": not missing and not invalid,
                      "missing_artifacts": missing, "invalid_artifacts": invalid,
                      "frames": frames,
                      "note": "Sharpness is a ranking signal, not a universal blur threshold. No raw data was changed."}


def evaluation_split(frames: list[dict], fraction=.15, minimum_distance=.30,
                     minimum_angle_degrees=15.) -> dict:
    """Reserve distinct evaluation viewpoints and remove near duplicates from fitting.

    The capture's globally estimated poses/mesh are shared priors; this is held-out
    RGB/depth observation evaluation, not an independent metric survey.
    """
    if len(frames) < 4:
        raise ValueError("At least four valid calibrated frames are required for an evaluation split")
    target = max(1, int(len(frames) * fraction))
    cosine = np.cos(np.deg2rad(minimum_angle_degrees))
    positions = np.array([f["position"] for f in frames])
    forwards = np.array([f["forward"] for f in frames])
    selected = []
    # Spread candidates over the capture; do not choose adjacent temporal frames.
    for index in np.linspace(0, len(frames)-1, len(frames), dtype=int):
        if all(np.linalg.norm(positions[index]-positions[j]) >= minimum_distance
               or np.dot(forwards[index], forwards[j]) <= cosine for j in selected):
            selected.append(int(index))
        if len(selected) >= target:
            break
    held = set(selected)
    training, excluded = [], []
    for index, frame in enumerate(frames):
        if index in held:
            continue
        near = any(np.linalg.norm(positions[index]-positions[j]) < minimum_distance
                   and np.dot(forwards[index], forwards[j]) > cosine for j in selected)
        (excluded if near else training).append(frame["id"])
    return {"training_frame_ids": training, "evaluation_frame_ids": [frames[i]["id"] for i in selected],
            "excluded_near_evaluation_frame_ids": excluded,
            "minimum_distance_m": minimum_distance, "minimum_angle_degrees": minimum_angle_degrees,
            "usable": len(training) >= 2,
            "note": "All methods must fit only training_frame_ids. Global capture poses and source mesh remain shared priors."}


def run_audit(folder: Path, output: Path):
    source = folder.resolve()
    destination = output.resolve()
    if destination == source or source in destination.parents:
        raise ValueError("Benchmark output must be outside the immutable capture directory")
    _, report = inspect_capture(source)
    if len(report["frames"]) >= 4:
        report["split"] = evaluation_split(report["frames"])
    else:
        report["split"] = {"usable": False, "reason": "too_few_valid_frames"}
    report["ready_for_reconstruction_benchmark"] = report["complete"] and report["split"]["usable"]
    destination.mkdir(parents=True, exist_ok=True)
    atomic_json(destination / "capture-audit.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_audit(args.capture, args.output)
    print(json.dumps({"capture_id": report["capture_id"], "complete": report["complete"],
                      "valid_frames": len(report["frames"]), "missing_artifact_types":
                      [a["type"] for a in report["missing_artifacts"]],
                      "ready": report["ready_for_reconstruction_benchmark"]}))


if __name__ == "__main__":
    main()
