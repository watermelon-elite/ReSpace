"""Bounded OBJ submesh extraction that preserves face-corner UVs and materials."""
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .models import SAFE_NAME


@dataclass
class TexturedMesh:
    vertices: np.ndarray
    uvs: np.ndarray
    normals: np.ndarray
    faces: list
    materials: list[str]
    libraries: list[str]

    @property
    def triangles(self):
        return np.array([[corner[0] for corner in face] for face in self.faces], dtype=np.int64)


def read_obj(path: Path):
    vertices, uvs, normals, faces, materials, libraries = [], [], [], [], [], []
    current = ""
    if path.stat().st_size > 128*1024**2:
        raise ValueError("Mesh exceeds asset budget")

    def index(value, count):
        number = int(value)
        result = number-1 if number > 0 else count+number
        if number == 0 or not 0 <= result < count:
            raise ValueError("OBJ index is out of bounds")
        return result

    with path.open() as stream:
        for line in stream:
            fields = line.strip().split()
            if not fields or fields[0].startswith("#"):
                continue
            tag, values = fields[0], fields[1:]
            if tag == "v":
                if len(values) < 3:
                    raise ValueError("Malformed OBJ vertex")
                vertices.append([float(v) for v in values[:3]])
            elif tag == "vt":
                if len(values) < 2:
                    raise ValueError("Malformed OBJ texture coordinate")
                uvs.append([float(v) for v in values[:2]])
            elif tag == "vn":
                if len(values) != 3:
                    raise ValueError("Malformed OBJ normal")
                normals.append([float(v) for v in values])
            elif tag == "mtllib":
                if any(not SAFE_NAME.fullmatch(v) or ".." in v for v in values):
                    raise ValueError("Unsafe OBJ material path")
                libraries.extend(values)
            elif tag == "usemtl":
                if len(values) != 1:
                    raise ValueError("Unsupported OBJ material name")
                current = values[0]
            elif tag == "f":
                if len(values) != 3:
                    raise ValueError("Only triangulated reconstruction meshes are supported")
                face = []
                for value in values:
                    parts = value.split("/")
                    if len(parts) > 3:
                        raise ValueError("Malformed OBJ corner")
                    face.append((index(parts[0], len(vertices)),
                                 index(parts[1], len(uvs)) if len(parts) > 1 and parts[1] else None,
                                 index(parts[2], len(normals)) if len(parts) > 2 and parts[2] else None))
                faces.append(face)
                materials.append(current)
            if len(vertices) > 2_000_000 or len(faces) > 1_000_000:
                raise ValueError("Reconstruction exceeds mesh budget")
    if not vertices or not faces:
        raise ValueError("Empty reconstruction mesh")
    v = np.asarray(vertices)
    t = np.asarray(uvs).reshape(-1, 2)
    n = np.asarray(normals).reshape(-1, 3)
    if not all(np.isfinite(array).all() for array in (v, t, n)):
        raise ValueError("Nonfinite mesh attributes")
    return TexturedMesh(v, t, n, faces, materials, list(dict.fromkeys(libraries)))


def write_submesh(mesh, face_ids, destination: Path, local_to_scan=None):
    face_ids = np.asarray(face_ids, dtype=int)
    if len(face_ids) == 0 or face_ids.min() < 0 or face_ids.max() >= len(mesh.faces):
        raise ValueError("Empty or invalid submesh selection")
    faces = [mesh.faces[i] for i in face_ids]
    used = [sorted({corner[axis] for face in faces for corner in face if corner[axis] is not None}) for axis in range(3)]
    maps = [{original: index+1 for index, original in enumerate(ids)} for ids in used]
    vertices = mesh.vertices[used[0]].copy()
    normals = mesh.normals[used[2]].copy()
    if local_to_scan is not None:
        inverse = np.linalg.inv(local_to_scan)
        vertices = vertices @ inverse[:3, :3].T+inverse[:3, 3]
        normals = normals @ inverse[:3, :3].T
    with destination.open("w") as stream:
        for library in mesh.libraries:
            stream.write(f"mtllib {library}\n")
        np.savetxt(stream, vertices, fmt="v %.8f %.8f %.8f")
        if used[1]: np.savetxt(stream, mesh.uvs[used[1]], fmt="vt %.8f %.8f")
        if len(normals): np.savetxt(stream, normals, fmt="vn %.8f %.8f %.8f")
        material = None
        for face, source_id in zip(faces, face_ids):
            current = mesh.materials[source_id]
            if current != material and current:
                stream.write(f"usemtl {current}\n")
                material = current
            corners = []
            for v, t, n in face:
                token = str(maps[0][v])
                if t is not None or n is not None:
                    token += "/"+(str(maps[1][t]) if t is not None else "")
                    if n is not None: token += "/"+str(maps[2][n])
                corners.append(token)
            stream.write("f "+" ".join(corners)+"\n")
    return vertices, sorted({mesh.materials[i] for i in face_ids})
