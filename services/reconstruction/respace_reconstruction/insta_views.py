"""Calibrated CPU previews and independent LiDAR checks for the modeling loop.

Rays have camera Z=1, so t_hit is optical-axis depth in meters, not ray length.
No graphics context, generated code, GPU or pose estimation is involved.
"""
import base64
import io

import numpy as np
from PIL import Image, ImageDraw

from .astra_room import part_mesh, transform
from .geometry import camera_to_cv_world


def rays(metadata, width, height):
    fx, fy, cx, cy = metadata.intrinsics
    sx, sy = width/metadata.width, height/metadata.height
    u, v = np.meshgrid(np.arange(width), np.arange(height))
    directions = np.stack([(u-cx*sx)/(fx*sx), (v-cy*sy)/(fy*sy), np.ones_like(u)], axis=-1)
    pose = camera_to_cv_world(metadata)
    world = directions @ pose[:3, :3].T
    return np.concatenate([np.broadcast_to(pose[:3, 3], world.shape), world], axis=-1).astype(np.float32)


def confident_depth(frame, inputs):
    """Use only registered confidence-2 measurements; never resize confidence."""
    m = frame.metadata
    artifacts = {a.type: a for a in frame.artifacts}
    if not {"depth", "confidence"} <= artifacts.keys():
        return None
    if (m.depth_width, m.depth_height) != (m.confidence_width, m.confidence_height):
        raise ValueError("LiDAR confidence dimensions disagree with depth")
    depth = np.fromfile(inputs/artifacts["depth"].filename, dtype="<f2").reshape(m.depth_height, m.depth_width).astype(float)
    confidence = np.fromfile(inputs/artifacts["confidence"].filename, dtype=np.uint8).reshape(depth.shape)
    depth[(confidence != 2) | ~np.isfinite(depth) | (depth < .1) | (depth >= 5)] = 0
    return depth


def object_mesh(entity, o3d):
    mesh = o3d.geometry.TriangleMesh()
    for part in entity.parts:
        mesh += part_mesh(part, o3d)
    mesh.transform(transform(entity.position, entity.yaw))
    return mesh


def observed_shell_colors(shell, evidence):
    """Approximate shell finishes from nearby captured colored LiDAR voxels.

    Geometry stays immutable. Lighting is baked into these observed RGB estimates;
    this is not inverse rendering or recovered physical material reflectance.
    """
    import open3d as o3d
    from .astra import Color
    voxels = np.asarray(evidence["lidar_voxels"], dtype=float)
    if len(voxels) == 0:
        return
    scene = o3d.t.geometry.RaycastingScene()
    identities = {}
    for entity in shell.entities:
        identity = scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(object_mesh(entity, o3d)))
        identities[identity] = entity.material_id
    hit = scene.compute_closest_points(o3d.core.Tensor(voxels[:, :3].astype(np.float32)))
    distance = np.linalg.norm(hit["points"].numpy()-voxels[:, :3], axis=1)
    materials = {m.id: m for m in shell.materials}
    for identity, material_id in identities.items():
        mask = (hit["geometry_ids"].numpy() == identity) & (distance < .08)
        if mask.sum() >= 8:
            rgb = np.clip(np.median(voxels[mask, 3:6], axis=0), 0, 1)
            materials[material_id].color = Color(r=float(rgb[0]), g=float(rgb[1]), b=float(rgb[2]))


class PreviewScene:
    def __init__(self, plan, meshes):
        import open3d as o3d
        self.o3d = o3d
        self.scene = o3d.t.geometry.RaycastingScene()
        self.owners, self.colors = {}, {}
        materials = {m.id: m for m in plan.materials}
        for entity in plan.entities:
            vertices, faces = meshes[entity.id]
            mesh = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(vertices), o3d.utility.Vector3iVector(faces))
            identity = self.scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
            self.owners[entity.id] = identity
            colors = []
            for part in entity.parts:
                color = materials[getattr(part, "material_id", entity.material_id)].color
                colors.extend([[color.r, color.g, color.b]]*len(part_mesh(part, o3d).triangles))
            self.colors[identity] = np.asarray(colors)

    def cast(self, frame, width, height):
        result = self.scene.cast_rays(self.o3d.core.Tensor(rays(frame.metadata, width, height)))
        return {k: v.numpy() for k, v in result.items()}

    def preview(self, frame, target_id, edge=1280):
        m = frame.metadata
        scale = min(1., edge/max(m.width, m.height))
        width, height = max(1, round(m.width*scale)), max(1, round(m.height*scale))
        hit = self.cast(frame, width, height)
        pixels = np.full((height, width, 3), 235, dtype=np.uint8)
        for owner, colors in self.colors.items():
            mask = hit["geometry_ids"] == owner
            pixels[mask] = np.clip(colors[hit["primitive_ids"][mask]]*255, 0, 255).astype(np.uint8)
        mask = np.isfinite(hit["t_hit"])
        if target_id != "room":
            mask &= hit["geometry_ids"] == self.owners[target_id]
        return Image.fromarray(pixels), mask

    def depth_check(self, frame, inputs, target_id):
        depth = confident_depth(frame, inputs)
        if depth is None:
            return {"frame_id": frame.id, "samples": 0, "passed": False, "reason": "no_confident_depth"}
        hit = self.cast(frame, depth.shape[1], depth.shape[0])
        rendered = hit["t_hit"]
        mask = np.isfinite(rendered) & (depth > 0)
        if target_id != "room":
            mask &= hit["geometry_ids"] == self.owners[target_id]
        count = int(mask.sum())
        difference = np.abs(rendered[mask]-depth[mask])
        fraction = float(np.mean(difference > .15)) if count else 1.
        return {"frame_id": frame.id, "samples": count, "error_over_15cm_fraction": fraction,
                "median_error_m": float(np.median(difference)) if count else None,
                "passed": count >= 16 and fraction <= .20}


def select_views(entity, manifest, inputs, maximum=4):
    """Rank ALL retained views by visible, depth-supported object coverage.

    Require translation between selected cameras. Reserve one view for a final
    check; it never enters an object's construction/correction requests.
    """
    import open3d as o3d
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(object_mesh(entity, o3d)))
    candidates = []
    for frame in manifest.frames:
        depth = confident_depth(frame, inputs)
        if depth is None:
            continue
        # Selection is cheap even for 900 retained photos; use depth resolution.
        hit = scene.cast_rays(o3d.core.Tensor(rays(frame.metadata, depth.shape[1], depth.shape[0])))
        z = hit["t_hit"].numpy()
        visible = np.isfinite(z) & (depth > 0) & (z <= depth+.15)
        count = int(visible.sum())
        if count >= 16:
            candidates.append((count, frame))
    selected = []
    for _, frame in sorted(candidates, key=lambda item: (-item[0], item[1].id)):
        position = camera_to_cv_world(frame.metadata)[:3, 3]
        if any(np.linalg.norm(position-camera_to_cv_world(f.metadata)[:3, 3]) < .15 for f in selected):
            continue
        selected.append(frame)
        if len(selected) == maximum:
            break
    if len(selected) < 3:
        raise ValueError(f"Object {entity.id} needs at least three translated views with confident LiDAR coverage; scan around it again")
    return selected[:-1], selected[-1:]


def encoded(image):
    stream = io.BytesIO()
    image.save(stream, format="JPEG", quality=90)
    return base64.b64encode(stream.getvalue()).decode("ascii")


def paired_content(scene, frames, inputs, target_id, directory):
    """Persist exactly the sensor-basis photo/render pairs sent to the model."""
    directory.mkdir(parents=True, exist_ok=True)
    content, records = [], []
    for index, frame in enumerate(frames):
        render, mask = scene.preview(frame, target_id)
        if int(mask.sum()) < 64:
            raise ValueError(f"Object {target_id} is not sufficiently visible in frame {frame.id}")
        photo_artifact = next(a for a in frame.artifacts if a.type == "jpeg")
        with Image.open(inputs/photo_artifact.filename) as source:
            if source.size != (frame.metadata.width, frame.metadata.height):
                raise ValueError("Photo dimensions disagree with calibration")
            photo = source.convert("RGB").resize(render.size, Image.Resampling.LANCZOS)
        record = {"frame_id": frame.id, "target_id": target_id, "image_size": list(render.size),
                  "source_photo_sha256": photo_artifact.sha256,
                  "source_size": [frame.metadata.width, frame.metadata.height],
                  "intrinsics": frame.metadata.intrinsics,
                  "camera_to_scan_columns": frame.metadata.camera_to_scan_transform,
                  "visible_pixels": int(mask.sum())}
        if target_id != "room":
            y, x = np.nonzero(mask)
            box = (int(x.min()), int(y.min()), int(x.max()), int(y.max()))
            for image in (photo, render):
                ImageDraw.Draw(image).rectangle(box, outline=(255, 0, 255), width=2)
            record["target_rectangle"] = box
        content.append({"type": "input_text", "text": "frame_id="+frame.id+"; PHOTO then CALIBRATED RENDER; magenta rectangle identifies target "+target_id})
        for label, image in (("photo", photo), ("render", render)):
            image.save(directory/f"{index}-{label}.jpg", quality=90)
            content.append({"type": "input_image", "image_url": "data:image/jpeg;base64,"+encoded(image), "detail": "high"})
        records.append(record)
    return content, records
