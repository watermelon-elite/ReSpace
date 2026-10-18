import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

import numpy as np

from .geometry import (camera_to_cv_world, depth_frame, quality_report,
                       read_scan, repair_small_holes, write_colored_obj)
from .models import Manifest
from .store import atomic_json, digest
from . import astra


def progress(stage):
    print(json.dumps({"stage": stage}), flush=True)


def fuse(manifest, inputs, o3d):
    volume = o3d.pipelines.integration.ScalableTSDFVolume(voxel_length=.015, sdf_trunc=.06,
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)
    integrated = 0
    for index, frame in enumerate(manifest.frames):
        observed = depth_frame(frame, inputs)
        if observed is None:
            continue
        depth, color = observed
        if np.count_nonzero(depth) < 16:
            continue
        m = frame.metadata
        sx, sy = m.depth_width / m.width, m.depth_height / m.height
        fx, fy, cx, cy = m.intrinsics
        intrinsics = o3d.camera.PinholeCameraIntrinsic(m.depth_width, m.depth_height, fx*sx, fy*sy, cx*sx, cy*sy)
        rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(o3d.geometry.Image(color),
            o3d.geometry.Image(depth), depth_scale=1., depth_trunc=6., convert_rgb_to_intensity=False)
        volume.integrate(rgbd, intrinsics, np.linalg.inv(camera_to_cv_world(m)))
        integrated += 1
        if index % 20 == 0:
            progress(f"depth_fusion:{index+1}/{len(manifest.frames)}")
    mesh = volume.extract_triangle_mesh()
    if integrated == 0 or len(mesh.triangles) == 0:
        raise ValueError("No usable registered depth surfaces were reconstructed")
    return mesh, integrated


def export_colmap(manifest, inputs, mesh, working):
    """Known ARKit poses + depth-verified observations for the stable OpenMVS importer.

    COLMAP is a file format here; no COLMAP executable or pose re-estimation.
    OpenMVS subtracts .5 from principal points, so encode that convention explicitly.
    """
    from scipy.spatial.transform import Rotation
    scene = working / "colmap"
    sparse = scene / "sparse"
    images = scene / "images"
    sparse.mkdir(parents=True, exist_ok=True)
    images.mkdir(exist_ok=True)
    points = np.asarray(mesh.vertices)[::max(1, len(mesh.vertices)//10000)].copy()
    colors = np.asarray(mesh.vertex_colors)
    colors = colors[::max(1, len(mesh.vertices)//10000)] if len(colors) == len(mesh.vertices) else np.full_like(points, .65)
    tracks = [[] for _ in points]
    camera_lines, image_records = [], []
    # Bound image optimization memory on an 8GB Mac; all depth frames were fused.
    # Spread photo keyframes over the complete scan, not just its beginning.
    limit = max(12, min(900, int(os.environ.get("RESPACE_PHOTO_LIMIT", "240"))))
    indices = np.linspace(0, len(manifest.frames)-1, min(limit, len(manifest.frames)), dtype=int)
    for image_id, frame_index in enumerate(indices, 1):
        frame = manifest.frames[frame_index]
        m = frame.metadata
        photo = next(a for a in frame.artifacts if a.type == "jpeg")
        destination = images / photo.filename
        if not destination.exists():
            os.link(inputs / photo.filename, destination)
        fx, fy, cx, cy = m.intrinsics
        camera_lines.append(f"{image_id} PINHOLE {m.width} {m.height} {fx} {fy} {cx+.5} {cy+.5}\n")
        inverse = np.linalg.inv(camera_to_cv_world(m))
        q = Rotation.from_matrix(inverse[:3, :3]).as_quat()
        t = inverse[:3, 3]
        first = f"{image_id} {q[3]} {q[0]} {q[1]} {q[2]} {t[0]} {t[1]} {t[2]} {image_id} {photo.filename}\n"
        pixels = []
        observation = depth_frame(frame, inputs)
        if observation is not None:
            depth, _ = observation
            camera = points @ inverse[:3, :3].T + inverse[:3, 3]
            z = camera[:, 2]
            safe = np.maximum(z, 1e-6)
            u, v = fx*camera[:, 0]/safe + cx, fy*camera[:, 1]/safe + cy
            valid = np.where((z > .1) & (u >= 0) & (u < m.width) & (v >= 0) & (v < m.height))[0]
            x = np.clip((u[valid]*depth.shape[1]/m.width).astype(int), 0, depth.shape[1]-1)
            y = np.clip((v[valid]*depth.shape[0]/m.height).astype(int), 0, depth.shape[0]-1)
            measured = depth[y, x]
            visible = valid[(measured > 0) & (abs(measured-z[valid]) < np.maximum(.05, z[valid]*.025))]
            for point_id in visible:
                tracks[point_id].append((image_id, len(pixels)))
                pixels.append(f"{u[point_id]+.5} {v[point_id]+.5} {point_id+1}")
        image_records.append(first + " ".join(pixels) + "\n")
    (sparse / "cameras.txt").write_text("".join(camera_lines))
    (sparse / "images.txt").write_text("".join(image_records))
    with (sparse / "points3D.txt").open("w") as f:
        for i, (point, color, track) in enumerate(zip(points, colors, tracks)):
            if len(track) < 2:
                continue
            rgb = np.clip(color*255, 0, 255).astype(int)
            f.write(f"{i+1} {point[0]} {point[1]} {point[2]} {rgb[0]} {rgb[1]} {rgb[2]} 0 " + " ".join(f"{image} {pixel}" for image, pixel in track) + "\n")
    if sum(len(t) >= 2 for t in tracks) < 16:
        raise ValueError("Too few depth-verified multi-view correspondences for photo refinement")
    return scene


def executable(name):
    configured = os.environ.get("RESPACE_OPENMVS_BIN")
    bundled = Path(__file__).resolve().parents[1] / ".tools" / "openmvs" / name
    path = Path(configured) / name if configured else bundled
    found = str(path) if path.is_file() else shutil.which(name)
    if not found:
        raise RuntimeError(f"OpenMVS {name} is unavailable; run setup.sh or set RESPACE_OPENMVS_BIN")
    return found


def run_command(command, working):
    with (working / "openmvs.log").open("a") as log:
        log.write("\n" + " ".join(command) + "\n")
        log.flush()
        result = subprocess.run(command, cwd=working, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"{Path(command[0]).name} failed ({result.returncode}); see openmvs.log")


def refine_and_texture(manifest, inputs, baseline, mesh, working):
    progress("photo_import")
    scene = export_colmap(manifest, inputs, mesh, working)
    common = ["--max-threads", "4", "--archive-type", "2"]
    project = working / "scene.mvs"
    run_command([executable("InterfaceCOLMAP"), "-i", str(scene), "-o", str(project), "--image-folder", str(scene / "images"), *common], working)
    progress("photo_refinement")
    refined = working / "refined.mvs"
    run_command([executable("RefineMesh"), str(project), "-m", str(baseline), "-o", str(refined),
        "--resolution-level", "1", "--min-resolution", "640", "--max-views", "4",
        "--close-holes", "0", "--decimate", "1", "--scales", "2", *common], working)
    progress("photo_texturing")
    run_command([executable("TextureMesh"), str(refined), "-m", str(working / "refined.ply"),
        "-o", str(working / "photo.obj"), "--export-type", "obj", "--close-holes", "0",
        "--resolution-level", "1", "--max-texture-size", "4096", "--decimate", "1",
        "--empty-color", "11184810", *common], working)
    if not (working / "photo.obj").is_file():
        raise RuntimeError("OpenMVS did not export its textured OBJ")
    return working / "photo.obj"


def surface_transform(surface):
    transform = surface.get("transform")
    if isinstance(transform, dict):
        transform = transform.get("columns", transform)
    if isinstance(transform, dict):
        transform = [transform.get(f"column{i}") for i in range(4)]
    m = np.asarray(transform, dtype=float)
    if m.size != 16 or not np.isfinite(m).all():
        raise ValueError("Cannot locate semantic surface; completion skipped")
    m = m.reshape((4, 4)).T  # Codable SIMD encodes columns.
    if not np.allclose(m[3], [0,0,0,1], atol=.001) or not np.allclose(m[:3,:3].T @ m[:3,:3], np.eye(3), atol=.01) or abs(np.linalg.det(m[:3,:3])-1)>.01:
        raise ValueError("Semantic surface transform is not rigid")
    return m


def vector3(value):
    if isinstance(value, dict):
        value = [value[k] for k in ("x", "y", "z")]
    vector = np.asarray(value, dtype=float)
    if vector.shape != (3,) or not np.isfinite(vector).all():
        raise ValueError("Invalid semantic surface vector")
    return vector


def semantic_openings(room):
    """Fail closed if a known opening cannot be located in native RoomPlan JSON."""
    boxes = []
    for key in ("doors", "windows", "openings"):
        for opening in room.get(key, []):
            m = surface_transform(opening)
            d = vector3(opening.get("dimensions"))
            boxes.append((np.linalg.inv(m), np.maximum(d/2, .1) + .05))
    return boxes


def inside_polygon(points, polygon):
    inside = np.zeros(len(points), dtype=bool)
    x, y = points[:,0], points[:,1]
    for a, b in zip(polygon, np.roll(polygon, -1, axis=0)):
        if abs(a[1]-b[1]) < 1e-10:
            continue
        crossing = ((a[1] > y) != (b[1] > y)) & (x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1]) + a[0])
        inside ^= crossing
    return inside


def complete_semantic_planes(mesh, room, boxes, o3d):
    """Add only missing cells on detected RoomPlan wall/floor polygons.

    Apple defines polygonCorners in local plane coordinates. This retains those
    transforms/shapes and never extends a patch outside its semantic polygon.
    """
    raycast = o3d.t.geometry.RaycastingScene()
    raycast.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
    vertices, faces = np.asarray(mesh.vertices), np.asarray(mesh.triangles)
    colors = np.asarray(mesh.vertex_colors)
    additions, new_faces, patches = [], [], []
    for kind in ("walls", "floors"):
        for surface in room.get(kind, []):
            # Curved walls cannot be represented faithfully as a plane.
            if surface.get("curve"):
                continue
            transform = surface_transform(surface)
            raw_polygon = surface.get("polygonCorners", surface.get("polygon_corners", []))
            if raw_polygon:
                polygon3 = np.asarray([vector3(p) for p in raw_polygon])
                if abs(polygon3[:,2]).max() > .01:
                    continue
                polygon = polygon3[:,:2]
            else:
                # Floors need their measured polygon to preserve nonrectangular shapes.
                if kind == "floors":
                    continue
                d = vector3(surface.get("dimensions"))
                if d[0] <= 0 or d[1] <= 0:
                    continue
                polygon = np.array([[-d[0]/2,-d[1]/2], [d[0]/2,-d[1]/2], [d[0]/2,d[1]/2], [-d[0]/2,d[1]/2]])
            low, high = polygon.min(axis=0), polygon.max(axis=0)
            if np.any(high-low > 50) or np.any(high-low < .01):
                continue
            x = np.arange(low[0], high[0], .15)
            y = np.arange(low[1], high[1], .15)
            if len(x)*len(y) > 40000:
                continue
            xx, yy = np.meshgrid(x, y)
            lo = np.stack([xx.ravel(), yy.ravel()], axis=1)
            hi = np.minimum(lo + .15, high)
            cells = np.stack([lo, np.stack([hi[:,0], lo[:,1]], axis=1), hi,
                np.stack([lo[:,0], hi[:,1]], axis=1)], axis=1)
            # Inset only for boundary numerical classification, not for emitted geometry.
            centers = cells.mean(axis=1)
            probes = centers[:,None,:] + (cells-centers[:,None,:])*.99999
            valid = inside_polygon(probes.reshape(-1,2), polygon).reshape(-1,4).all(axis=1)
            # Reject cells crossed by a polygon edge, including narrow concavities
            # whose four cell corners could all lie inside the polygon.
            lower, upper = cells.min(axis=1)+1e-6, cells.max(axis=1)-1e-6
            for a, b in zip(polygon, np.roll(polygon, -1, axis=0)):
                enter, leave = np.zeros(len(cells)), np.ones(len(cells))
                possible = np.ones(len(cells), dtype=bool)
                for axis in (0,1):
                    delta = b[axis] - a[axis]
                    if abs(delta) < 1e-10:
                        possible &= (a[axis] >= lower[:,axis]) & (a[axis] <= upper[:,axis])
                    else:
                        t0, t1 = (lower[:,axis]-a[axis])/delta, (upper[:,axis]-a[axis])/delta
                        enter = np.maximum(enter, np.minimum(t0,t1))
                        leave = np.minimum(leave, np.maximum(t0,t1))
                valid &= ~(possible & (leave > enter + 1e-8))
            cells = cells[valid]
            if len(cells) == 0:
                continue
            local = np.concatenate([cells, np.zeros((*cells.shape[:2],1))], axis=2)
            world = local @ transform[:3,:3].T + transform[:3,3]
            protected = np.zeros(len(world), dtype=bool)
            for inverse, half in boxes:
                points = world @ inverse[:3,:3].T + inverse[:3,3]
                protected |= ((points.min(axis=1) <= half) & (points.max(axis=1) >= -half)).all(axis=1)
            centers3 = world.mean(axis=1).astype(np.float32)
            distance = raycast.compute_distance(o3d.core.Tensor(centers3)).numpy()
            missing = world[(distance > .04) & ~protected]
            face_ids = []
            for cell in missing:
                if len(faces) + len(new_faces) + 2 > 500000:
                    break
                offset = len(vertices) + len(additions)*4
                face_ids.extend([len(faces)+len(new_faces), len(faces)+len(new_faces)+1])
                additions.append(cell)
                new_faces.extend([[offset,offset+1,offset+2], [offset,offset+2,offset+3]])
            if face_ids:
                polygon_world = np.c_[polygon, np.zeros(len(polygon))] @ transform[:3,:3].T + transform[:3,3]
                patches.append({"source": "roomplan_" + kind, "source_identifier": surface.get("identifier"),
                    "boundary_vertices": polygon_world.tolist(), "face_indices": face_ids})
    if additions:
        added = np.concatenate(additions)
        mesh.vertices = o3d.utility.Vector3dVector(np.concatenate([vertices, added]))
        mesh.triangles = o3d.utility.Vector3iVector(np.concatenate([faces, np.asarray(new_faces)]))
        if len(colors) != len(vertices):
            colors = np.full_like(vertices, .65)
        mesh.vertex_colors = o3d.utility.Vector3dVector(np.concatenate([colors, np.full_like(added, .65)]))
        mesh.remove_duplicated_vertices()
    return mesh, patches


def process_legacy(folder: Path, revision: int):
    import open3d as o3d
    folder = folder.resolve()
    manifest = Manifest.model_validate_json((folder / "manifest.json").read_text())
    inputs = folder / "inputs"
    working = folder / "work"
    working.mkdir(exist_ok=True)
    output = folder / "results" / str(revision)
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    progress("loading_original")
    original = read_scan(inputs / manifest.scene_mesh.filename, manifest.capture_id, o3d)
    checkpoint = working / "depth.ply"
    progress("depth_fusion")
    if checkpoint.is_file():
        mesh = o3d.io.read_triangle_mesh(str(checkpoint))
    else:
        mesh, _ = fuse(manifest, inputs, o3d)
        if len(mesh.triangles) > 400_000:
            mesh = mesh.simplify_quadric_decimation(400_000)
        mesh = mesh.filter_smooth_taubin(number_of_iterations=2)
        mesh.remove_degenerate_triangles()
        mesh.compute_vertex_normals()
        temporary = working / "depth-in-progress.ply"
        if not o3d.io.write_triangle_mesh(str(temporary), mesh):
            raise ValueError("Could not retain depth checkpoint")
        temporary.replace(checkpoint)
    if len(mesh.triangles) == 0:
        raise ValueError("Empty depth reconstruction")
    progress("hole_repair")
    vertices, faces = np.asarray(mesh.vertices), np.asarray(mesh.triangles).copy()
    repairs = []
    room, boxes = None, None
    try:
        room = json.loads((inputs / manifest.room_export.filename).read_text())
        if not isinstance(room, dict):
            raise ValueError("RoomPlan export must contain an object")
        boxes = semantic_openings(room)
        repaired, candidates = repair_small_holes(vertices, faces)
        for patch in candidates:
            points = np.asarray(patch["boundary_vertices"])
            overlaps = False
            for inverse, half_extents in boxes:
                local = points @ inverse[:3, :3].T + inverse[:3, 3]
                # AABB overlap in the opening's coordinates also protects patches enclosing it.
                if ((local.min(axis=0) <= half_extents) & (local.max(axis=0) >= -half_extents)).all():
                    overlaps = True
                    break
            if not overlaps:
                repairs.append(patch)
        patch_ids = [i for p in repairs for i in p["face_indices"]]
        selected = np.concatenate([faces, repaired[patch_ids]]) if patch_ids else faces
        # Report indices in this actual baseline, after protected candidates were removed.
        offset = len(faces)
        for patch in repairs:
            n = len(patch["face_indices"])
            patch["face_indices"] = list(range(offset, offset+n))
            offset += n
        mesh.triangles = o3d.utility.Vector3iVector(selected)
        progress("semantic_completion")
        mesh, semantic_patches = complete_semantic_planes(mesh, room, boxes, o3d)
        repairs.extend(semantic_patches)
    except (ValueError, KeyError, TypeError, np.linalg.LinAlgError) as exc:
        errors.append({"stage": "hole_repair", "message": str(exc)})
    mesh.compute_vertex_normals()
    baseline = working / "baseline.ply"
    o3d.io.write_triangle_mesh(str(baseline), mesh)
    write_colored_obj(mesh, output)
    final_mesh = mesh
    try:
        photo = refine_and_texture(manifest, inputs, baseline, mesh, working)
        candidate = o3d.io.read_triangle_mesh(str(photo), enable_post_processing=False)
        if len(candidate.triangles) == 0 or not np.isfinite(np.asarray(candidate.vertices)).all():
            raise ValueError("Photo refinement exported invalid geometry")
        if len(candidate.triangles) > 1_000_000:
            raise ValueError("Photo refinement exceeded the mobile viewer triangle budget")
        final_mesh = candidate
        # Move a self-contained, locally generated OBJ/MTL/texture set together.
        for p in working.glob("photo*"):
            if p.suffix.lower() in (".obj", ".mtl", ".png", ".jpg", ".jpeg"):
                shutil.copyfile(p, output / p.name)
        model_name = "photo.obj"
    except Exception as exc:
        errors.append({"stage": "photo_processing", "message": str(exc)})
        model_name = "model.obj"
    measured_face_count = len(final_mesh.triangles)
    generated = o3d.geometry.TriangleMesh()
    generation = None
    try:
        if astra.enabled():
            if not isinstance(room, dict) or boxes is None:
                raise ValueError("Cannot protect RoomPlan openings; Astra generation skipped")
            final_mesh, generated, generation = astra.generate(manifest, inputs, original, final_mesh,
                room, boxes, output / model_name, working, output, o3d, progress)
            model_name = "astra.obj"
    except Exception as exc:
        errors.append({"stage": "astra_generation", "message": str(exc)})
        # Never publish incomplete generated assets if validation/export failed.
        for filename in ("astra.obj", "astra.mtl", "astra-scene.json", "astra-provenance.json"):
            (output / filename).unlink(missing_ok=True)
    progress("quality_report")
    report = quality_report(original, final_mesh, o3d)
    report["stages_failed"] = errors
    report["pipeline_version"] = 2
    report["generation"] = generation
    report["needs_review"] |= bool(len(generated.triangles))
    report["repair_policy"] = "Missing cells on RoomPlan wall/floor polygons plus planar convex loops <=20cm; semantic openings protected; OpenMVS automatic hole closing disabled"
    report["patches"] = repairs
    report["provenance_note"] = "Repair face IDs describe baseline.ply before photo refinement; their final overlay is approximate. All accepted Astra additions are included exactly in the inferred overlay. Neither is an observation confidence map."
    atomic_json(output / "quality.json", report)
    # Transfer patch labels through refinement by closest baseline triangle.
    inferred = [i for p in repairs for i in p["face_indices"]]
    overlay = o3d.geometry.TriangleMesh()
    if inferred:
        raycast = o3d.t.geometry.RaycastingScene()
        raycast.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
        centers = np.asarray(final_mesh.vertices)[np.asarray(final_mesh.triangles)].mean(axis=1).astype(np.float32)
        nearest = raycast.compute_closest_points(o3d.core.Tensor(centers))["primitive_ids"].numpy()
        chosen = np.where(np.isin(nearest, inferred) & (np.arange(len(centers)) < measured_face_count))[0]
        if len(chosen):
            overlay = o3d.geometry.TriangleMesh(final_mesh)
            overlay.remove_triangles_by_mask(~np.isin(np.arange(len(centers)), chosen))
            overlay.remove_unreferenced_vertices()
    if len(generated.triangles):
        overlay += generated
    if len(overlay.triangles):
        o3d.io.write_triangle_mesh(str(output / "inferred.obj"), overlay)
    # Baseline geometry is retained for exact patch provenance and partial-stage inspection.
    shutil.copyfile(baseline, output / "baseline.ply")
    assets = [{"filename": p.name, "byte_length": p.stat().st_size, "sha256": digest(p)}
        for p in sorted(output.iterdir()) if p.is_file() and p.name != "completion.json"]
    if any(a["byte_length"] > 128*1024**2 for a in assets) or sum(a["byte_length"] for a in assets) > 512*1024**2:
        raise ValueError("Result exceeds mobile asset budget; inputs and intermediates are retained")
    result = {"revision": revision, "status": "partially_processed" if errors else "succeeded", "model_filename": model_name,
        "assets": assets, "needs_review": report["needs_review"], "error": "; ".join(e["stage"] + ": " + e["message"] for e in errors) or None,
        "coordinate_system": "arkit_scan_meters_y_up", "quality_filename": "quality.json"}
    result["generation_model"] = generation["model"] if generation else None
    result["generated_triangle_count"] = len(generated.triangles)
    atomic_json(output / "completion.json", result)
    return result


def process(folder: Path, revision: int, generation_id=None):
    mode=os.environ.get("RESPACE_PIPELINE","astra")
    if mode=="astra":
        from .astra_room import process_astra_room
        if generation_id is not None:
            return process_astra_room(folder,revision,generation_id=generation_id)
        return process_astra_room(folder,revision)
    if generation_id is not None:
        raise ValueError("Fresh generation requires the direct OpenAI pipeline")
    if mode=="legacy":return process_legacy(folder,revision)
    if mode!="walkthrough":raise ValueError("Unknown reconstruction pipeline")
    from .walkthrough import process_walkthrough
    return process_walkthrough(folder,revision)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--revision", type=int, required=True)
    parser.add_argument("--generation-id")
    args = parser.parse_args()
    try:
        process(args.job, args.revision, args.generation_id)
    except Exception as exc:
        from .instances import RescanRequired
        (args.job/"work").mkdir(parents=True,exist_ok=True)
        atomic_json(args.job/"work"/"failure.json",{"revision":args.revision,
            "rescan_required":isinstance(exc,RescanRequired),"message":str(exc)[:1000]})
        raise


if __name__ == "__main__":
    main()
