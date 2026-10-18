"""Compose a modelled room and a solved Scene into one preview USDZ.

The room is the reconstruction's own USDZ, read with its version 2 record
(`reconstruction.room_from_reconstruction`). The Scene is the solver's. New
Items are referenced in at their placements, moved Objects have their nodes
moved, and removed or replaced Objects have their nodes deactivated. Nothing
is re-measured here: placement is the solver's job, and this only draws it.

Needs usd-core, which the API image does not install by default:
`pip install './backend[usd]'`.
"""

import math
from pathlib import Path
import tempfile
import zipfile

import numpy as np

from .assets import asset_path
from .products import ProductError
from .reconstruction import TOLERANCE as CONTACT_TOLERANCE

# How closely a USD node must match its record before its pose is trusted (proposal: 1 cm, 1 degree).
POSITION_TOLERANCE = .01
YAW_TOLERANCE = math.radians(1)


class CompositionError(ValueError):
    def __init__(self, message, problems=()):
        super().__init__(message)
        self.problems = list(problems)


def catalog_asset(render):
    """Default resolver: the immutable catalog or stand-in asset a render descriptor names."""
    try:
        return asset_path(render["asset_id"], render["asset_revision"])
    except (KeyError, ProductError):
        return None


def _unpack(package, target):
    """Extract a USDZ so flattening finds its textures as plain files; nested packages lose them."""
    package = Path(package)
    if package.suffix != ".usdz":
        return package
    with zipfile.ZipFile(package) as archive:
        archive.extractall(target)
        root = next(n for n in archive.namelist() if n.endswith((".usdc", ".usda", ".usd")))
    return Path(target) / root


def _pose(position, yaw):
    """Row-vector USD matrix for a bottom-centre pose: rotate about +Y, then translate."""
    from pxr import Gf

    rotate = Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(0, 1, 0), math.degrees(yaw)))
    return rotate * Gf.Matrix4d().SetTranslate(Gf.Vec3d(*position))


def _yaw(matrix):
    # Row 2 of a USD matrix is the node's local +Z, its front, in the parent frame.
    return math.atan2(matrix[2][0], matrix[2][2])


def _nodes(stage):
    from pxr import Usd

    root = stage.GetDefaultPrim()
    return {prim.GetName(): prim for prim in Usd.PrimRange(root) if prim != root} if root else {}


def _node(nodes, name):
    """A record's node by exact name, else by the name USD gives it (hyphens become underscores)."""
    from pxr import Tf

    return nodes.get(name) or nodes.get(Tf.MakeValidIdentifier(name))


def node_disagreements(stage, room):
    """Records whose USD node is missing or posed differently from the record."""
    from pxr import UsdGeom

    nodes, cache, problems = _nodes(stage), UsdGeom.XformCache(), []
    raise_by = .5 if room["render"]["node_pivot"] == "box_center" else 0
    records = {e["id"]: e for e in [*room["objects"], *room.get("obstacles", [])]}
    for record_id, name in sorted(room["render"]["nodes"].items()):
        prim = _node(nodes, name)
        if prim is None:
            problems.append({"id": record_id, "node_name": name, "code": "missing_node"})
            continue
        record = records.get(record_id)
        if record is None:
            continue
        world = cache.GetLocalToWorldTransform(prim)
        origin = np.asarray(world.ExtractTranslation())
        expected = np.array([record["center"][0], record["base_y"] + raise_by * record["size"][2], record["center"][1]])
        turn = abs(math.remainder(_yaw(world) - record["yaw"], 2 * math.pi))
        # The reader snaps floor, ceiling and tabletop contact by up to its own tolerance.
        if (np.linalg.norm((origin - expected)[[0, 2]]) > POSITION_TOLERANCE or turn > YAW_TOLERANCE
                or abs(origin[1] - expected[1]) > POSITION_TOLERANCE + CONTACT_TOLERANCE):
            problems.append({"id": record_id, "node_name": name, "code": "pose_mismatch",
                             "offset_m": round(float(np.linalg.norm(origin - expected)), 4),
                             "turn_deg": round(math.degrees(turn), 2)})
    return problems


def compose(room_usdz, room, scene, destination, *, resolve=catalog_asset):
    """Write `destination` (.usdz) and return what was inserted, moved and hidden.

    `resolve(render)` returns a local asset path or None; None draws a labelled
    box of the placement's size, the last step of SPEC 11.1's fallback order.
    """
    from pxr import Gf, Sdf, Tf, Usd, UsdGeom, UsdUtils

    if not room.get("validity", {}).get("usable") or not room.get("render", {}).get("node_pivot"):
        raise CompositionError("Composition needs a usable room read from a reconstruction record.")
    report: dict[str, list] = {"inserted": [], "moved": [], "hidden": [], "warnings": []}
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        source = Usd.Stage.Open(str(_unpack(room_usdz, work / "room")))
        problems = node_disagreements(source, room)
        if problems:
            raise CompositionError("Room record and room model disagree.", problems)
        root = source.GetDefaultPrim()
        stage = Usd.Stage.CreateNew(str(work / "preview.usda"))
        UsdGeom.SetStageMetersPerUnit(stage, 1)
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
        # Same root name, so every room node keeps its path in the composed stage.
        top = stage.DefinePrim(root.GetPath(), "Xform")
        top.GetReferences().AddReference(source.GetRootLayer().identifier)
        stage.SetDefaultPrim(top)
        cache = UsdGeom.XformCache()
        items_root = top.GetPath().AppendChild("ReSpace")
        # Placements are room-frame coordinates, which node_disagreements matched against
        # world space; undo whatever transform the model's root carries.
        UsdGeom.Xform.Define(stage, items_root).AddTransformOp().Set(cache.GetLocalToWorldTransform(top).GetInverse())
        nodes = {name: stage.GetPrimAtPath(prim.GetPath()) for name, prim in _nodes(source).items()}

        def node(item):
            name = room["render"]["nodes"].get(item.get("object_id"))
            return _node(nodes, name) if name else None

        for item in scene["items"]:
            placement, existing = item.get("placement"), item.get("origin") == "existing"
            replaced = existing and item.get("replacement_of_object_id")
            if existing and (item.get("status") == "removed" or replaced):
                prim = node(item)
                if prim is None:
                    report["warnings"].append({"item_id": item["id"], "code": "missing_node"})
                else:
                    prim.SetActive(False)
                    report["hidden"].append(item["id"])
            if item.get("status") == "removed":
                continue
            if existing and not replaced:
                original = item.get("original_placement")
                if placement == original:
                    continue
                prim = node(item)
                if prim is None:
                    report["warnings"].append({"item_id": item["id"], "code": "missing_node"})
                    continue
                # Move the node by the same rigid change the solver made, whatever its pivot.
                change = _pose(original["position"], original["yaw"]).GetInverse() * _pose(placement["position"], placement["yaw"])
                parent = cache.GetLocalToWorldTransform(prim.GetParent())
                local = cache.GetLocalToWorldTransform(prim) * change * parent.GetInverse()
                xformable = UsdGeom.Xformable(prim)
                xformable.ClearXformOpOrder()
                xformable.AddTransformOp().Set(local)
                report["moved"].append(item["id"])
                continue

            w, d, h = placement["size"]
            xform = UsdGeom.Xform.Define(stage, items_root.AppendChild(Tf.MakeValidIdentifier(item["id"])))
            xform.AddTranslateOp().Set(Gf.Vec3d(*placement["position"]))
            xform.AddRotateYOp().Set(math.degrees(placement["yaw"]))  # SPEC yaw is radians, USD degrees
            prim = xform.GetPrim()
            prim.SetCustomDataByKey("respace:item_id", item["id"])
            render = item.get("render") or {}
            path = resolve(render) if render.get("asset_id") else None
            if path is None:
                cube = UsdGeom.Cube.Define(stage, prim.GetPath().AppendChild("Box"))
                cube.AddTranslateOp().Set(Gf.Vec3d(0, h / 2, 0))
                cube.AddScaleOp().Set(Gf.Vec3f(w, h, d))
                cube.CreateSizeAttr(1)
                tint = render.get("tint", "#B9ADA0").lstrip("#")
                cube.CreateDisplayColorAttr([Gf.Vec3f(*(int(tint[i:i + 2], 16) / 255 for i in (0, 2, 4)))])
                report["inserted"].append({"item_id": item["id"], "drawn_as": "box"})
                continue
            bounds = render.get("authored_bounds") or [w, d, h]
            if render.get("scaling_mode") == "normalized":
                xform.AddScaleOp().Set(Gf.Vec3f(w / bounds[0], h / bounds[2], d / bounds[1]))
            elif max(abs(a - b) for a, b in zip(bounds, (w, d, h))) > POSITION_TOLERANCE:
                # A dimensioned asset is never scaled twice (SPEC 11.1); say so instead.
                report["warnings"].append({"item_id": item["id"], "code": "asset_size_mismatch",
                                           "asset_size": bounds, "placement_size": [w, d, h]})
            prim.SetCustomDataByKey("respace:asset_id", render["asset_id"])
            prim.SetCustomDataByKey("respace:asset_revision", render.get("asset_revision", ""))
            prim.GetReferences().AddReference(str(_unpack(path, work / "assets" / Tf.MakeValidIdentifier(item["id"]))))
            report["inserted"].append({"item_id": item["id"], "drawn_as": render.get("kind", "asset")})

        stage.GetRootLayer().Save()
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not UsdUtils.CreateNewARKitUsdzPackage(Sdf.AssetPath(stage.GetRootLayer().identifier), str(destination)):
            raise CompositionError("USDZ packaging failed.")
    return report
