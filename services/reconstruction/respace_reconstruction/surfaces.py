"""Measured room shells, occlusion-safe photo baking and bounded mesh closure."""
from dataclasses import dataclass
from pathlib import Path

import mapbox_earcut
import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, gaussian_filter
from shapely import Polygon, contains_xy

from .geometry import camera_to_cv_world, depth_frame
from .instances import RescanRequired, project, stable_id
from .pipeline import surface_transform, vector3


@dataclass
class Surface:
    id: str
    source_id: str
    kind: str
    transform: np.ndarray
    polygon: object


def triangulate(polygon):
    vertices, faces = [], []
    polygons = list(polygon.geoms) if polygon.geom_type == "MultiPolygon" else [polygon]
    for part in polygons:
        if part.is_empty or part.area < 1e-6:
            continue
        rings = [np.asarray(part.exterior.coords)[:-1]] + [np.asarray(r.coords)[:-1] for r in part.interiors]
        points = np.concatenate(rings).astype(np.float64)
        indices = mapbox_earcut.triangulate_float64(points, np.cumsum([len(r) for r in rings], dtype=np.uint32)).reshape(-1, 3)
        # Earcut is checked against the actual polygon, including all holes.
        area = sum(Polygon(points[t]).area for t in indices)
        if abs(area-part.area) > max(1e-6, part.area*1e-5) or any(not part.buffer(1e-8).covers(Polygon(points[t])) for t in indices):
            raise RescanRequired("The room boundary could not be triangulated safely")
        faces.extend(indices + len(vertices))
        vertices.extend(points)
    return np.c_[np.asarray(vertices), np.zeros(len(vertices))], np.asarray(faces, dtype=np.int32)


def room_surfaces(room):
    result = []
    for key, kind in (("walls", "wall"), ("floors", "floor")):
        for item in room.get(key, []):
            if item.get("curve"):
                raise RescanRequired("Curved room surfaces require another reconstruction method")
            transform = surface_transform(item)
            raw = item.get("polygonCorners", item.get("polygon_corners", []))
            if raw:
                points = np.array([vector3(p) for p in raw])
                if abs(points[:, 2]).max() > .01:
                    raise RescanRequired("Room polygon is not planar")
                polygon = Polygon(points[:, :2])
            else:
                if kind == "floor":
                    raise RescanRequired("The scan did not retain the room floor boundary")
                d = vector3(item["dimensions"])
                polygon = Polygon([[-d[0]/2, -d[1]/2], [d[0]/2, -d[1]/2], [d[0]/2, d[1]/2], [-d[0]/2, d[1]/2]])
            if not polygon.is_valid or not .1 <= polygon.area <= 2500:
                raise RescanRequired("The room has an invalid surface boundary")
            if kind == "floor" and abs(transform[1, 2]) < .99:
                raise RescanRequired("The floor is not horizontal")
            if kind == "wall":
                inverse = np.linalg.inv(transform)
                for opening in sum([room.get(k, []) for k in ("doors", "windows", "openings")], []):
                    pose, d = surface_transform(opening), vector3(opening["dimensions"])
                    if abs(np.dot(pose[:3, 2], transform[:3, 2])) < .95:
                        continue
                    corners = np.array([[-d[0]/2, -d[1]/2, 0], [d[0]/2, -d[1]/2, 0], [d[0]/2, d[1]/2, 0], [-d[0]/2, d[1]/2, 0]])
                    points = corners @ pose[:3, :3].T + pose[:3, 3]
                    local = points @ inverse[:3, :3].T + inverse[:3, 3]
                    if abs(local[:, 2]).max() < .15:
                        polygon = polygon.difference(Polygon(local[:, :2]))
            identifier = str(item.get("identifier", ""))
            if polygon.is_empty or not polygon.is_valid or polygon.area<.01:
                raise RescanRequired("The measured wall has no usable surface around its openings")
            if not identifier:
                raise RescanRequired("A room surface has no stable identity")
            result.append(Surface(stable_id(kind, identifier), identifier, kind, transform, polygon))
    floors = [s for s in result if s.kind == "floor"]
    walls = [s for s in result if s.kind == "wall"]
    if len(floors) != 1 or len(walls) < 3:
        raise RescanRequired("Capture one complete room with its floor and walls")
    floor = floors[0]
    tops = []
    for wall in walls:
        v, _ = triangulate(wall.polygon)
        tops.append((v @ wall.transform[:3, :3].T + wall.transform[:3, 3])[:, 1].max())
    ceiling = floor.transform.copy()
    ceiling[1, 3] = float(np.median(tops))
    if not 1.8 <= ceiling[1, 3]-floor.transform[1, 3] <= 8:
        raise RescanRequired("The room height could not be established")
    result.append(Surface(stable_id("ceiling", floor.source_id), floor.source_id, "ceiling", ceiling, floor.polygon))
    return result


def fill_texture(rgb, known):
    """Continue source boundary colors without modifying any observed pixels."""
    if np.count_nonzero(known) < 64:
        raise RescanRequired("Capture more of the wall, floor or ceiling finish")
    indices = distance_transform_edt(~known, return_distances=False, return_indices=True)
    result = rgb[tuple(indices)].astype(np.float32)
    # Boundary-conditioned harmonic continuation; observed pixels are immutable.
    for sigma in (16, 8, 4, 2, 1):
        for _ in range(4):
            smooth = gaussian_filter(result, (sigma, sigma, 0), mode="nearest")
            result[~known] = smooth[~known]
            result[known] = rgb[known]
    return np.clip(result, 0, 255).astype(np.uint8)


class PhotoBaker:
    def __init__(self, manifest, inputs, exclusions=None, limit=32):
        self.inputs, self.exclusions = inputs, exclusions or {}
        indices = np.linspace(0, len(manifest.frames)-1, min(limit, len(manifest.frames)), dtype=int)
        self.frames = [manifest.frames[i] for i in indices]
        self.depths = {}
        self.images = {}

    def source(self, frame):
        if frame.id not in self.depths:
            self.depths[frame.id] = depth_frame(frame, self.inputs)
        if frame.id not in self.images:
            photo = next(a for a in frame.artifacts if a.type == "jpeg")
            with Image.open(self.inputs/photo.filename) as image:
                self.images[frame.id] = np.array(image.convert("RGB"))
        return self.depths[frame.id], self.images[frame.id]

    def sample(self, points, frame, clean=False):
        observation, image = self.source(frame)
        uv, z = project(points, frame.metadata)
        x = np.floor(uv[:, 0]).astype(int); y = np.floor(uv[:, 1]).astype(int)
        valid = (z > .1) & (x >= 0) & (x < image.shape[1]) & (y >= 0) & (y < image.shape[0])
        ids = np.flatnonzero(valid)
        valid[:] = False
        if observation is None:
            return uv, valid, np.zeros((len(points), 3), dtype=np.uint8)
        depth, _ = observation
        dx = np.clip((uv[ids, 0]*depth.shape[1]/frame.metadata.width).astype(int), 0, depth.shape[1]-1)
        dy = np.clip((uv[ids, 1]*depth.shape[0]/frame.metadata.height).astype(int), 0, depth.shape[0]-1)
        measured = depth[dy, dx]
        ids = ids[(measured > 0) & (abs(measured-z[ids]) < np.maximum(.035, z[ids]*.015))]
        if clean and frame.id in self.exclusions:
            mask = self.exclusions[frame.id]
            mx = np.clip((uv[ids, 0]*mask.shape[1]/frame.metadata.width).astype(int), 0, mask.shape[1]-1)
            my = np.clip((uv[ids, 1]*mask.shape[0]/frame.metadata.height).astype(int), 0, mask.shape[0]-1)
            ids = ids[~mask[my, mx]]
        valid[ids] = True
        color = np.zeros((len(points), 3), dtype=np.uint8)
        color[ids] = image[y[ids], x[ids]]
        return uv, valid, color

    def plane(self, surface, folder, blocked=(), ppm=256):
        lo = np.array(surface.polygon.bounds[:2]); hi = np.array(surface.polygon.bounds[2:])
        width, height = np.clip(np.ceil((hi-lo)*ppm).astype(int), 64, 2048)
        xx, yy = np.meshgrid(np.linspace(lo[0], hi[0], width), np.linspace(hi[1], lo[1], height))
        xy = np.c_[xx.ravel(), yy.ravel()]
        domain = contains_xy(surface.polygon, xy[:, 0], xy[:, 1])
        permitted = domain.copy()
        for polygon in blocked:
            permitted &= ~contains_xy(polygon.buffer(.015), xy[:, 0], xy[:, 1])
        points = np.c_[xy, np.zeros(len(xy))] @ surface.transform[:3, :3].T + surface.transform[:3, 3]
        color = np.zeros((len(points), 3), dtype=np.uint8)
        best = np.zeros(len(points))
        for frame in self.frames:
            _, valid, rgb = self.sample(points, frame, clean=True)
            camera = camera_to_cv_world(frame.metadata)[:3, 3]
            ray = camera-points
            distance = np.linalg.norm(ray, axis=1)
            angle = abs(ray @ surface.transform[:3, 2])/np.maximum(distance, .001)
            score = angle/np.maximum(distance, .3)**2
            chosen = valid & permitted & (angle > .15) & (score > best)
            color[chosen] = rgb[chosen]; best[chosen] = score[chosen]
        known = (best > 0).reshape(height, width)
        if np.count_nonzero(known)/max(1, domain.sum()) < .03:
            raise RescanRequired("Capture more unobstructed views of the "+surface.kind)
        texture = fill_texture(color.reshape(height, width, 3), known)
        name = surface.id
        Image.fromarray(texture).save(folder/(name+".png"))
        vertices, faces = triangulate(surface.polygon)
        uvs = (vertices[:, :2]-lo)/(hi-lo)
        write_obj(folder/(name+".obj"), vertices, faces, uvs, np.arange(len(vertices)), name)
        (folder/(name+".mtl")).write_text(f"newmtl {name}\nKd 1 1 1\nmap_Kd {name}.png\n")
        return vertices, faces, float(np.count_nonzero(known)/max(1, domain.sum()))


def write_obj(path, vertices, faces, uvs, uv_indices, material):
    with path.open("w") as stream:
        stream.write(f"mtllib {path.stem}.mtl\nusemtl {material}\n")
        np.savetxt(stream, vertices, fmt="v %.8f %.8f %.8f")
        np.savetxt(stream, uvs, fmt="vt %.8f %.8f")
        for face in faces:
            stream.write("f "+" ".join(f"{v+1}/{uv_indices[v]+1}" for v in face)+"\n")


def close_observed(mesh):
    """Cap simple occlusion boundaries, retaining every observed vertex/face.

    Complex/nonplanar boundaries require the configured completion provider.
    Never substitute a box, convex hull, or a different furniture asset.
    """
    import open3d as o3d
    result = o3d.geometry.TriangleMesh(mesh)
    result.remove_duplicated_vertices(); result.remove_degenerate_triangles()
    result.remove_duplicated_triangles(); result.remove_unreferenced_vertices()
    result.orient_triangles()
    vertices, original = np.asarray(result.vertices).copy(), np.asarray(result.triangles).copy()
    edges = np.concatenate([original[:, [0, 1]], original[:, [1, 2]], original[:, [2, 0]]])
    _, inverse, counts = np.unique(np.sort(edges, axis=1), axis=0, return_inverse=True, return_counts=True)
    if counts.max() > 2:
        raise RescanRequired("Object surface has nonmanifold intersections")
    boundary = edges[counts[inverse] == 1]
    outgoing, incoming = {}, {}
    for a, b in boundary:
        outgoing.setdefault(int(a), []).append(int(b)); incoming.setdefault(int(b), []).append(int(a))
    if any(len(v) != 1 for v in outgoing.values()) or any(len(v) != 1 for v in incoming.values()):
        raise RescanRequired("Object boundary is fragmented; capture its sides more clearly")
    visited, additions = set(), []
    for start in outgoing:
        if start in visited: continue
        loop, current = [], start
        while current not in visited:
            visited.add(current); loop.append(current); current = outgoing[current][0]
        if current != start or not 3 <= len(loop) <= 8192:
            raise RescanRequired("Object boundary could not be completed")
        loop.reverse()
        points = vertices[loop]
        _, _, basis = np.linalg.svd(points-points.mean(axis=0), full_matrices=False)
        local = (points-points.mean(axis=0)) @ basis.T
        if abs(local[:, 2]).max() > max(.015, np.linalg.norm(np.ptp(points, axis=0))*.03):
            raise RescanRequired("A completion model is required for the unseen object surfaces")
        polygon = Polygon(local[:, :2])
        if not polygon.is_valid:
            raise RescanRequired("Object boundary intersects itself")
        indices = mapbox_earcut.triangulate_float64(local[:, :2].copy(), np.array([len(loop)], dtype=np.uint32)).reshape(-1, 3)
        patch = np.asarray(loop)[indices]
        # Orient each new face against the existing directed boundary.
        direction = {tuple(edge) for edge in zip(loop, loop[1:]+loop[:1])}
        for face in patch:
            for a, b in zip(face, np.roll(face, -1)):
                if (int(a), int(b)) in direction: break
                if (int(b), int(a)) in direction:
                    face[1], face[2] = face[2], face[1]; break
        additions.extend(patch)
    if additions:
        result.triangles = o3d.utility.Vector3iVector(np.concatenate([original, additions]))
    result.compute_vertex_normals()
    if not result.is_watertight() or result.is_self_intersecting():
        raise RescanRequired("Completed object geometry failed surface checks")
    if abs(result.get_volume())<1e-8:
        raise RescanRequired("A flat captured fragment is not a completed three-dimensional object")
    return result, len(original)
