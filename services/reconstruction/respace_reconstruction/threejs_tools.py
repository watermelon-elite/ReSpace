"""Restricted authoring tools for the pinned Scan to Three.js workflow.

Generated TypeScript runs in an isolated, network-blocked browser. No generated
source or tool argument is ever evaluated by Python, Node, or a command shell.
"""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

import numpy as np
from PIL import Image, ImageDraw

from .store import atomic_json, digest

ROOT=Path(__file__).resolve().parents[2]/'scan-to-threejs'
SCRIPTS=ROOT/'.agents/skills/scan-to-threejs/scripts'


def source_module():
    import importlib.util
    spec=importlib.util.spec_from_file_location('respace_scan_prepare',ROOT/'prepare.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def image_input(path,limit=1536):
    with Image.open(path) as image:
        image=image.convert('RGB');image.thumbnail((limit,limit));stream=io.BytesIO();image.save(stream,'JPEG',quality=88)
    return {'type':'input_image','image_url':'data:image/jpeg;base64,'+base64.b64encode(stream.getvalue()).decode(),'detail':'high'}


def clean_environment(work):
    # The browser, Vite, TypeScript and public texture helper never inherit keys.
    home=work/'process-home';home.mkdir(exist_ok=True)
    env={k:v for k,v in os.environ.items() if k in ('PATH','SYSTEMROOT','TMPDIR','LANG')}
    env.update(HOME=str(home),PLAYWRIGHT_BROWSERS_PATH=str(ROOT/'worker/.browsers'),NO_PROXY='127.0.0.1,localhost')
    return env


def run(command,project,timeout=180):
    result=subprocess.run(command,cwd=project,env=clean_environment(project),capture_output=True,text=True,timeout=timeout)
    if result.returncode:raise ValueError((result.stderr or result.stdout or f'Tool exited with code {result.returncode}')[-8000:])
    return result.stdout[-12000:]


def browser(project,request):
    operation=uuid.uuid4().hex
    request_file=project/('request-'+operation+'.json');response_file=project/('response-'+operation+'.json')
    atomic_json(request_file,request)
    try:
        try:run(['node',str(ROOT/'worker/render.mjs'),str(project),str(request_file),str(response_file)],project,180)
        except ValueError:
            if response_file.exists():raise ValueError(json.loads(response_file.read_text()).get('error','Browser operation failed')) from None
            raise
        result=json.loads(response_file.read_text())
        if result.get('error'):raise ValueError(result['error'])
        return result
    finally:
        request_file.unlink(missing_ok=True);response_file.unlink(missing_ok=True)


def source_hash(project):
    paths=sorted(p for parent in (project/'demos/room',project/'data/web-assets/room/textures') if parent.exists() for p in parent.rglob('*') if p.is_file())
    return hashlib.sha256(json.dumps([(str(p.relative_to(project)),digest(p)) for p in paths]).encode()).hexdigest()


class AuthoringTools:
    def __init__(self,project,progress):
        self.project=project;self.progress=progress
        self.evidence=project/'evidence';self.evidence.mkdir(exist_ok=True)
        self.photos=sorted((project/'data/web-assets/room/photos').glob('*.jpg'))
        self.textures=project/'data/web-assets/room/textures';self.textures.mkdir(parents=True,exist_ok=True)

    def path(self,name):
        if not isinstance(name,str) or '\\' in name or Path(name).is_absolute():raise ValueError('Use a project-relative path')
        path=(self.project/name).resolve()
        if not path.is_relative_to(self.project.resolve()) or any(x.startswith('.') and x!='.agents' for x in Path(name).parts):raise ValueError('Path is outside the authoring project')
        return path

    def read(self,name):
        path=self.path(name)
        allowed=('demos/','packages/room-runtime/','.agents/skills/scan-to-threejs/','data/demos/','data/captures-in/room/','evidence/')
        if name!='reconstruction.ts' and not name.startswith(allowed):raise ValueError('Only modeling sources and measured evidence may be read')
        if path.is_dir():return {'files':[str(p.relative_to(self.project)) for p in sorted(path.rglob('*')) if p.is_file()][:600]}
        if path.suffix not in ('.ts','.json','.md','.txt','.py') or path.stat().st_size>400000:raise ValueError('Use inspect_photo/inspect_image for visual evidence')
        return {'path':name,'text':path.read_text()}

    def write(self,name,text):
        path=self.path(name)
        if not re.fullmatch(r'demos/room/(items|parts)/[a-zA-Z0-9_-]+\.ts',name):raise ValueError('Write modular items/*.ts or parts/*.ts only; trusted runtime is read-only')
        if len(text.encode())>250000:raise ValueError('Split this Object into readable modules')
        # Imports stay in the project. Network imports and Vite filesystem routes
        # must not provide another execution or data-access surface.
        if re.search(r'https?:|file:|/@fs/|node:|import\s*\(\s*[^\'"\s]',text):raise ValueError('Use local static Three.js/runtime imports and local assets')
        path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix('.writing');temporary.write_text(text);temporary.replace(path)
        return {'written':name,'sha256':digest(path)}

    def crop(self,photo,name,quad,width,height):
        if not 0<=photo<len(self.photos) or not re.fullmatch(r'[a-zA-Z0-9_-]+\.png',name):raise ValueError('Invalid source photo or texture name')
        if not 16<=width<=4096 or not 16<=height<=4096 or len(quad)!=8 or not all(np.isfinite(quad)):raise ValueError('Invalid texture crop dimensions')
        with Image.open(self.photos[photo]) as image:
            if any(not 0<=quad[i]<=image.size[i%2] for i in range(8)):raise ValueError('Crop corners are outside the upright photo')
            # PIL QUAD order is top-left, bottom-left, bottom-right, top-right.
            image.transform((width,height),Image.Transform.QUAD,quad,Image.Resampling.BICUBIC).save(self.textures/name)
        record=self.textures/'sources.json';sources=json.loads(record.read_text()) if record.exists() else {}
        sources[name]={'source':'capture-photo','photo_index':photo,'source_sha256':digest(self.photos[photo]),'quad':quad,'size':[width,height]};atomic_json(record,sources)
        return {'url':'/room/textures/'+name,'file':str((self.textures/name).relative_to(self.project))}

    def texture(self,query,asset,name):
        if asset is None:
            if not re.fullmatch(r'[a-zA-Z0-9 _-]{1,120}',query):raise ValueError('Use plain material search terms')
            return {'search':run([sys.executable,str(SCRIPTS/'fetch_textures.py'),'search',query],self.project,60)}
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',asset) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,60}',name):raise ValueError('Invalid CC0 asset or local material name')
        self.progress('creating_textures')
        result=run([sys.executable,str(SCRIPTS/'fetch_textures.py'),'get',str(self.textures),name+'=polyhaven:'+asset],self.project,180)
        record=self.textures/'sources.json';sources=json.loads(record.read_text()) if record.exists() else {}
        sources[name]={'source':'Poly Haven','asset':asset,'license':'CC0','url':'https://polyhaven.com/a/'+asset};atomic_json(record,sources)
        return {'result':result,'files':[str(p.relative_to(self.project)) for p in sorted(self.textures.rglob('*')) if p.is_file()]}

    def render(self,photo,view,source):
        if source not in ('scan','model'):raise ValueError('Choose scan or model')
        if photo is not None and not 0<=photo<len(self.photos):raise ValueError('Photo index is out of range')
        if view not in ('top','up','n','s','e','w'):raise ValueError('Unknown orthographic view')
        path=self.evidence/f'{source}-{photo if photo is not None else view}.png'
        self.progress('checking_threejs')
        browser(self.project,{'operation':'capture','room':'room','photo':photo,'view':view,'source':source,'output':str(path)} if photo is not None else {'operation':'capture','room':'room','view':view,'source':source,'output':str(path)})
        return {'file':str(path.relative_to(self.project))},[image_input(path)]

    def contacts(self):
        result=[]
        # Every photo remains represented, in original array order. Larger
        # captures are paginated, never silently reordered or truncated.
        for start in range(0,len(self.photos),36):
            subset=self.photos[start:start+36];sheet=Image.new('RGB',(1200,270*((len(subset)+3)//4)),(35,35,35));draw=ImageDraw.Draw(sheet)
            for j,path in enumerate(subset):
                with Image.open(path) as im:
                    im=im.convert('RGB');im.thumbnail((294,240));x=(j%4)*300;y=(j//4)*270;sheet.paste(im,(x,y));draw.text((x+3,y+242),f'Photo {start+j}',fill='white')
            out=self.evidence/f'contacts-{start}.jpg';sheet.save(out,quality=88);result.append(image_input(out,1800))
        return result

    def execute(self,name,args):
        if name=='read_file':return self.read(args['path']),[]
        if name=='write_source':return self.write(args['path'],args['source']),[]
        if name=='inspect_photo':
            i=args['index']
            if not 0<=i<len(self.photos):raise ValueError('Photo index is out of range')
            with Image.open(self.photos[i]) as im:size=list(im.size)
            return {'photo':i,'upright_size':size},[image_input(self.photos[i])]
        if name=='inspect_image':
            path=self.path(args['path'])
            if not path.is_relative_to(self.evidence) and not path.is_relative_to(self.textures):raise ValueError('Inspect rendered evidence or created textures')
            return {'path':args['path']},[image_input(path)]
        if name=='crop_texture':return self.crop(**args),[]
        if name=='pbr_texture':return self.texture(**args),[]
        if name=='render':return self.render(**args)
        raise ValueError('Unknown modeling tool')
