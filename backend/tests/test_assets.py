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


def test_offline_glb_to_usdz_reopens_exact_bounds_and_keeps_asymmetry(tmp_path):
    pytest.importorskip("trimesh")
    pytest.importorskip("pxr")
    script = Path(__file__).resolve().parents[2] / "assets" / "prepare.py"
    specification = importlib.util.spec_from_file_location("prepare", script)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    record = module.convert(script.parent / "sources" / "kenney" / "chair.glb", tmp_path / "chair.usdz", "chair")
    assert record["conversion"]["physical_bounds_reopened"] == pytest.approx([1, 1, 1])
    from pxr import Usd, UsdGeom
    stage = Usd.Stage.Open(str(tmp_path / "chair.usdz"))
    points = [p for prim in stage.Traverse() if prim.IsA(UsdGeom.Mesh) for p in UsdGeom.Mesh(prim).GetPointsAttr().Get()]
    back = [p for p in points if p[1] > .8]
    assert sum(p[2] for p in back) / len(back) < 0, "Asymmetric chair back must face away from +Z front"
