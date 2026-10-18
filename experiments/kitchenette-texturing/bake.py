"""Bake a known-camera image into the existing kitchenette USDZ's surface UVs.

Run with the repository's .local/venv/bin/python. No model/API calls are made.
"""

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from PIL import Image, ImageFilter
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, UsdUtils


ROOT = Path(__file__).resolve().parent


def project(points, camera):
    view = np.c_[points, np.ones(len(points))] @ np.array(camera["world_to_camera"]).T
    clip = view @ np.array(camera["projection"]).T
    ndc = clip[:, :2] / clip[:, 3:4]
    return (ndc * [0.5, -0.5] + 0.5) * [camera["width"], camera["height"]], -view[:, 2]


def pixels(triangle, width, height):
    """Pixel-center triangle coverage and barycentrics, clipped to an image."""
    lo = np.maximum(np.floor(triangle.min(axis=0)).astype(int), 0)
    hi = np.minimum(np.ceil(triangle.max(axis=0)).astype(int), [width - 1, height - 1])
    if np.any(hi < lo):
        return None
    a, b, c = triangle
    denominator = (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])
    if abs(denominator) < 1e-10:
        return None
    xx, yy = np.meshgrid(np.arange(lo[0], hi[0] + 1), np.arange(lo[1], hi[1] + 1))
    dx, dy = xx + 0.5 - a[0], yy + 0.5 - a[1]
    w1 = (dx * (c[1] - a[1]) - dy * (c[0] - a[0])) / denominator
    w2 = ((b[0] - a[0]) * dy - (b[1] - a[1]) * dx) / denominator
    bary = np.stack([1 - w1 - w2, w1, w2], axis=-1)
    inside = bary.min(axis=-1) >= -1e-7
    return xx[inside], yy[inside], bary[inside]


def clipped_triangles(clip):
    # Clip before rasterization: walls can cross the source camera's near plane.
    polygon = list(clip)
    for axis, sign in [(3, 0), (0, 1), (0, -1), (1, 1), (1, -1), (2, 1), (2, -1)]:
        if not polygon:
            return
        result = []
        def distance(p):
            return p[3] - 1e-7 if axis == 3 else p[3] + sign * p[axis]
        previous = polygon[-1]
        dp = distance(previous)
        for current in polygon:
            dc = distance(current)
            if (dc >= 0) != (dp >= 0):
                result.append(previous + (current - previous) * dp / (dp - dc))
            if dc >= 0:
                result.append(current)
            previous, dp = current, dc
        polygon = result
    for i in range(1, len(polygon) - 1):
        yield np.array([polygon[0], polygon[i], polygon[i + 1]])


def visibility(meshes, camera):
    width, height = camera["width"], camera["height"]
    depth = np.full((height, width), np.inf)
    owner = np.full((height, width), -1, dtype=np.int32)
    vp = np.array(camera["projection"]) @ np.array(camera["world_to_camera"])
    for index, mesh in enumerate(meshes):
        clip = np.c_[mesh["world"], np.ones(len(mesh["world"]))] @ vp.T
        for face in mesh["faces"]:
            for triangle in clipped_triangles(clip[face]):
                uv = (triangle[:, :2] / triangle[:, 3:4] * [0.5, -0.5] + 0.5) * [width, height]
                covered = pixels(uv, width, height)
                if covered is None:
                    continue
                x, y, bary = covered
                z = 1 / (bary @ (1 / triangle[:, 3]))
                nearer = z < depth[y, x]
                depth[y[nearer], x[nearer]] = z[nearer]
                owner[y[nearer], x[nearer]] = index
    return depth, owner


def patches(mesh):
    groups = {}
    for index, face in enumerate(mesh["faces"]):
        a, b, c = mesh["world"][face]
        normal = np.cross(b - a, c - a)
        length = np.linalg.norm(normal)
        if length < 1e-10:
            raise ValueError("Source contains a zero-area triangle")
        normal /= length
        key = tuple(np.round(np.r_[normal, normal @ a], 5))
        groups.setdefault(key, []).append(index)
    result = []
    for key, faces in groups.items():
        normal = np.array(key[:3]); normal /= np.linalg.norm(normal)
        # Stable planar coordinates, with vertical grain on vertical faces.
        helper = np.eye(3)[np.argmin(abs(normal))]
        u = np.cross(helper, normal); u /= np.linalg.norm(u)
        v = np.cross(normal, u)
        indices = mesh["faces"][faces]
        points = mesh["world"][indices]
        xy = np.stack([points @ u, points @ v], axis=-1)
        lo, hi = xy.reshape(-1, 2).min(axis=0), xy.reshape(-1, 2).max(axis=0)
        result.append(dict(faces=faces, xy=xy, lo=lo, extent=np.maximum(hi-lo, 1e-5), normal=normal, u=u, v=v))
    return result


def layout(groups, ppm=180, padding=4):
    for attempt in range(18):
        sizes = [np.maximum(2, np.ceil(p["extent"] * ppm).astype(int)) + padding * 2 for p in groups]
        for dimension in [128, 256, 512, 1024, 2048]:
            positions, x, y, row_height = {}, 0, 0, 0
            for i in sorted(range(len(groups)), key=lambda i: -sizes[i][1]):
                w, h = sizes[i]
                if w > dimension or h > dimension:
                    break
                if x+w > dimension:
                    x, y, row_height = 0, y+row_height, 0
                if y+h > dimension:
                    break
                positions[i] = (x+padding, y+padding, int(w-2*padding), int(h-2*padding))
                x += int(w); row_height = max(row_height, int(h))
            if len(positions) == len(groups):
                return dimension, positions
        ppm *= 0.8
    raise ValueError("Could not pack mesh UV patches")


def srgb(linear):
    linear = np.clip(linear, 0, 1)
    return np.where(linear <= 0.0031308, linear*12.92, 1.055*linear**(1/2.4)-0.055)


def sample(image, uv):
    x = np.clip(uv[:, 0] - 0.5, 0, image.shape[1]-1)
    y = np.clip(uv[:, 1] - 0.5, 0, image.shape[0]-1)
    ix, iy = x.astype(int), y.astype(int)
    jx, jy = np.minimum(ix+1, image.shape[1]-1), np.minimum(iy+1, image.shape[0]-1)
    ax, ay = (x-ix)[:, None], (y-iy)[:, None]
    return (image[iy, ix]*(1-ax)*(1-ay) + image[iy, jx]*ax*(1-ay)
            + image[jy, ix]*(1-ax)*ay + image[jy, jx]*ax*ay)


def finish_samples(mesh, points, group, image, base):
    """Room-specific swatch fallbacks; they describe appearance, not observations."""
    colors = np.full((len(points), 3), base, dtype=float)
    path = mesh["path"]
    family = None
    if "cabinets/" in path:
        family, period, crop = "wood", [.28, .65], [.10, .10, .20, .23]
    elif "scan_floor_" in path:
        family, period, crop = "floor", [.8, .8], [.50, .81, .60, .89]
    elif "scan_main_countertop/" in path:
        family, period, crop = "stone", [.4, .4], [.25, .72, .28, .75]
    elif "scan_wall_687159d16597d3f99eb4/" in path:
        family, period, crop = "tile", [.45, .16], [.02, .48, .14, .52]
    if family:
        lo = (np.array(crop[:2])*[image.shape[1], image.shape[0]]).astype(int)
        hi = (np.array(crop[2:])*[image.shape[1], image.shape[0]]).astype(int)
        swatch = image[lo[1]:hi[1], lo[0]:hi[0]]
        xy = np.c_[points @ group["u"], points @ group["v"]]
        uv = (xy/period % 1) * [swatch.shape[1]-1, swatch.shape[0]-1] + .5
        fill = sample(swatch, uv)
        allowed = (points[:, 1] > .94) & (points[:, 1] < 1.60) if family == "tile" else np.ones(len(points), dtype=bool)
        colors[allowed] = fill[allowed]
    return colors


def bake_mesh(mesh, index, camera, image, depth, owners, destination, accepted_image_mask=None, hybrid=False):
    groups = patches(mesh)
    size, boxes = layout(groups)
    base = srgb(np.array(mesh["color"])) * 255
    atlas = np.full((size, size, 3), base, dtype=float)
    fallback_atlas = atlas.copy()
    weights = np.zeros((size, size))
    uv_faces = np.zeros((len(mesh["faces"]), 3, 2))
    safe = np.array(Image.fromarray((owners == index).astype(np.uint8)*255).filter(ImageFilter.MinFilter(5))) > 0
    if accepted_image_mask is not None:
        safe &= accepted_image_mask
    area, covered_area = 0., 0.
    for group_index, group in enumerate(groups):
        bx, by, width, height = boxes[group_index]
        plane_uv = (group["xy"]-group["lo"])/group["extent"] * [width-1, height-1] + [bx+0.5, by+0.5]
        for local_index, face_index in enumerate(group["faces"]):
            xy = plane_uv[local_index]
            uv_faces[face_index] = xy / size * [1, -1] + [0, 1]
            raster = pixels(xy, size, size)
            if raster is None:
                continue
            x, y, bary = raster
            triangle = mesh["world"][mesh["faces"][face_index]]
            points = bary @ triangle
            if hybrid:
                atlas[y, x] = finish_samples(mesh, points, group, image, base)
                fallback_atlas[y, x] = atlas[y, x]
            uv, z = project(points, camera)
            ix, iy = np.floor(uv).astype(int).T
            valid = (z > 0.03) & (ix >= 0) & (iy >= 0) & (ix < camera["width"]) & (iy < camera["height"])
            ids = np.flatnonzero(valid)
            valid[:] = False
            # Depth AND identity prevent projecting foreground Objects onto walls.
            accepted = safe[iy[ids], ix[ids]] & (abs(depth[iy[ids], ix[ids]]-z[ids]) < .015)
            valid[ids[accepted]] = True
            atlas[y[valid], x[valid]] = sample(image, uv[valid])
            weights[y[valid], x[valid]] = 1
            triangle_area = np.linalg.norm(np.cross(triangle[1]-triangle[0], triangle[2]-triangle[0]))/2
            area += triangle_area
            covered_area += triangle_area * (float(valid.mean()) if len(valid) else 0)
        # Pad each patch within its own allocation to avoid cross-surface mip bleed.
        patch = atlas[by:by+height, bx:bx+width]
        if weights[by:by+height, bx:bx+width].any():
            fallback = fallback_atlas[by:by+height, bx:bx+width] if hybrid else np.median(patch[weights[by:by+height, bx:bx+width] > 0], axis=0)
            if not hybrid:
                patch[weights[by:by+height, bx:bx+width] == 0] = fallback
            mask = weights[by:by+height, bx:bx+width]
            feather = np.array(Image.fromarray((mask*255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2)))/255
            patch[:] = patch*(mask*feather)[:, :, None] + fallback*(1-mask*feather)[:, :, None]
        padded = np.pad(patch, ((4, 4), (4, 4), (0, 0)), mode="edge")
        atlas[by-4:by+height+4, bx-4:bx+width+4] = padded
    name = f"atlas-{index:03d}.png"
    Image.fromarray(np.clip(atlas, 0, 255).astype(np.uint8)).save(destination/name)
    return uv_faces, name, dict(mesh=mesh["path"], atlas_size=size, area_m2=area,
                               projected_area_m2=covered_area, projected_fraction=covered_area/max(area, 1e-10))


def material(stage, mesh, index, texture_name, projected):
    path = f"/Room/Materials/Baked{index}"
    mat = UsdShade.Material.Define(stage, path)
    shader = UsdShade.Shader.Define(stage, path+"/Surface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(mesh["roughness"])
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(mesh["metallic"] if not projected else 0)
    if texture_name is None:
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*mesh["color"]))
        mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
        UsdShade.MaterialBindingAPI.Apply(stage.GetPrimAtPath(mesh["path"])).Bind(mat)
        return
    reader = UsdShade.Shader.Define(stage, path+"/Reader")
    reader.CreateIdAttr("UsdPrimvarReader_float2")
    reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    texture = UsdShade.Shader.Define(stage, path+"/Texture")
    texture.CreateIdAttr("UsdUVTexture")
    texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath("textures/"+texture_name))
    texture.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("sRGB")
    texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(reader.ConnectableAPI(), "result")
    if projected:
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(1)
        shader.CreateInput("useSpecularWorkflow", Sdf.ValueTypeNames.Int).Set(1)
        shader.CreateInput("specularColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0))
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0))
        shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(texture.ConnectableAPI(), "rgb")
    else:
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(texture.ConnectableAPI(), "rgb")
    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    UsdShade.MaterialBindingAPI.Apply(stage.GetPrimAtPath(mesh["path"])).Bind(mat)


def projectable(mesh):
    return mesh["metallic"] < .6 and any(name in mesh["path"] for name in (
        "scan_wall_", "scan_floor_", "scan_base_cabinets/", "scan_upper_cabinets/",
        "scan_main_countertop/", "scan_shade_"))


def load_meshes(stage):
    cache = UsdGeom.XformCache()
    meshes = []
    for prim in stage.Traverse():
        if not prim.IsA(UsdGeom.Mesh):
            continue
        geometry = UsdGeom.Mesh(prim)
        if set(geometry.GetFaceVertexCountsAttr().Get()) != {3} or UsdGeom.Subset.GetAllGeomSubsets(geometry):
            raise ValueError("This experiment expects the kitchenette's triangulated, single-material meshes")
        vertices = np.array(geometry.GetPointsAttr().Get(), dtype=float)
        world = np.c_[vertices, np.ones(len(vertices))] @ np.array(cache.GetLocalToWorldTransform(prim))
        bound = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0]
        shader = bound.ComputeSurfaceSource()[0]
        def value(name, fallback):
            attr = shader.GetInput(name)
            result = attr.Get() if attr else None
            return fallback if result is None else result
        meshes.append(dict(path=str(prim.GetPath()), vertices=vertices, world=world[:, :3],
                           faces=np.array(geometry.GetFaceVertexIndicesAttr().Get()).reshape(-1, 3),
                           color=list(value("diffuseColor", Gf.Vec3f(.7))),
                           roughness=float(value("roughness", .8)), metallic=float(value("metallic", 0))))
    return meshes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=ROOT.parents[1]/"ReSpace/Resources/ImportedKitchenette/kitchenette.usdz")
    args = parser.parse_args()
    camera = json.loads((ROOT/"inputs/camera.json").read_text())
    photo = ROOT/"inputs/photorealistic.png"
    image = np.array(Image.open(photo).convert("RGB").resize((camera["width"], camera["height"]), Image.Resampling.LANCZOS), dtype=float)
    source = Usd.Stage.Open(str(args.model))
    meshes = load_meshes(source)
    output = ROOT/"output"
    textures = output/"textures"
    textures.mkdir(parents=True, exist_ok=True)
    depth, owners = visibility(meshes, camera)
    np.savez_compressed(output/"visibility.npz", depth=depth, owners=owners)
    palette = np.array([[41+(i*67)%190, 35+(i*113)%200, 45+(i*43)%190] for i in range(len(meshes))], dtype=np.uint8)
    ids = np.zeros((*owners.shape, 3), dtype=np.uint8); ids[owners >= 0] = palette[owners[owners >= 0]]
    Image.fromarray(ids).save(output/"surface-ids.png")
    alignment = json.loads((ROOT/"alignment.json").read_text())
    accepted_mask = np.ones((camera["height"], camera["width"]), dtype=bool)
    for x0, y0, x1, y1 in alignment["excluded_rectangles"]:
        accepted_mask[int(y0*camera["height"]):int(y1*camera["height"]),
                      int(x0*camera["width"]):int(x1*camera["width"])] = False
    Image.fromarray(accepted_mask.astype(np.uint8)*255).save(output/"accepted-image-mask.png")
    baked, hybrid_baked, reports = [], [], []
    for index, mesh in enumerate(meshes):
        uv, name, report = bake_mesh(mesh, index, camera, image, depth, owners, textures)
        baked.append((uv, name)); reports.append(report)
        if projectable(mesh):
            hybrid_textures = textures/"hybrid"
            hybrid_textures.mkdir(exist_ok=True)
            mask = accepted_mask if "scan_wall_" in mesh["path"] or "scan_main_countertop/" in mesh["path"] else None
            huv, hname, hreport = bake_mesh(mesh, index, camera, image, depth, owners, hybrid_textures, mask, hybrid=True)
            hybrid_baked.append((huv, "hybrid/"+hname))
            report["hybrid_projected_fraction"] = hreport["projected_fraction"]
        else:
            hybrid_baked.append((uv, None))
            report["hybrid_projected_fraction"] = 0
    for mode in ["hybrid", "projected"]:
        stage_path = output/f"kitchenette-{mode}.usdc"
        source.Flatten().Export(str(stage_path))
        stage = Usd.Stage.Open(str(stage_path))
        stage.RemovePrim("/Room/Materials")
        for index, (mesh, (uv, name)) in enumerate(zip(meshes, hybrid_baked if mode == "hybrid" else baked)):
            geometry = UsdGeom.Mesh(stage.GetPrimAtPath(mesh["path"]))
            UsdGeom.PrimvarsAPI(geometry).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.faceVarying).Set([Gf.Vec2f(*p) for p in uv.reshape(-1, 2)])
            material(stage, mesh, index, name, projected=mode == "projected")
            assert np.array_equal(np.array(geometry.GetPointsAttr().Get()), mesh["vertices"])
            assert np.array_equal(np.array(geometry.GetFaceVertexIndicesAttr().Get()).reshape(-1, 3), mesh["faces"])
        stage.GetRootLayer().Save()
        destination = output/f"kitchenette-{mode}.usdz"
        if destination.exists():
            destination.unlink()
        if not UsdUtils.CreateNewUsdzPackage(Sdf.AssetPath(str(stage_path)), str(destination)):
            raise RuntimeError("USDZ packaging failed")
        loaded = Usd.Stage.Open(str(destination))
        assert len(load_meshes(loaded)) == len(meshes)
        # Check packaged image bytes as well as reopening geometry: missing textures
        # can otherwise pass a mesh-only USDZ check.
        with ZipFile(destination) as archive:
            for prim in loaded.Traverse():
                if prim.GetTypeName() == "Shader":
                    attr = UsdShade.Shader(prim).GetInput("file")
                    if attr:
                        path = attr.Get().path
                        assert path in archive.namelist(), path
                        assert archive.read(path), path
        original = load_meshes(loaded)
        for before, after in zip(meshes, original):
            assert before["path"] == after["path"]
            np.testing.assert_array_equal(before["world"], after["world"])
            np.testing.assert_array_equal(before["faces"], after["faces"])
    report = dict(source_model=str(args.model.resolve()), source_sha256=hashlib.sha256(args.model.read_bytes()).hexdigest(),
                  source_image_sha256=hashlib.sha256(photo.read_bytes()).hexdigest(), source_image_size=list(Image.open(photo).size),
                  camera=camera, mesh_count=len(meshes), triangle_count=sum(len(m["faces"]) for m in meshes),
                  manual_alignment=alignment,
                  geometry_preserved=True, source_view_only=True,
                  projected_area_m2=sum(r["projected_area_m2"] for r in reports),
                  total_area_m2=sum(r["area_m2"] for r in reports), meshes=reports)
    (output/"report.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k not in ["meshes", "camera"]}, indent=2))


if __name__ == "__main__":
    main()
