"""Assemble the supplied segmented ReSpace scan into one textured, named USDZ scene."""

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

import numpy as np
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, UsdUtils


def source_file(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"Missing or out-of-folder asset: {name}")
    return path


def read_obj(path: Path):
    vertices, uvs, faces, libraries = [], [], defaultdict(list), []
    material = None
    for line in path.read_text().splitlines():
        fields = line.split()
        if not fields or fields[0].startswith("#"):
            continue
        tag, values = fields[0], fields[1:]
        if tag == "v":
            vertices.append([float(x) for x in values])
        elif tag == "vt":
            uvs.append([float(x) for x in values[:2]])
        elif tag == "mtllib":
            libraries.extend(values)
        elif tag == "usemtl":
            material = " ".join(values)
        elif tag == "f":
            corners = []
            for value in values:
                indices = value.split("/")
                vertex = int(indices[0])
                uv = int(indices[1]) if len(indices) > 1 and indices[1] else None
                vertex = vertex - 1 if vertex > 0 else len(vertices) + vertex
                uv = (uv - 1 if uv > 0 else len(uvs) + uv) if uv is not None else None
                if not 0 <= vertex < len(vertices) or (uv is not None and not 0 <= uv < len(uvs)):
                    raise ValueError(f"Invalid OBJ index in {path.name}")
                corners.append((vertex, uv))
            if len(corners) < 3:
                raise ValueError(f"Degenerate face in {path.name}")
            for index in range(1, len(corners) - 1):
                faces[material].append([corners[0], corners[index], corners[index + 1]])
    points = np.asarray(vertices, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all() or not faces:
        raise ValueError(f"Invalid OBJ geometry in {path.name}")
    if uvs and (np.asarray(uvs).shape[1] != 2 or not np.isfinite(uvs).all()):
        raise ValueError(f"Invalid texture coordinates in {path.name}")
    return points, uvs, faces, libraries


def read_materials(root: Path, libraries: list[str]) -> dict:
    materials = {}
    current = None
    for library in libraries:
        for line in source_file(root, library).read_text().splitlines():
            fields = line.split()
            if not fields:
                continue
            tag, values = fields[0], fields[1:]
            if tag == "newmtl":
                current = {}; materials[" ".join(values)] = current
            elif current is not None and tag in {"Kd", "Pr", "Pm", "map_Kd"}:
                current[tag] = " ".join(values) if tag == "map_Kd" else [float(x) for x in values]
    return materials


def assemble(source: Path, destination: Path) -> dict:
    scene_bytes = source_file(source, "scene.json").read_bytes()
    scene = json.loads(scene_bytes)
    if scene.get("schema_version") != 2 or scene.get("coordinate_system") != "arkit_scan_meters_y_up":
        raise ValueError("Expected the segmented scan's schema 2 ARKit metre coordinates")
    entities = scene["entities"]
    if not entities or len({e["id"] for e in entities}) != len(entities):
        raise ValueError("Scene requires unique entity identities")
    polygon = np.asarray(scene["navigation"]["floor_polygons"][0], dtype=float)
    floor_y = float(scene["navigation"]["floor_height"])
    if polygon.ndim != 2 or polygon.shape[1] != 2 or len(polygon) < 3 or not np.isfinite(polygon).all() or not np.isfinite(floor_y):
        raise ValueError("Scene requires a finite measured floor polygon and elevation")
    offset = np.array([-polygon[:, 0].min(), -floor_y, -polygon[:, 1].min()])
    edges = np.roll(polygon, -1, axis=0) - polygon
    following = np.roll(polygon, -1, axis=0)
    area = (polygon[:, 0] * following[:, 1] - polygon[:, 1] * following[:, 0]).sum() / 2
    if abs(area) < 1e-6 or (np.linalg.norm(edges, axis=1) < 1e-6).any():
        raise ValueError("Scene floor polygon is degenerate")
    destination.mkdir(parents=True, exist_ok=True)
    records, expected_points, textures = [], [], set()
    triangles = dropped_triangles = 0
    with tempfile.TemporaryDirectory(prefix="respace-scene-") as temporary:
        work = Path(temporary)
        stage = Usd.Stage.CreateNew(str(work / "scene.usda"))
        root = UsdGeom.Xform.Define(stage, "/Room")
        stage.SetDefaultPrim(root.GetPrim())
        UsdGeom.SetStageMetersPerUnit(stage, 1)
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
        for index, entity in enumerate(entities):
            points, uvs, groups, libraries = read_obj(source_file(source, entity["asset"]))
            materials = read_materials(source, libraries)
            transform = np.asarray(entity["local_to_scan_transform"], dtype=float)
            if transform.shape != (16,) or not np.isfinite(transform).all():
                raise ValueError(f"Invalid transform for {entity['id']}")
            matrix = transform.reshape(4, 4, order="F").copy()
            if not np.allclose(matrix[3], [0, 0, 0, 1]) or not np.allclose(matrix[:3, :3].T @ matrix[:3, :3], np.eye(3), atol=1e-5):
                raise ValueError(f"Expected a rigid column-major transform for {entity['id']}")
            matrix[:3, 3] += offset
            world = points @ matrix[:3, :3].T + matrix[:3, 3]
            expected_points.append(world)
            name = "scan_" + re.sub(r"[^a-zA-Z0-9_]", "_", entity["id"])
            node = UsdGeom.Xform.Define(stage, f"/Room/{name}")
            node.AddTransformOp().Set(Gf.Matrix4d(*matrix.T.flatten().tolist()))
            node.GetPrim().SetDisplayName(entity["label"])
            if not entity.get("visible", True):
                node.CreateVisibilityAttr(UsdGeom.Tokens.invisible)
            for group_index, (material_id, faces) in enumerate(groups.items()):
                valid_faces, normals = [], []
                for face in faces:
                    a, b, c = points[[corner[0] for corner in face]]
                    normal = np.cross(b - a, c - a)
                    length = np.linalg.norm(normal)
                    if length <= 1e-12:
                        dropped_triangles += 1
                        continue
                    valid_faces.append(face); normals.append(Gf.Vec3f(*(normal / length)))
                faces = valid_faces
                if not faces:
                    continue
                mesh = UsdGeom.Mesh.Define(stage, f"/Room/{name}/Mesh{group_index}")
                mesh.CreatePointsAttr([Gf.Vec3f(*p) for p in points])
                mesh.CreateFaceVertexCountsAttr([3] * len(faces))
                mesh.CreateFaceVertexIndicesAttr([corner[0] for face in faces for corner in face])
                mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
                mesh.CreateDoubleSidedAttr(True)
                mesh.CreateNormalsAttr(normals); mesh.SetNormalsInterpolation(UsdGeom.Tokens.uniform)
                triangles += len(faces)
                values = materials.get(material_id)
                if values is None:
                    raise ValueError(f"Missing material {material_id} for {entity['id']}")
                material_path = f"/Room/Materials/M{index}_{group_index}"
                material = UsdShade.Material.Define(stage, material_path)
                shader = UsdShade.Shader.Define(stage, material_path + "/Surface")
                shader.CreateIdAttr("UsdPreviewSurface")
                shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*values.get("Kd", [0.7, 0.7, 0.7])))
                for key, attribute, default in [("Pr", "roughness", 0.8), ("Pm", "metallic", 0.0)]:
                    shader.CreateInput(attribute, Sdf.ValueTypeNames.Float).Set(values.get(key, [default])[0])
                if "map_Kd" in values:
                    if any(corner[1] is None for face in faces for corner in face):
                        raise ValueError(f"Textured faces require UV coordinates: {entity['id']}")
                    filename = values["map_Kd"]
                    texture_file = source_file(source, filename)
                    if filename not in textures:
                        shutil.copyfile(texture_file, work / texture_file.name); textures.add(filename)
                    UsdGeom.PrimvarsAPI(mesh).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.faceVarying).Set([Gf.Vec2f(*uvs[corner[1]]) for face in faces for corner in face])
                    reader = UsdShade.Shader.Define(stage, material_path + "/UV")
                    reader.CreateIdAttr("UsdPrimvarReader_float2")
                    reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
                    texture = UsdShade.Shader.Define(stage, material_path + "/Texture")
                    texture.CreateIdAttr("UsdUVTexture")
                    texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(texture_file.name))
                    texture.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("sRGB")
                    texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(reader.ConnectableAPI(), "result")
                    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(texture.ConnectableAPI(), "rgb")
                material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
                UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)
            record = {key: entity[key] for key in ["id", "label", "kind", "category", "move_ready"]}
            record.update(node_name=name, bounds_min=world.min(axis=0).tolist(), bounds_max=world.max(axis=0).tolist())
            if entity["kind"] == "ceiling" or entity["id"].startswith("ceiling-"):
                record["cutaway"] = "ceiling"
            if entity["kind"] == "wall" or entity["category"] in {"window", "curtain"}:
                center = (world.min(axis=0) + world.max(axis=0)) / 2
                scan_center = center[[0, 2]] - offset[[0, 2]]
                projection = np.clip(((scan_center - polygon) * edges).sum(axis=1) / (edges * edges).sum(axis=1), 0, 1)
                nearest = np.linalg.norm(polygon + edges * projection[:, None] - scan_center, axis=1).argmin()
                dx, dz = edges[nearest] / np.linalg.norm(edges[nearest]) * np.sign(area)
                record.update(cutaway="wall", center=center.tolist(), inward_normal=[-float(dz), 0, float(dx)])
            records.append(record)
        stage.GetRootLayer().Save()
        stage.GetRootLayer().Export(str(work / "scene.usdc"))
        output = destination / "kitchenette.usdz"
        if not UsdUtils.CreateNewUsdzPackage(Sdf.AssetPath(str(work / "scene.usdc")), str(output)):
            raise ValueError("Scene USDZ packaging failed")
    reopened = Usd.Stage.Open(str(output))
    if UsdUtils.ComputeAllDependencies(str(output))[2]:
        raise ValueError("Packaged scene has unresolved texture dependencies")
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
    transforms = UsdGeom.XformCache()
    for record, expected in zip(records, expected_points):
        part = reopened.GetPrimAtPath("/Room/" + record["node_name"])
        meshes = [UsdGeom.Mesh(prim) for prim in Usd.PrimRange(part) if prim.IsA(UsdGeom.Mesh)]
        if not meshes:
            raise ValueError(f"No usable triangles for {record['id']}")
        for mesh in meshes:
            points = np.asarray(mesh.GetPointsAttr().Get())
            world = np.column_stack([points, np.ones(len(points))]) @ np.asarray(transforms.GetLocalToWorldTransform(mesh.GetPrim()))
            if not np.allclose(world[:, :3], expected, atol=1e-5):
                raise ValueError(f"Packaged geometry/transform changed for {record['id']}")
        bounds = cache.ComputeWorldBound(part).ComputeAlignedRange()
        record.update(bounds_min=list(bounds.GetMin()), bounds_max=list(bounds.GetMax()))
    bounds = cache.ComputeWorldBound(reopened.GetDefaultPrim()).ComputeAlignedRange()
    provenance = json.loads(source_file(source, "provenance.json").read_text())
    quality = json.loads(source_file(source, "quality.json").read_text())
    manifest = {"schema_version": 1, "name": "Imported kitchenette", "capture_id": scene["capture_id"],
                "source_scene_sha256": hashlib.sha256(scene_bytes).hexdigest(),
                "model_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "coordinate_system": "meters_y_up_floor_zero", "translation_from_scan": offset.tolist(),
                "bounds_min": list(bounds.GetMin()), "bounds_max": list(bounds.GetMax()),
                "triangle_count": triangles, "dropped_zero_area_triangles": dropped_triangles,
                "texture_count": len(textures), "entities": records,
                "geometry_source": provenance["geometry"], "assumptions": provenance["assumptions"],
                "coarse_object_count": sum(o["detail"] == "coarse" for o in quality["objects"])}
    (destination / "kitchenette.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    result = assemble(args.source, args.destination)
    print(json.dumps({key: result[key] for key in ["name", "triangle_count", "texture_count", "bounds_min", "bounds_max"]}, indent=2))
