"""Local encoding of all retained depth frames and the ARKit mesh for Astra.

No reconstruction model or subprocess runs here. Dense measurements are pooled
into weighted metric voxels; source files remain immutable on the user's worker.
"""
import base64
import io
import json

import numpy as np
from PIL import Image

from .astra import compact_mesh, image_limit, select_frames
from .geometry import camera_to_cv_world, depth_frame


def collect_evidence(manifest, inputs, mesh):
    cells, voxel_size, records = {}, .08, []
    valid_count = 0
    for frame in manifest.frames:
        observation = depth_frame(frame, inputs)
        count = 0
        if observation is not None:
            depth, color = observation
            y, x = np.nonzero(depth > 0)
            z = depth[y, x]
            meta = frame.metadata
            fx, fy, cx, cy = meta.intrinsics
            camera = np.c_[(x*meta.width/depth.shape[1]-cx)*z/fx,
                           (y*meta.height/depth.shape[0]-cy)*z/fy, z]
            transform = camera_to_cv_world(meta)
            points = camera @ transform[:3, :3].T + transform[:3, 3]
            count = len(points)
            valid_count += count
            keys, inverse = np.unique(np.floor(points/voxel_size).astype(np.int64), axis=0, return_inverse=True)
            values = np.zeros((len(keys), 7))
            np.add.at(values, inverse, np.c_[points, color[y, x]/255., np.ones(count)])
            for key, value in zip(keys, values):
                key = tuple(key)
                cells[key] = cells.get(key, np.zeros(7)) + value
            # Re-pool sums, never drop a frame or truncate the tail of the scan.
            while len(cells) > 6000:
                pooled = {}
                for key, value in cells.items():
                    key = tuple(k//2 for k in key)
                    pooled[key] = pooled.get(key, np.zeros(7)) + value
                cells = pooled
                voxel_size *= 2
        records.append({"frame_id": frame.id, "valid_depth_pixels": count,
                        "original_image_size": [frame.metadata.width, frame.metadata.height],
                        "intrinsics_fx_fy_cx_cy": frame.metadata.intrinsics,
                        "camera_to_scan_columns": frame.metadata.camera_to_scan_transform})
    if not valid_count:
        raise ValueError("No usable LiDAR data; retain this scan and capture depth coverage")
    voxels = []
    for _, value in sorted(cells.items()):
        voxels.append([*np.round(value[:6]/value[6], 4).tolist(), int(value[6])])
    selected = select_frames(manifest, inputs, image_limit())
    images, photos = [], []
    for frame in selected:
        artifact = next(a for a in frame.artifacts if a.type == "jpeg")
        with Image.open(inputs/artifact.filename) as image:
            image = image.convert("RGB")
            image.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
            stream = io.BytesIO()
            image.save(stream, format="JPEG", quality=85)
            images.append(base64.b64encode(stream.getvalue()).decode("ascii"))
            photos.append({"frame_id": frame.id, "supplied_image_size": list(image.size)})
    try:
        room = json.loads((inputs/manifest.room_export.filename).read_text())
    except (UnicodeError, ValueError):
        room = {"unavailable": "RoomPlan export is not JSON; infer layout from LiDAR, mesh and photos"}
    vertices = np.asarray(mesh.vertices)
    evidence = {"schema_version": 1, "coordinate_system": "arkit_scan_meters_y_up",
                "capture_id": manifest.capture_id,
                "source_mesh_sha256": manifest.scene_mesh.sha256,
                "source_mesh_triangles": len(mesh.triangles),
                "mesh_encoding": "quadric-decimated metric mesh, all anchors considered; not full resolution",
                "arkit_mesh": compact_mesh(mesh), "roomplan": room,
                "raw_mesh_bounds_min": vertices.min(axis=0).round(4).tolist(),
                "raw_mesh_bounds_max": vertices.max(axis=0).round(4).tolist(),
                "depth_encoding": "all valid 0.1-6m, confidence>=1 pixels pooled; columns x,y,z,r,g,b,count",
                "depth_voxel_size_m": voxel_size, "valid_depth_pixel_count": valid_count,
                "lidar_voxels": voxels, "frames": records, "selected_photos": photos}
    return evidence, images
