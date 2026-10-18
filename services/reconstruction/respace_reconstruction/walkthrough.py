"""Final-only segmented room reconstruction. Gemini is deliberately absent."""
import json
import os
from pathlib import Path
import time

import numpy as np
from PIL import Image
from shapely import Polygon

from .benchmark import inspect_capture
from .decor import WallPlane, rectified_asset, wall_rays
from .geometry import read_scan
from .instances import assign_surface_ownership, RescanRequired, stable_id
from .inventory import automatic_inventory
from .navigation import build_navigation
from .object_completion import bake_object, complete_object
from .obj import read_obj
from .scene import SceneBundle, SceneEntity, SceneMaterial
from .store import atomic_json, digest
from .surfaces import PhotoBaker, room_surfaces, triangulate


def merge_scene(bundle,output):
    vertex_offset,uv_offset=0,0
    with (output/"model.obj").open("w") as stream:
        for entity in bundle.entities:
            mesh=read_obj(output/entity.asset)
            transform=np.array(entity.local_to_scan_transform).reshape(4,4,order="F")
            vertices=mesh.vertices@transform[:3,:3].T+transform[:3,3]
            for name in mesh.libraries:stream.write("mtllib "+name+"\n")
            stream.write("o "+entity.id+"\n")
            np.savetxt(stream,vertices,fmt="v %.8f %.8f %.8f")
            np.savetxt(stream,mesh.uvs,fmt="vt %.8f %.8f")
            material=None
            for face,name in zip(mesh.faces,mesh.materials):
                if name!=material:stream.write("usemtl "+name+"\n");material=name
                stream.write("f "+" ".join(str(v+vertex_offset+1)+(f"/{uv+uv_offset+1}" if uv is not None else "") for v,uv,_ in face)+"\n")
            vertex_offset+=len(vertices);uv_offset+=len(mesh.uvs)


def process_walkthrough(folder:Path,revision:int,inventory_fn=automatic_inventory):
    import open3d as o3d
    from .pipeline import progress
    folder=folder.resolve()
    manifest,audit=inspect_capture(folder)
    if not audit["complete"]:
        raise RuntimeError("Finish uploading the original mesh and calibrated scan artifacts before processing")
    if revision<1:raise ValueError("Invalid reconstruction revision")
    committed=folder/"results"/str(revision)
    if committed.exists():
        cached=json.loads((committed/"completion.json").read_text())
        quality=json.loads((committed/"quality.json").read_text())
        scene=SceneBundle.model_validate_json((committed/"scene.json").read_text())
        if (cached["revision"]!=revision or cached["status"]!="succeeded" or not scene.ready
            or scene.capture_id!=manifest.capture_id or quality.get("source_manifest_sha256")!=audit["manifest_sha256"]):
            raise ValueError("Committed scene does not match its immutable input")
        scene.validate_files(committed,{a["filename"] for a in cached["assets"]})
        for asset in cached["assets"]:
            if (committed/asset["filename"]).stat().st_size!=asset["byte_length"] or digest(committed/asset["filename"])!=asset["sha256"]:
                raise ValueError("Committed scene failed integrity verification")
        return cached
    inputs=folder/"inputs";working=folder/"work"/"walkthrough"
    working.mkdir(parents=True,exist_ok=True)
    # Failed attempts never become downloadable successful revisions.
    output=folder/"results"/(str(revision)+".building")
    output.mkdir(parents=True,exist_ok=True)
    for path in output.iterdir():
        if path.is_file():path.unlink()
    start=time.monotonic()
    deadline=float(os.environ.get("RESPACE_ROOM_TIMEOUT_SECONDS","1800"))
    def budget():
        if time.monotonic()-start>deadline:raise TimeoutError("Room processing exceeded its configured time budget")
    room=json.loads((inputs/manifest.room_export.filename).read_text())
    progress("room_structure")
    surfaces=room_surfaces(room)
    source=read_scan(inputs/manifest.scene_mesh.filename,manifest.capture_id,o3d)
    source.remove_degenerate_triangles();source.remove_duplicated_triangles();source.compute_triangle_normals()
    if len(source.triangles)>800000:
        raise RuntimeError("The captured mesh exceeds the mobile reconstruction budget; the original scan is retained")
    progress("object_inventory")
    seeds,masks,decor,exclusions=inventory_fn(manifest,inputs,room,surfaces,working,budget)
    budget()
    # One view may own an individual face after the instance itself was confirmed
    # across independent views. Occluded backs are not deleted for lacking two masks.
    progress("surface_ownership")
    vertices,faces=np.asarray(source.vertices),np.asarray(source.triangles)
    seed_ids={s.id for s in seeds}
    ownership,ownership_report=assign_surface_ownership(vertices,faces,seeds,[m for m in masks if m["entity_id"] in seed_ids],inputs,minimum_views=1)
    centers=vertices[faces].mean(axis=1)
    plane_faces=np.zeros(len(faces),dtype=bool)
    for surface in surfaces:
        inverse=np.linalg.inv(surface.transform)
        local=centers@inverse[:3,:3].T+inverse[:3,3]
        from shapely import contains_xy
        plane_faces|=(abs(local[:,2])<.045)&contains_xy(surface.polygon.buffer(.015),local[:,0],local[:,1])&(
            abs(np.asarray(source.triangle_normals)@surface.transform[:3,2])>.85)
    # Restrict connected completion to a measured object's own box. No nearest
    # semantic-label propagation across room geometry or adjacent objects.
    for index,seed in enumerate(seeds):
        inverse=np.linalg.inv(seed.transform)
        local=centers@inverse[:3,:3].T+inverse[:3,3]
        inside=(abs(local)<=seed.dimensions/2+.025).all(axis=1)&~plane_faces
        part=o3d.geometry.TriangleMesh(source)
        part.remove_triangles_by_mask(~inside)
        if not len(part.triangles):continue
        labels,_,_=part.cluster_connected_triangles()
        selected=np.flatnonzero(inside)
        for label in np.unique(labels):
            ids=selected[np.asarray(labels)==label]
            owners=np.unique(ownership[ids][ownership[ids]>=0])
            if len(owners)==1 and owners[0]==index:
                ownership[ids[ownership[ids]<0]]=index
        if seed.kind in ("furniture","wall_decor"):
            ambiguous=inside&(ownership<0)
            triangle=vertices[faces[ambiguous]]
            area=np.linalg.norm(np.cross(triangle[:,1]-triangle[:,0],triangle[:,2]-triangle[:,0]),axis=1).sum()/2 if len(triangle) else 0
            if area>.005:
                raise RescanRequired("The "+seed.label+" could not be isolated without leaving fragments")
    baker=PhotoBaker(manifest,inputs,exclusions)
    # Include every mask view in the texture evidence, even if uniform sampling
    # omitted a useful close pass. Keep a bounded cache by limiting to 48 views.
    extra={m["frame"].id:m["frame"] for m in masks}
    baker.frames=list({f.id:f for f in baker.frames+list(extra.values())}.values())[:48]
    entities,materials,provenance=[],[],[]
    def add_entity(identity,label,category,kind,transform,v,asset,bindings,observed,**kwargs):
        ids=[]
        for binding in bindings:
            identifier=stable_id("material",identity+"/"+binding)
            materials.append(SceneMaterial(id=identifier,owner_id=identity,slot=binding,source_material=binding))
            ids.append(identifier)
        entity=SceneEntity(id=identity,label=label,category=category,kind=kind,asset=asset,
            local_to_scan_transform=transform.flatten(order="F").tolist(),bounds_min=np.min(v,axis=0).tolist(),
            bounds_max=np.max(v,axis=0).tolist(),material_ids=ids,observed_fraction=observed,**kwargs)
        entities.append(entity)
        return entity
    claimed=np.zeros(len(faces),dtype=bool)
    for index,seed in enumerate(seeds):
        ids=np.flatnonzero((ownership==index)&~plane_faces)
        if not len(ids):
            if seed.kind in ("furniture","wall_decor"):raise RescanRequired("The "+seed.label+" has no isolated captured surface")
            continue
        part=o3d.geometry.TriangleMesh(source)
        part.remove_triangles_by_mask(~np.isin(np.arange(len(faces)),ids));part.remove_unreferenced_vertices()
        part.transform(np.linalg.inv(seed.transform))
        progress("object_completion:"+seed.id)
        if seed.kind in ("furniture","wall_decor"):
            part,details=complete_object(part,seed,manifest,inputs,working,masks,budget)
        else:details={"method":"captured_fixed_geometry"}
        bindings,observed=bake_object(part,seed,baker,output,masks)
        add_entity(seed.id,seed.label,seed.category,seed.kind,seed.transform,np.asarray(part.vertices),
            seed.id+".obj",bindings,observed,move_ready=seed.kind in ("furniture","wall_decor"),
            source_object_id=seed.source_id,support_id=getattr(seed,"support_id",None))
        claimed[ids]=True
        provenance.append(dict(id=seed.id,**details))
        budget()
    blocked={s.id:[] for s in surfaces}
    for item in decor:
        surface=item["support"]
        member=max(item["members"],key=lambda m:np.count_nonzero(m["mask"])*m["score"])
        frame=member["frame"]
        photo=next(a for a in frame.artifacts if a.type=="jpeg")
        lo=np.array(surface.polygon.bounds[:2]);hi=np.array(surface.polygon.bounds[2:])
        with Image.open(inputs/photo.filename) as image:
            result=rectified_asset(image,member["mask"],frame.metadata,
                WallPlane(surface.id,surface.transform,float(max(abs(lo[0]),abs(hi[0]))*2),float(max(abs(lo[1]),abs(hi[1]))*2)),output,item["id"])
        mesh=read_obj(output/result["asset"])
        transform=np.array(result["local_to_scan_transform"]).reshape(4,4,order="F")
        decor_kind="furniture" if surface.kind=="floor" else "wall_decor"
        add_entity(item["id"],item["label"],"rug" if surface.kind=="floor" else "wall_decor",decor_kind,transform,mesh.vertices,result["asset"],
            [item["id"]],1.,move_ready=True,support_id=surface.id,collidable=False)
        world=mesh.vertices@transform[:3,:3].T+transform[:3,3]
        inverse=np.linalg.inv(surface.transform);local=world@inverse[:3,:3].T+inverse[:3,3]
        blocked[surface.id].append(Polygon(local[:,:2]))
        provenance.append({"id":item["id"],"method":result["method"],"source_frame_id":frame.id})
    # Architecture is rebuilt as a clean, complete shell. Its textures cannot
    # contain coplanar decor or depth-occluding furniture from the original scan.
    for surface in surfaces:
        progress("clean_background:"+surface.id)
        v,t,observed=baker.plane(surface,output,blocked[surface.id])
        add_entity(surface.id,surface.kind.title(),surface.kind,surface.kind,surface.transform,v,
                   surface.id+".obj",[surface.id],observed,finish_ready=True,collidable=False,
                   source_object_id=surface.source_id,
                   surface_polygons=[np.asarray(p.exterior.coords)[:-1].tolist() for p in (surface.polygon.geoms if surface.polygon.geom_type=="MultiPolygon" else [surface.polygon])],
                   surface_holes=[np.asarray(r.coords)[:-1].tolist() for p in (surface.polygon.geoms if surface.polygon.geom_type=="MultiPolygon" else [surface.polygon]) for r in p.interiors])
        provenance.append({"id":surface.id,"method":"measured_plane_source_photos_harmonic_hidden_texture",
                           "observed_texture_fraction":observed})
        budget()
    remaining=~claimed&~plane_faces
    fixed=o3d.geometry.TriangleMesh(source)
    fixed.remove_triangles_by_mask(~remaining);fixed.remove_unreferenced_vertices()
    if len(fixed.triangles):
        from .instances import InstanceSeed
        v=np.asarray(fixed.vertices)
        seed=InstanceSeed("fixed-details","fixed-details","fixed","Built-in details","fixed",np.eye(4),np.ptp(v,axis=0))
        bindings,observed=bake_object(fixed,seed,baker,output,[],minimum_photo_fraction=.05)
        add_entity(seed.id,seed.label,"fixed","fixed",np.eye(4),v,seed.id+".obj",bindings,observed,collidable=False)
    progress("walkthrough_navigation")
    navigation=build_navigation(next(s for s in surfaces if s.kind=="floor"),entities,np.asarray(fixed.vertices),manifest.frames,surfaces,np.asarray(fixed.triangles))
    report={"schema_version":2,"capture_id":manifest.capture_id,"ready":True,
        "source_manifest_sha256":audit["manifest_sha256"],"object_ownership":ownership_report,
        "entity_count":len(entities),"triangles":sum(len(read_obj(output/e.asset).faces) for e in entities),
        "seconds":time.monotonic()-start,"validation":"geometry_depth_texture_navigation",
        "lighting_required":False,"gemini_enabled":False}
    if report["triangles"]>1000000:raise RuntimeError("The finished room exceeds the mobile triangle budget; reduce export detail")
    atomic_json(output/"quality.json",report)
    atomic_json(output/"provenance.json",{"capture_id":manifest.capture_id,"manifest_sha256":audit["manifest_sha256"],"entities":provenance})
    bundle=SceneBundle(capture_id=manifest.capture_id,scene_id=stable_id("scene",manifest.capture_id),
        reconstruction_revision=revision,entities=entities,materials=materials,navigation=navigation,ready=True)
    merge_scene(bundle,output)
    from .usdz import export_usdz
    progress("exporting_usdz")
    usdz_filename=export_usdz(output/"model.obj")
    atomic_json(output/"scene.json",bundle.model_dump())
    names={p.name for p in output.iterdir() if p.is_file()}
    bundle.validate_files(output,names)
    assets=[{"filename":name,"byte_length":(output/name).stat().st_size,"sha256":digest(output/name)} for name in sorted(names)]
    if len(assets)>512 or any(a["byte_length"]>128*1024**2 for a in assets) or sum(a["byte_length"] for a in assets)>512*1024**2:
        raise RuntimeError("The finished room exceeds the mobile asset budget; reduce export detail")
    result={"revision":revision,"status":"succeeded","model_filename":"model.obj","scene_filename":"scene.json",
        "usdz_filename":usdz_filename,
        "scene_schema_version":2,"assets":assets,"needs_review":False,"error":None,
        "coordinate_system":"arkit_scan_meters_y_up","quality_filename":"quality.json"}
    atomic_json(output/"completion.json",result)
    final=folder/"results"/str(revision)
    if final.exists():raise RuntimeError("A committed result revision already exists")
    output.replace(final)
    progress("finished_walkthrough")
    return result
