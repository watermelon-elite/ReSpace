import json

from respace_reconstruction.benchmark import evaluation_split, run_audit
from respace_reconstruction.store import atomic_json


def test_incomplete_original_is_reported_without_mutating_capture(tmp_path, capture):
    manifest, payloads = capture
    source = tmp_path / "capture"
    (source / "inputs").mkdir(parents=True)
    atomic_json(source / "manifest.json", manifest.model_dump())
    before = (source / "manifest.json").read_bytes()
    for name, payload in payloads.items():
        if name != manifest.scene_mesh.filename:
            (source / "inputs" / name).write_bytes(payload)
    report = run_audit(source, tmp_path / "benchmark")
    assert not report["complete"]
    assert report["missing_artifacts"][0]["type"] == "scene_mesh"
    assert len(report["frames"]) == 5
    assert not report["ready_for_reconstruction_benchmark"]
    assert (source / "manifest.json").read_bytes() == before
    assert json.loads((tmp_path / "benchmark/capture-audit.json").read_text())["capture_id"] == manifest.capture_id


def test_evaluation_neighbors_cannot_leak_into_training():
    frames = [{"id": str(i), "position": [i*.1, 0, 0], "forward": [0, 0, -1]} for i in range(20)]
    split = evaluation_split(frames, fraction=.1)
    assert split["usable"]
    lookup = {f["id"]: f for f in frames}
    for a in split["evaluation_frame_ids"]:
        for b in split["training_frame_ids"]:
            assert abs(lookup[a]["position"][0]-lookup[b]["position"][0]) >= .30
