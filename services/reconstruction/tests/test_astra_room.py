"""Offline end-to-end contract tests; no paid calls or private scan fixtures."""
import copy
import json

import numpy as np
import open3d as o3d
import pytest
from shapely import Point, Polygon

from respace_reconstruction import astra, astra_room, pipeline
from respace_reconstruction.astra_evidence import collect_evidence
from respace_reconstruction.geometry import read_scan
from respace_reconstruction.scene import SceneBundle
from respace_reconstruction.store import Store, digest
from test_walkthrough import room_capture


def vector(x=0., y=0., z=0.):
    return {"x": x, "y": y, "z": z}


def box(center, size, shape="box"):
    return {"shape": shape, "center": vector(*center), "size": vector(*size),
            "yaw": 0., "vertices": [], "triangles": []}


def room_plan():
    def entity(identifier, kind, parts):
        return {"id": identifier, "label": identifier, "kind": kind, "material_id": "wood",
                "position": vector(), "yaw": 0., "parts": parts, "support_id": None,
                "evidence_frame_ids": ["frame-0"], "observed_fraction": .8}
    entities = [entity("floor", "floor", [box([0., -.025, 0.], [4., .05, 4.])]),
                entity("ceiling", "ceiling", [box([0., 2.525, 0.], [4., .05, 4.])])]
    for i, (center, size) in enumerate([
        ([0., 1.25, -2.], [4., 2.5, .08]), ([0., 1.25, 2.], [4., 2.5, .08]),
        ([-2., 1.25, 0.], [.08, 2.5, 4.]), ([2., 1.25, 0.], [.08, 2.5, 4.])]):
        entities.append(entity("wall"+str(i), "wall", [box(center, size)]))
    entities.append(entity("chair", "furniture", [box([0., .4, -.5], [.8, .8, .8]),
                    box([0., .9, -.8], [.8, .4, .15], "ellipsoid")]))
    return {"schema_version": 1, "coordinate_system": "arkit_scan_meters_y_up",
            "summary": "A complete synthetic room", "assumptions": ["Complete hidden chair back"],
            "ignored_evidence": ["Mirror image is not a second chair"],
            "floor_polygon": [{"x": x, "z": z} for x, z in [(-2., -2.), (2., -2.), (2., 2.), (-2., 2.)]],
            "floor_height": 0., "ceiling_height": 2.5,
            "materials": [{"id": "wood", "color": {"r": .4, "g": .3, "b": .2}, "roughness": .7}],
            "entities": entities}


def response(plan=None):
    return {"status": "completed", "output": [{"type": "message", "content": [
        {"type": "output_text", "text": json.dumps(plan or room_plan())}]}],
        "usage": {"input_tokens": 100000, "output_tokens": 20000,
                  "input_tokens_details": {"cached_tokens": 0},
                  "output_tokens_details": {"reasoning_tokens": 4000}}}


def test_all_lidar_frames_contribute_even_when_only_one_photo_is_selected(tmp_path, monkeypatch):
    manifest, _ = room_capture(tmp_path)
    monkeypatch.setenv("RESPACE_ASTRA_IMAGE_LIMIT", "1")
    mesh = read_scan(tmp_path/"inputs"/manifest.scene_mesh.filename, manifest.capture_id, o3d)
    evidence, images = collect_evidence(manifest, tmp_path/"inputs", mesh)
    assert len(images) == len(evidence["selected_photos"]) == 1
    assert len(evidence["frames"]) == len(manifest.frames) == 5
    assert all(f["valid_depth_pixels"] > 0 for f in evidence["frames"])
    assert sum(v[-1] for v in evidence["lidar_voxels"]) == evidence["valid_depth_pixel_count"]
    assert evidence["valid_depth_pixel_count"] == sum(f["valid_depth_pixels"] for f in evidence["frames"])
    assert len(evidence["lidar_voxels"]) <= 6000
    body = astra_room.request_body(evidence, images)
    assert body["model"] == "gpt-6-astra" and body["store"] is False
    assert "tools" not in body and "mirror" in body["instructions"].lower()
    assert body["text"]["format"]["schema"]["additionalProperties"] is False


def test_full_generation_is_default_and_assets_are_atomic_reusable_and_navigable(tmp_path, monkeypatch):
    manifest, _ = room_capture(tmp_path)
    monkeypatch.delenv("RESPACE_PIPELINE")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls = []
    monkeypatch.setattr(astra, "call_astra", lambda *args: calls.append(args[0]) or response())
    # Any accidental handoff to the old reconstruction pipeline is an error.
    monkeypatch.setattr(pipeline, "fuse", lambda *args: pytest.fail("TSDF ran"))
    monkeypatch.setattr(pipeline, "refine_and_texture", lambda *args: pytest.fail("OpenMVS ran"))
    result = pipeline.process(tmp_path, 1)
    output = tmp_path/"results/1"
    bundle = SceneBundle.model_validate_json((output/"scene.json").read_text())
    bundle.validate_files(output, {a["filename"] for a in result["assets"]})
    assert bundle.ready and result["generation_model"] == "gpt-6-astra"
    assert {e.kind for e in bundle.entities} >= {"floor", "ceiling", "wall", "furniture"}
    assert all(digest(output/a["filename"]) == a["sha256"] for a in result["assets"])
    assert not (tmp_path/"results/1.building").exists()
    assert pipeline.process(tmp_path, 1) == result
    assert pipeline.process(tmp_path, 2)["scene_schema_version"] == 2
    assert len(calls) == 1
    report = json.loads((output/"quality.json").read_text())
    assert report["estimated_cost_usd"] == 2.
    provenance = json.loads((output/"provenance.json").read_text())
    assert provenance["assumptions"] and provenance["ignored_evidence"]
    position = bundle.navigation.spawn_position
    assert Polygon(bundle.navigation.floor_polygons[0]).contains(Point(position[0], position[2]))
    assert not any(Polygon(p).buffer(.2).contains(Point(position[0], position[2])) for p in bundle.navigation.obstacles)
    for e in bundle.entities:
        imported = o3d.io.read_triangle_mesh(str(output/e.asset))
        assert len(imported.triangles) > 0


@pytest.mark.parametrize("fault", ["missing_ceiling", "missing_walls", "bad_index", "open_mesh", "unknown_frame", "unknown_material", "outside", "duplicate", "no_spawn"])
def test_invalid_or_incomplete_model_never_publishes(tmp_path, monkeypatch, fault):
    room_capture(tmp_path)
    plan = copy.deepcopy(room_plan())
    if fault == "missing_ceiling":
        plan["entities"] = [e for e in plan["entities"] if e["kind"] != "ceiling"]
    elif fault == "missing_walls":
        plan["entities"] = [e for e in plan["entities"] if e["id"] != "wall0"]
    elif fault in ("bad_index", "open_mesh"):
        plan["entities"][-1]["parts"] = [{"shape": "mesh", "center": vector(), "size": vector(1., 1., 1.),
            "yaw": 0., "vertices": [vector(), vector(1., 0., 0.), vector(0., 1., 0.)],
            "triangles": [{"a": 0, "b": 1, "c": 5 if fault == "bad_index" else 2}]}]
    elif fault == "unknown_frame":
        plan["entities"][-1]["evidence_frame_ids"] = ["invented-frame"]
    elif fault == "unknown_material":
        plan["entities"][-1]["material_id"] = "../file"
    elif fault == "outside":
        plan["entities"][-1]["position"]["x"] = 50.
    elif fault == "duplicate":
        plan["entities"][-1]["id"] = "floor"
    else:
        plan["entities"][-1]["parts"] = [box([0., .5, 0.], [4., 1., 4.])]
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(astra, "call_astra", lambda *args: response(plan))
    with pytest.raises(ValueError):
        astra_room.process_astra_room(tmp_path, 1)
    assert not (tmp_path/"results/1").exists()
    assert not (tmp_path/"results/1.building").exists()
    assert (tmp_path/"work/astra-room-rejected.json").exists()


def test_unknown_billing_outcome_blocks_automatic_repayment(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    evidence = {"selected_photos": []}
    calls = []
    def interrupted(*args):
        calls.append(1)
        raise RuntimeError("interrupted")
    monkeypatch.setattr(astra, "call_astra", interrupted)
    with pytest.raises(RuntimeError, match="interrupted"):
        astra_room.generate(evidence, [], tmp_path)
    with pytest.raises(RuntimeError, match="unknown billing"):
        astra_room.generate(evidence, [], tmp_path)
    assert len(calls) == 1


def test_missing_key_does_not_publish_or_contact_api(tmp_path, monkeypatch):
    room_capture(tmp_path)
    monkeypatch.setattr(astra, "call_astra", lambda *args: pytest.fail("Unconfigured API was contacted"))
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        astra_room.process_astra_room(tmp_path, 1)
    assert not (tmp_path/"results/1").exists()


def test_explicit_retry_replaces_rejected_response_but_preserves_good_paid_checkpoint(tmp_path):
    manifest, _ = room_capture(tmp_path)
    store = Store(tmp_path/"service")
    store.create(manifest)
    folder = store.folder(manifest.capture_id)
    for artifact in manifest.artifacts:
        (folder/"inputs"/artifact.filename).write_bytes((tmp_path/"inputs"/artifact.filename).read_bytes())
    work = folder/"work"
    work.mkdir()
    checkpoint = work/"astra-room-response.json"
    checkpoint.write_text("{}")
    store.finish(manifest.capture_id, "failed", error="Invalid geometry")
    store.queue(manifest.capture_id, retry=True)
    assert checkpoint.exists()
    store.finish(manifest.capture_id, "failed", error="Invalid geometry")
    (work/"astra-room-rejected.json").write_text("{}")
    store.queue(manifest.capture_id, retry=True)
    assert not checkpoint.exists()


def test_pricing_includes_reasoning_and_long_context_rates():
    assert astra_room.usage_cost(response())["estimated_cost_usd"] == 2.
    result = response()
    result["usage"]["input_tokens"] = 300000
    assert astra_room.usage_cost(result)["estimated_cost_usd"] == 7.5
    assert astra_room.usage_cost({})["estimated_cost_usd"] is None
