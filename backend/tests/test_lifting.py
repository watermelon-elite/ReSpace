import numpy as np
import pytest
import json
from pathlib import Path

from respace.lifting import decode_depth
from respace.geometry import normalize_room


def test_depth_transport_decodes_little_endian_without_inventing_confidence():
    frame = decode_depth(bytes.fromhex("0000803f000000400000404000008040"), None, 2, 2)
    assert frame["depth"].tolist() == [[1, 2], [3, 4]]
    assert frame["confidence"] is None
    assert frame["units"] == "m"
    qualified = decode_depth(np.array([1, 2, 3, 4], dtype="<f4").tobytes(), bytes([2, 1, 0, 2]), 2, 2)
    assert qualified["confidence"].tolist() == [[2, 1], [0, 2]]
    for data, confidence, width, height in [(b"123", None, 1, 1), (b"1234", b"", 1, 1),
                                            (b"1234", b"\x03", 1, 1), (b"", None, 0, 1)]:
        with pytest.raises(ValueError):
            decode_depth(data, confidence, width, height)


def calibrated_room():
    raw = json.loads((Path(__file__).parent / "fixtures/spatial/rectangle_v1.json").read_text())["raw_export"]
    return normalize_room(raw, "capture", "room")


def camera():
    return {"schema_version": 1, "capture_id": "capture", "frame_id": "frame-edge", "idx": 0,
            "input_revision": 1, "w": 800, "h": 600, "orientation": "sensor_landscape",
            "intrinsics": {"fx": 400, "fy": 400, "cx": 400, "cy": 300},
            "transform": [1,0,0,0, 0,1,0,0, 0,0,1,0, 4,0,5.8,1]}


def test_floor_roundtrip_at_image_edge_uses_optical_axis_depth_and_translates_origin():
    from respace.lifting import lift_keyframe

    rgb = np.zeros((600, 800, 3), dtype=np.uint8)
    depth = decode_depth(np.full((6, 8), 2, dtype="<f4").tobytes(), bytes([2] * 48), 8, 6)
    result = lift_keyframe(calibrated_room(), camera(), [
        {"category": "floor_lamp", "box_px": [675, 440, 725, 540]}], rgb, depth)
    observed = result["detections"][0]
    assert observed["position"] == pytest.approx([3.5, 0, .8], abs=.01)
    assert observed["mount"] == "floor"
    assert observed["method"] == "raycast+depth"
    assert observed["size"] == pytest.approx([.25, .4, .5])
    assert result["rejected"] == []


@pytest.mark.parametrize("value,confidence,expected", [(2.15, 2, "raycast+depth"),
    (2.3, 2, "raycast"), (2, 1, "raycast"), (2, None, "raycast"),
    (5, 2, "raycast"), (0, 2, "raycast"), (float("nan"), 2, "raycast")])
def test_depth_only_refines_nearby_high_confidence_positive_subfive_meter_samples(value, confidence, expected):
    from respace.lifting import lift_keyframe

    depth = decode_depth(np.full((6, 8), value, dtype="<f4").tobytes(),
                         bytes([confidence] * 48) if confidence is not None else None, 8, 6)
    result = lift_keyframe(calibrated_room(), camera(), [
        {"category": "floor_lamp", "box_px": [675, 440, 725, 540]}], np.zeros((600, 800, 3), dtype=np.uint8), depth)
    observed = result["detections"][0]
    assert observed["method"] == expected
    assert observed["position"][1] == 0
    if expected == "raycast":
        assert observed["position"] == pytest.approx([3.5, 0, .8])


def test_mount_raycast_uses_actual_table_support_but_floor_lamp_ignores_it():
    from respace.lifting import lift_keyframe

    room = calibrated_room()
    room["objects"].append({"id": "o_1", "category": "desk", "center": [2, 2.05], "base_y": 0,
                            "size": [1, 1, .75], "yaw": 0, "mount": "floor"})
    detections = [{"category": label, "box_px": [375, 460, 425, 540]} for label in ("table_lamp", "floor_lamp")]
    result = lift_keyframe(room, camera(), detections, np.zeros((600, 800, 3), dtype=np.uint8))
    table, floor = result["detections"]
    assert table["position"] == pytest.approx([2, .75, 2.05])
    assert table["mount"] == "tabletop" and table["support_id"] == "o_1"
    assert floor["position"] == pytest.approx([2, 0, .8])
    assert floor["mount"] == "floor" and floor["support_id"] is None


def test_wall_and_ceiling_observation_points_convert_to_explicit_bottom_elevations():
    from respace.lifting import lift_keyframe

    result = lift_keyframe(calibrated_room(), camera(), [
        {"category": "wall_art", "box_px": [350, 250, 450, 350]},
        {"category": "ceiling_light", "box_px": [350, 0, 450, 100]}], np.zeros((600, 800, 3), dtype=np.uint8))
    wall, ceiling = result["detections"]
    assert wall["observation_point"] == pytest.approx([2, 1.2, 0])
    assert wall["position"] == pytest.approx([2, .85, 0])
    assert wall["wall_id"] == "w_1" and wall["mount"] == "wall"
    assert ceiling["observation_point"][1] == pytest.approx(2.6)
    assert ceiling["position"][1] + ceiling["size"][2] == pytest.approx(2.6)
    assert ceiling["mount"] == "ceiling"


def test_window_and_mirror_reflections_and_outside_floor_have_explicit_rejections():
    from respace.lifting import lift_keyframe

    room = calibrated_room()
    room["openings"].append({"id": "win", "wall_id": "w_1", "type": "window", "offset": 1.5,
                             "width": 1, "bottom": .8, "height": 1})
    detection = {"category": "wall_art", "box_px": [350, 250, 450, 350]}
    rgb = np.zeros((600, 800, 3), dtype=np.uint8)
    assert lift_keyframe(room, camera(), [detection], rgb)["rejected"][0]["reason"] == "opening_reflection"
    room["openings"] = []
    room["objects"].append({"id": "o_1", "category": "mirror", "center": [2, 0], "base_y": .5,
                            "size": [1, .04, 1.5], "yaw": 0, "wall_id": "w_1"})
    assert lift_keyframe(room, camera(), [detection], rgb)["rejected"][0]["reason"] == "mirror_reflection"
    outside = {"category": "floor_lamp", "box_px": [750, 290, 790, 310]}
    assert lift_keyframe(room, camera(), [outside], rgb)["rejected"][0]["reason"] == "outside_floor"


def test_depth_calibration_aspect_and_rgb_sensor_orientation_are_not_guessed():
    from respace.lifting import lift_keyframe

    rgb = np.zeros((600, 800, 3), dtype=np.uint8)
    frame = camera()
    frame["orientation"] = "portrait"
    with pytest.raises(ValueError, match="orientation"):
        lift_keyframe(calibrated_room(), frame, [], rgb)
    depth = decode_depth(bytes(4 * 4 * 4), None, 4, 4)
    with pytest.raises(ValueError, match="aspect"):
        lift_keyframe(calibrated_room(), camera(), [], rgb, depth)


def test_wall_depth_refinement_cannot_move_a_feature_beyond_the_mount_threshold():
    from respace.lifting import lift_keyframe

    depth = decode_depth(np.full((6, 8), 2.6, dtype="<f4").tobytes(), bytes([2] * 48), 8, 6)
    result = lift_keyframe(calibrated_room(), camera(), [
        {"category": "outlet", "box_px": [390, 290, 410, 310]}], np.zeros((600, 800, 3), dtype=np.uint8), depth)
    assert result["detections"][0]["method"] == "raycast"
    assert result["detections"][0]["depth_evidence"][0]["state"] == "outside_surface"


def test_calibrated_projection_overlay_matches_known_pixel_and_includes_native_corners():
    from respace.lifting import lift_keyframe, calibrated_overlay_svg, project_room_points

    room = calibrated_room()
    room["objects"].append({"id": "o_1", "category": "desk", "center": [2, 1], "base_y": 0,
                            "size": [1, .5, .75], "yaw": .3, "mount": "floor"})
    assert project_room_points(room, camera(), [[3.5, 0, .8], [2, 1.2, 4]]) == [
        pytest.approx([700, 540]), None]
    result = lift_keyframe(room, camera(), [
        {"category": "floor_lamp", "box_px": [675, 440, 725, 540]}], np.zeros((600, 800, 3), dtype=np.uint8))
    overlay = calibrated_overlay_svg(room, camera(), result)
    assert 'viewBox="0 0 800 600"' in overlay
    assert 'data-object="o_1"' in overlay and 'data-wall="w_1"' in overlay
    assert 'cx="700.000" cy="540.000"' in overlay


def test_rotated_camera_and_resized_intrinsics_roundtrip_within_one_centimeter():
    from respace.lifting import lift_keyframe

    frame = camera()
    frame["transform"] = [0,0,-1,0, 0,1,0,0, 1,0,0,0, 5,0,4.5,1]
    frame.update(w=400, h=300, intrinsics={"fx": 200, "fy": 200, "cx": 200, "cy": 150})
    result = lift_keyframe(calibrated_room(), frame, [
        {"category": "floor_lamp", "box_px": [290, 220, 310, 270]}], np.zeros((300, 400, 3), dtype=np.uint8))
    assert result["detections"][0]["position"] == pytest.approx([1, 0, .5], abs=.01)


def test_tabletop_depth_refinement_must_remain_on_the_observed_support():
    from respace.lifting import lift_keyframe

    room = calibrated_room()
    room["objects"].append({"id": "o_1", "category": "desk", "center": [2, 2.05], "base_y": 0,
                            "size": [.1, .1, .75], "yaw": 0, "mount": "floor"})
    depth = decode_depth(np.full((6, 8), .9, dtype="<f4").tobytes(), bytes([2] * 48), 8, 6)
    result = lift_keyframe(room, camera(), [{"category": "table_lamp", "box_px": [390, 460, 410, 540]}],
                           np.zeros((600, 800, 3), dtype=np.uint8), depth)
    assert result["detections"][0]["position"] == pytest.approx([2, .75, 2.05])
    assert result["detections"][0]["method"] == "raycast"


def test_versioned_stored_detection_outcomes_decode_lift_merge_and_replay_without_provider():
    from respace.lifting import lift_keyframe
    from respace.merging import merge

    fixture = json.loads((Path(__file__).parent / "fixtures/lifting/calibrated_observations_v1.json").read_text())
    room = normalize_room(fixture["raw_export"], fixture["capture_id"], fixture["room_id"])
    depth = decode_depth(bytes.fromhex(fixture["depth_hex"]), bytes.fromhex(fixture["confidence_hex"]), 8, 6)
    stored_lifts = [lift_keyframe(room, frame["meta"], frame["outcome"]["detections"],
                                np.zeros((600, 800, 3), dtype=np.uint8), depth) for frame in fixture["frames"]]
    floor_lamp, art, rug = stored_lifts[0]["detections"]
    assert floor_lamp["position"] == pytest.approx(fixture["expected_floor_lamp_position"], abs=.01)
    assert art["position"] == pytest.approx(fixture["expected_wall_art_position"], abs=.01)
    assert np.asarray(rug["floor_points"]) == pytest.approx(np.asarray(fixture["expected_rug_points"]), abs=.01)
    snapshot = merge(room, stored_lifts)
    assert [o["category"] for o in snapshot["objects"]] == fixture["expected_object_categories"]
    assert json.loads(json.dumps(snapshot)) == merge(room, json.loads(json.dumps(stored_lifts)), snapshot)
