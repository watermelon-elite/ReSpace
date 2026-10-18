import json
import numpy as np
import open3d as o3d

from respace_reconstruction.pipeline import process
from respace_reconstruction.store import atomic_json


def stage_capture(folder, capture):
    manifest, payloads = capture
    (folder / "inputs").mkdir()
    atomic_json(folder / "manifest.json", manifest.model_dump())
    for name, data in payloads.items():
        (folder / "inputs" / name).write_bytes(data)


def test_real_tsdf_coordinates_and_partial_photo_failure(tmp_path, capture, monkeypatch):
    stage_capture(tmp_path, capture)
    monkeypatch.setenv("RESPACE_OPENMVS_BIN", str(tmp_path / "missing"))
    result = process(tmp_path, 1)
    assert result["status"] == "partially_processed"
    assert result["model_filename"] == "model.obj"
    mesh = o3d.io.read_triangle_mesh(str(tmp_path / "results/1/model.obj"))
    vertices = np.asarray(mesh.vertices)
    assert len(mesh.triangles) > 100
    assert abs(np.median(vertices[:,2]) + 2) < .02  # No Z sign or scale error.
    assert abs(np.median(vertices[:,1])) < .05
    report = json.loads((tmp_path / "results/1/quality.json").read_text())
    assert report["stages_failed"][0]["stage"] == "photo_processing"
    assert "patches" in report
    checkpoint = tmp_path / "work/depth.ply"
    timestamp = checkpoint.stat().st_mtime_ns
    assert process(tmp_path, 2)["revision"] == 2
    assert checkpoint.stat().st_mtime_ns == timestamp
