"""Convert the final scan-space OBJ/MTL/texture set into one portable USDZ."""
from pathlib import Path
from tempfile import TemporaryDirectory
import math
import shutil

import numpy as np
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, UsdUtils, Vt

from .models import SAFE_NAME
from .obj import read_obj


def dependency(folder, name):
    if not SAFE_NAME.fullmatch(name) or ".." in name:
        raise ValueError("Unsafe USDZ material/texture dependency")
    path = folder/name
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 128*1024**2:
        raise ValueError("Missing or oversized USDZ dependency: "+name)
    return path


def read_materials(source, libraries):
    materials = {}
    for library in libraries:
        current = None
        for line in dependency(source.parent, library).read_text().splitlines():
            fields = line.split("#", 1)[0].split()
            if not fields:
                continue
            tag, values = fields[0], fields[1:]
            if tag == "newmtl":
                if len(values) != 1:
                    raise ValueError("Malformed USDZ source material")
                current = materials[values[0]] = {}
            elif current is not None:
                if tag in ("Kd", "Pr", "Pm", "Ns", "d", "Tr"):
                    numbers = [float(v) for v in values]
                    if len(numbers) != (3 if tag == "Kd" else 1) or not all(math.isfinite(v) for v in numbers):
                        raise ValueError("Invalid USDZ material property: "+tag)
                    current[tag] = numbers if tag == "Kd" else numbers[0]
                elif tag in ("map_Kd", "map_Pr", "map_Pm", "map_d", "norm"):
                    if len(values) != 1:
                        raise ValueError("Unsupported USDZ texture options")
                    path = dependency(source.parent, values[0])
                    if path.suffix.lower() not in (".png", ".jpg", ".jpeg"):
                        raise ValueError("Unsupported USDZ texture format")
                    current[tag] = path
    return materials


def make_material(stage, path, properties, staging):
    material = UsdShade.Material.Define(stage, path)
    shader = UsdShade.Shader.Define(stage, path+"/Surface")
    shader.CreateIdAttr("UsdPreviewSurface")
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    color = properties.get("Kd", [0.8, 0.8, 0.8])
    roughness = properties.get("Pr", math.sqrt(2/(max(0, properties.get("Ns", 0))+2)))
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(roughness)
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(properties.get("Pm", 0.0))
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(properties.get("d", 1-properties.get("Tr", 0.0)))
    reader = UsdShade.Shader.Define(stage, path+"/UV")
    reader.CreateIdAttr("UsdPrimvarReader_float2")
    reader.CreateInput("varname", Sdf.ValueTypeNames.String).Set("st")
    reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)
    for tag, target, value_type, channel in (
        ("map_Kd", "diffuseColor", Sdf.ValueTypeNames.Color3f, "rgb"),
        ("map_Pr", "roughness", Sdf.ValueTypeNames.Float, "r"),
        ("map_Pm", "metallic", Sdf.ValueTypeNames.Float, "r"),
        ("map_d", "opacity", Sdf.ValueTypeNames.Float, "r"),
        ("norm", "normal", Sdf.ValueTypeNames.Normal3f, "rgb"),
    ):
        if tag not in properties:
            continue
        texture_path = properties[tag]
        destination = staging/texture_path.name
        if not destination.exists():
            shutil.copyfile(texture_path, destination)
        texture = UsdShade.Shader.Define(stage, path+"/"+target+"Texture")
        texture.CreateIdAttr("UsdUVTexture")
        texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(texture_path.name))
        texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(reader.ConnectableAPI(), "result")
        texture.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("sRGB" if tag == "map_Kd" else "raw")
        texture.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("repeat")
        texture.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("repeat")
        if tag == "map_Kd":
            texture.CreateInput("scale", Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(*color, 1))
        elif tag == "norm":
            texture.CreateInput("scale", Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(2, 2, 2, 1))
            texture.CreateInput("bias", Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(-1, -1, -1, 0))
        texture.CreateOutput(channel, Sdf.ValueTypeNames.Float3 if channel == "rgb" else Sdf.ValueTypeNames.Float)
        shader.CreateInput(target, value_type).ConnectToSource(texture.ConnectableAPI(), channel)
    return material


def export_usdz(source: Path) -> str:
    """Fail before publication if the finished OBJ cannot be packaged completely.

    Coordinates are already ARKit meters/Y-up in the aggregate OBJ. Face-corner
    primvars retain UV seams and authored normals without changing topology.
    """
    source = source.resolve()
    mesh = read_obj(source)
    properties = read_materials(source, mesh.libraries)
    used = list(dict.fromkeys(mesh.materials))
    if any(name and name not in properties for name in used):
        raise ValueError("OBJ references an undefined USDZ material")
    destination = source.with_suffix(".usdz")
    with TemporaryDirectory(prefix="usdz-", dir=source.parent) as temporary:
        staging = Path(temporary)
        layer = staging/"scene.usdc"
        stage = Usd.Stage.CreateNew(str(layer))
        root = UsdGeom.Xform.Define(stage, "/Room")
        stage.SetDefaultPrim(root.GetPrim())
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        geometry = UsdGeom.Mesh.Define(stage, "/Room/Scan")
        geometry.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(mesh.vertices.astype(np.float32)))
        geometry.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(np.full(len(mesh.faces), 3, dtype=np.int32)))
        geometry.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(mesh.triangles.astype(np.int32).ravel()))
        geometry.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
        geometry.CreateDoubleSidedAttr(True)
        geometry.CreateExtentAttr([Gf.Vec3f(*mesh.vertices.min(axis=0)), Gf.Vec3f(*mesh.vertices.max(axis=0))])
        corners = [corner for face in mesh.faces for corner in face]
        if any(t is not None for _, t, _ in corners):
            uv = np.array([mesh.uvs[t] if t is not None else [0, 0] for _, t, _ in corners], dtype=np.float32)
            UsdGeom.PrimvarsAPI(geometry).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray,
                UsdGeom.Tokens.faceVarying).Set(Vt.Vec2fArray.FromNumpy(uv))
        if all(n is not None for _, _, n in corners):
            normals = np.array([mesh.normals[n] for _, _, n in corners], dtype=np.float32)
            geometry.CreateNormalsAttr(Vt.Vec3fArray.FromNumpy(normals))
            geometry.SetNormalsInterpolation(UsdGeom.Tokens.faceVarying)
        binding = UsdShade.MaterialBindingAPI.Apply(geometry.GetPrim())
        face_materials = np.asarray(mesh.materials)
        for index, name in enumerate(used):
            material = make_material(stage, f"/Room/Materials/Material_{index}", properties.get(name, {}), staging)
            material.GetPrim().SetDisplayName(name or "Default")
            subset = binding.CreateMaterialBindSubset(f"material_{index}",
                Vt.IntArray.FromNumpy(np.flatnonzero(face_materials == name).astype(np.int32)))
            UsdShade.MaterialBindingAPI.Apply(subset.GetPrim()).Bind(material)
        binding.SetMaterialBindSubsetsFamilyType(UsdGeom.Tokens.partition)
        stage.GetRootLayer().Save()
        package = staging/"package.usdz"
        # All references are already local flat filenames. The USD writer keeps
        # entries uncompressed and aligned to 64 bytes without rewriting paths.
        with Sdf.ZipFileWriter.CreateNew(str(package)) as writer:
            files = [layer]+sorted(p for p in staging.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
            for path in files:
                if not writer.AddFile(str(path), path.name):
                    raise ValueError("Could not package the finished scan as USDZ")
        if package.stat().st_size > 128*1024**2:
            raise ValueError("USDZ exceeds the mobile asset budget")
        # Reopen the package itself; unresolved textures must never be published.
        layers, _, unresolved = UsdUtils.ComputeAllDependencies(Sdf.AssetPath(str(package)))
        if not layers or unresolved:
            raise ValueError("USDZ contains unresolved dependencies")
        package.replace(destination)
    return destination.name
