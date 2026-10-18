"""Validated placement-ready room.json, using room-reconstruction-json.md v2.

The native viewer retains scan coordinates. This export uses the authoritative
RoomPlan floor origin and the same bottom-centered local OBJ assets. Applying
room_from_world to the native scene produces these exact node transforms.
"""
import math
from typing import Annotated, Literal

import numpy as np
from pydantic import Field, model_validator
from shapely import LineString, MultiPoint, Point, Polygon, union_all
from shapely.geometry.polygon import orient

from .categories import CATEGORIES, category
from .pipeline import surface_transform, vector3
from .scene import SceneContract, SceneMaterial, Identifier, Vector3, Matrix4, rigid
from .store import atomic_json
from .instances import stable_id

Point2 = Annotated[list[float], Field(min_length=2, max_length=2)]
Ring = Annotated[list[Point2], Field(min_length=4, max_length=4097)]


def ring(points):
    return [list(p) for p in orient(Polygon(points), sign=1).exterior.coords]


def polygon_valid(points):
    polygon = Polygon(points)
    return points[0] == points[-1] and polygon.is_valid and polygon.area > 1e-8 and polygon.exterior.is_ccw


def polygons(shape):
    if shape.geom_type == "Polygon":
        return [shape] if not shape.is_empty else []
    return [p for part in getattr(shape, "geoms", []) for p in polygons(part)]


def footprint(entity):
    half = np.array(entity.size[:2])/2
    corners = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]])*half
    c, s = math.cos(entity.yaw), math.sin(entity.yaw)
    return Polygon(corners @ np.array([[c, -s], [s, c]])+entity.center)


def surface_shape(surface):
    return Polygon(surface.polygon, surface.holes)


def order_walls(walls):
    remaining = list(walls)
    if len(remaining) < 3:
        raise ValueError("A room requires at least three perimeter walls")
    ordered = [remaining.pop(0)]
    while remaining:
        matches = [w for w in remaining if np.linalg.norm(np.array(w.a)-ordered[-1].b) <= .02]
        if len(matches) != 1:
            raise ValueError("Measured walls must join in one closed loop within 2 cm")
        ordered.append(matches[0])
        remaining.remove(matches[0])
    return ordered


def partition_headroom(shape, top, identity, world, height, ceiling_id):
    """Split at overhead boundaries; each region keeps its own lowest limiter."""
    covers = {}
    minx, minz, maxx, maxz = shape.bounds
    for other_id, (vertices, faces) in world.items():
        if other_id == ceiling_id:
            continue
        triangles = vertices[faces]
        lower, upper = triangles.min(axis=1), triangles.max(axis=1)
        minimum = top+.02 if other_id == identity else top-.001
        nearby = ((lower[:, 1] >= minimum) & (lower[:, 1] < height)
                  & (upper[:, 0] > minx) & (lower[:, 0] < maxx)
                  & (upper[:, 2] > minz) & (lower[:, 2] < maxz))
        for triangle in triangles[nearby]:
            projection = MultiPoint(triangle[:, [0, 2]]).convex_hull
            if projection.geom_type == "Polygon" and projection.area > 1e-8:
                key = (max(top, round(float(triangle[:, 1].min()), 6)), other_id)
                covers.setdefault(key, []).append(projection)
    remaining = shape
    result = []
    for (bottom, limiter), projections in sorted(covers.items()):
        covered = remaining.intersection(union_all(projections))
        if covered.is_empty:
            continue
        result.extend((p, bottom-top, limiter) for p in polygons(covered) if p.area > 1e-8)
        remaining = remaining.difference(covered)
        if remaining.is_empty:
            break
    result.extend((p, max(0., height-top), ceiling_id) for p in polygons(remaining) if p.area > 1e-8)
    return result


class Floor(SceneContract):
    node_name: Identifier
    asset: Identifier
    center: Point2
    base_y: float
    yaw: float
    polygon: Ring
    area: float = Field(gt=0)


class Ceiling(SceneContract):
    node_name: Identifier
    asset: Identifier
    center: Point2
    base_y: float
    yaw: float
    height: float = Field(gt=0)


class Protrusion(SceneContract):
    entity_id: Identifier
    depth: float = Field(gt=0)
    bottom: float
    top: float
    from_a: float = Field(ge=0)
    to_a: float = Field(gt=0)


class Wall(SceneContract):
    id: Identifier
    node_name: Identifier
    asset: Identifier
    center: Point2
    base_y: float
    yaw: float
    a: Point2
    b: Point2
    length: float = Field(gt=0)
    height: float = Field(gt=0)
    inward_normal: Point2
    virtual: bool = False
    protrusions: list[Protrusion] = Field(default_factory=list)


class Opening(SceneContract):
    id: Identifier
    type: Literal["door", "window", "opening"]
    wall_id: Identifier
    offset: float = Field(ge=0)
    width: float = Field(gt=0)
    bottom: float
    height: float = Field(gt=0)
    node_name: Identifier | None = None


class UsableSurface(SceneContract):
    top: float
    polygon: Ring
    holes: list[Ring] = Field(default_factory=list)
    clearance_above: float = Field(ge=0)
    clearance_limited_by: Identifier


class PlacementEntity(SceneContract):
    id: Identifier
    label: str
    node_name: Identifier | None
    asset: Identifier | None
    member_ids: list[Identifier] = Field(default_factory=list)
    category: str = Field(json_schema_extra={"enum": sorted(CATEGORIES)})
    collision_class: Literal["floor", "wall", "tabletop", "ceiling", "none"]
    fixed_in_place: bool
    center: Point2
    base_y: float
    yaw: float
    size: Vector3  # width, depth, height (local X, Z, Y)
    mount: Literal["floor", "wall", "ceiling", "tabletop", "inset"]
    wall_id: Identifier | None = None
    support_id: Identifier | None = None
    surfaces: list[UsableSurface] = Field(default_factory=list)
    cutaway: bool | None = None
    source: Literal["roomplan", "mk1", "refined"]
    material_ids: list[Identifier] = Field(default_factory=list)


class Zone(SceneContract):
    id: Identifier
    type: Literal["keep_clear"] = "keep_clear"
    reason: Literal["door"] = "door"
    opening_id: Identifier
    polygon: Ring


class RoomDocument(SceneContract):
    schema_version: Literal[2] = 2
    room_id: Identifier
    capture_id: Identifier
    units: Literal["meters"] = "meters"
    up_axis: Literal["+Y"] = "+Y"
    coordinate_system: Literal["meters_y_up_floor_zero"] = "meters_y_up_floor_zero"
    node_pivot: Literal["bottom_center"]
    room_from_world: Matrix4
    height: float = Field(gt=0)
    floor: Floor
    ceiling: Ceiling
    walls: list[Wall] = Field(min_length=3)
    openings: list[Opening]
    entities: list[PlacementEntity]
    zones: list[Zone]
    materials: list[SceneMaterial] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_placement(self):
        if not rigid(self.room_from_world) or not polygon_valid(self.floor.polygon):
            raise ValueError("Room transform or closed counterclockwise floor is invalid")
        if abs(Polygon(self.floor.polygon).area-self.floor.area) > .0001:
            raise ValueError("Room floor area disagrees with its polygon")
        boundary = Polygon(self.floor.polygon).boundary
        wall_loop = Polygon([w.a for w in self.walls])
        if (not wall_loop.is_valid or not wall_loop.exterior.is_ccw
                or wall_loop.boundary.hausdorff_distance(boundary) > .02):
            raise ValueError("Walls must follow the floor outline in one counterclockwise loop within 2 cm")
        if abs(self.floor.base_y) > .02 or abs(self.ceiling.base_y-self.height) > .02:
            raise ValueError("Floor and ceiling nodes must match their declared planes within 2 cm")
        walls = {w.id: w for w in self.walls}
        entities = {e.id: e for e in self.entities}
        openings = {o.id: o for o in self.openings}
        ids = [self.floor.node_name, self.ceiling.node_name,
               *[w.id for w in self.walls], *[e.id for e in self.entities], *[o.id for o in self.openings]]
        if len(set(ids)) != len(ids):
            raise ValueError("Room identities must be unique across sections")
        materials = {m.id: m for m in self.materials}
        if len(materials) != len(self.materials) or any(m.owner_id not in ids for m in self.materials):
            raise ValueError("Room material ownership is invalid")
        for index, wall in enumerate(self.walls):
            if (np.linalg.norm(np.array(wall.b)-self.walls[(index+1) % len(self.walls)].a) > .02
                    or not boundary.buffer(.020001).covers(LineString([wall.a, wall.b]))):
                raise ValueError("Walls must join end to start on the floor outline within 2 cm")
            dx, dz = np.array(wall.b)-wall.a
            length = math.hypot(dx, dz)
            if length <= .001 or abs(length-wall.length) > .0001 or not np.allclose(wall.inward_normal, [-dz/length, dx/length], atol=.0001):
                raise ValueError("Wall direction or inward normal is invalid")
            for p in wall.protrusions:
                if p.entity_id not in entities or not 0 <= p.from_a < p.to_a <= wall.length+.001 or p.top < p.bottom:
                    raise ValueError("Wall protrusion is invalid")
        for opening in self.openings:
            if (opening.wall_id not in walls or opening.offset+opening.width > walls[opening.wall_id].length+.01
                    or opening.bottom < -.02 or opening.bottom+opening.height > self.height+.02):
                raise ValueError("Opening lies outside its supporting wall")
            if opening.node_name is not None and opening.node_name not in {e.node_name for e in self.entities}:
                raise ValueError("Opening refers to an unknown model node")
        for entity in self.entities:
            if entity.member_ids:
                if (entity.node_name is not None or entity.asset is not None or entity.material_ids
                        or entity.category != "counter" or entity.collision_class != "none"
                        or entity.mount != "floor" or not entity.fixed_in_place
                        or entity.support_id is not None
                        or len(set(entity.member_ids)) != len(entity.member_ids)
                        or any(member not in entities or member == entity.id or entities[member].member_ids
                               or entities[member].support_id == entity.id
                               for member in entity.member_ids)):
                    raise ValueError("A counter support group requires physical members and no model or collision asset")
            elif entity.node_name is None or entity.asset is None:
                raise ValueError("A physical entity requires a model node and asset")
            if any(identifier not in materials or materials[identifier].owner_id != entity.id for identifier in entity.material_ids):
                raise ValueError("Room entity material binding is invalid")
            if entity.category not in CATEGORIES or any(v <= 0 for v in entity.size):
                raise ValueError("Invalid placement category or oriented size")
            if entity.wall_id is not None and entity.wall_id not in walls:
                raise ValueError("Unknown entity wall")
            if entity.mount == "wall" and entity.wall_id is None:
                raise ValueError("Wall-mounted entity requires wall_id")
            if entity.support_id is not None and (entity.support_id not in entities or entity.support_id == entity.id):
                raise ValueError("Supported entity requires a known support_id")
            if entity.mount == "floor" and abs(entity.base_y) > .02:
                raise ValueError("Floor-mounted entity must be within 2 cm of the floor")
            if entity.mount == "ceiling" and abs(entity.base_y+entity.size[2]-self.height) > .02:
                raise ValueError("Ceiling-mounted entity must be within 2 cm of the ceiling")
            if entity.mount in ("tabletop", "inset"):
                support = entities.get(entity.support_id)
                if support is None:
                    raise ValueError("Supported entity requires support_id")
                candidates = [s for s in support.surfaces if (
                    abs(entity.base_y-s.top) <= .020001 if entity.mount == "tabletop" else
                    entity.base_y-.02 <= s.top <= entity.base_y+entity.size[2]+.02)]
                # An inset basin occupies a hole in the usable surface; the
                # enclosing worktop outline still establishes its attachment.
                shapes = [Polygon(s.polygon) if entity.mount == "inset" else surface_shape(s) for s in candidates]
                if not shapes or footprint(entity).intersection(union_all(shapes)).area < 1e-6:
                    raise ValueError("Supported entity must meet its support surface within 2 cm")
            for surface in entity.surfaces:
                if (not polygon_valid(surface.polygon) or any(not polygon_valid(hole) for hole in surface.holes)
                        or not surface_shape(surface).is_valid or surface_shape(surface).area <= 0
                        or surface.clearance_limited_by not in ids
                        or not entity.base_y-.02 <= surface.top <= entity.base_y+entity.size[2]+.02
                        or surface.top+surface.clearance_above > self.height+.02):
                    raise ValueError("Invalid usable surface")
            visited = {entity.id}
            support = entity.support_id
            while support is not None:
                if support in visited or support not in entities:
                    raise ValueError("Entity support references must not contain cycles or unknown IDs")
                visited.add(support)
                support = entities[support].support_id
            if entity.member_ids:
                if not any(abs(entities[m].base_y) <= .02 for m in entity.member_ids):
                    raise ValueError("A counter support group must include floor-standing members")
                for surface in entity.surfaces:
                    members = [surface_shape(s) for m in entity.member_ids for s in entities[m].surfaces
                               if abs(s.top-surface.top) < .001
                               and s.clearance_limited_by == surface.clearance_limited_by
                               and abs(s.clearance_above-surface.clearance_above) < .001]
                    if not members or surface_shape(surface).difference(union_all(members).buffer(.001)).area > 1e-6:
                        raise ValueError("Counter group surfaces must come from its physical members")
        for zone in self.zones:
            if zone.opening_id not in openings or not polygon_valid(zone.polygon):
                raise ValueError("Invalid door keep-clear zone")
        return self


def export_room(bundle, plan, roomplan, meshes, output):
    polygon = Polygon([[p.x, p.z] for p in plan.floor_polygon])
    shift = np.array([-polygon.bounds[0], -plan.floor_height, -polygon.bounds[1]])
    room_from_world = np.eye(4); room_from_world[:3, 3] = shift
    floor_ring = ring(np.asarray(polygon.exterior.coords)+shift[[0, 2]])
    floor_polygon = Polygon(floor_ring)
    by_id = {e.id: e for e in bundle.entities}
    floor = next(e for e in bundle.entities if e.kind == "floor")
    ceiling = next(e for e in bundle.entities if e.kind == "ceiling")
    height = plan.ceiling_height-plan.floor_height
    def placement(entity):
        m = np.asarray(entity.local_to_scan_transform).reshape(4, 4, order="F")
        position = m[:3, 3]+shift
        return {"center": position[[0, 2]].tolist(), "base_y": float(position[1]), "yaw": float(math.atan2(m[0, 2], m[2, 2]))}
    walls = []
    for entity in bundle.entities:
        if entity.kind != "wall":
            continue
        m = np.asarray(entity.local_to_scan_transform).reshape(4, 4, order="F")
        lo, hi = np.array(entity.bounds_min), np.array(entity.bounds_max)
        center = m[:3, :3] @ ((lo+hi)/2)+m[:3, 3]+shift
        tangent = m[[0, 2], 0]
        a, b = center[[0, 2]]-tangent*(hi[0]-lo[0])/2, center[[0, 2]]+tangent*(hi[0]-lo[0])/2
        normal = np.array([-(b-a)[1], (b-a)[0]])/np.linalg.norm(b-a)
        if not floor_polygon.buffer(.001).covers(Point((a+b)/2+normal*.05)):
            a, b, normal = b, a, -normal
        walls.append(Wall(id=entity.id, node_name=entity.id, asset=entity.asset, **placement(entity), a=a.tolist(), b=b.tolist(),
            length=float(np.linalg.norm(b-a)), height=height, inward_normal=normal.tolist()))
    walls = order_walls(walls)
    world = {key: (v+shift, f) for key, (v, f) in meshes.items()}
    obstacles = {e.id: (float(world[e.id][0][:, 1].min()), float(world[e.id][0][:, 1].max()),
                       MultiPoint(world[e.id][0][:, [0, 2]]).convex_hull)
                 for e in bundle.entities if e.kind not in ("floor", "ceiling", "wall")}
    original_entities = {e.id: e for e in plan.entities}
    part_cache = {}
    def world_parts(identity):
        if identity not in part_cache:
            import open3d as o3d
            from .astra_room import part_mesh, transform
            original = original_entities[identity]
            pose = transform(original.position, original.yaw)
            part_cache[identity] = [np.asarray(part_mesh(part, o3d).vertices) @ pose[:3, :3].T+pose[:3, 3]+shift
                                    for part in original.parts]
        return part_cache[identity]
    exported = []
    for entity in bundle.entities:
        if entity.kind in ("wall", "floor", "ceiling"):
            continue
        m = np.array(entity.local_to_scan_transform).reshape(4, 4, order="F")
        position = m[:3, 3]+shift
        extent = np.array(entity.bounds_max)-entity.bounds_min
        vertices, _ = world[entity.id]
        nearby_walls = []
        for wall in walls:
            tangent = (np.array(wall.b)-wall.a)/wall.length
            along = (vertices[:, [0, 2]]-wall.a) @ tangent
            signed = (vertices[:, [0, 2]]-wall.a) @ wall.inward_normal
            gap = max(0., float(signed.min()), -float(signed.max()))
            if gap < .2 and along.max() > 0 and along.min() < wall.length:
                nearby_walls.append((gap, wall.id))
        wall_id = entity.support_id if entity.support_id in {w.id for w in walls} else min(nearby_walls)[1] if nearby_walls else None
        support_id = entity.support_id if entity.support_id in by_id and by_id[entity.support_id].kind not in ("wall", "floor", "ceiling") else None
        inset = original_entities[entity.id].category == "sink"
        mount = ("ceiling" if abs(vertices[:, 1].max()-height) <= .02 and position[1] > .3 else
                 "inset" if inset else "tabletop" if support_id else
                 "wall" if entity.kind == "wall_decor" or entity.kind == "fixed" and position[1] > .2 and wall_id else "floor")
        value = category(entity.category, entity.label)
        exported.append(PlacementEntity(id=entity.id, label=entity.label, node_name=entity.id, asset=entity.asset,
            category=value, collision_class="none" if value == "rug" else "tabletop" if inset else mount,
            fixed_in_place=entity.kind == "fixed", center=position[[0, 2]].tolist(), base_y=float(position[1]), yaw=float(math.atan2(m[0, 2], m[2, 2])),
            size=extent[[0, 2, 1]].tolist(), mount=mount, wall_id=wall_id, support_id=support_id, source="refined", material_ids=entity.material_ids))
    # Usable surfaces come from actual horizontal mesh faces, excluding narrow
    # upstands. Ordinary occupants retain their own collision records, so the
    # physical support surface remains available for validating their contact.
    support_owners = {e.support_id for e in exported if e.support_id is not None}
    # Installed appliances such as dishwashers can physically support a counter
    # without having a dedicated registry category. Their actual top is needed
    # for attachment validation too; it has zero headroom when covered.
    for counter in exported:
        if counter.category == "counter" and counter.fixed_in_place:
            support_owners.update(other.id for other in exported if other.id != counter.id and other.fixed_in_place
                and other.base_y <= .02 and abs(other.base_y+other.size[2]-counter.base_y) <= .02
                and footprint(other).intersection(footprint(counter)).area > 1e-6)
    for entity in exported:
        if entity.category not in {"table", "coffee_table", "desk", "cabinet", "shelf", "counter"} and entity.id not in support_owners:
            continue
        vertices, faces = world[entity.id]
        # Parts crossing a work plane (backsplashes, legs, uprights) occupy
        # surface area. Remove their footprint before computing overhead space.
        occupied = [(float(pv[:, 1].min()), float(pv[:, 1].max()), MultiPoint(pv[:, [0, 2]]).convex_hull)
                    for pv in world_parts(entity.id)]
        triangles = vertices[faces]
        normals = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
        levels = {}
        for triangle, normal in zip(triangles, normals):
            if normal[1] <= .99*np.linalg.norm(normal) or normal[1] < .0001:
                continue
            p = Polygon(triangle[:, [0, 2]])
            levels.setdefault(round(float(triangle[:, 1].mean()), 3), []).append(p)
        surfaces = [(y, union_all(polys)) for y, polys in levels.items()]
        maximum = max((p.area for _, p in surfaces), default=0)
        for top, shape in sorted(surfaces, reverse=True, key=lambda v: v[0]):
            if shape.area < max(.02, maximum*.3) or top <= entity.base_y+.001:
                continue
            shape = shape.difference(union_all([p for bottom, high, p in occupied if bottom <= top+.01 and high > top+.02]))
            shape = shape.difference(union_all([p for identity, (bottom, high, p) in obstacles.items()
                if identity != entity.id and original_entities[identity].category == "sink"
                and bottom <= top+.02 and high >= top-.02]))
            for p, clearance, limiter in partition_headroom(shape, top, entity.id, world, height, ceiling.id):
                entity.surfaces.append(UsableSurface(top=top, polygon=ring(p.exterior.coords), holes=[ring(h.coords) for h in p.interiors],
                    clearance_above=clearance, clearance_limited_by=limiter))
    # Infer only geometrically established contacts. An elevated object without
    # a wall, ceiling or supporting surface is rejected rather than grounded.
    def supports(entity):
        result = []
        for other in exported:
            if other.id == entity.id:
                continue
            for surface in other.surfaces:
                meets = (entity.base_y-.02 <= surface.top <= entity.base_y+entity.size[2]+.02 if entity.mount == "inset"
                         else abs(entity.base_y-surface.top) <= .020001)
                shape = Polygon(surface.polygon) if entity.mount == "inset" else surface_shape(surface)
                overlap = footprint(entity).intersection(shape).area
                if meets and overlap > 1e-6:
                    result.append((overlap, other.id))
        return sorted(result, reverse=True)

    for entity in exported:
        if entity.support_id is None and (entity.mount == "inset" or entity.mount == "floor" and entity.base_y > .02):
            candidates = supports(entity)
            if candidates:
                entity.support_id = candidates[0][1]
                if entity.mount != "inset":
                    entity.mount = entity.collision_class = "tabletop"

    groups = []
    for counter in exported:
        if counter.category != "counter" or not counter.fixed_in_place or counter.base_y <= .02:
            continue
        members = {identity for _, identity in supports(counter)
                   if by_id[identity].kind == "fixed" and next(e for e in exported if e.id == identity).base_y <= .02}
        if not members:
            continue
        members.add(counter.id)
        yaw = counter.yaw
        c, s = math.cos(yaw), math.sin(yaw)
        rotation = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
        local = np.concatenate([world[identity][0] for identity in sorted(members)]) @ rotation
        lo, hi = local.min(axis=0), local.max(axis=0)
        pivot = np.array([(lo[0]+hi[0])/2, lo[1], (lo[2]+hi[2])/2]) @ rotation.T
        group = PlacementEntity(id=stable_id("counter-run", counter.id), label=counter.label+" support run",
            node_name=None, asset=None, member_ids=sorted(members), category="counter", collision_class="none",
            fixed_in_place=True, center=pivot[[0, 2]].tolist(), base_y=float(pivot[1]), yaw=yaw,
            size=(hi-lo)[[0, 2, 1]].tolist(), mount="floor", source="refined",
            surfaces=[surface.model_copy(deep=True) for surface in counter.surfaces])
        for entity in exported:
            if entity.id not in members and entity.support_id == counter.id:
                entity.support_id = group.id
        groups.append(group)
    for entity in exported:
        if not entity.wall_id or not (entity.fixed_in_place or entity.mount == "wall"):
            continue
        wall = next(w for w in walls if w.id == entity.wall_id)
        tangent = (np.array(wall.b)-wall.a)/wall.length
        # Keep separate height intervals for sills, skirting and handles. An
        # assembly's deepest part must not inflate its depth at every height.
        for vertices in world_parts(entity.id):
            along = (vertices[:, [0, 2]]-wall.a) @ tangent
            depth = float(((vertices[:, [0, 2]]-wall.a) @ wall.inward_normal).max())
            start, end = max(0., float(along.min())), min(wall.length, float(along.max()))
            if depth > .005 and end > start:
                wall.protrusions.append(Protrusion(entity_id=entity.id, depth=depth, bottom=float(vertices[:, 1].min()),
                    top=float(vertices[:, 1].max()), from_a=start, to_a=end))
    openings, zones = [], []
    for plural, kind in (("doors", "door"), ("windows", "window"), ("openings", "opening")):
        for item in roomplan.get(plural, []):
            pose, size = surface_transform(item), vector3(item["dimensions"])
            center = pose[:3, 3]+shift
            candidates = []
            for wall in walls:
                if abs(float(np.dot(pose[[0, 2], 2], wall.inward_normal))) < .95:
                    continue
                tangent = (np.array(wall.b)-wall.a)/wall.length
                offset = float(np.dot(center[[0, 2]]-wall.a, tangent))-size[0]/2
                gap = abs(float(np.dot(center[[0, 2]]-wall.a, wall.inward_normal)))
                if gap < .2 and offset >= -.01 and max(0., offset)+size[0] <= wall.length+.01:
                    candidates.append((gap, wall, max(0., offset)))
            if not candidates:
                raise ValueError("A measured opening could not be assigned to a wall")
            _, wall, offset = min(candidates, key=lambda v: v[0])
            identifier = stable_id(kind, str(item["identifier"]))
            width = float(size[0])
            def opening_distance(entity):
                return np.linalg.norm(np.array([entity.center[0], entity.base_y+entity.size[2]/2, entity.center[1]])-center)
            matching = [e for e in exported if by_id[e.id].category == kind and opening_distance(e) < .4]
            node = min(matching, key=opening_distance).node_name if matching else None
            openings.append(Opening(id=identifier, type=kind, wall_id=wall.id, offset=offset,
                width=width, bottom=float(center[1]-size[1]/2), height=float(size[1]), node_name=node))
            if kind in ("door", "opening"):
                tangent = (np.array(wall.b)-wall.a)/wall.length
                a = np.array(wall.a)+tangent*max(0, offset-.45)
                b = np.array(wall.a)+tangent*min(wall.length, offset+width+.45)
                normal = np.array(wall.inward_normal)*1.2
                clear = floor_polygon.intersection(Polygon([a, b, b+normal, a+normal]))
                for index, p in enumerate(list(clear.geoms) if hasattr(clear, "geoms") else [clear]):
                    if p.geom_type == "Polygon" and p.area > .001:
                        zones.append(Zone(id=f"keep-clear-{identifier}-{index}", opening_id=identifier, polygon=ring(p.exterior.coords)))
    document = RoomDocument(room_id=bundle.scene_id, capture_id=bundle.capture_id, node_pivot="bottom_center",
        room_from_world=room_from_world.flatten(order="F").tolist(), height=height,
        floor=Floor(node_name=floor.id, asset=floor.asset, **placement(floor), polygon=floor_ring, area=floor_polygon.area),
        ceiling=Ceiling(node_name=ceiling.id, asset=ceiling.asset, **placement(ceiling), height=height),
        walls=walls, openings=openings, entities=exported+groups, zones=zones, materials=bundle.materials)
    validate_assets(document, bundle, output)
    atomic_json(output/"room.json", document.model_dump(mode="json"))
    atomic_json(output/"room.schema.json", RoomDocument.model_json_schema())
    return document


def validate_assets(document, bundle, directory):
    transform = np.array(document.room_from_world).reshape(4, 4, order="F")
    native = {e.id: e for e in bundle.entities}
    world = {}
    for entity in [*document.entities, *document.walls, document.floor, document.ceiling]:
        if isinstance(entity, PlacementEntity) and entity.member_ids:
            continue
        if entity.node_name not in native:
            raise ValueError("Room JSON refers to an unknown model node")
        source = native[entity.node_name]
        m = transform @ np.array(source.local_to_scan_transform).reshape(4, 4, order="F")
        vertices = np.array([[float(v) for v in line.split()[1:]] for line in (directory/entity.asset).read_text().splitlines() if line.startswith("v ")])
        lo, hi = vertices.min(axis=0), vertices.max(axis=0)
        expected_pivot = [(lo[0]+hi[0])/2, lo[1], (lo[2]+hi[2])/2]
        yaw = math.atan2(m[0, 2], m[2, 2])
        angle = math.atan2(math.sin(yaw-entity.yaw), math.cos(yaw-entity.yaw))
        size_matches = not isinstance(entity, PlacementEntity) or np.allclose(entity.size, (hi-lo)[[0, 2, 1]], atol=.01)
        position = [entity.center[0], entity.base_y, entity.center[1]]
        if entity.asset != source.asset or not np.allclose(expected_pivot, 0, atol=.01) or not np.allclose(position, m[:3, 3], atol=.01) or abs(angle) > math.pi/180 or not size_matches:
            raise ValueError("Room JSON disagrees with its actual model nodes")
        world[getattr(entity, "id", entity.node_name)] = vertices @ m[:3, :3].T+m[:3, 3]
    for entity in document.entities:
        if not entity.member_ids:
            continue
        c, s = math.cos(entity.yaw), math.sin(entity.yaw)
        rotation = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
        vertices = np.concatenate([world[member] for member in entity.member_ids]) @ rotation
        lo, hi = vertices.min(axis=0), vertices.max(axis=0)
        pivot = np.array([(lo[0]+hi[0])/2, lo[1], (lo[2]+hi[2])/2]) @ rotation.T
        if (not np.allclose([entity.center[0], entity.base_y, entity.center[1]], pivot, atol=.01)
                or not np.allclose(entity.size, (hi-lo)[[0, 2, 1]], atol=.01)):
            raise ValueError("Counter support group bounds disagree with its physical members")


def load_room(directory):
    from .scene import SceneBundle
    document = RoomDocument.model_validate_json((directory/"room.json").read_text())
    bundle = SceneBundle.model_validate_json((directory/"scene.json").read_text())
    if document.capture_id != bundle.capture_id or document.room_id != bundle.scene_id:
        raise ValueError("Room JSON belongs to another scene")
    validate_assets(document, bundle, directory)
    return document
