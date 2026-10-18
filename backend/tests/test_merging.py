from copy import deepcopy

import pytest

from test_lifting import calibrated_room
from respace.merging import merge


def observation(frame, position=(1, 0, 1), category="plant", **changes):
    return {"id": f"det:{frame}:0", "frame_id": frame, "idx": int(frame[-1]), "category": category,
            "position": list(position), "observation_point": list(position), "size": [.4, .4, .7],
            "mount": "floor", "wall_id": None, "support_id": None, "yaw": 0,
            "floor_points": [], "method": "raycast", **changes}


def lifts(*detections):
    return [{"schema_version": 1, "capture_id": "capture", "frame_id": d["frame_id"],
             "input_revision": 1, "idx": d["idx"], "state": "succeeded", "detections": [d],
             "color_samples": [], "rejected": []} for d in detections]


def test_multiview_merge_clusters_with_counts_and_replays_without_mutating_inputs():
    room = calibrated_room()
    inputs = lifts(observation("f0"), observation("f1", (1.2, 0, 1)))
    before = deepcopy((room, inputs))
    merged = merge(room, inputs)
    obj = merged["objects"][0]
    assert obj["center"] == pytest.approx([1.1, 1])
    assert obj["id"] == "o_1" and obj["observation_count"] == 2
    assert merged["identity_map"]["det:f0:0"] == {"kind": "object", "id": "o_1"}
    assert merged["processing"]["completed"] == 2
    assert merge(room, list(reversed(inputs)), merged) == merged
    assert (room, inputs) == before


@pytest.mark.parametrize("distance,count", [(.4, 1), (.4001, 0)])
def test_object_clustering_threshold_and_two_view_requirement(distance, count):
    result = merge(calibrated_room(), lifts(observation("f0"), observation("f1", (1 + distance, 0, 1))))
    assert len(result["objects"]) == count
    if not count:
        assert all(w["code"] == "insufficient_observations" for w in result["validity"]["warnings"])


def test_mount_relationships_prevent_merging_stacked_objects_or_counting_one_view_twice():
    first = observation("f0")
    duplicate = {**first, "id": "det:f0:1"}
    input_lifts = lifts(first)
    input_lifts[0]["detections"].append(duplicate)
    assert merge(calibrated_room(), input_lifts)["objects"] == []
    supported = observation("f1", (1, .1, 1), mount="tabletop", support_id="o_1")
    assert merge(calibrated_room(), lifts(first, supported))["objects"] == []


def test_wall_feature_clusters_snap_to_real_wall_with_center_height_and_tighter_threshold():
    changes = {"category": "outlet", "mount": "wall", "wall_id": "w_1"}
    result = merge(calibrated_room(), lifts(observation("f0", (1, .4, .1), **changes),
                                           observation("f1", (1.2, .4, .1), **changes)))
    feature = result["wall_features"][0]
    assert feature["wall_id"] == "w_1" and feature["offset"] == pytest.approx(1.1)
    assert feature["height"] == pytest.approx(.4) and feature["observation_count"] == 2
    beyond = merge(calibrated_room(), lifts(observation("f0", (1, .4, .1), **changes),
                                            observation("f1", (1.2001, .4, .1), **changes)))
    assert beyond["wall_features"] == []
    no_wall = merge(calibrated_room(), lifts(observation("f0", (1, .4, .1501), **changes),
                                             observation("f1", (1.1, .4, .1501), **changes)))
    assert no_wall["wall_features"] == []
    assert no_wall["validity"]["warnings"][0]["code"] == "feature_without_wall"


def test_single_rug_observation_fits_rotated_rectangle_and_wall_art_survives_one_view():
    rug = observation("f0", category="rug", floor_points=[[1, 1], [2, 2], [1.5, 2.5], [.5, 1.5]])
    art = observation("f1", (2, 1, 0), category="wall_art", mount="wall", wall_id="w_1")
    result = merge(calibrated_room(), lifts(rug, art))
    rug_obj = next(o for o in result["objects"] if o["category"] == "rug")
    assert rug_obj["center"] == pytest.approx([1.25, 1.75])
    assert rug_obj["size"] == pytest.approx([2 ** .5, .5 ** .5, .02])
    assert rug_obj["yaw"] == pytest.approx(3 * 3.141592653589793 / 4)
    assert len(result["objects"]) == 2


def test_native_absorption_refines_without_duplicate_and_preserves_old_planning_alias():
    room = calibrated_room()
    old = merge(room, lifts(observation("f0"), observation("f1")))
    room["objects"].append({"id": "o_7", "category": "plant", "source": "roomplan", "center": [1, 1],
        "size": [.4, .4, .7], "base_y": 0, "yaw": 0, "mount": "floor", "wall_id": None, "support_id": None,
        "source_ids": ["native-plant"], "observation_count": 0, "attrs": {}, "fixed_in_place": False})
    room["identity_map"]["native-plant"] = {"kind": "object", "id": "o_7"}
    refined = merge(room, lifts(observation("f0"), observation("f1")), old)
    assert len(refined["objects"]) == 1 and refined["objects"][0]["id"] == "o_7"
    assert refined["objects"][0]["source"] == "refined"
    assert refined["identity_map"]["o_1"] == {"kind": "object", "id": "o_7"}
    assert refined["identity_map"]["native-plant"] == {"kind": "object", "id": "o_7"}


def test_disappearing_identity_stays_explicit_and_number_is_never_recycled_across_reprocessing():
    room = calibrated_room()
    first = merge(room, lifts(observation("f0"), observation("f1")))
    absent = merge(room, [], first)
    assert absent["identity_map"]["o_1"]["kind"] == "unresolved_object"
    assert absent["identity_map"]["det:f0:0"]["kind"] == "unresolved_object"
    another = merge(room, lifts(observation("f2", (2, 0, 2)), observation("f3", (2, 0, 2))), absent)
    assert another["objects"][0]["id"] == "o_2"
    assert another["identity_map"]["o_1"]["kind"] == "unresolved_object"
    assert another["identity_map"]["det:f0:0"]["kind"] == "unresolved_object"


def test_merge_rejects_mixed_capture_revision_and_duplicate_frame_replay():
    room = calibrated_room()
    first = lifts(observation("f0"), observation("f1"))
    first[1]["input_revision"] = 2
    with pytest.raises(ValueError, match="revision"):
        merge(room, first)
    first[1]["input_revision"] = 1
    first[1]["capture_id"] = "other"
    with pytest.raises(ValueError, match="capture"):
        merge(room, first)
    with pytest.raises(ValueError, match="twice"):
        merge(room, first[:1] * 2)


def test_changed_detection_frames_reuse_identity_and_keep_old_observation_aliases():
    room = calibrated_room()
    first = merge(room, lifts(observation("f0"), observation("f1")))
    changed = merge(room, lifts(observation("f2", (1.1, 0, 1)), observation("f3", (1.1, 0, 1))), first)
    assert changed["objects"][0]["id"] == "o_1"
    assert changed["identity_map"]["det:f0:0"] == {"kind": "object", "id": "o_1"}


def test_failed_detection_frame_is_terminal_and_does_not_become_a_successful_empty_lift():
    failed = {"schema_version": 1, "capture_id": "capture", "frame_id": "f0", "input_revision": 1,
              "idx": 0, "state": "failed", "detections": [], "failure": {"code": "timeout"}}
    result = merge(calibrated_room(), [failed])
    assert result["processing"] == {"expected_frames": 1, "not_started": 0, "pending": 0,
                                     "succeeded": 0, "failed": 1, "lifted": 0, "completed": 0}
