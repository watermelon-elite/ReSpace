"""Immutable asset metadata and the shared category fallback rendering contract."""

from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re

from .categories import CATEGORY_VERSION, CATEGORIES
from .products import ProductError, canonical_url


ASSET_ROOT = Path(os.environ.get("RESPACE_ASSET_ROOT", Path(__file__).resolve().parents[2] / "assets"))


def manifest(revision: str | None = None) -> dict:
    if revision is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", revision):
        raise ProductError("invalid_manifest", "Manifest revision has an invalid format")
    path = ASSET_ROOT / "manifest.json"
    data: dict = json.loads(path.read_text()) if path.exists() else {
        "schema_version": 1, "manifest_revision": "registry-1", "category_version": CATEGORY_VERSION, "assets": []}
    if revision is not None and revision != data["manifest_revision"]:
        old = ASSET_ROOT / "manifests" / f"{revision}.json"
        if not old.is_file():
            raise ProductError("unknown_manifest", "Requested immutable asset manifest revision was not found")
        data = json.loads(old.read_text())
    data["categories"] = deepcopy(CATEGORIES)
    base = os.environ.get("PUBLIC_ASSET_BASE_URL")
    for asset in data["assets"]:
        validate_asset(asset)
        if base:
            asset["url"] = canonical_url(base.rstrip("/") + "/" + asset["path"])
        else:
            asset["url"] = "/v1/catalog/assets/" + asset["asset_id"] + "/" + asset["revision"]
    return data


def asset_path(asset_id: str, revision: str) -> Path:
    record = next((a for a in manifest()["assets"] if a["asset_id"] == asset_id and a["revision"] == revision), None)
    if record is None:
        for saved in sorted((ASSET_ROOT / 'manifests').glob('*.json')):
            record=next((a for a in manifest(saved.stem)['assets'] if a['asset_id']==asset_id and a['revision']==revision),None)
            if record is not None:break
    if not record:
        raise ProductError("unknown_asset", "Immutable render asset was not found")
    path = (ASSET_ROOT / record["path"]).resolve()
    if not path.is_relative_to(ASSET_ROOT.resolve()) or not path.is_file():
        raise ProductError("unknown_asset", "Render asset file was not found")
    if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
        raise ProductError("invalid_asset", "Render asset does not match its immutable revision")
    return path


def validate_asset(record: dict) -> dict:
    if record.get("category") not in CATEGORIES:
        raise ProductError("invalid_category", "Asset category must use the shared registry")
    if (record.get("units") != "meters" or record.get("pivot") != "bottom_center"
            or record.get("forward_axis") != "+Z" or record.get("up_axis") != "+Y"
            or record.get("scaling_mode") not in ("normalized", "dimensioned")):
        raise ProductError("invalid_asset", "Asset axes, pivot, units and scaling mode must be explicit")
    size = record.get("authored_bounds", [])
    if len(size) != 3 or any(not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in size):
        raise ProductError("invalid_asset", "Asset bounds must be finite positive width/depth/height")
    if record.get("kind") == "catalog" and (not record.get("variant_id") or not record.get("dimension_evidence_id")):
        raise ProductError("unverified_catalog_asset", "Catalog mesh appearance cannot substitute for exact-variant dimension evidence")
    return deepcopy(record)


def render_descriptor(category: str, variant_id: str | None = None) -> dict:
    if category not in CATEGORIES:
        raise ProductError("invalid_category", "Render category must use the shared registry")
    registry = CATEGORIES[category]
    candidates = manifest()["assets"]
    asset = next((a for a in candidates if variant_id and a.get("variant_id") == variant_id and a["kind"] == "catalog"), None)
    if asset is None:
        asset = next((a for a in candidates if a["category"] == category and a["kind"] == "standin"), None)
    return {"kind": asset["kind"] if asset else "standin", "category": category,
            "asset_id": asset["asset_id"] if asset else registry["standin"],
            "asset_revision": asset["revision"] if asset else str(CATEGORY_VERSION),
            "asset_url": asset["url"] if asset else None, "sha256":asset.get('sha256') if asset else None,"byte_count":asset.get('byte_count') if asset else None,"tint": registry["default_tint"], "texture_url": None,
            "authored_bounds": asset["authored_bounds"] if asset else [1, 1, 1], "units": "meters",
            "scaling_mode": asset["scaling_mode"] if asset else "normalized", "pivot": "bottom_center",
            "forward_axis": "+Z", "up_axis": "+Y"}
