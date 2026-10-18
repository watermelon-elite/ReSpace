import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from respace.assets import asset_path, manifest, render_descriptor, validate_asset
from respace.products import ProductError


def test_manifest_delivers_immutable_asset_with_correct_conventions():
    data = manifest()
    asset = data["assets"][0]
    path = asset_path(asset["asset_id"], asset["revision"])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == asset["sha256"]
    assert asset["byte_count"] < 3_000_000
    assert asset["category"] in data["categories"]
    descriptor = render_descriptor(asset["category"])
    assert descriptor["pivot"] == "bottom_center" and descriptor["forward_axis"] == "+Z"
    assert descriptor["scaling_mode"] == "normalized"
    assert descriptor["asset_url"].endswith(asset["revision"])
    with pytest.raises(ProductError):
        manifest("../../private")
    with pytest.raises(ProductError):
        asset_path(asset["asset_id"], "changed")


def test_catalog_mesh_cannot_establish_purchase_dimensions():
    record = {**manifest()["assets"][0], "kind": "catalog", "variant_id": None}
    with pytest.raises(ProductError, match="dimension evidence"):
        validate_asset(record)


def test_expanded_standins_use_licensed_sources_and_keep_the_original_revision():
    data = manifest()
    required = {"sofa", "armchair", "chair", "stool", "table", "dining_table", "coffee_table",
                "side_table", "desk", "nightstand", "cabinet", "shelf", "tv_stand", "bed", "tv",
                "floor_lamp", "table_lamp", "plant", "mirror", "rug", "ceiling_light"}
    assert {record["category"] for record in data["assets"]} == required
    root = Path(__file__).resolve().parents[2] / "assets"
    for record in data["assets"]:
        assert record["kind"] == "standin" and record["license"] == "CC0-1.0"
        assert record["variant_id"] is None and record["dimension_evidence_id"] is None
        path = asset_path(record["asset_id"], record["revision"])
        assert path.stat().st_size == record["byte_count"] < 3_000_000
        source = root / record.get("source_path", "sources/kenney/chair.glb")
        assert hashlib.sha256(source.read_bytes()).hexdigest() == record["source_sha256"]
        descriptor = render_descriptor(record["category"])
        assert descriptor["asset_id"] == record["asset_id"]
        assert descriptor["authored_bounds"] == [1, 1, 1]
    original = manifest("kenney-chair-67d8cb9ab6c620bb")["assets"][0]
    assert original == data["assets"][0]
    assert asset_path(original["asset_id"], original["revision"]).is_file()


def test_saved_asset_revision_remains_available_after_manifest_update(tmp_path,monkeypatch):
    from respace import assets
    prior=manifest();record=prior['assets'][0]
    target=tmp_path/record['path'];target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(asset_path(record['asset_id'],record['revision']).read_bytes())
    (tmp_path/'manifests').mkdir();(tmp_path/'manifests'/f"{prior['manifest_revision']}.json").write_text(json.dumps(prior))
    (tmp_path/'manifest.json').write_text(json.dumps({**prior,'manifest_revision':'new','assets':[]}))
    monkeypatch.setattr(assets,'ASSET_ROOT',tmp_path)
    assert assets.asset_path(record['asset_id'],record['revision'])==target
    assert assets.manifest(prior['manifest_revision'])['assets'][0]['revision']==record['revision']


@pytest.fixture
def converter():
    pytest.importorskip("trimesh")
    pytest.importorskip("pxr")
    script = Path(__file__).resolve().parents[2] / "assets" / "prepare.py"
    specification = importlib.util.spec_from_file_location("prepare", script)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_offline_glb_to_usdz_reopens_exact_bounds_and_keeps_asymmetry(tmp_path, converter):
    source = Path(__file__).resolve().parents[2] / "assets/sources/kenney/chair.glb"
    record = converter.convert(source, tmp_path / "chair.usdz", "chair")
    assert record["conversion"]["physical_bounds_reopened"] == pytest.approx([1, 1, 1])
    from pxr import Usd, UsdGeom
    stage = Usd.Stage.Open(str(tmp_path / "chair.usdz"))
    points = [p for prim in stage.Traverse() if prim.IsA(UsdGeom.Mesh) for p in UsdGeom.Mesh(prim).GetPointsAttr().Get()]
    back = [p for p in points if p[1] > .8]
    assert sum(p[2] for p in back) / len(back) < 0, "Asymmetric chair back must face away from +Z front"


@pytest.mark.parametrize("arguments", [
    {"dimensions": [0.7, 0.3, 1.1]},
    {"variant_id": "test_variant"},
    {"evidence_id": "test_dimensions"},
    {"variant_id": "test_variant", "evidence_id": "test_dimensions"},
    {"dimensions": [0.7, 0.3, 1.1], "variant_id": "test_variant"},
    {"dimensions": [0.7, 0.3, 1.1], "evidence_id": "test_dimensions"},
])
def test_catalog_conversion_requires_dimensions_variant_and_evidence(tmp_path, converter, arguments):
    with pytest.raises(ValueError, match="exact-variant dimension evidence"):
        converter.convert(tmp_path / "unused.glb", tmp_path / "unused.usdz", "chair", **arguments)
    assert not (tmp_path / "unused.usdz").exists()


def _reconstruction(path, parts, yaw, pitch, roll=0):
    """A GLB posed the way SPAR3D leaves a product: front toward the camera at -Z,
    turned by a three-quarter photograph, tipped by the camera looking down and
    leaning slightly sideways."""
    import numpy as np
    import trimesh
    mesh = trimesh.util.concatenate(parts)
    mesh.apply_transform(trimesh.transformations.rotation_matrix(np.radians(yaw), [0, 1, 0]))
    mesh.apply_transform(trimesh.transformations.rotation_matrix(np.radians(roll), [0, 0, 1]))
    mesh.apply_transform(trimesh.transformations.rotation_matrix(np.radians(pitch), [1, 0, 0]))
    mesh.export(path)
    return path


def _chair(path, yaw=20, pitch=-20, roll=4):
    import trimesh
    box = lambda size, centre: trimesh.creation.box(size, trimesh.transformations.translation_matrix(centre))
    legs = [box([.04, .45, .04], [x, .225, z]) for x in (-.2, .2) for z in (-.22, .22)]
    seat = box([.45, .04, .5], [0, .47, 0])
    back = box([.45, .4, .04], [0, .69, .23])  # backrest away from the camera: front is -Z
    return _reconstruction(path, [*legs, seat, back], yaw, pitch, roll)


def _points(path):
    import numpy as np
    from pxr import Usd, UsdGeom
    stage = Usd.Stage.Open(str(path))
    return np.array([p for prim in stage.Traverse() if prim.IsA(UsdGeom.Mesh)
                     for p in UsdGeom.Mesh(prim).GetPointsAttr().Get()])


def test_auto_orient_stands_a_tipped_turned_reconstruction_on_its_feet_facing_forward(tmp_path, converter):
    pytest.importorskip("scipy")
    import numpy as np
    source = _chair(tmp_path / "chair.glb")
    arguments = {"dimensions": [0.45, 0.5, 0.8], "variant_id": "test_variant", "evidence_id": "test_dimensions"}
    record = converter.convert(source, tmp_path / "chair.usdz", "chair", auto_orient=True, **arguments)
    assert record["source_pitch_degrees"] == pytest.approx(20, abs=1)
    assert abs(record["source_roll_degrees"]) == pytest.approx(4, abs=1)
    assert record["orientation"]["level_method"] == "resting_face"
    assert record["orientation"]["flags"] == []
    points = _points(tmp_path / "chair.usdz")
    feet = points[points[:, 1] < 0.01]
    quadrants = {(x > 0, z > 0) for x, _, z in feet}
    assert quadrants == {(False, False), (False, True), (True, False), (True, True)}, "all four feet on the floor"
    back = points[points[:, 1] > 0.6]
    assert back[:, 2].mean() < 0, "backrest behind the seat, so the front faces +Z"
    assert np.ptp(back[:, 2]) < 0.08, "backrest square to the axes, not still turned by the photograph"


def test_auto_orient_leaves_a_round_footprint_unturned_and_levels_lamps_by_their_base(tmp_path, converter):
    pytest.importorskip("scipy")
    import trimesh
    base = trimesh.creation.cylinder(.12, .02, sections=48)
    base.apply_translation([0, 0, 0])
    base.apply_transform(trimesh.transformations.rotation_matrix(-1.5708, [1, 0, 0]))
    pole = trimesh.creation.cylinder(.01, .5, sections=16)
    pole.apply_transform(trimesh.transformations.rotation_matrix(-1.5708, [1, 0, 0]))
    pole.apply_translation([0, .25, 0])
    shade = trimesh.creation.cone(.15, .2, sections=48)
    shade.apply_transform(trimesh.transformations.rotation_matrix(-1.5708, [1, 0, 0]))
    shade.apply_translation([0, .45, 0])
    source = _reconstruction(tmp_path / "lamp.glb", [base, pole, shade], yaw=30, pitch=-10)
    record = converter.convert(source, tmp_path / "lamp.usdz", "table_lamp", auto_orient=True)
    assert record["orientation"]["level_method"] == "base_plane"
    assert record["source_pitch_degrees"] == pytest.approx(10, abs=1.5)
    assert record["orientation"]["straighten_degrees"] == 0
    assert record["orientation"]["straighten_reason"] == "round footprint"


def test_auto_orient_flags_a_footprint_turned_too_close_to_45_degrees(tmp_path, converter):
    pytest.importorskip("scipy")
    source = _chair(tmp_path / "chair.glb", yaw=43, pitch=0, roll=0)
    record = converter.convert(source, tmp_path / "chair.usdz", "chair", auto_orient=True)
    assert any("45" in flag for flag in record["orientation"]["flags"])


def test_auto_orient_refuses_manual_angles_as_well(tmp_path, converter):
    for manual in ({"yaw": 90}, {"pitch": 5}, {"roll": 2}):
        with pytest.raises(ValueError, match="auto_orient"):
            converter.convert(tmp_path / "unused.glb", tmp_path / "unused.usdz", "chair", auto_orient=True, **manual)


def test_dimensioned_conversion_reopens_supplied_bounds(tmp_path, converter):
    source = Path(__file__).resolve().parents[2] / "assets/sources/kenney/chair.glb"
    arguments = {"dimensions": [0.7, 0.3, 1.1], "variant_id": "test_variant", "evidence_id": "test_dimensions"}
    record = converter.convert(source, tmp_path / "dimensioned.usdz", "chair", **arguments)
    assert record["kind"] == "catalog" and record["scaling_mode"] == "dimensioned"
    assert record["authored_bounds"] == arguments["dimensions"]
    assert record["conversion"]["physical_bounds_reopened"] == pytest.approx(arguments["dimensions"])
    assert validate_asset(record)["dimension_evidence_id"] == "test_dimensions"
    with pytest.raises(ValueError, match="positive finite"):
        converter.convert(source, tmp_path / "empty.usdz", "chair", **{**arguments, "dimensions": []})
