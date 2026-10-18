"""Offline GLB/OBJ -> normalized or dimensioned USDZ. Requires trimesh and usd-core.

Usage: python assets/prepare.py input.glb output.usdz --category chair --yaw 180
Catalog: add --dimensions WIDTH DEPTH HEIGHT --variant-id ID --evidence-id ID.
The caller supplies verified source dimensions; reconstruction never establishes size.
"""

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

import numpy as np
# Imported for its absence, not its API: trimesh reads glTF textures only when
# it can import PIL, and without it logs at debug level and hands back an
# untextured mesh. That silently packages grey models, so fail at import.
import PIL  # noqa: F401
import trimesh
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, UsdUtils


def convert(source: Path, destination: Path, category: str, *, yaw: float = 0,
            dimensions: list[float] | None = None, variant_id: str | None = None,
            evidence_id: str | None = None) -> dict:
    catalog = dimensions is not None or variant_id is not None or evidence_id is not None
    if catalog and (dimensions is None or not variant_id or not evidence_id):
        raise ValueError("Catalog conversion requires exact-variant dimension evidence")
    desired = np.array([1, 1, 1] if dimensions is None else dimensions, dtype=float)
    if desired.shape != (3,) or not np.isfinite(desired).all() or (desired <= 0).any():
        raise ValueError("Bounds must be positive finite width/depth/height")
    scene = trimesh.load_scene(source, process=False)
    scene.apply_transform(trimesh.transformations.rotation_matrix(np.radians(yaw), [0, 1, 0]))
    meshes = list(scene.dump())
    low = np.min([mesh.bounds[0] for mesh in meshes], axis=0)
    high = np.max([mesh.bounds[1] for mesh in meshes], axis=0)
    extent = high - low
    if (extent <= 0).any():
        raise ValueError("Source mesh has degenerate physical bounds")
    scale = desired[[0, 2, 1]] / extent
    origin = np.array([(low[0] + high[0]) / 2, low[1], (low[2] + high[2]) / 2])
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="respace-asset-") as temporary:
        # .usdc, the binary crate format, not .usda: ASCII stores every vertex
        # and index as text and roughly doubles the package. Measured over the
        # 15 reconstruction meshes, binary saved 34-60% and brought all of them
        # under SPEC's 3 MB ceiling, which nine of them had breached.
        stage_path = Path(temporary) / "model.usdc"
        stage = Usd.Stage.CreateNew(str(stage_path))
        root = UsdGeom.Xform.Define(stage, "/Model")
        stage.SetDefaultPrim(root.GetPrim())
        UsdGeom.SetStageMetersPerUnit(stage, 1)
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
        for index, mesh in enumerate(meshes):
            mesh.vertices = (mesh.vertices - origin) * scale
            usd_mesh = UsdGeom.Mesh.Define(stage, f"/Model/Mesh{index}")
            usd_mesh.CreatePointsAttr([Gf.Vec3f(*point) for point in mesh.vertices])
            usd_mesh.CreateFaceVertexCountsAttr([3] * len(mesh.faces))
            usd_mesh.CreateFaceVertexIndicesAttr(mesh.faces.flatten().tolist())
            usd_mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
            usd_mesh.CreateDoubleSidedAttr(True)
            usd_mesh.CreateNormalsAttr([Gf.Vec3f(*normal) for normal in mesh.vertex_normals])
            usd_mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
            material = UsdShade.Material.Define(stage, f"/Model/Material{index}")
            shader = UsdShade.Shader.Define(stage, f"/Model/Material{index}/PreviewSurface")
            shader.CreateIdAttr("UsdPreviewSurface")
            shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.8)
            shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0)
            visual_material = getattr(mesh.visual, "material", None)
            image = getattr(visual_material, "baseColorTexture", None)
            if image is None:
                image = getattr(visual_material, "image", None)
            uv = getattr(mesh.visual, "uv", None)
            if image is not None and uv is not None:
                image_name = f"texture{index}.png"
                image.save(Path(temporary) / image_name)
                primvars = UsdGeom.PrimvarsAPI(usd_mesh)
                primvars.CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex).Set([Gf.Vec2f(*pair) for pair in uv])
                reader = UsdShade.Shader.Define(stage, f"/Model/Material{index}/UVReader")
                reader.CreateIdAttr("UsdPrimvarReader_float2")
                reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
                texture = UsdShade.Shader.Define(stage, f"/Model/Material{index}/Texture")
                texture.CreateIdAttr("UsdUVTexture")
                texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(image_name))
                texture.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("sRGB")
                texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(reader.ConnectableAPI(), "result")
                shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(texture.ConnectableAPI(), "rgb")
            else:
                color = getattr(visual_material, "baseColorFactor", None)
                if color is None:
                    # A PBRMaterial carries main_color; only ColorVisuals puts it
                    # on the visual. Reaching past the material raised
                    # AttributeError on every textureless glTF.
                    color = getattr(visual_material, "main_color", None)
                if color is None:
                    color = mesh.visual.main_color
                rgb = np.array(color[:3], dtype=float)
                if rgb.max() > 1:
                    rgb /= 255
                shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*rgb))
            material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
            UsdShade.MaterialBindingAPI.Apply(usd_mesh.GetPrim()).Bind(material)
        stage.GetRootLayer().Save()
        if not UsdUtils.CreateNewUsdzPackage(Sdf.AssetPath(str(stage_path)), str(destination)):
            raise ValueError("USDZ packaging failed")
    reopened = Usd.Stage.Open(str(destination))
    bounds = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_]).ComputeWorldBound(reopened.GetDefaultPrim()).ComputeAlignedRange()
    actual = np.array(bounds.GetSize())[[0, 2, 1]]
    minimum = np.array(bounds.GetMin())
    if not np.allclose(actual, desired, atol=1e-5) or not np.allclose(minimum, [-desired[0] / 2, 0, -desired[1] / 2], atol=1e-5):
        raise ValueError("Packaged model failed physical bounds/pivot validation")
    data = destination.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    return {"schema_version": 1, "asset_id": ("catalog-" + variant_id) if variant_id else "kenney-" + category,
            "revision": digest[:16], "kind": "catalog" if variant_id else "standin", "category": category,
            "variant_id": variant_id, "dimension_evidence_id": evidence_id, "sha256": digest,
            "byte_count": len(data), "under_3_mb": len(data) < 3_000_000,
            "authored_bounds": desired.tolist(), "units": "meters", "pivot": "bottom_center",
            "forward_axis": "+Z", "up_axis": "+Y", "scaling_mode": "dimensioned" if variant_id else "normalized",
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "source_yaw_degrees": yaw,
            "conversion": {"trimesh": trimesh.__version__, "usd": list(Usd.GetVersion()),
                           "triangles": sum(len(mesh.faces) for mesh in meshes),
                           "physical_bounds_reopened": actual.tolist()},
            "native_validation": "pending"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--category", required=True)
    parser.add_argument("--yaw", type=float, default=0)
    parser.add_argument("--dimensions", nargs=3, type=float)
    parser.add_argument("--variant-id")
    parser.add_argument("--evidence-id")
    args = parser.parse_args()
    record = convert(args.source, args.destination, args.category, yaw=args.yaw,
                     dimensions=args.dimensions, variant_id=args.variant_id, evidence_id=args.evidence_id)
    print(json.dumps(record, indent=2))
