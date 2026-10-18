"""Metric adapters and conservative repair; no scene normalization or rescaling."""
import json
import plistlib

import numpy as np


CAMERA_FLIP = np.diag([1., -1., -1., 1.])


def camera_to_cv_world(metadata):
    return np.asarray(metadata.camera_to_scan_transform).reshape((4, 4), order="F") @ CAMERA_FLIP


def read_scan(path, capture_id, o3d):
    with path.open("rb") as f:
        data = plistlib.load(f)
    if data.get("schemaVersion") != 1 or data.get("captureId") != capture_id or data.get("coordinateSystem") != "arkit_scan_meters_y_up":
        raise ValueError("Unsupported scan mesh coordinates/schema")
    anchors = data["anchors"]
    if not 0 < len(anchors) <= 4096:
        raise ValueError("Invalid mesh anchor count")
    vertices, triangles, offset = [], [], 0
    for a in anchors:
        count, faces = a["vertexCount"], a["triangleCount"]
        if count <= 0 or faces <= 0 or offset + count > 1_000_000:
            raise ValueError("Mesh exceeds vertex limit")
        v = np.frombuffer(a["positions"], dtype="<f4").reshape((-1, 3))
        t = np.frombuffer(a["triangles"], dtype="<u4").reshape((-1, 3))
        m = np.asarray(a["transform"], dtype=float).reshape((4, 4), order="F")
        if len(v) != count or len(t) != faces or t.max() >= count or not np.isfinite(v).all() or not np.isfinite(m).all():
            raise ValueError("Invalid mesh buffers")
        if not np.allclose(m[3], [0, 0, 0, 1], atol=.001) or not np.allclose(m[:3, :3].T @ m[:3, :3], np.eye(3), atol=.01) or abs(np.linalg.det(m[:3, :3]) - 1) > .01:
            raise ValueError("Invalid mesh transform")
        vertices.append(v @ m[:3, :3].T + m[:3, 3])
        triangles.append(t.astype(np.int64) + offset)
        offset += count
    if sum(len(t) for t in triangles) > 2_000_000:
        raise ValueError("Mesh exceeds triangle limit")
    mesh = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(np.concatenate(vertices)), o3d.utility.Vector3iVector(np.concatenate(triangles)))
    mesh.remove_duplicated_vertices()
    mesh.remove_degenerate_triangles()
    mesh.compute_vertex_normals()
    return mesh


def depth_frame(frame, inputs):
    from PIL import Image
    meta = frame.metadata
    artifacts = {a.type: a for a in frame.artifacts}
    if "depth" not in artifacts:
        return None
    depth = np.fromfile(inputs / artifacts["depth"].filename, dtype="<f2").astype(np.float32).reshape(meta.depth_height, meta.depth_width)
    depth[(~np.isfinite(depth)) | (depth < .1) | (depth > 6)] = 0
    if "confidence" in artifacts:
        confidence = np.fromfile(inputs / artifacts["confidence"].filename, dtype=np.uint8).reshape(meta.confidence_height, meta.confidence_width)
        if confidence.shape != depth.shape:
            confidence = np.asarray(Image.fromarray(confidence).resize((meta.depth_width, meta.depth_height), Image.Resampling.NEAREST))
        depth[confidence < 1] = 0
    with Image.open(inputs / artifacts["jpeg"].filename) as photo:
        if photo.size != (meta.width, meta.height):
            raise ValueError("JPEG dimensions disagree with calibration")
        color = np.asarray(photo.convert("RGB").resize((meta.depth_width, meta.depth_height), Image.Resampling.LANCZOS)).copy()
    return depth, color


def masked_world_points(frame, mask, inputs):
    """Backproject registered, confidence-filtered mask depth in scan meters."""
    from PIL import Image
    observation=depth_frame(frame,inputs)
    if observation is None:
        return np.empty((0,3)),0.
    depth,_=observation
    small=np.asarray(Image.fromarray(mask).resize((depth.shape[1],depth.shape[0]),Image.Resampling.NEAREST))
    valid=small & (depth>0)
    y,x=np.nonzero(valid)
    z=depth[y,x]
    meta=frame.metadata
    fx,fy,cx,cy=meta.intrinsics
    camera=np.c_[(x*meta.width/depth.shape[1]-cx)*z/fx,
                 (y*meta.height/depth.shape[0]-cy)*z/fy,z]
    transform=camera_to_cv_world(meta)
    world=camera@transform[:3,:3].T+transform[:3,3]
    return world,float(len(z)/max(1,np.count_nonzero(small)))


def repair_small_holes(vertices, triangles, max_diameter=.20):
    """Fill only planar convex boundary loops <=20cm across; preserve face order.

    No arbitrary watertight closure: real openings and complex/nonmanifold loops
    remain open. Returned face IDs refer to the appended patch triangles.
    """
    edges = np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]])
    _, inverse, count = np.unique(np.sort(edges, axis=1), axis=0, return_inverse=True, return_counts=True)
    boundary = edges[count[inverse] == 1]
    outgoing, incoming = {}, {}
    for a, b in boundary:
        outgoing.setdefault(int(a), []).append(int(b))
        incoming.setdefault(int(b), []).append(int(a))
    visited, patches, loops = set(), [], []
    for start in outgoing:
        if start in visited:
            continue
        loop, current = [], start
        while current not in loop and current not in visited and len(loop) <= 64:
            if len(outgoing.get(current, [])) != 1 or len(incoming.get(current, [])) != 1:
                break
            loop.append(current)
            current = outgoing[current][0]
        visited.update(loop)
        if current != start or not 3 <= len(loop) <= 64:
            continue
        # Reverse to oppose the existing boundary winding.
        loop.reverse()
        points = vertices[loop]
        if np.linalg.norm(np.ptp(points, axis=0)) > max_diameter:
            continue
        _, _, basis = np.linalg.svd(points - points.mean(axis=0), full_matrices=False)
        local = (points - points.mean(axis=0)) @ basis.T
        if abs(local[:, 2]).max() > .005:
            continue
        p = local[:, :2]
        turns = []
        for i in range(len(p)):
            a, b = p[(i+1) % len(p)] - p[i], p[(i+2) % len(p)] - p[(i+1) % len(p)]
            turns.append(a[0]*b[1]-a[1]*b[0])
        if not (min(turns) >= -1e-9 or max(turns) <= 1e-9):
            continue
        indices = []
        for i in range(1, len(loop)-1):
            indices.append(len(triangles) + len(patches))
            patches.append([loop[0], loop[i], loop[i+1]])
        loops.append({"boundary_vertices": points.tolist(), "face_indices": indices})
    if patches:
        triangles = np.concatenate([triangles, np.asarray(patches, dtype=np.int32)])
    return triangles, loops


def quality_report(original, processed, o3d):
    reference = np.asarray(original.vertices)
    derived = np.asarray(processed.vertices)
    dimensions = np.ptp(reference, axis=0)
    result_dimensions = np.ptp(derived, axis=0)
    thresholds = np.maximum(.05, dimensions * .02)
    differences = abs(result_dimensions - dimensions)
    samples = reference[::max(1, len(reference)//20000)].astype(np.float32)
    raycast = o3d.t.geometry.RaycastingScene()
    raycast.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(processed))
    distances = raycast.compute_distance(o3d.core.Tensor(samples)).numpy()
    return {
        "reference": "original_arkit_mesh", "units": "meters", "coordinate_system": "arkit_scan_meters_y_up",
        "reference_spans": dimensions.tolist(), "processed_spans": result_dimensions.tolist(),
        "span_tolerances": thresholds.tolist(), "span_differences": differences.tolist(),
        "needs_review": bool((differences > thresholds).any()),
        "surface_distance_median": float(np.median(distances)), "surface_distance_p95": float(np.percentile(distances, 95)),
        "note": "Axis-aligned room-span comparison, not a measurement of each wall or ground-truth accuracy. Original measurements remain authoritative.",
    }


def write_colored_obj(mesh, folder, stem="model"):
    """A compact face-color atlas makes the depth fallback portable to Model I/O."""
    from PIL import Image
    vertices, faces = np.asarray(mesh.vertices), np.asarray(mesh.triangles)
    colors = np.asarray(mesh.vertex_colors)
    if len(colors) != len(vertices):
        colors = np.full_like(vertices, .65)
    side = int(np.ceil(np.sqrt(len(faces))))
    atlas = np.full((side, side, 3), 165, dtype=np.uint8)
    atlas.reshape(-1, 3)[:len(faces)] = np.clip(colors[faces].mean(axis=1) * 255, 0, 255).astype(np.uint8)
    Image.fromarray(atlas).save(folder / (stem + ".png"))
    (folder / (stem + ".mtl")).write_text(f"newmtl scan\nKd 1 1 1\nmap_Kd {stem}.png\n")
    with (folder / (stem + ".obj")).open("w") as f:
        f.write(f"mtllib {stem}.mtl\nusemtl scan\n")
        np.savetxt(f, vertices, fmt="v %.7f %.7f %.7f")
        for i in range(len(faces)):
            f.write(f"vt {(i % side + .5)/side:.8f} {1-(i//side+.5)/side:.8f}\n")
        for i, face in enumerate(faces):
            f.write("f " + " ".join(f"{v+1}/{i+1}" for v in face) + "\n")
