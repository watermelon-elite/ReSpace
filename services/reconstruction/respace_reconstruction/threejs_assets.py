"""Validate and preserve authored geometry/UV/PBR data in native assets.

Nothing here assigns a default texture family or reconstructs Objects from boxes.
"""
import base64
import io
import math
from pathlib import Path

import numpy as np
from PIL import Image
from shapely import Polygon, Point, LineString, union_all
from shapely.ops import triangulate

from .models import SAFE_NAME
from .scene import SceneBundle, SceneEntity, SceneMaterial, Navigation
from .navigation import entity_footprint
from .store import atomic_json, digest
from .walkthrough import merge_scene
from .usdz import export_usdz


def name(value):
    if not isinstance(value,str) or not SAFE_NAME.fullmatch(value) or '..' in value:
        raise ValueError('Unsafe Three.js export identity')
    return value


def array(value,dtype,columns):
    raw=base64.b64decode(value,validate=True)
    if len(raw)>128*1024**2: raise ValueError('Export array too large')
    result=np.frombuffer(raw,dtype=dtype)
    if len(result)%columns or not np.isfinite(result).all(): raise ValueError('Invalid exported geometry array')
    return result.reshape(-1,columns)


def compile_assets(data,measurements,output,capture_id,revision,quality,provenance,*,generation_model):
    if data.get('format')!='respace-threejs-export/1': raise ValueError('Unknown Three.js export')
    if not 1<=len(data['entities'])<=512 or not 1<=len(data['materials'])<=4096: raise ValueError('Native scene resource limits exceeded')
    output.mkdir(parents=True,exist_ok=True)
    r2s=np.linalg.inv(np.array(measurements['transform']['worldToRoom']).reshape(4,4,order='F'))
    if not np.isfinite(r2s).all(): raise ValueError('Invalid capture transform')
    for filename,encoded in data['textures'].items():
        name(filename)
        raw=base64.b64decode(encoded,validate=True)
        if len(raw)>32*1024**2: raise ValueError('Oversized material image')
        with Image.open(io.BytesIO(raw)) as image:
            if image.format!='PNG' or max(image.size)>8192: raise ValueError('Unsupported baked texture')
            image.verify()
        (output/filename).write_bytes(raw)
    materials=[]; by_material={}
    for raw in data['materials']:
        identity=name(raw['id']); owner=name(raw['owner_id'])
        if identity in by_material: raise ValueError('Duplicate material identity')
        fields={k:raw.get(k) for k in ('base_color_texture','roughness_texture','normal_texture','metallic_texture','emissive_texture')}
        if any(v is not None and v not in data['textures'] for v in fields.values()): raise ValueError('Missing texture in export')
        material=SceneMaterial(id=identity,owner_id=owner,slot=identity,source_material=identity,
            base_color=raw['base_color'],roughness=raw['roughness'],metallic=raw['metallic'],
            emissive_color=raw['emissive_color'],emissive_intensity=raw['emissive_intensity'],opacity=raw['opacity'],
            unlit=raw.get('unlit',False),**fields)
        materials.append(material);by_material[identity]=(material,raw)
        if material.base_color_texture:
            with Image.open(output/material.base_color_texture) as image:
                alpha=image.convert('RGBA').getchannel('A')
                if alpha.getextrema()!=(255,255):
                    alpha.save(output/(identity+'-opacity.png'))
    entities=[];triangles=0;wall_obstacles=[]
    for source in data['entities']:
        identity=name(source['id']); filename=identity+'.obj'; library=identity+'.mtl'
        if identity in {e.id for e in entities}: raise ValueError('Duplicate Object id')
        buffers=[];all_vertices=[];used=[]; offset=0
        for part in source['parts']:
            mat=name(part['material'])
            if mat not in by_material or by_material[mat][0].owner_id!=identity: raise ValueError('Material owner mismatch')
            v=array(part['positions'],'<f4',3).astype(float); uv=array(part['uvs'],'<f4',2); normals=array(part['normals'],'<f4',3).astype(float)
            f=array(part['indices'],'<u4',3).astype(np.int64)
            if not len(v) or not len(f) or len(uv)!=len(v) or len(normals)!=len(v) or f.max()>=len(v): raise ValueError('Invalid native mesh topology')
            v=v@r2s[:3,:3].T+r2s[:3,3];normals=normals@r2s[:3,:3].T
            if abs(v).max()>10000 or (v.max(axis=0)-v.min(axis=0)).max()>50: raise ValueError('Mesh is outside measured room scale')
            triangles+=len(f)
            if triangles>1000000: raise ValueError('Optimize geometry below the mobile triangle limit')
            if source['kind']=='wall':
                # Slice the delivered wall triangles, preserving actual door
                # gaps instead of turning a whole wall's bounds into a barrier.
                for triangle in v[f]:
                    for height in (.3,1.,1.6):
                        y=float(r2s[1,3])+height;points=[]
                        for a,b in zip(triangle,np.roll(triangle,-1,axis=0)):
                            if (a[1]<=y<b[1]) or (b[1]<=y<a[1]):
                                point=a+(b-a)*(y-a[1])/(b[1]-a[1]);points.append(point[[0,2]])
                        if len(points)==2 and np.linalg.norm(points[0]-points[1])>1e-5:
                            wall_obstacles.append(LineString(points).buffer(.015,cap_style='square'))
            buffers.append((mat,v,uv,normals,f));all_vertices.append(v)
            if mat not in used:used.append(mat)
        if not buffers:raise ValueError('Empty authored Object')
        with (output/filename).open('w') as stream:
            stream.write('mtllib '+library+'\n')
            for mat,v,uv,normals,f in buffers:
                np.savetxt(stream,v,fmt='v %.7f %.7f %.7f');np.savetxt(stream,uv,fmt='vt %.7f %.7f');np.savetxt(stream,normals,fmt='vn %.7f %.7f %.7f')
                stream.write('usemtl '+mat+'\n')
                for face in f+offset+1:stream.write('f '+' '.join(f'{i}/{i}/{i}' for i in face)+'\n')
                offset+=len(v)
        with (output/library).open('w') as stream:
            for mat in used:
                binding,raw=by_material[mat]
                color=raw['linear_color'];emissive=raw['emissive_linear_color']
                if any(not isinstance(x,(int,float)) or not math.isfinite(x) for x in color+emissive):raise ValueError('Invalid material color')
                if binding.unlit:emissive=color;color=[0,0,0]
                stream.write(f'newmtl {mat}\nKd '+' '.join(map(str,color))+f'\nPr {binding.roughness}\nPm {binding.metallic}\nd {binding.opacity}\nKe '+' '.join(map(str,emissive))+'\n')
                if (output/(mat+'-opacity.png')).exists():stream.write(f'map_d {mat}-opacity.png\n')
                for tag,field in [('map_Kd','base_color_texture'),('map_Pr','roughness_texture'),('map_Pm','metallic_texture'),('norm','normal_texture'),('map_Ke','emissive_texture')]:
                    if binding.unlit and tag=='map_Kd':tag='map_Ke'
                    if getattr(binding,field):stream.write(f'{tag} {getattr(binding,field)}\n')
        vertices=np.concatenate(all_vertices);lo=vertices.min(axis=0);hi=vertices.max(axis=0)
        floor_y=float(r2s[1,3])
        collidable=bool(source['collidable']) and lo[1]<floor_y+1.6 and hi[1]>floor_y+.15
        entities.append(SceneEntity(id=identity,label=source['label'] or identity,category=source['category'] or source['kind'],kind=source['kind'],
            asset=filename,local_to_scan_transform=np.eye(4).flatten(order='F').tolist(),bounds_min=lo.tolist(),bounds_max=hi.tolist(),material_ids=used,
            support_id=source.get('support_id'),collidable=collidable,move_ready=source['kind'] in ('furniture','wall_decor'),observed_fraction=1.))
    if not {'floor','ceiling','wall'}<={e.kind for e in entities}:raise ValueError('Authored scene is missing its room shell')
    floor_poly=np.array([[x,0,z] for x,z in measurements['polygon']])@r2s[:3,:3].T+r2s[:3,3]
    polygon=Polygon(floor_poly[:,[0,2]])
    if not polygon.is_valid or polygon.area<.5:raise ValueError('Invalid measured floor')
    free=polygon.buffer(-.21)
    obstacles=[]
    if wall_obstacles:
        occupied=union_all(wall_obstacles).simplify(.005,preserve_topology=True)
        parts=list(occupied.geoms) if hasattr(occupied,'geoms') else [occupied]
        # Navigation's polygon contract has no hole field. Decompose rings so
        # enclosing walls never turn the room interior into a solid obstacle.
        simple=[triangle for p in parts if p.geom_type=='Polygon' and not p.is_empty
                for triangle in (triangulate(p) if p.interiors else [p]) if p.covers(triangle)]
        obstacles=[list(map(list,p.exterior.coords))[:-1] for p in simple]
        free=free.difference(occupied.buffer(.205))
    for e in entities:
        if e.collidable and e.kind not in ('wall','floor','ceiling','wall_decor'):free=free.difference(entity_footprint(e).buffer(.205))
    if free.is_empty:raise ValueError('No safe first-person starting point in authored scene')
    spawn=None; yaw=0.
    for photo in measurements['photos']:
        p=np.array(photo['position'])@r2s[:3,:3].T+r2s[:3,3]
        if free.contains(Point(p[[0,2]])):
            spawn=p[[0,2]];forward=r2s[:3,:3]@photo['forward'];yaw=float(math.atan2(-forward[0],-forward[2]));break
    if spawn is None:
        p=free.representative_point();spawn=[p.x,p.y]
    navigation=Navigation(floor_polygons=[floor_poly[:,[0,2]].tolist()],floor_height=float(r2s[1,3]),
        spawn_position=[float(spawn[0]),float(r2s[1,3])+1.6,float(spawn[1])],spawn_yaw=yaw,obstacles=obstacles)
    bundle=SceneBundle(capture_id=capture_id,scene_id='threejs-'+capture_id,reconstruction_revision=revision,
        entities=entities,materials=materials,navigation=navigation,ready=True)
    if not free.contains(Point(navigation.spawn_position[0],navigation.spawn_position[2])):raise ValueError('Unsafe exported spawn')
    atomic_json(output/'quality.json',dict(quality,triangle_count=triangles,ready=True))
    atomic_json(output/'provenance.json',provenance)
    atomic_json(output/'scene.json',bundle.model_dump())
    merge_scene(bundle,output)
    usdz=export_usdz(output/'model.obj')
    names={p.name for p in output.iterdir() if p.is_file()}
    bundle.validate_files(output,names)
    assets=[{'filename':n,'byte_length':(output/n).stat().st_size,'sha256':digest(output/n)} for n in sorted(names)]
    if len(assets)>512 or any(a['byte_length']>128*1024**2 for a in assets) or sum(a['byte_length'] for a in assets)>512*1024**2:
        raise ValueError('Authored scene exceeds mobile file limits; optimize without replacing appearance')
    return {'revision':revision,'status':'succeeded','model_filename':'model.obj','usdz_filename':usdz,'scene_filename':'scene.json',
        'scene_schema_version':2,'assets':assets,'needs_review':False,'error':None,'coordinate_system':'arkit_scan_meters_y_up',
        'quality_filename':'quality.json','generation_model':generation_model,'generated_triangle_count':triangles,'pipeline':'threejs'}
