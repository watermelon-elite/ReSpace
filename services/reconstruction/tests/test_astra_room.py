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


@pytest.fixture(autouse=True)
def single_call_contract(monkeypatch):
    # These tests cover the retained coarse-generation contract. The staged
    # default and spending controller are exercised by test_astra_detail.py.
    from functools import partial
    monkeypatch.setattr(astra_room, "process_astra_room", partial(astra_room.process_astra_room, detailed=False))


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
    entities = [entity("chair", "furniture", [box([0., .4, -.5], [.8, .8, .8]),
                    box([0., .9, -.8], [.8, .4, .15], "ellipsoid")])]
    entities[0]["category"] = "seating"
    entities[0]["model_description"] = "Wooden chair with a red upholstered seat, four legs and a curved backrest"
    return {"schema_version": 1, "coordinate_system": "arkit_scan_meters_y_up",
            "summary": "Furniture only", "assumptions": ["Complete hidden chair back"],
            "ignored_evidence": ["Mirror image is not a second chair"],
            "materials": [{"id": "wood", "color": {"r": .4, "g": .3, "b": .2}, "roughness": .7, "texture_family": "wood"}],
            "entities": entities}


def response(plan=None):
    return {"status": "completed", "output": [{"type": "message", "content": [
        {"type": "output_text", "text": json.dumps(plan or room_plan())}]}],
        "usage": {"input_tokens": 100000, "output_tokens": 20000,
                  "input_tokens_details": {"cached_tokens": 0},
                  "output_tokens_details": {"reasoning_tokens": 4000}}}


def test_all_lidar_frames_contribute_even_when_only_one_photo_is_selected(tmp_path, monkeypatch):
    manifest, _ = room_capture(tmp_path)
    room_file = tmp_path/"inputs"/manifest.room_export.filename
    room = json.loads(room_file.read_text())
    room["coreModel"] = "opaque-binary-payload-not-useful-as-text"
    room_file.write_text(json.dumps(room))
    monkeypatch.setenv("RESPACE_ASTRA_IMAGE_LIMIT", "1")
    mesh = read_scan(tmp_path/"inputs"/manifest.scene_mesh.filename, manifest.capture_id, o3d)
    evidence, images = collect_evidence(manifest, tmp_path/"inputs", mesh)
    assert "coreModel" not in evidence["roomplan"]
    assert len(images) == len(evidence["selected_photos"]) == 1
    assert len(evidence["frames"]) == len(manifest.frames) == 5
    assert all(f["valid_depth_pixels"] > 0 for f in evidence["frames"])
    assert sum(v[-1] for v in evidence["lidar_voxels"]) == evidence["valid_depth_pixel_count"]
    assert evidence["valid_depth_pixel_count"] == sum(f["valid_depth_pixels"] for f in evidence["frames"])
    assert len(evidence["lidar_voxels"]) <= 6000
    body = astra_room.request_body(evidence, images)
    assert body["model"] == "gpt-6-sol" and body["store"] is False
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
    assert bundle.ready and result["generation_model"] == "gpt-6-sol"
    assert {e.kind for e in bundle.entities} >= {"floor", "ceiling", "wall", "furniture"}
    assert all(digest(output/a["filename"]) == a["sha256"] for a in result["assets"])
    assert not (tmp_path/"results/1.building").exists()
    assert pipeline.process(tmp_path, 1) == result
    assert pipeline.process(tmp_path, 2)["scene_schema_version"] == 2
    assert len(calls) == 1
    report = json.loads((output/"quality.json").read_text())
    assert report["estimated_cost_usd"] == .4
    provenance = json.loads((output/"provenance.json").read_text())
    assert provenance["assumptions"] and provenance["ignored_evidence"]
    position = bundle.navigation.spawn_position
    assert Polygon(bundle.navigation.floor_polygons[0]).contains(Point(position[0], position[2]))
    assert not any(Polygon(p).buffer(.2).contains(Point(position[0], position[2])) for p in bundle.navigation.obstacles)
    for e in bundle.entities:
        imported = o3d.io.read_triangle_mesh(str(output/e.asset))
        assert len(imported.triangles) > 0


@pytest.mark.parametrize("fault", ["architecture", "clutter", "bad_index", "open_mesh", "unknown_frame", "unknown_material", "outside", "duplicate", "no_spawn"])
def test_invalid_or_incomplete_model_never_publishes(tmp_path, monkeypatch, fault):
    room_capture(tmp_path)
    plan = copy.deepcopy(room_plan())
    if fault == "architecture":
        plan["entities"][0]["kind"] = "wall"
    elif fault == "clutter":
        plan["entities"][0]["category"] = "dish_soap"
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
        plan["entities"] *= 2
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
    assert astra_room.usage_cost(response())["estimated_cost_usd"] == .4
    result = response()
    result["usage"]["input_tokens"] = 300000
    assert astra_room.usage_cost(result)["estimated_cost_usd"] == 1.5
    assert astra_room.usage_cost({})["estimated_cost_usd"] is None
    result["usage"] = {"input_tokens": 218518, "output_tokens": 48000,
                       "input_tokens_details": {"cache_write_tokens": 218515, "cached_tokens": 0}}
    assert astra_room.usage_cost(result)["estimated_cost_usd"] == pytest.approx(1.026294, abs=.000001)


def test_empty_room_does_not_require_invented_furniture(tmp_path, monkeypatch):
    room_capture(tmp_path)
    plan = room_plan()
    plan["entities"] = []
    plan["materials"] = []
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(astra, "call_astra", lambda *args: response(plan))
    result = astra_room.process_astra_room(tmp_path, 1)
    scene = SceneBundle.model_validate_json((tmp_path/"results/1/scene.json").read_text())
    assert result["status"] == "succeeded"
    assert {e.kind for e in scene.entities} == {"wall", "floor", "ceiling"}


def test_small_intentional_decor_remains_eligible_and_detail_is_bounded(tmp_path):
    manifest, _ = room_capture(tmp_path)
    evidence = {"roomplan": json.loads((tmp_path/"inputs"/manifest.room_export.filename).read_text())}
    shell = astra_room.measured_structure(evidence)
    plan = room_plan()
    plan["entities"][0]["label"] = "Small decorative vase"
    plan["entities"][0]["category"] = "decorative_vase"
    furnishings = astra_room.FurnishingPlan.model_validate(plan)
    assert astra_room.assemble_room(shell, furnishings).entities[-1].category == "decorative_vase"
    plan["entities"] = [dict(plan["entities"][0], id="item"+str(i),
                             parts=[plan["entities"][0]["parts"][0]]*12) for i in range(14)]
    with pytest.raises(ValueError, match="160-part"):
        astra_room.assemble_room(shell, astra_room.FurnishingPlan.model_validate(plan))


def test_bad_measured_shell_fails_before_any_paid_generation(tmp_path, monkeypatch):
    room_capture(tmp_path)
    from respace_reconstruction.instances import RescanRequired
    monkeypatch.setattr(astra_room, "collect_evidence", lambda *args: ({"roomplan": {}}, []))
    monkeypatch.setattr(astra_room, "generate", lambda *args: pytest.fail("Paid generation preceded shell checks"))
    with pytest.raises(RescanRequired):
        astra_room.process_astra_room(tmp_path, 1)


def test_incomplete_response_reports_output_budget_reason():
    with pytest.raises(ValueError, match="max_output_tokens"):
        astra_room.parse_response({"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}})


@pytest.mark.parametrize("category,label,kind", [
    ("appliance", "Microwave", "furniture"),
    ("appliance", "Built-in microwave", "fixed"),
    ("electronics", "Desktop computer", "furniture"),
    ("countertop", "Installed countertop", "fixed"),
    ("sink", "Kitchen sink", "fixed"),
    ("faucet", "Installed faucet", "fixed"),
    ("plumbing_fixture", "Radiator", "fixed"),
    ("lighting_fixture", "Ceiling light", "fixed"),
    ("architectural_detail", "Vent grille", "fixed"),
    ("door", "Door panel", "fixed"),
    ("window", "Window frame", "fixed"),
    ("functional_equipment", "Exercise equipment", "furniture"),
    ("organized_contents", "Organized books", "furniture"),
    ("other_intentional_item", "Intentional room contents", "furniture"),
])
def test_intentional_contents_and_installed_features_are_eligible(tmp_path, category, label, kind):
    manifest, _ = room_capture(tmp_path)
    shell = astra_room.measured_structure({"roomplan": json.loads((tmp_path/"inputs"/manifest.room_export.filename).read_text())})
    data = room_plan()
    data["entities"][0].update(category=category, label=label, kind=kind)
    contents = astra_room.parse_response(response(data))
    composed = astra_room.assemble_room(shell, contents)
    assert composed.entities[-1].category == category
    assert composed.entities[-1].kind == kind


def test_ceiling_fixtures_do_not_make_entire_floor_unwalkable(tmp_path, monkeypatch):
    room_capture(tmp_path)
    data = room_plan()
    entity = data["entities"][0]
    entity.update(id="ceiling-light", label="Ceiling light", kind="fixed", category="lighting_fixture")
    entity["parts"] = [box([0., 2.3, 0.], [3.5, .1, 3.5])]
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(astra, "call_astra", lambda *args: response(data))
    assert astra_room.process_astra_room(tmp_path, 1)["status"] == "succeeded"
    bundle = SceneBundle.model_validate_json((tmp_path/"results/1/scene.json").read_text())
    fixture = next(e for e in bundle.entities if e.id == "ceiling-light")
    assert fixture.kind == "fixed" and not fixture.move_ready and not fixture.collidable
