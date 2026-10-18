import hashlib
import io
import json
import plistlib

import numpy as np
import open3d as o3d
from PIL import Image
import pytest
from shapely import Polygon

from respace_reconstruction.geometry import CAMERA_FLIP
from respace_reconstruction.instances import InstanceSeed, RescanRequired
from respace_reconstruction.models import Manifest
from respace_reconstruction.scene import SceneBundle
from respace_reconstruction.store import atomic_json, digest
from respace_reconstruction.surfaces import close_observed, fill_texture, room_surfaces, triangulate
from respace_reconstruction.walkthrough import process_walkthrough


def room_capture(folder):
    inputs=folder/"inputs";inputs.mkdir()
    capture_id="analytic-room"
    def artifact(kind,data,suffix):
        identity=str(len(list(inputs.iterdir()))+1)
        name=identity+"."+suffix;(inputs/name).write_bytes(data)
        return {"id":identity,"type":kind,"filename":name,"byte_length":len(data),"sha256":hashlib.sha256(data).hexdigest()}
    def surface(identifier,transform,dimensions,polygon=None):
        result={"identifier":identifier,"transform":transform.flatten(order="F").tolist(),"dimensions":dimensions}
        if polygon:result["polygonCorners"]=[[x,y,0] for x,y in polygon]
        return result
    floor=np.eye(4);floor[:3,:3]=[[1,0,0],[0,0,-1],[0,1,0]]
    walls=[]
    for index,(axis,value) in enumerate(((2,-2),(2,2),(0,-2),(0,2))):
        t=np.eye(4);t[1,3]=1.25;t[axis,3]=value
        if axis==0:t[:3,:3]=[[0,0,1],[0,1,0],[-1,0,0]]
        walls.append(surface("wall-"+str(index),t,[4,2.5,0]))
    room={"walls":walls,"floors":[surface("floor",floor,[4,4,0],[[-2,-2],[2,-2],[2,2],[-2,2]])],"objects":[],"doors":[],"windows":[],"openings":[]}
    surfaces=room_surfaces(room)
    mesh=o3d.geometry.TriangleMesh()
    for plane in surfaces:
        v,f=triangulate(plane.polygon)
        part=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(v),o3d.utility.Vector3iVector(f))
        part.transform(plane.transform);mesh+=part
    object_start=len(mesh.triangles)
    cube=o3d.geometry.TriangleMesh.create_box(.8,.8,.8);cube.translate([-.4,0,-.9]);mesh+=cube
    scene=o3d.t.geometry.RaycastingScene();scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
    frames=[];masks={}
    for index,position in enumerate(([0,.75,1.7],[1.7,.75,0],[0,.75,-1.7],[-1.7,.75,0],[.7,.75,1.7])):
        position=np.array(position,dtype=float);forward=np.array([0,.75,0])-position;forward/=np.linalg.norm(forward)
        right=np.cross(forward,[0,1,0]);down=np.cross(forward,right)
        cv=np.eye(4);cv[:3,:3]=np.c_[right,down,forward];cv[:3,3]=position
        def render(w,h):
            x,y=np.meshgrid(np.arange(w),np.arange(h));f=w*.65
            rays=np.c_[((x.ravel()-w/2)/f),((y.ravel()-h/2)/f),np.ones(w*h)]@cv[:3,:3].T
            hit=scene.cast_rays(o3d.core.Tensor(np.c_[np.tile(position,(w*h,1)),rays].astype(np.float32)))
            z=hit["t_hit"].numpy();ids=hit["primitive_ids"].numpy()
            points=position+rays*z[:,None]
            color=np.tile([155,145,135],(w*h,1)).astype(np.uint8)
            color[ids>=object_start]=[210,35,25]
            # Actual wall artwork appears only in captured pixels, not geometry.
            poster=(abs(points[:,2]+2)<.02)&(points[:,0]>.3)&(points[:,0]<.9)&(points[:,1]>1)&(points[:,1]<1.6)
            color[poster]=[15,35,230]
            return z.reshape(h,w),color.reshape(h,w,3),((ids>=object_start)&(ids<len(mesh.triangles))).reshape(h,w)
        depth,_,mask=render(80,80);_,rgb,_=render(320,320)
        photo=io.BytesIO();Image.fromarray(rgb).save(photo,format="JPEG",quality=98)
        meta={"schema_version":1,"id":"frame-"+str(index),"capture_id":capture_id,"timestamp":index*30,
            "width":320,"height":320,"intrinsics":[208,208,160,160],"camera_to_scan_transform":(cv@CAMERA_FLIP).flatten(order="F").tolist(),
            "depth_width":80,"depth_height":80,"depth_format":"float16_le_meters",
            "confidence_width":80,"confidence_height":80,"confidence_format":"uint8_arkit"}
        artifacts=[artifact("jpeg",photo.getvalue(),"jpg"),artifact("depth",depth.astype('<f2').tobytes(),"bin"),
            artifact("confidence",np.full((80,80),2,dtype=np.uint8).tobytes(),"bin"),artifact("metadata",json.dumps(meta).encode(),"json")]
        frames.append({"id":meta["id"],"metadata":meta,"artifacts":artifacts});masks[meta["id"]]=mask
    data={"schemaVersion":1,"captureId":capture_id,"coordinateSystem":"arkit_scan_meters_y_up","anchors":[{
        "transform":np.eye(4).flatten(order="F").tolist(),"vertexCount":len(mesh.vertices),"triangleCount":len(mesh.triangles),
        "positions":np.asarray(mesh.vertices,dtype='<f4').tobytes(),"triangles":np.asarray(mesh.triangles,dtype='<u4').tobytes()}]}
    manifest=Manifest.model_validate({"schema_version":1,"capture_id":capture_id,"state":"local_saved","frames":frames,
        "scene_mesh":artifact("scene_mesh",plistlib.dumps(data,fmt=plistlib.FMT_BINARY),"mesh"),
        "room_export":artifact("roomplan",json.dumps(room).encode(),"json")})
    atomic_json(folder/"manifest.json",manifest.model_dump())
    def inventory(manifest,inputs,room,surfaces,working,budget):
        t=np.eye(4);t[:3,3]=[0,.4,-.5]
        seed=InstanceSeed("actual-chair","source-chair","chair","Actual captured chair","furniture",t,np.array([.8,.8,.8]))
        observations=[{"entity_id":seed.id,"frame":f,"mask":masks[f.id],"score":.99} for f in manifest.frames]
        members=[];exclusions={}
        for frame in manifest.frames:
            photo=next(a for a in frame.artifacts if a.type=="jpeg")
            with Image.open(inputs/photo.filename) as image:rgb=np.array(image)
            poster=(rgb[:,:,2]>180)&(rgb[:,:,0]<70)
            small=np.asarray(Image.fromarray(poster).resize((80,80),Image.Resampling.NEAREST))
            exclusions[frame.id]=masks[frame.id]|small
            if poster.sum()>256:
                members.append({"frame":frame,"mask":poster,"score":.99})
                observations.append({"entity_id":"actual-poster","frame":frame,"mask":small,"score":.99})
        assert len(members)>=2
        decor=[{"id":"actual-poster","label":"Captured poster","support":next(s for s in surfaces if s.source_id=="wall-0"),"members":members}]
        return [seed],observations,decor,exclusions
    return manifest,inventory


def test_complete_room_publish_has_closed_object_clean_shell_and_verified_assets(tmp_path):
    manifest,inventory=room_capture(tmp_path)
    result=process_walkthrough(tmp_path,1,inventory_fn=inventory)
    output=tmp_path/"results/1"
    assert not (tmp_path/"results/1.building").exists()
    assert result["status"]=="succeeded" and result["scene_schema_version"]==2
    bundle=SceneBundle.model_validate_json((output/"scene.json").read_text())
    assert bundle.ready and len(bundle.entities)==8
    chair=next(e for e in bundle.entities if e.id=="actual-chair")
    assert chair.move_ready and chair.kind=="furniture"
    mesh=o3d.io.read_triangle_mesh(str(output/chair.asset))
    mesh.remove_duplicated_vertices()  # OBJ imports split vertices at legitimate UV seams.
    assert mesh.is_watertight() and not mesh.is_self_intersecting()
    for asset in result["assets"]:assert digest(output/asset["filename"])==asset["sha256"]
    assert all(not e.move_ready for e in bundle.entities if e.kind in ("wall","floor","ceiling"))
    assert json.loads((output/"quality.json").read_text())["gemini_enabled"] is False
    assert process_walkthrough(tmp_path,1,inventory_fn=lambda *a:pytest.fail("Committed revision was recomputed"))==result
    poster=next(e for e in bundle.entities if e.id=="actual-poster")
    assert poster.kind=="wall_decor" and poster.move_ready and poster.support_id
    with Image.open(output/"actual-poster.png") as image:
        pixel=np.asarray(image)[image.height//2,image.width//2,:3]
        assert pixel[2]>180 and pixel[0]<70 # Captured poster pixels survive.
    with Image.open(output/(poster.support_id+".png")) as image:
        pixel=np.asarray(image)[int(image.height*.48),int(image.width*.65)]
        assert not (pixel[2]>180 and pixel[0]<70) # No original poster ghost.


def test_failed_room_never_commits_a_partial_scene(tmp_path):
    _,inventory=room_capture(tmp_path)
    def broken(*args):raise RescanRequired("missing object views")
    with pytest.raises(RescanRequired):process_walkthrough(tmp_path,1,inventory_fn=broken)
    assert not (tmp_path/"results/1").exists()


def test_occlusion_boundary_closure_preserves_measured_faces():
    mesh=o3d.geometry.TriangleMesh.create_box(1,1,1)
    triangles=np.asarray(mesh.triangles)
    centers=np.asarray(mesh.vertices)[triangles].mean(axis=1)
    mesh.remove_triangles_by_mask(centers[:,1]>.99)
    vertices=np.asarray(mesh.vertices).copy()
    completed,count=close_observed(mesh)
    assert count==10 and completed.is_watertight()
    assert np.array_equal(vertices,np.asarray(completed.vertices))


def test_flat_fragment_cannot_be_declared_complete_by_duplicating_its_back():
    mesh=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector([[0,0,0],[1,0,0],[1,1,0],[0,1,0]]),o3d.utility.Vector3iVector([[0,1,2],[0,2,3]]))
    with pytest.raises(RescanRequired):close_observed(mesh)


def test_surface_holes_preserve_openings_and_inpainting_preserves_observed_pixels():
    polygon=Polygon([[-2,-2],[2,-2],[2,2],[-2,2]],holes=[[[-.5,-.5],[.5,-.5],[.5,.5],[-.5,.5]]])
    vertices,faces=triangulate(polygon)
    assert sum(Polygon(vertices[f,:2]).area for f in faces)==pytest.approx(15)
    rgb=np.full((32,32,3),[120,130,140],dtype=np.uint8)
    known=np.ones((32,32),dtype=bool);known[10:20,10:20]=False;rgb[~known]=[255,0,0]
    filled=fill_texture(rgb,known)
    assert np.array_equal(filled[known],rgb[known])
    assert np.max(abs(filled[~known].astype(int)-[120,130,140]))<=1
