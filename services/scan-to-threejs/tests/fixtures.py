"""Synthetic calibration evidence, never a substitute for a user's Room."""
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw


def cm(matrix):
    return np.asarray(matrix).flatten(order='F').tolist()


def room_plan(world=None):
    world = np.eye(4) if world is None else world
    walls = []
    for i,(x,z,yaw,length) in enumerate([(0,-1.5,0,4),(2,0,np.pi/2,3),(0,1.5,np.pi,4),(-2,0,-np.pi/2,3)]):
        c,s = np.cos(yaw),np.sin(yaw)
        m = np.array([[c,0,s,x],[0,1,0,1.3],[-s,0,c,z],[0,0,0,1.]])
        walls.append({'identifier':f'wall-{i}','transform':cm(world@m),
                      'dimensions':[length,2.6,0],'confidence':{'high':{}}})
    floor = np.array([[1,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1.]])
    return {'walls':walls,'doors':[],'windows':[],'openings':[],'objects':[],
        'floors':[{'transform':cm(world@floor),'dimensions':[4,3,0],
                   'polygonCorners':[[-2,-1.5,0],[2,-1.5,0],[2,1.5,0],[-2,1.5,0]]}]}


def native_bundle(root: Path, *, mesh=True):
    for sub in ('rooms','photos','depth','mesh'):
        (root/sub).mkdir(parents=True,exist_ok=True)
    c,s = np.cos(.26),np.sin(.26)
    world = np.array([[c,0,s,2.5],[0,1,0,.4],[-s,0,c,-3],[0,0,0,1.]])
    (root/'rooms/room-7.json').write_text(json.dumps(room_plan(world)))
    records = []
    for i,(name,index) in enumerate([('0009',7),('0000',3),('0002',7)]):
        image = Image.new('RGB',(640,480),(40+40*i,80,130))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0,0,320,200),fill=(240,30,20)); draw.text((50,50),name,fill='white')
        image.save(root/f'photos/{name}.jpg',quality=95)
        pose = np.array([[0,1,0,-.2+i*.2],[-1,0,0,1.4],[0,0,1,1],[0,0,0,1.]])
        records.append({'file':f'photos/{name}.jpg','room':index,'timestamp':i,
                        'transform':cm(world@pose),'intrinsics':[600,0,0,0,600,0,320,240,1],
                        'width':640,'height':480,'blurPixels':.2,'highRes':False})
    (root/'photos/photos.json').write_text(json.dumps(records))
    (root/'depth/frames.json').write_text('[]')
    (root/'manifest.json').write_text(json.dumps({'format':'house-capture/5',
        'rooms':[{'index':7,'name':'Synthetic calibration room','file':'rooms/room-7.json'}],
        'photos':'photos/photos.json','depthFrames':'depth/frames.json'}))
    if mesh:
        points = [(x,y,-1.5) for y in np.linspace(0,2.6,13) for x in np.linspace(-2,2,17)]
        vertices = (world@np.c_[points,np.ones(len(points))].T).T[:,:3]
        faces = []
        for y in range(12):
            for x in range(16):
                a=y*17+x
                faces.extend([(a,a+1,a+18),(a,a+18,a+17)])
        with (root/'mesh/room-7.ply').open('w') as f:
            f.write(f'ply\nformat ascii 1.0\nelement vertex {len(vertices)}\nproperty float x\nproperty float y\nproperty float z\nelement face {len(faces)}\nproperty list uchar int vertex_indices\nend_header\n')
            for v in vertices: f.write(' '.join(map(str,v))+'\n')
            for v in faces: f.write('3 '+' '.join(map(str,v))+'\n')
    return world,records
