import asyncio
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from respace.categories import CATEGORIES
from respace.lifting import calibrated_overlay_svg, decode_depth, lift_keyframe
from respace.merging import merge
from respace.operations import OperationService
from respace.solver import solve
from respace.spatial import SpatialPipeline
from test_api import MemoryStorage
from test_lifting import calibrated_room, camera


def native_object(identity="o_1", **changes):
    return {"id": identity, "category": "chair", "source": "roomplan", "source_ids": [identity],
            "center": [2, 1], "base_y": 0, "size": [1, .5, 1], "yaw": 0, "mount": "floor",
            "wall_id": None, "support_id": None, "attrs": {}, "fixed_in_place": False,
            "observation_count": 0, **changes}


def color_frame():
    return {**camera(), "w": 160, "h": 120,
            "intrinsics": {"fx": 80, "fy": 80, "cx": 80, "cy": 60}}


def test_native_masks_occlude_far_boxes_erode_edges_and_include_projected_diagnostics():
    room, frame = calibrated_room(), color_frame()
    room["objects"] = [native_object(), native_object("o_2", center=[2, .5], size=[.5, .25, .5])]
    rgb = np.full((120, 160, 3), [32, 96, 160], dtype=np.uint8)
    lift = lift_keyframe(room, frame, [], rgb)
    assert lift["color_samples"][0]["rgb"] == [32, 96, 160]
    assert len(lift["color_samples"]) == 1
    front, hidden = lift["color_diagnostics"]["masks"]
    assert front["visible_pixels"] > front["usable_pixels"] >= 200
    assert hidden["visible_pixels"] == hidden["usable_pixels"] == 0
    # The upper face widens the projected silhouette; erosion trims its outer rows.
    assert front["usable_runs"][0][0] == front["visible_runs"][0][0] + 2
    assert front["usable_runs"][-1][0] == front["visible_runs"][-1][0] - 2
    overlay = calibrated_overlay_svg(room, frame, lift)
    assert 'data-mask="visible" data-object="o_1"' in overlay
    assert 'data-mask="usable" data-object="o_1"' in overlay
    assert 'data-object="o_2"' in overlay  # Corners remain diagnostic even when fully hidden.
    room["walls"].append({"id": "occluder", "a": [0, 1.7], "b": [4, 1.7], "length": 4,
                           "inward_normal": [0, 1], "virtual": False})
    assert lift_keyframe(room, frame, [], rgb)["color_samples"] == []


@pytest.mark.parametrize("offset,confidence,retained", [(.1499, 2, True), (.1501, 2, False),
                                                        (.5, 1, True), (.5, None, True)])
def test_only_qualified_depth_filters_native_pixels_at_fifteen_centimeter_boundary(offset, confidence, retained):
    room, frame = calibrated_room(), color_frame()
    room["objects"] = [native_object()]
    # Camera Z=2.8, front box Z=1.25: predicted optical depth is 1.55 m.
    depth = decode_depth(np.full((120, 160), 1.55+offset, dtype="<f4").tobytes(),
                         bytes([confidence]*19200) if confidence is not None else None, 160, 120)
    lift = lift_keyframe(room, frame, [], np.zeros((120, 160, 3), dtype=np.uint8), depth)
    assert bool(lift["color_samples"]) == retained
    mask = lift["color_diagnostics"]["masks"][0]
    assert bool(mask["depth_rejected_pixels"]) != retained


def test_native_oriented_bounds_change_the_visible_projection_and_behind_camera_has_no_sample():
    room, frame = calibrated_room(), color_frame()
    room["objects"] = [native_object(size=[1, .2, 1])]
    rgb = np.zeros((120, 160, 3), dtype=np.uint8)
    first = lift_keyframe(room, frame, [], rgb)["color_diagnostics"]["masks"][0]
    room["objects"][0]["yaw"] = np.pi/2
    turned = lift_keyframe(room, frame, [], rgb)["color_diagnostics"]["masks"][0]
    assert turned["visible_pixels"] < first["visible_pixels"]
    room["objects"][0]["center"] = [2, 4]
    assert lift_keyframe(room, frame, [], rgb)["color_samples"] == []


def test_detected_objects_sample_only_central_half_of_valid_lifted_boxes():
    rgb = np.full((120, 160, 3), [250, 250, 250], dtype=np.uint8)
    rgb[93:103, 137:142] = [11, 22, 33]
    lift = lift_keyframe(calibrated_room(), color_frame(), [
        {"category": "floor_lamp", "box_px": [135, 88, 145, 108]}], rgb)
    assert lift["color_samples"] == [{"reference": {"kind": "detection", "id": "det:frame-edge:0"},
        "rgb": [11, 22, 33], "usable_pixels": 50, "method": "detected_box"}]


def sample_lift(index, count, rgb=(20, 60, 100)):
    return {"capture_id": "capture", "frame_id": f"f{index}", "input_revision": 1, "idx": index,
            "state": "succeeded", "detections": [], "color_samples": [{"reference": {"kind": "object", "id": "o_1"},
            "rgb": list(rgb), "usable_pixels": count, "method": "native_visibility"}]}


def test_native_threshold_best_five_views_and_default_tint_reach_the_scene_without_mutating_room():
    room = calibrated_room()
    room["objects"] = [native_object()]
    before = deepcopy(room)
    below = merge(room, [sample_lift(0, 199)])
    enough = merge(room, [sample_lift(0, 199), sample_lift(1, 1)])
    assert "color" not in below["objects"][0]["attrs"]
    assert enough["objects"][0]["attrs"]["color"] == "#143C64"
    views = [sample_lift(i, count, (i*10, i*10, i*10)) for i, count in enumerate([100, 60, 40, 30, 20, 10])]
    best = merge(room, views)["objects"][0]
    assert best["attrs"]["color"] == "#141414"
    assert best["color_evidence"]["usable_pixels"] == 250
    assert [v["frame_id"] for v in best["color_evidence"]["views"]] == ["f0", "f1", "f2", "f3", "f4"]
    plan = {"decision_revision": 0, "removals": [], "moves": [], "adds": []}
    constraints = {"intent": "add", "approved_ceiling": "100", "instructions": {}}
    for measured, tint in [(below, CATEGORIES["chair"]["default_tint"]), (enough, "#143C64")]:
        scene = solve({"snapshot_id": "snapshot", "room": measured}, plan, {}, constraints)["scene"]
        assert scene["items"][0]["render"]["tint"] == tint
    assert room == before


def prepare_color_capture(store):
    """Test-only retained capture used by the shared API/native transport fixture."""
    raw = json.loads((Path(__file__).parent / "fixtures/spatial/rectangle_v1.json").read_text())["raw_export"]
    for identity, x, z, size in [("native-colored-chair", 4, 4, [1, 1, .5]),
                                  ("native-unseen-chair", 2.3, 5.7, [.2, .4, .2])]:
        raw["objects"].append({"identifier": identity, "category": {"chair": {}}, "dimensions": size,
            "transform": [1,0,0,0, 0,1,0,0, 0,0,1,0, x,-1.2+size[1]/2,z,1]})
    frame = {**color_frame(), "room_id": "room", "frame_id": "color-frame", "artifacts": [{"kind": "jpeg", "artifact_id": "color-photo"}]}
    storage, operations = MemoryStorage(), OperationService(store)
    image = BytesIO(); Image.new("RGB", (160, 120), (64, 128, 64)).save(image, "JPEG", quality=100, subsampling=0)
    with store.transaction():
        store.put("rooms", "room", {"room_id": "room", "device_id": "device", "latest_capture_id": "capture",
            "latest_snapshot_id": None, "active_design_id": None, "active_revision": 0,
            "planning_revision": 0, "current_operation_id": None})
        store.put("captures", "capture", {"capture_id": "capture", "room_id": "room", "state": "complete", "raw_export": raw})
        store.put("keyframes", frame["frame_id"], frame)
        store.put("artifacts", "color-photo", {"artifact_id": "color-photo", "room_id": "room", "storage_key": "color-photo"})
        storage.put("color-photo", image.getvalue(), "image/jpeg")
        store.put("detection_outcomes", frame["frame_id"], {"frame_id": frame["frame_id"], "room_id": "room",
            "capture_id": "capture", "state": "failed", "detections": [], "failure": {"code": "timeout"}})
    operations.submit("device", "room", "generation", {"operation_id": "process-color", "capture_id": "capture",
        "planning_revision": 0, "expected_active_revision": 0})
    return operations, SpatialPipeline(store, operations, storage), storage


def test_native_color_survives_detector_failure_and_reprocessing_publishes_a_new_immutable_snapshot(store):
    _, pipeline, _ = prepare_color_capture(store)
    snapshot = asyncio.run(pipeline.process_snapshot("process-color"))
    colored = next(o for o in snapshot["room"]["objects"] if o["source_ids"] == ["native-colored-chair"])
    unseen = next(o for o in snapshot["room"]["objects"] if o["source_ids"] == ["native-unseen-chair"])
    assert colored["attrs"]["color"] == "#408141"  # RGB after JPEG decoding.
    assert "color" not in unseen["attrs"]
    lift = store.list("keyframe_lifts", "room")[0]
    assert lift["state"] == "failed" and lift["color_samples"][0]["usable_pixels"] >= 200
    with store.transaction():
        room = store.get("rooms", "room"); room["latest_snapshot_id"] = snapshot["snapshot_id"]; store.put("rooms", "room", room)
        frame = store.get("keyframes", "color-frame")
        frame["transform"][8:11] = [0, 0, -1]; frame["transform"][0] = -1
        store.put("keyframes", "color-frame", frame)
    changed = asyncio.run(pipeline.process_snapshot("process-color"))
    assert changed["snapshot_id"] != snapshot["snapshot_id"]
    assert changed["revision"] == snapshot["revision"]+1
    assert store.get("snapshots", snapshot["snapshot_id"]) == snapshot
    assert all("color" not in o["attrs"] for o in changed["room"]["objects"])
