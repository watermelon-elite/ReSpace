"""Project original photos onto depth-visible generated faces, preserving PBR slots.

No image/model service is called. Unseen/misaligned faces retain the object's
material instead of inventing photographic detail or stretching unrelated pixels.
"""
import hashlib
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy.ndimage import distance_transform_edt

from .geometry import camera_to_cv_world
from .instances import project
from .obj import read_obj
from .scene import SceneMaterial, matrix
from .surfaces import PhotoBaker


def texture_furnishings(bundle, manifest, inputs, output, object_reports=()):
    reports = []
    bindings = {m.id: m for m in bundle.materials}
    object_details = {r["entity_id"]: r for r in object_reports}
    for entity in bundle.entities:
        if entity.kind in ("wall", "floor", "ceiling") or entity.category == "mirror":
            continue
        mesh = read_obj(output/entity.asset)
        vertices, faces = mesh.vertices, mesh.triangles
        pose = matrix(entity.local_to_scan_transform)
        world = vertices @ pose[:3, :3].T+pose[:3, 3]
        triangles = world[faces]
        centers = triangles.mean(axis=1)
        normals = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
        areas = np.linalg.norm(normals, axis=1)/2
        normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-10)
        material_by_name = {bindings[i].source_material: bindings[i] for i in entity.material_ids}
        eligible = np.array([material_by_name[name].metallic < .7 and material_by_name[name].roughness > .12 for name in mesh.materials])
        # Candidate ranking is object-specific; a whole-room sampling sequence
        # should not miss an object's close-up photos.
        candidates = []
        details = object_details.get(entity.id, {})
        exclusions = {}
        for exclusion in details.get("photo_exclusions", []):
            mask = Image.new("L", (256, 256)); draw = ImageDraw.Draw(mask)
            for polygon in exclusion["polygons"]:
                draw.polygon([(u*255, v*255) for u, v in polygon], fill=1)
            prior = exclusions.get(exclusion["frame_id"], np.zeros((256, 256), dtype=bool))
            exclusions[exclusion["frame_id"]] = prior | np.array(mask, dtype=bool)
        for frame in manifest.frames:
            if details.get("photo_frame_ids") and frame.id not in details["photo_frame_ids"]:
                continue
            uv, z = project(centers.mean(axis=0)[None], frame.metadata)
            if z[0] <= .1 or not (0 <= uv[0, 0] < frame.metadata.width and 0 <= uv[0, 1] < frame.metadata.height):
                continue
            distance = np.linalg.norm(camera_to_cv_world(frame.metadata)[:3, 3]-centers.mean(axis=0))
            candidates.append((distance, frame))
        chosen = []
        for _, frame in sorted(candidates, key=lambda v: v[0]):
            p = camera_to_cv_world(frame.metadata)
            if any(np.linalg.norm(p[:3, 3]-camera_to_cv_world(f.metadata)[:3, 3]) < .15 for f in chosen):
                continue
            chosen.append(frame)
            if len(chosen) == 6:
                break
        baker = PhotoBaker(manifest, inputs, exclusions=exclusions, limit=1)
        baker.frames = chosen
        best, sources = np.zeros(len(faces)), np.full(len(faces), -1, dtype=int)
        uvs = {}
        for index, frame in enumerate(chosen):
            _, visible, _ = baker.sample(centers, frame, clean=True)
            corner_uv, corner_visible, _ = baker.sample(world, frame, clean=True)
            in_bounds = ((corner_uv[:, 0] >= 0) & (corner_uv[:, 0] < frame.metadata.width)
                         & (corner_uv[:, 1] >= 0) & (corner_uv[:, 1] < frame.metadata.height))
            ray = camera_to_cv_world(frame.metadata)[:3, 3]-centers
            distance = np.linalg.norm(ray, axis=1)
            angle = np.abs(np.sum(normals*ray, axis=1))/np.maximum(distance, .01)
            score = angle/np.maximum(distance, .1)**2
            valid = (eligible & visible & in_bounds[faces].all(axis=1)
                     & (corner_visible[faces].sum(axis=1) >= 2) & (angle > .15) & (score > best))
            sources[valid], best[valid] = index, score[valid]
            uvs[index] = corner_uv/[frame.metadata.width, frame.metadata.height]
        known = sources >= 0
        fraction = float(areas[known].sum()/max(areas.sum(), 1e-10))
        reports.append({"entity_id": entity.id, "photo_surface_fraction": fraction,
                        "textured_faces": int(known.sum()), "total_faces": len(faces),
                        "unseen_finish": "generated_PBR_material"})
        if not known.any():
            continue
        photo_names = {}
        for index in set(sources[known]):
            frame = chosen[index]
            artifact = next(a for a in frame.artifacts if a.type == "jpeg")
            name = "photo-"+artifact.sha256[:24]+".jpg"
            excluded = exclusions.get(frame.id)
            if excluded is not None and excluded.any():
                name = name[:-4]+"-"+hashlib.sha256(excluded.tobytes()).hexdigest()[:8]+".jpg"
            if not (output/name).exists():
                with Image.open(inputs/artifact.filename) as image:
                    image = image.convert("RGB"); image.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
                    if excluded is not None and excluded.any():
                        mask = np.array(Image.fromarray(excluded).resize(image.size, Image.Resampling.NEAREST), dtype=bool)
                        if mask.all():
                            raise ValueError("Cannot texture an entirely excluded photo")
                        pixels = np.array(image)
                        nearest = distance_transform_edt(mask, return_distances=False, return_indices=True)
                        pixels[mask] = pixels[tuple(nearest[:, mask])]
                        softened = np.array(Image.fromarray(pixels).filter(ImageFilter.GaussianBlur(2)))
                        pixels[mask] = softened[mask]
                        image = Image.fromarray(pixels)
                    image.save(output/name, quality=95)
            photo_names[index] = name
        new_bindings, materials, face_names = {}, [], []
        for face_index, original_name in enumerate(mesh.materials):
            original = material_by_name[original_name]
            index = sources[face_index]
            name = original_name+("-p"+str(index) if index >= 0 else "-plain")
            face_names.append(name)
            if name in new_bindings:
                continue
            color = [1., 1., 1.] if index >= 0 else original.base_color
            binding = SceneMaterial(id=name, owner_id=entity.id, slot=original.slot, source_material=name,
                                    base_color=color, roughness=original.roughness, metallic=original.metallic)
            new_bindings[name] = binding
            materials.append(f"newmtl {name}\nKd {' '.join(map(str, color))}\nPr {original.roughness}\nPm {original.metallic}\n")
            if index >= 0:
                materials.append("map_Kd "+photo_names[index]+"\n")
        if len(new_bindings) > 128:
            raise ValueError("Photo material slots exceed the native entity budget")
        with (output/entity.asset).open("w") as stream:
            stream.write(f"mtllib {entity.asset[:-4]}.mtl\n")
            np.savetxt(stream, vertices, fmt="v %.8f %.8f %.8f")
            for face_index, face in enumerate(faces):
                index = sources[face_index]
                uv = uvs[index][face].copy() if index >= 0 else np.array([[0., 0.], [1., 0.], [0., 1.]])
                uv[:, 1] = 1-uv[:, 1]
                np.savetxt(stream, uv, fmt="vt %.8f %.8f")
            for name in new_bindings:
                stream.write("usemtl "+name+"\n")
                for i in np.flatnonzero(np.array(face_names) == name):
                    stream.write("f "+" ".join(f"{v+1}/{i*3+j+1}" for j, v in enumerate(faces[i]))+"\n")
        (output/(entity.asset[:-4]+".mtl")).write_text("".join(materials))
        bundle.materials = [m for m in bundle.materials if m.owner_id != entity.id]+list(new_bindings.values())
        entity.material_ids = list(new_bindings)
    return reports
