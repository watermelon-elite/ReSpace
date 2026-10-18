"""Metric floor navigation; immutable obstacles plus independent object bounds."""
import numpy as np
from shapely import Polygon, Point, LineString, box, union_all

from .instances import RescanRequired
from .scene import Navigation, matrix


def entity_footprint(entity):
    transform=matrix(entity.local_to_scan_transform)
    lo,hi=entity.bounds_min,entity.bounds_max
    points=np.array([[x,y,z] for x in (lo[0],hi[0]) for y in (lo[1],hi[1]) for z in (lo[2],hi[2])])
    world=points@transform[:3,:3].T+transform[:3,3]
    from shapely import MultiPoint
    return MultiPoint(world[:,[0,2]]).convex_hull


def build_navigation(floor,entities,fixed_vertices,frames,surfaces=(),fixed_faces=None):
    vertices=np.c_[np.asarray(floor.polygon.exterior.coords)[:-1],np.zeros(len(floor.polygon.exterior.coords)-1)]
    world=vertices@floor.transform[:3,:3].T+floor.transform[:3,3]
    polygon=Polygon(world[:,[0,2]])
    floor_height=float(np.median(world[:,1]))
    radius=.2
    obstacles=[]
    for surface in surfaces:
        if surface.kind!="wall":continue
        denominator=surface.transform[1,1]
        if abs(denominator)<.99:raise RescanRequired("Wall orientation cannot support safe navigation")
        y=(floor_height+.3-surface.transform[1,3])/denominator
        x0,_,x1,_=surface.polygon.bounds
        section=surface.polygon.intersection(LineString([[x0-.01,y],[x1+.01,y]]))
        lines=list(section.geoms) if hasattr(section,"geoms") else [section]
        for line in lines:
            if line.is_empty or line.geom_type!="LineString":continue
            local=np.c_[np.asarray(line.coords),np.zeros(len(line.coords))]
            w=local@surface.transform[:3,:3].T+surface.transform[:3,3]
            obstacles.append(LineString(w[:,[0,2]]).buffer(.035,cap_style="square",join_style="mitre"))
    fixed=np.asarray(fixed_vertices)
    if len(fixed) and fixed_faces is not None and len(fixed_faces):
        triangles=fixed[np.asarray(fixed_faces)]
        span=np.max(np.linalg.norm(triangles-np.roll(triangles,1,axis=1),axis=2),axis=1)
        large=triangles[(span>.12)&(triangles[:,:,1].min(axis=1)<floor_height+1.8)&(triangles[:,:,1].max(axis=1)>floor_height+.1)]
        samples=[];sample_count=0
        for triangle in large:
            steps=min(128,max(2,int(np.ceil(np.max(np.linalg.norm(triangle-np.roll(triangle,1,axis=0),axis=1))/.08))))
            bary=np.array([(a/steps,b/steps) for a in range(steps+1) for b in range(steps+1-a)])
            sample_count+=len(bary)
            if sample_count>2000000:raise RuntimeError("Fixed-geometry navigation exceeded its sampling budget")
            samples.append(triangle[0]+bary[:,0,None]*(triangle[1]-triangle[0])+bary[:,1,None]*(triangle[2]-triangle[0]))
        if samples:fixed=np.concatenate([fixed,*samples])
    if len(fixed):
        fixed=fixed[(fixed[:,1]>floor_height+.10)&(fixed[:,1]<floor_height+1.8)]
        cells=np.unique(np.floor(fixed[:,[0,2]]/.10).astype(int),axis=0)
        # Coalesce consecutive cells into row strips before the geometric union.
        strips=[]
        for row in np.unique(cells[:,1]) if len(cells) else []:
            columns=np.sort(cells[cells[:,1]==row,0])
            for group in np.split(columns,np.flatnonzero(np.diff(columns)>1)+1):
                strips.append(box(group[0]*.1,row*.1,(group[-1]+1)*.1,(row+1)*.1))
        if strips:
            occupied=union_all(strips).buffer(.025).simplify(.015,preserve_topology=True)
            parts=list(occupied.geoms) if occupied.geom_type=="MultiPolygon" else [occupied]
            obstacles.extend(p for p in parts if p.area>.005)
    # Holes in a measured floor are never walkable.
    for ring in floor.polygon.interiors:
        p=np.c_[np.asarray(ring.coords)[:-1],np.zeros(len(ring.coords)-1)]
        w=p@floor.transform[:3,:3].T+floor.transform[:3,3]
        obstacles.append(Polygon(w[:,[0,2]]))
    moving=[entity_footprint(e) for e in entities if e.collidable and e.kind not in ("wall","floor","ceiling","wall_decor")]
    free=polygon.buffer(-radius-.01)
    if obstacles or moving:
        free=free.difference(union_all(obstacles+moving).buffer(radius+.01))
    if free.is_empty:
        raise RescanRequired("There is no safe place to stand in the reconstructed room")
    spawn=None
    for frame in frames:
        position=np.array(frame.metadata.camera_to_scan_transform).reshape(4,4,order="F")[:3,3]
        if free.contains(Point(position[[0,2]])):
            spawn=position[[0,2]];break
    if spawn is None:
        point=free.representative_point();spawn=np.array([point.x,point.y])
    return Navigation(floor_polygons=[world[:,[0,2]].tolist()],floor_height=floor_height,
        spawn_position=[float(spawn[0]),floor_height+1.6,float(spawn[1])],spawn_yaw=0,
        obstacles=[np.asarray(p.exterior.coords)[:-1].tolist() for p in obstacles])
