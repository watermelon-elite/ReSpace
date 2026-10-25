"""Analytic room, real ray casting/exports, mocked paid API boundary."""
import copy
import json

import numpy as np
import pytest
from PIL import Image

from respace_reconstruction import astra, astra_room, astra_spending, insta_method, pipeline
from respace_reconstruction.astra_room import FurnishingPlan
from respace_reconstruction.geometry import CAMERA_FLIP, camera_to_cv_world, read_scan
from respace_reconstruction.insta_views import PreviewScene, confident_depth, paired_content, rays, select_views
from respace_reconstruction.models import Metadata
from respace_reconstruction.scene import SceneBundle
from respace_reconstruction.store import digest
from test_astra_detail import reply
from test_astra_room import box, room_plan
from test_walkthrough import room_capture


@pytest.fixture(autouse=True)
def select_method(monkeypatch):
    # The legacy suite deliberately defaults its worker environment to legacy.
    monkeypatch.setenv("RESPACE_PIPELINE", "insta")


def inventory():
    plan = room_plan()
    entity = plan["entities"][0]
    entity["parts"] = [box([0., .4, -.5], [.8, .8, .8])]
    entity["evidence_frame_ids"] = [f"frame-{i}" for i in range(5)]
    return plan


def detail():
    plan = inventory()
    entity = copy.deepcopy(plan["entities"][0])
    entity["parts"][0]["material_id"] = "wood"
    return {"entity": entity, "materials": [dict(plan["materials"][0], metallic=0.)]}


def configured_api(monkeypatch, *, fail_fit_once=False, heldout_failure=False):
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test-key")
    monkeypatch.setattr(astra_spending, "count_input_tokens", lambda *args: 1000)
    calls = []
    fitting_reviews = 0
    constructions = 0

    def call(body, key):
        nonlocal fitting_reviews, constructions
        calls.append(body)
        schema = body["text"]["format"]["schema"]
        if "entities" in schema["properties"]:
            return reply(inventory())
        if "entity" in schema["properties"]:
            constructions += 1
            candidate = detail()
            if fail_fit_once and constructions > 1:
                # Correction changes rendered evidence; an unchanged render's
                # identical critique must reuse the prior verdict, not rebuy it.
                candidate["materials"][0]["color"]["r"] = .8
            return reply(candidate)
        content = body["input"][0]["content"]
        labels = [c["text"] for c in content if c["type"] == "input_text"]
        target = labels[0].split("target ")[-1]
        frames = [label.split(";")[0].split("=")[1] for label in labels]
        fail = heldout_failure and len(frames) == 1
        if target != "room" and len(frames) > 1:
            fitting_reviews += 1
            fail |= fail_fit_once and fitting_reviews == 1
        return reply({"target_id": target, "views": [
            {"frame_id": frame, "passed": not fail, "issues": ["Backrest silhouette differs"] if fail else []}
            for frame in frames]})

    monkeypatch.setattr(astra, "call_astra", call)
    return calls


def test_camera_rays_use_optical_axis_depth_at_edges_and_sensor_orientation():
    pose = np.eye(4)
    pose[:3, 3] = [1., 2., 3.]
    m = Metadata(id="f", capture_id="c", timestamp=0., width=8, height=6,
                 intrinsics=[4., 4., 4., 3.], camera_to_scan_transform=pose.flatten(order="F").tolist())
    ray = rays(m, 4, 3)
    np.testing.assert_allclose(ray[0, 0, :3], [1, 2, 3])
    np.testing.assert_allclose(ray[0, 0, 3:], [-1, .75, -1])
    # Edge ray has length >1, yet depth remains camera Z. Round trip into CV.
    point = ray[0, 0, :3]+2*ray[0, 0, 3:]
    inverse = np.linalg.inv(camera_to_cv_world(m))
    np.testing.assert_allclose((inverse @ np.r_[point, 1])[:3], [-2, -1.5, 2])


def preview_fixture(tmp_path):
    import open3d as o3d
    manifest, _ = room_capture(tmp_path)
    room = json.loads((tmp_path/"inputs"/manifest.room_export.filename).read_text())
    shell = astra_room.measured_structure({"roomplan": room})
    plan = astra_room.assemble_room(shell, FurnishingPlan.model_validate(inventory()))
    output = tmp_path/"preview"
    output.mkdir()
    _, _, meshes, _, _ = astra_room.compile_room(plan, {f.id for f in manifest.frames}, output, o3d)
    return manifest, plan, PreviewScene(plan, meshes)


def test_real_renders_match_depth_and_select_disjoint_translated_views(tmp_path):
    manifest, plan, scene = preview_fixture(tmp_path)
    fit, heldout = select_views(plan.entities[-1], manifest, tmp_path/"inputs")
    assert len(fit) == 3 and len(heldout) == 1
    assert not {f.id for f in fit} & {f.id for f in heldout}
    for frame in fit+heldout:
        check = scene.depth_check(frame, tmp_path/"inputs", "chair")
        assert check["passed"] and check["samples"] >= 16
        assert check["median_error_m"] < .003
    content, cameras = paired_content(scene, fit, tmp_path/"inputs", "chair", tmp_path/"pairs")
    assert len([c for c in content if c["type"] == "input_image"]) == 6
    assert cameras[0]["camera_to_scan_columns"] == fit[0].metadata.camera_to_scan_transform
    assert Image.open(tmp_path/"pairs/0-render.jpg").size == Image.open(tmp_path/"pairs/0-photo.jpg").size
    # Translation corrupts real depth correspondence despite a valid schema.
    wrong = copy.deepcopy(plan)
    wrong.entities[-1].parts[0].size.z = .3
    import open3d as o3d
    other = tmp_path/"wrong"; other.mkdir()
    _, _, meshes, _, _ = astra_room.compile_room(wrong, {f.id for f in manifest.frames}, other, o3d)
    checks = [PreviewScene(wrong, meshes).depth_check(f, tmp_path/"inputs", "chair") for f in fit+heldout]
    assert any(not c["passed"] for c in checks)


def test_missing_or_mismatched_confidence_cannot_claim_metric_agreement(tmp_path):
    manifest, _ = room_capture(tmp_path)
    frame = manifest.frames[0]
    artifact = next(a for a in frame.artifacts if a.type == "confidence")
    path = tmp_path/"inputs"/artifact.filename
    path.write_bytes(bytes(artifact.byte_length))
    assert not confident_depth(frame, tmp_path/"inputs").any()
    with pytest.raises(ValueError, match="three translated"):
        select_views(FurnishingPlan.model_validate(inventory()).entities[0],
                     manifest.model_copy(update={"frames": [frame, frame, frame]}), tmp_path/"inputs")
    frame.metadata.confidence_width = 10
    with pytest.raises(ValueError, match="dimensions"):
        confident_depth(frame, tmp_path/"inputs")


def test_explicit_historical_pipeline_publishes_real_mesh_usdz_photos_and_reuses_paid_work(tmp_path, monkeypatch):
    room_capture(tmp_path)
    calls = configured_api(monkeypatch)
    monkeypatch.setenv("RESPACE_PIPELINE", "insta")
    result = pipeline.process(tmp_path, 1)
    assert result["generation_model"] == "gpt-6-astra" and len(calls) == 5
    assert all(c["store"] is False and "tools" not in c for c in calls)
    output = tmp_path/"results/1"
    scene = SceneBundle.model_validate_json((output/"scene.json").read_text())
    scene.validate_files(output, {a["filename"] for a in result["assets"]})
    assert (output/"model.usdz").stat().st_size > 0
    assert list(output.glob("photo-*.jpg"))
    quality = json.loads((output/"quality.json").read_text())
    assert quality["pipeline"] == "insta" and quality["objects"][0]["attempts"] == 1
    assert quality["objects"][0]["validation"]["visual"]["views"][0]["passed"]
    assert quality["budget"]["paid_call_count"] == 5
    assert all(digest(output/a["filename"]) == a["sha256"] for a in result["assets"])
    assert pipeline.process(tmp_path, 2)["status"] == "succeeded"
    assert len(calls) == 5
    assert json.loads((tmp_path/"results/2/quality.json").read_text())["response_reused"]
    # A corrupted completed asset must not be presented as verified on reopen.
    (output/"model.obj").write_text("corrupt")
    with pytest.raises(ValueError, match="integrity"):
        pipeline.process(tmp_path, 1)


def test_visual_failure_drives_correction_and_heldout_is_never_construction_input(tmp_path, monkeypatch):
    room_capture(tmp_path)
    calls = configured_api(monkeypatch, fail_fit_once=True)
    pipeline.process(tmp_path, 1)
    report = json.loads((tmp_path/"results/1/quality.json").read_text())
    assert report["objects"][0]["attempts"] == 2 and len(calls) == 7
    constructions = [c for c in calls if "entity" in c["text"]["format"]["schema"]["properties"]]
    for call in constructions:
        # All-frame inventory IDs are metadata, but paired images use fitting IDs only.
        pair_labels = [c["text"] for c in call["input"][0]["content"][1:] if c["type"] == "input_text"]
        assert all("frame_id="+report["objects"][0]["heldout_frame_ids"][0]+";" not in label for label in pair_labels)
    assert "Backrest silhouette differs" in json.dumps(constructions[1])


def test_failed_heldout_retains_receipts_without_publishing_or_rebuying(tmp_path, monkeypatch):
    room_capture(tmp_path)
    calls = configured_api(monkeypatch, heldout_failure=True)
    for revision in (1, 2):
        with pytest.raises(ValueError, match="held-out"):
            pipeline.process(tmp_path, revision)
    assert len(calls) == 4
    assert not (tmp_path/"results/1").exists() and not (tmp_path/"results/2").exists()
    assert len(list((tmp_path/"work/insta-v1").rglob("response.json"))) == 4


def test_review_cannot_omit_duplicate_or_invent_view_identities(tmp_path):
    manifest, _ = room_capture(tmp_path)
    for frame_ids in (["frame-0"], ["frame-0", "frame-0"], ["frame-0", "foreign"]):
        response = reply({"target_id": "chair", "views": [
            {"frame_id": f, "passed": True, "issues": []} for f in frame_ids]})
        with pytest.raises(ValueError, match="identities"):
            insta_method.parse_review(response, "chair", manifest.frames[:2])


def test_budget_failure_never_publishes_coarse_fallback(tmp_path, monkeypatch):
    room_capture(tmp_path)
    calls = configured_api(monkeypatch)
    counts = iter([1000, 10_000_000])
    monkeypatch.setattr(astra_spending, "count_input_tokens", lambda *args: next(counts))
    with pytest.raises(astra_spending.BudgetExhausted):
        pipeline.process(tmp_path, 1)
    assert len(calls) == 1 and not (tmp_path/"results/1").exists()
    assert list((tmp_path/"work/insta-v1/responses").glob("*/response.json"))


def test_unknown_provider_outcome_blocks_retry_before_another_paid_request(tmp_path, monkeypatch):
    room_capture(tmp_path)
    configured_api(monkeypatch)
    calls = []
    def disconnected(*args):
        calls.append(1)
        raise RuntimeError("Connection interrupted")
    monkeypatch.setattr(astra, "call_astra", disconnected)
    with pytest.raises(RuntimeError, match="interrupted"):
        pipeline.process(tmp_path, 1)
    with pytest.raises(RuntimeError, match="unknown billing"):
        pipeline.process(tmp_path, 2)
    assert calls == [1] and not (tmp_path/"results/1").exists()
    ledger = json.loads((tmp_path/"work/astra-budget-v3.json").read_text())
    assert next(iter(ledger["entries"].values()))["state"] == "reserved"


def test_identical_failed_comparison_reuses_verdict_and_stops_at_attempt_limit(tmp_path, monkeypatch):
    room_capture(tmp_path)
    configured_api(monkeypatch)
    calls = []
    def repeated(body, key):
        calls.append(body)
        properties = body["text"]["format"]["schema"]["properties"]
        if "entities" in properties:
            return reply(inventory())
        if "entity" in properties:
            return reply(detail())
        labels = [c["text"] for c in body["input"][0]["content"] if c["type"] == "input_text"]
        return reply({"target_id": "chair", "views": [
            {"frame_id": label.split(";")[0].split("=")[1], "passed": False,
             "issues": ["Visible silhouette differs"]} for label in labels]})
    monkeypatch.setattr(astra, "call_astra", repeated)
    with pytest.raises(ValueError, match="after 3 attempts"):
        pipeline.process(tmp_path, 1)
    assert len(calls) == 4  # Inventory, two distinct constructions, one cached critique.
    assert not (tmp_path/"results/1").exists()
    assert (tmp_path/"work/insta-v1/objects").exists()


def test_fresh_generation_isolates_new_responses_without_replacing_prior_result(tmp_path, monkeypatch):
    import uuid
    room_capture(tmp_path)
    calls = configured_api(monkeypatch)
    first = pipeline.process(tmp_path, 1)
    run_id = str(uuid.uuid4())
    second = pipeline.process(tmp_path, 2, generation_id=run_id)
    assert len(calls) == 10 and first["revision"] == 1 and second["revision"] == 2
    assert (tmp_path/"results/1/completion.json").exists()
    assert (tmp_path/"work/runs"/run_id/"astra-budget-v3.json").exists()
    assert len(list((tmp_path/"work/runs"/run_id/"insta-v1/responses").glob("*/response.json"))) == 5
