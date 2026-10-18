"""Versioned editable scene contract. Identities belong to the scene, not OBJ faces."""
from pathlib import Path
from typing import Annotated, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import SAFE_NAME

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")]
Vector3 = Annotated[list[float], Field(min_length=3, max_length=3)]
Matrix4 = Annotated[list[float], Field(min_length=16, max_length=16)]


class SceneContract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


def matrix(value):
    return np.asarray(value, dtype=float).reshape(4, 4, order="F")


def rigid(value):
    m = matrix(value)
    return (np.isfinite(m).all() and np.allclose(m[3], [0, 0, 0, 1], atol=1e-5)
            and np.allclose(m[:3, :3].T @ m[:3, :3], np.eye(3), atol=.001)
            and abs(np.linalg.det(m[:3, :3])-1) < .001)


def point_inside(point, polygon):
    """Even/odd containment; wall/floor boundaries are deliberately not walkable."""
    x, z = point
    inside = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if (a[1] > z) != (b[1] > z) and x < (b[0]-a[0])*(z-a[1])/(b[1]-a[1])+a[0]:
            inside = not inside
    return inside


class SceneMaterial(SceneContract):
    id: Identifier
    owner_id: Identifier
    slot: str = Field(min_length=1, max_length=128)
    source_material: str = Field(max_length=256)
    base_color: Vector3 = Field(default_factory=lambda: [1., 1., 1.])
    finish: Literal["captured", "paint", "tile", "wallpaper"] = "captured"
    repeat_meters: float = Field(default=.25, ge=.01, le=10)

    @model_validator(mode="after")
    def color(self):
        if not all(0 <= v <= 1 for v in self.base_color):
            raise ValueError("Material color must be in [0,1]")
        return self


class SceneEntity(SceneContract):
    id: Identifier
    source_object_id: str | None = Field(default=None, max_length=256)
    label: str = Field(min_length=1, max_length=256)
    category: str = Field(min_length=1, max_length=64)
    kind: Literal["wall", "floor", "ceiling", "fixed", "furniture", "wall_decor"]
    asset: Identifier
    local_to_scan_transform: Matrix4
    # Bounds in object coordinates; unlike design size these are XYZ, not W/D/H.
    bounds_min: Vector3
    bounds_max: Vector3
    material_ids: list[Identifier] = Field(min_length=1, max_length=128)
    support_id: Identifier | None = None
    visible: bool = True
    move_ready: bool = False
    finish_ready: bool = False
    collidable: bool = True
    surface_polygons: list[list[list[float]]] = Field(default_factory=list,max_length=64)
    surface_holes: list[list[list[float]]] = Field(default_factory=list,max_length=64)
    observed_fraction: float = Field(ge=0, le=1)

    @property
    def movable(self):
        return self.kind in ("furniture", "wall_decor")

    @model_validator(mode="after")
    def geometry(self):
        if not rigid(self.local_to_scan_transform):
            raise ValueError("Entity transform must be rigid in scan meters")
        extent = np.array(self.bounds_max)-self.bounds_min
        if (extent < 0).any() or max(extent) <= .001 or max(extent) > 50:
            raise ValueError("Invalid entity bounds")
        if len(set(self.material_ids)) != len(self.material_ids):
            raise ValueError("Duplicate material bindings")
        if self.move_ready and not self.movable:
            raise ValueError("Room structure and built-ins cannot move")
        if not self.asset.endswith(".obj"):
            raise ValueError("This scene schema currently supports validated OBJ assets")
        if self.kind == "wall_decor" and not self.support_id:
            raise ValueError("Wall decor requires a supporting wall")
        return self


class Navigation(SceneContract):
    floor_polygons: list[list[list[float]]] = Field(min_length=1, max_length=64)
    floor_height: float
    spawn_position: Vector3
    spawn_yaw: float
    eye_height: float = Field(default=1.6, ge=.5, le=2.2)
    player_radius: float = Field(default=.2, ge=.1, le=.5)
    obstacles: list[list[list[float]]] = Field(default_factory=list, max_length=4096)

    @model_validator(mode="after")
    def polygons(self):
        for polygon in self.floor_polygons:
            p = np.asarray(polygon)
            if p.ndim != 2 or p.shape[1] != 2 or not 3 <= len(p) <= 4096 or not np.isfinite(p).all():
                raise ValueError("Invalid floor polygon")
            area = abs(np.sum(p[:, 0]*np.roll(p[:, 1], -1)-p[:, 1]*np.roll(p[:, 0], -1)))/2
            if not .1 <= area <= 2500:
                raise ValueError("Invalid floor area")
        if not any(point_inside([self.spawn_position[0], self.spawn_position[2]], p) for p in self.floor_polygons):
            raise ValueError("Camera spawn must be on the room floor")
        if abs(self.spawn_position[1] - self.floor_height - self.eye_height) > .01:
            raise ValueError("Camera spawn must preserve eye height")
        for obstacle in self.obstacles:
            p=np.asarray(obstacle)
            if p.ndim!=2 or p.shape[1]!=2 or len(p)<3 or not np.isfinite(p).all():
                raise ValueError("Invalid navigation obstacle")
        return self


class SceneBundle(SceneContract):
    schema_version: Literal[2] = 2
    capture_id: Identifier
    scene_id: Identifier
    reconstruction_revision: int = Field(gt=0)
    design_revision: int = Field(default=0, ge=0)
    parent_design_revision: int | None = Field(default=None, ge=0)
    coordinate_system: Literal["arkit_scan_meters_y_up"] = "arkit_scan_meters_y_up"
    entities: list[SceneEntity] = Field(min_length=1, max_length=512)
    materials: list[SceneMaterial] = Field(min_length=1, max_length=4096)
    navigation: Navigation
    quality_filename: Identifier = "quality.json"
    provenance_filename: Identifier = "provenance.json"
    ready: bool = False

    @model_validator(mode="after")
    def references(self):
        entities = {e.id: e for e in self.entities}
        materials = {m.id: m for m in self.materials}
        if len(entities) != len(self.entities) or len(materials) != len(self.materials):
            raise ValueError("Scene identities must be unique")
        if any(m.owner_id not in entities for m in self.materials):
            raise ValueError("Material owner does not exist")
        for e in self.entities:
            for identifier in e.material_ids:
                if identifier not in materials or materials[identifier].owner_id != e.id:
                    raise ValueError("Material bindings must be owned by the selected entity")
            if e.support_id:
                support = entities.get(e.support_id)
                if support is None or e.kind == "wall_decor" and support.kind != "wall":
                    raise ValueError("Invalid support relationship")
        if self.ready and any(e.movable and not e.move_ready for e in self.entities):
            raise ValueError("A finished room requires ready movable items")
        return self

    def validate_files(self, folder: Path, filenames: set[str]):
        required = {e.asset for e in self.entities} | {self.quality_filename, self.provenance_filename}
        if not required <= filenames:
            raise ValueError("Scene references an uncommitted asset")
        for name in filenames:
            if not SAFE_NAME.fullmatch(name) or ".." in name or not (folder / name).is_file():
                raise ValueError("Scene asset path is invalid")
        # OBJ/MTL dependency allowlist is checked without allowing external URLs.
        for name in filenames:
            path = folder / name
            if path.suffix.lower() not in (".obj", ".mtl"):
                continue
            for line in path.read_text().splitlines():
                fields = line.strip().split()
                if not fields:
                    continue
                if fields[0] == "mtllib":
                    dependencies = fields[1:]
                elif fields[0].lower().startswith("map_") or fields[0].lower() in ("bump", "disp", "decal"):
                    # Exporter uses plain filenames; reject option-bearing texture statements.
                    dependencies = fields[1:]
                    if len(dependencies) != 1:
                        raise ValueError("Unsupported texture options")
                else:
                    continue
                if not dependencies or any(d not in filenames for d in dependencies):
                    raise ValueError("Uncommitted mesh/material dependency")
        return self


def world_bounds(entity):
    m = matrix(entity.local_to_scan_transform)
    lo, hi = entity.bounds_min, entity.bounds_max
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    p = corners @ m[:3, :3].T + m[:3, 3]
    return p.min(axis=0), p.max(axis=0)
