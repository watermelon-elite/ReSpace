import copy
import hashlib
import io
import json
import shutil
import urllib.error

import numpy as np
import open3d as o3d
from PIL import Image, ImageFilter
from fastapi.testclient import TestClient
import pytest

from respace_reconstruction import astra, pipeline
from respace_reconstruction.app import create_app
from respace_reconstruction.geometry import read_scan, write_colored_obj
from respace_reconstruction.store import digest
from test_pipeline import stage_capture


def scene():
    return {"schema_version": 1, "coordinate_system": "arkit_scan_meters_y_up", "summary": "Complete a missing shelf edge.",
            "materials": [{"id": "wood", "color": {"r": .6, "g": .3, "b": .1}, "roughness": .8}],
            "components": [{"id": "shelf", "label": "Shelf edge", "kind": "object", "material_id": "wood",
                "evidence_frame_ids": ["frame-0", "frame-1"], "confidence": .9,
                "vertices": [{"x": -.2, "y": 0., "z": -2.08}, {"x": .2, "y": 0., "z": -2.08},
                             {"x": .2, "y": .2, "z": -2.08}],
                "triangles": [{"a": 0, "b": 1, "c": 2}]}]}


def response(plan=None):
    return {"id": "resp_test", "status": "completed", "usage": {"input_tokens": 120, "output_tokens": 80},
            "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(plan or scene())}]}]}


def setup_evidence(tmp_path, capture):
    stage_capture(tmp_path, capture)
    manifest, _ = capture
    inputs = tmp_path / "inputs"
    original = read_scan(inputs / manifest.scene_mesh.filename, manifest.capture_id, o3d)
    evidence, photos, observations = astra.prepare_evidence(manifest, inputs, original, original, {}, 4)
    return manifest, original, evidence, photos, observations


def test_evidence_has_bounded_photos_lidar_meshes_and_calibration(tmp_path, capture):
    manifest, original, evidence, photos, _ = setup_evidence(tmp_path, capture)
    assert 2 <= len(photos) <= 4 < len(manifest.frames)
    assert evidence["original_arkit_mesh"]["vertices"][0][2] == -2
    assert evidence["measured_reconstruction"]["triangles"] == [[0, 1, 2], [0, 2, 3]]
    for frame in evidence["frames"]:
        assert len(frame["lidar_samples_u_v_meters"]) == 192
        assert frame["lidar_samples_u_v_meters"][0][2] == 2
        assert len(frame["camera_to_scan_columns"]) == 16
        assert frame["intrinsics_fx_fy_cx_cy"] == [480, 480, 320, 240]
    body = astra.request_body(evidence, photos)
    assert body["model"] == "gpt-6-sol"
    assert body["reasoning"] == {"effort": "high"}
    assert body["store"] is False
    assert body["text"]["format"]["strict"] is True
    images = [item for item in body["input"][0]["content"] if item["type"] == "input_image"]
    assert len(images) == len(photos)
    assert all(item["image_url"].startswith("data:image/jpeg;base64,") for item in images)


def test_selection_excludes_blurred_view_and_spans_capture(tmp_path, capture):
    manifest, _, _, _, _ = setup_evidence(tmp_path, capture)
    photo = manifest.frames[2].artifacts[0]
    path = tmp_path / "inputs" / photo.filename
    with Image.open(path) as image:
        image.filter(ImageFilter.GaussianBlur(30)).save(path)
    selected = astra.select_frames(manifest, tmp_path / "inputs", 3)
    assert manifest.frames[2] not in selected
    assert selected[0].id == "frame-0"
    assert selected[-1].id == "frame-4"


def test_compact_mesh_excludes_unused_vertices_and_remaps_indices():
    vertices = np.zeros((20000, 3))
    vertices[[10, 100, 1000]] = [[0, 0, -2], [1, 0, -2], [0, 1, -2]]
    mesh = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(vertices),
                                    o3d.utility.Vector3iVector([[10, 100, 1000]]))
    compact = astra.compact_mesh(mesh)
    assert compact == {"vertices": [[0, 0, -2], [1, 0, -2], [0, 1, -2]], "triangles": [[0, 1, 2]]}
    assert len(mesh.vertices) == 20000
    assert np.array_equal(np.asarray(mesh.triangles), [[10, 100, 1000]])


def test_oversized_text_evidence_is_rejected_before_a_billable_request(monkeypatch):
    monkeypatch.setattr(astra, "MAX_EVIDENCE_BYTES", 64)
    with pytest.raises(ValueError, match="evidence exceeds"):
        astra.request_body({"frames": [], "geometry": "x"*100}, [])


def test_request_transport_and_schema_checkpoint_reuse(tmp_path, capture, monkeypatch):
    _, _, evidence, photos, _ = setup_evidence(tmp_path, capture)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-never-log")
    requests = []

    def urlopen(request, timeout):
        requests.append(request)
        assert request.full_url == "https://api.openai.com/v1/responses"
        assert request.get_header("Authorization") == "Bearer test-key-never-log"
        assert timeout == 900
        return io.BytesIO(json.dumps(response()).encode())

    monkeypatch.setattr(astra.urllib.request, "urlopen", urlopen)
    plan, raw, cached = astra.plan_scene(evidence, photos, tmp_path)
    assert not cached and plan.components[0].id == "shelf" and raw["id"] == "resp_test"
    monkeypatch.delenv("OPENAI_API_KEY")  # A completed response can compile without credentials.
    assert astra.plan_scene(evidence, photos, tmp_path)[2] is True
    assert len(requests) == 1
    changed = copy.deepcopy(evidence)
    changed["frames"][0]["intrinsics_fx_fy_cx_cy"][0] += 1
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        astra.plan_scene(changed, photos, tmp_path)


@pytest.mark.parametrize("case", ["refusal", "incomplete", "bad_schema", "multiple_messages"])
def test_response_failures_are_explicit(case):
    raw = response()
    if case == "refusal":
        raw["output"][0]["content"] = [{"type": "refusal", "refusal": "No"}]
    elif case == "incomplete":
        raw["status"] = "incomplete"
    elif case == "bad_schema":
        raw["output"][0]["content"][0]["text"] = '{"unexpected":"value"}'
    else:
        raw["output"] *= 2
    with pytest.raises(ValueError):
        astra.parse_response(raw)


def test_transport_errors_do_not_echo_keys_or_retry(monkeypatch):
    calls = []

    def denied(request, timeout):
        calls.append(request)
        raise urllib.error.HTTPError(request.full_url, 401, "secret-test-key", {}, io.BytesIO(b"private"))

    monkeypatch.setattr(astra.urllib.request, "urlopen", denied)
    with pytest.raises(RuntimeError, match="HTTP 401") as caught:
        astra.call_astra({}, "secret-test-key")
    assert "secret-test-key" not in str(caught.value)
    assert len(calls) == 1


def test_interrupted_api_call_is_not_repeated_by_automatic_recovery(tmp_path, capture, monkeypatch):
    _, _, evidence, photos, _ = setup_evidence(tmp_path, capture)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls = []

    def interrupted(body, key):
        calls.append(body)
        raise TimeoutError("response lost")

    monkeypatch.setattr(astra, "call_astra", interrupted)
    with pytest.raises(TimeoutError):
        astra.plan_scene(evidence, photos, tmp_path)
    assert (tmp_path / "astra-inflight.json").is_file()
    with pytest.raises(RuntimeError, match="unknown billing outcome"):
        astra.plan_scene(evidence, photos, tmp_path)
    assert len(calls) == 1


def test_compiler_preserves_coordinates_and_rejects_conflicting_geometry(tmp_path, capture):
    _, original, _, _, observations = setup_evidence(tmp_path, capture)
    # Use all frames so evidence IDs remain fixed independently of selection order.
    manifest = capture[0]
    observations = [(f, np.full((120, 160), 2., dtype=np.float32)) for f in manifest.frames]
    plan = astra.ScenePlan.model_validate(scene())
    generated, accepted, rejected = astra.compile_scene(plan, original, original, observations, [], o3d)
    assert len(generated.triangles) == 1 and len(accepted) == 1 and not rejected
    assert np.allclose(np.asarray(generated.vertices)[:, 2], -2.08)
    for z, reason in [(-1.9, "free space"), (-2., "measured surfaces"), (-5., "bounds")]:
        bad = scene()
        for v in bad["components"][0]["vertices"]:
            v["z"] = z
        mesh, kept, rejected = astra.compile_scene(astra.ScenePlan.model_validate(bad), original, original, observations, [], o3d)
        assert not len(mesh.triangles) and not kept and reason in rejected[0]["reason"]
    inverse = np.eye(4)
    inverse[2, 3] = 2.08
    mesh, _, rejected = astra.compile_scene(plan, original, original, observations, [(inverse, np.ones(3))], o3d)
    assert not len(mesh.triangles) and rejected
    offscreen = [(f.model_copy(deep=True), d) for f, d in observations]
    for frame, _ in offscreen:
        frame.metadata.camera_to_scan_transform[12] = 100
    mesh, _, rejected = astra.compile_scene(plan, original, original, offscreen, [], o3d)
    assert not len(mesh.triangles) and rejected[0]["reason"] == "not visible in supporting views"


@pytest.mark.parametrize("mutation", ["bad_index", "unknown_material", "unknown_frame", "duplicate_id", "nan"])
def test_untrusted_scene_cannot_escape_validation(tmp_path, capture, mutation):
    _, original, _, _, observations = setup_evidence(tmp_path, capture)
    data = scene()
    if mutation == "bad_index":
        data["components"][0]["triangles"][0]["a"] = 999
    elif mutation == "unknown_material":
        data["components"][0]["material_id"] = "../arbitrary"
    elif mutation == "unknown_frame":
        data["components"][0]["evidence_frame_ids"] = ["unseen"]
    elif mutation == "duplicate_id":
        data["components"] *= 2
    else:
        data["components"][0]["vertices"][0]["x"] = float("nan")
    with pytest.raises(ValueError):
        plan = astra.ScenePlan.model_validate(data)
        astra.compile_scene(plan, original, original, observations, [], o3d)


def test_export_preserves_source_uv_materials_and_appends_valid_faces(tmp_path, capture):
    _, original, _, _, observations = setup_evidence(tmp_path, capture)
    observations = [(f, None) for f in capture[0].frames]
    plan = astra.ScenePlan.model_validate(scene())
    generated, accepted, _ = astra.compile_scene(plan, original, original, observations, [], o3d)
    write_colored_obj(original, tmp_path)
    source = (tmp_path / "model.obj").read_text()
    astra.export_scene(tmp_path / "model.obj", tmp_path, generated, plan, accepted)
    obj = (tmp_path / "astra.obj").read_text()
    assert "\n".join(line for line in source.splitlines() if line.startswith(("vt ", "f "))) in obj
    assert obj.count("mtllib ") == 1 and "f 5 6 7" in obj
    mtl = (tmp_path / "astra.mtl").read_text()
    assert "map_Kd model.png" in mtl and "newmtl astra_wood" in mtl
    loaded = o3d.io.read_triangle_mesh(str(tmp_path / "astra.obj"))
    assert len(loaded.triangles) == len(original.triangles)+1


def test_pipeline_generates_served_model_overlay_and_reuses_paid_response(tmp_path, capture, monkeypatch):
    stage_capture(tmp_path, capture)
    monkeypatch.setenv("RESPACE_SCENE_GENERATOR", "astra")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("RESPACE_ASTRA_IMAGE_LIMIT", "5")
    calls = []

    def generate(body, key):
        calls.append(body)
        return response()

    def measured_photos(manifest, inputs, baseline, mesh, working):
        write_colored_obj(mesh, working, stem="photo")
        return working / "photo.obj"

    monkeypatch.setattr(astra, "call_astra", generate)
    monkeypatch.setattr(pipeline, "refine_and_texture", measured_photos)
    result = pipeline.process(tmp_path, 1)
    assert result["status"] == "succeeded" and result["model_filename"] == "astra.obj"
    assert result["generation_model"] == "gpt-6-sol" and result["generated_triangle_count"] == 1
    assert result["needs_review"]
    output = tmp_path / "results/1"
    assert (output / "inferred.obj").is_file()
    assert len(o3d.io.read_triangle_mesh(str(output / "inferred.obj")).triangles) == 1
    for asset in result["assets"]:
        assert digest(output / asset["filename"]) == asset["sha256"]
    report = json.loads((output / "quality.json").read_text())
    assert report["generation"]["selected_frame_ids"] == [f.id for f in capture[0].frames]
    assert report["generation"]["components"][0]["label"] == "Shelf edge"
    app = create_app(tmp_path / "service", "test-reconstruction-token", start_worker=False)
    app.state.store.create(capture[0])
    served = app.state.store.folder(capture[0].capture_id) / "results/1"
    shutil.copytree(output, served)
    app.state.store.finish(capture[0].capture_id, result["status"], result)
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer test-reconstruction-token"
        prefix = f"/v1/reconstructions/{capture[0].capture_id}/results/1/assets/"
        for asset in result["assets"]:
            download = client.get(prefix + asset["filename"])
            assert download.status_code == 200
            assert hashlib.sha256(download.content).hexdigest() == asset["sha256"]
        assert client.get(prefix + "astra-response.json").status_code == 404
    assert pipeline.process(tmp_path, 2)["model_filename"] == "astra.obj"
    assert len(calls) == 1


def test_missing_key_retains_retryable_measured_model(tmp_path, capture, monkeypatch):
    stage_capture(tmp_path, capture)
    monkeypatch.setenv("RESPACE_SCENE_GENERATOR", "astra")
    monkeypatch.setattr(pipeline, "refine_and_texture", lambda *args: (_ for _ in ()).throw(RuntimeError("photo unavailable")))
    result = pipeline.process(tmp_path, 1)
    assert result["status"] == "partially_processed" and result["model_filename"] == "model.obj"
    assert result["generation_model"] is None
    assert "OPENAI_API_KEY" in result["error"]
    assert not (tmp_path / "results/1/astra.obj").exists()


def test_invalid_geometry_checkpoint_does_not_trap_user_in_failing_retries(tmp_path, capture, monkeypatch):
    stage_capture(tmp_path, capture)
    monkeypatch.setenv("RESPACE_SCENE_GENERATOR", "astra")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("RESPACE_ASTRA_IMAGE_LIMIT", "5")
    bad = scene()
    bad["components"][0]["triangles"][0]["a"] = 999
    replies = [response(bad), response()]
    monkeypatch.setattr(astra, "call_astra", lambda *args: replies.pop(0))
    monkeypatch.setattr(pipeline, "refine_and_texture", lambda *args: (_ for _ in ()).throw(RuntimeError("photo unavailable")))
    first = pipeline.process(tmp_path, 1)
    assert first["model_filename"] == "model.obj" and first["generation_model"] is None
    assert (tmp_path / "work/astra-rejected-response.json").is_file()
    assert not (tmp_path / "work/astra-response.json").exists()
    assert pipeline.process(tmp_path, 2)["model_filename"] == "astra.obj"
    assert not replies
