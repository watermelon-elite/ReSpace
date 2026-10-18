import math
from copy import deepcopy

import pytest

from respace.reconstruction import room_from_reconstruction
from respace.solver import solve
from test_reconstruction import add, chair, reconstruction

pxr = pytest.importorskip("pxr")
from pxr import Gf, Usd, UsdGeom  # noqa: E402

from respace.composition import CompositionError, compose  # noqa: E402


def write_room(path, room, shift=(0, 0, 0)):
    """A room model whose nodes sit where its record says, pivoted at the box centre.

    `shift` moves the root and moves every node back by the same amount, as a model
    authored in scan coordinates under a root that applies room_from_world does.
    """
    stage = Usd.Stage.CreateNew(str(path))
    root = UsdGeom.Xform.Define(stage, "/Room")
    root.AddTranslateOp().Set(Gf.Vec3d(*shift))
    stage.SetDefaultPrim(root.GetPrim())
    for record in [*room["objects"], *room["obstacles"]]:
        node = room["render"]["nodes"][record["id"]]
        xform = UsdGeom.Xform.Define(stage, f"/Room/{node}")
        w, d, h = record["size"]
        xform.AddTranslateOp().Set(Gf.Vec3d(record["center"][0] - shift[0], record["base_y"] + h / 2 - shift[1],
                                            record["center"][1] - shift[2]))
        xform.AddRotateYOp().Set(math.degrees(record["yaw"]))
        cube = UsdGeom.Cube.Define(stage, f"/Room/{node}/Mesh")
        cube.AddScaleOp().Set(Gf.Vec3f(w / 2, h / 2, d / 2))
    stage.GetRootLayer().Save()
    return path


def write_product(path):
    """A bottom-centre, +Z-forward asset with a marker on its front."""
    stage = Usd.Stage.CreateNew(str(path))
    root = UsdGeom.Xform.Define(stage, "/Product")
    stage.SetDefaultPrim(root.GetPrim())
    front = UsdGeom.Cube.Define(stage, "/Product/Front")
    front.AddTranslateOp().Set(Gf.Vec3d(0, .5, .2))
    front.AddScaleOp().Set(Gf.Vec3f(.05, .05, .05))
    stage.GetRootLayer().Save()
    return path


def world(stage, path):
    return UsdGeom.XformCache().GetLocalToWorldTransform(stage.GetPrimAtPath(path))


@pytest.fixture(params=[(0, 0, 0), (.82, 1.54, 4.59)], ids=["room_frame_root", "shifted_root"])
def kitchen(tmp_path, request):
    room = room_from_reconstruction(reconstruction(), "room")
    room["render"]["nodes"] = {k: v for k, v in room["render"]["nodes"].items() if not k.startswith("w_")}
    return room, write_room(tmp_path / "room.usda", room, request.param), write_product(tmp_path / "chair.usda")


def test_record_node_names_match_the_names_usd_gives_them(kitchen, tmp_path):
    room, room_file, product = kitchen
    # USD prim names cannot hold hyphens; exporters write "scan-counter", USD stores "scan_counter".
    room["render"]["nodes"]["o_1"] = "scan-counter"
    scene = solve(room, {"adds": []}, {}, {"intent": "add"})["scene"]
    next(i for i in scene["items"] if i["object_id"] == "o_1")["status"] = "removed"
    report = compose(room_file, room, scene, tmp_path / "out.usdz", resolve=lambda render: product)
    assert report["hidden"] == ["i_o_1"]


def test_new_items_are_referenced_at_their_placement_facing_their_yaw(kitchen, tmp_path):
    room, room_file, product = kitchen
    # The east wall faces -X, so a sign error in yaw would turn the chair to face the wall.
    result = solve(room, add({"type": "against_wall", "wall_id": "w_2", "alignment": "center"}),
                   {"sel": chair()}, {"intent": "add"})
    assert result["scene"]["items"][-1]["placement"]["yaw"] == pytest.approx(-math.pi / 2)
    report = compose(room_file, room, result["scene"], tmp_path / "out.usdz", resolve=lambda render: product)
    assert report == {"inserted": [{"item_id": "i_a_0", "drawn_as": "catalog"}], "moved": [], "hidden": [], "warnings": []}
    stage = Usd.Stage.Open(str(tmp_path / "out.usdz"))
    placement = result["scene"]["items"][-1]["placement"]
    assert list(world(stage, "/Room/ReSpace/i_a_0").ExtractTranslation()) == pytest.approx(placement["position"])
    # The marker on the asset's +Z front lands in front of the item, facing into the room.
    front = world(stage, "/Room/ReSpace/i_a_0/Front").ExtractTranslation()
    forward = [math.sin(placement["yaw"]), math.cos(placement["yaw"])]
    assert [front[0] - placement["position"][0], front[2] - placement["position"][2]] == pytest.approx([.2 * v for v in forward])
    assert stage.GetPrimAtPath("/Room/scan_counter").IsActive()


def test_moved_and_removed_objects_change_their_room_nodes(kitchen, tmp_path):
    room, room_file, product = kitchen
    scene = solve(room, {"adds": []}, {}, {"intent": "add"})["scene"]
    fridge = next(i for i in scene["items"] if i["object_id"] == "o_2")
    fridge["placement"] = {**deepcopy(fridge["placement"]), "position": [3, 0, 1.5], "yaw": 0}
    fridge["status"] = "moved"
    next(i for i in scene["items"] if i["object_id"] == "o_1")["status"] = "removed"
    report = compose(room_file, room, scene, tmp_path / "out.usdz", resolve=lambda render: product)
    assert (report["moved"], report["hidden"]) == (["i_o_2"], ["i_o_1"])
    stage = Usd.Stage.Open(str(tmp_path / "out.usdz"))
    moved = world(stage, "/Room/scan_fridge")
    assert list(moved.ExtractTranslation()) == pytest.approx([3, .9, 1.5])
    assert moved.TransformDir(Gf.Vec3d(0, 0, 1)) == pytest.approx(Gf.Vec3d(0, 0, 1))
    assert not stage.GetPrimAtPath("/Room/scan_counter").IsValid() or not stage.GetPrimAtPath("/Room/scan_counter").IsActive()


def test_missing_asset_is_drawn_as_a_sized_box(kitchen, tmp_path):
    room, room_file, _ = kitchen
    result = solve(room, add({"type": "against_wall", "wall_id": "w_1", "alignment": "center"}),
                   {"sel": chair()}, {"intent": "add"})
    report = compose(room_file, room, result["scene"], tmp_path / "out.usdz", resolve=lambda render: None)
    assert report["inserted"] == [{"item_id": "i_a_0", "drawn_as": "box"}]
    stage = Usd.Stage.Open(str(tmp_path / "out.usdz"))
    bounds = UsdGeom.Imageable(stage.GetPrimAtPath("/Room/ReSpace/i_a_0")).ComputeWorldBound(0, "default").ComputeAlignedRange()
    assert list(bounds.GetSize()) == pytest.approx([.45, .76, .5])


def test_a_record_that_disagrees_with_its_model_is_refused(kitchen, tmp_path):
    room, room_file, product = kitchen
    room["objects"][1]["center"] = [.35, 2.7]  # 5 cm from where the model has it
    scene = solve(room, {"adds": []}, {}, {"intent": "add"})["scene"]
    with pytest.raises(CompositionError) as error:
        compose(room_file, room, scene, tmp_path / "out.usdz", resolve=lambda render: product)
    assert [(p["id"], p["code"]) for p in error.value.problems] == [("o_2", "pose_mismatch")]
