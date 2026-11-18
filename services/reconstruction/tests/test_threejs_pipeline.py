"""Real browser authoring/export/native reload; only paid API calls are mocked."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
from types import SimpleNamespace

from fastapi.testclient import TestClient
import numpy as np
from PIL import Image
import pytest
from pxr import Usd, UsdGeom

from respace_reconstruction import astra, astra_spending, pipeline, threejs_agent, threejs_pipeline, threejs_tools
from respace_reconstruction.app import create_app
from respace_reconstruction.models import NativeManifest, parse_manifest
from respace_reconstruction.scene import SceneBundle
from respace_reconstruction.store import Store, atomic_json, digest

ROOT=threejs_tools.ROOT
spec=importlib.util.spec_from_file_location('threejs_synthetic_fixture',ROOT/'tests/fixtures.py')
fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixtures)


@pytest.fixture
def native(tmp_path):
    source=tmp_path/'original';world,_=fixtures.native_bundle(source)
    metadata=json.loads((source/'manifest.json').read_text());metadata.update(state='completed',integrityFile='integrity.json');atomic_json(source/'manifest.json',metadata)
    atomic_json(source/'integrity.json',{'format':'respace-source-integrity/1','files':[
        {'path':str(p.relative_to(source)),'byteLength':p.stat().st_size,'sha256':digest(p)} for p in sorted(source.rglob('*')) if p.is_file()]})
    files=[]
    for p in sorted(source.rglob('*')):
        if p.is_file():
            path=str(p.relative_to(source));identity=hashlib.sha256(path.encode()).hexdigest()
            files.append({'id':identity,'filename':identity,'relative_path':path,'byte_length':p.stat().st_size,'sha256':digest(p)})
    manifest=NativeManifest(schema_version=2,capture_id='native-synthetic',format='house-capture/5',state='completed',files=files)
    return manifest,source,world


MODULE='''import * as T from 'three';
import type {PartContext} from '../../../reconstruction';
export async function build(ctx:PartContext) {
 const texture=await new T.TextureLoader().loadAsync('/room/textures/captured-floor.png');texture.colorSpace=T.SRGBColorSpace;texture.wrapS=texture.wrapT=T.RepeatWrapping;texture.repeat.set(2,2);
 const canvas=document.createElement('canvas');canvas.width=canvas.height=2;const paint=canvas.getContext('2d')!;paint.fillStyle='rgb(64,192,128)';paint.fillRect(0,0,2,2);
 const orm=new T.CanvasTexture(canvas);orm.repeat.copy(texture.repeat);orm.wrapS=orm.wrapT=T.RepeatWrapping;
 const floor=ctx.group.getObjectByName('floor') as T.Mesh;floor.material=new T.MeshStandardMaterial({map:texture,roughnessMap:orm,roughness:.65,metalnessMap:orm,metalness:.5,emissiveMap:texture,emissive:0xffffff,emissiveIntensity:.2,side:T.DoubleSide});
 const item=new T.Group();item.name='curved-chair';item.userData.respace={id:'curved-chair',label:'Curved chair',category:'chair',kind:'furniture',collidable:true};
 const points=[new T.Vector2(.1,0),new T.Vector2(.3,.3),new T.Vector2(.4,.5),new T.Vector2(.32,.7)];
 const mesh=new T.Mesh(new T.LatheGeometry(points,48),new T.MeshStandardMaterial({color:'#ac4528',roughness:.4,metalness:.2}));item.add(mesh);ctx.group.add(item);
 const art=new T.Mesh(new T.PlaneGeometry(.4,.3),new T.MeshBasicMaterial({map:texture}));art.position.set(.5,1.4,-1.43);art.name='captured-art';art.userData.respace={id:'captured-art',label:'Captured graphic',category:'art',kind:'wall_decor',supportId:'wall-0',collidable:false};ctx.group.add(art);
}'''


def fake_api(monkeypatch,reject=False,batch=False):
    monkeypatch.setenv('OPENAI_API_KEY','offline-only');monkeypatch.setattr(astra_spending,'count_input_tokens',lambda *_:1000)
    calls=[];step=0
    sequence=[('inspect_photo',{'index':0}),('crop_texture',{'photo':0,'name':'captured-floor.png','quad':[0,0,0,640,480,640,480,0],'width':128,'height':128}),
              ('write_source',{'path':'demos/room/items/chair.ts','source':MODULE}),('render',{'photo':0,'view':'top','source':'model'}),('submit_model',{'summary':'Synthetic test room with curved mesh and photo maps','uncertainties':['Synthetic functional fixture, not a real fidelity test']})]
    def call(body,key):
        nonlocal step
        # HTTP serializes each request before the mutable conversation advances.
        calls.append(json.loads(json.dumps(body)))
        if body.get('tools'):
            # Stop an intentionally rejected test after one review, rather than
            # purchasing endless mocked author turns.
            if step>=len(sequence):raise RuntimeError('Review rejected; no fixture correction provided')
            stop=(2 if step<2 else len(sequence)) if batch and body.get('parallel_tool_calls') else step+1
            output=[]
            while step<stop:
                name,args=sequence[step];step+=1
                output.append({'type':'function_call','name':name,'call_id':f'call-{step}','arguments':json.dumps(args)})
        else:
            indices=[int(re.search(r'Photo index (\d+)',c['text'])[1]) for c in body['input'][0]['content'] if c['type']=='input_text' and c['text'].endswith(': SOURCE')]
            output=[{'type':'message','role':'assistant','content':[{'type':'output_text','text':json.dumps({'views':[{'photo_index':i,'passed':not reject,'issues':['Missing distinctive source shape'] if reject else []} for i in indices]})}]}]
        return {'status':'completed','output':output,'usage':{'input_tokens':1000,'output_tokens':100,'input_tokens_details':{'cached_tokens':0}}}
    monkeypatch.setattr(astra,'call_astra',call)
    return calls


def upload(store,manifest,source):
    store.create(manifest);folder=store.folder(manifest.capture_id)
    for file in manifest.files:shutil.copyfile(source/file.relative_path,folder/'inputs'/file.filename)
    return folder


def test_native_upload_api_integrity_resume_and_no_legacy_adapter(tmp_path,native):
    manifest,source,_=native
    with TestClient(create_app(tmp_path/'api',token='native-test-token',start_worker=False)) as client:
        client.headers['Authorization']='Bearer native-test-token';base='/v1/reconstructions/'+manifest.capture_id
        assert client.put(base,json=manifest.model_dump()).status_code==200
        for item in manifest.files:
            assert client.put(base+'/artifacts/'+item.id,content=(source/item.relative_path).read_bytes()).status_code==200
        assert client.get(base).json()['missing_artifact_ids']==[]
        assert client.post(base+'/run').json()['state']=='queued'
    modified=manifest.model_dump();modified['files'][0]['relative_path']='../escape'
    with pytest.raises(ValueError):parse_manifest(json.dumps(modified))
    # The native seal is mandatory and must match every retained original file.
    store=Store(tmp_path/'bad');folder=upload(store,manifest,source)
    (folder/'inputs'/manifest.files[0].filename).write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='integrity'):store.queue(manifest.capture_id)


def test_threejs_full_flow_photo_texture_curves_native_reload_and_retry(tmp_path,native,monkeypatch):
    manifest,source,world=native;store=Store(tmp_path/'jobs');folder=upload(store,manifest,source)
    calls=fake_api(monkeypatch);monkeypatch.delenv('RESPACE_PIPELINE',raising=False)
    store.queue(manifest.capture_id);assert store.claim()['revision']==1
    result=pipeline.process(folder,1)
    output=folder/'results/1';scene=SceneBundle.model_validate_json((output/'scene.json').read_text())
    scene.validate_files(output,{a['filename'] for a in result['assets']})
    assert result['pipeline']=='threejs' and scene.ready
    assert result['generated_triangle_count']>150
    chair=next(e for e in scene.entities if e.id=='curved-chair')
    np.testing.assert_allclose(chair.bounds_min[1],world[1,3],atol=1e-5)
    # Real source photo pixels, no default material-library assignment.
    floor=next(m for m in scene.materials if m.owner_id=='floor')
    assert floor.base_color_texture and floor.texture_family is None
    assert floor.roughness_texture and floor.metallic_texture and floor.emissive_texture
    assert floor.emissive_intensity==.2
    with Image.open(output/floor.roughness_texture) as image:assert abs(image.getpixel((0,0))[0]-192*.65)<2
    with Image.open(output/floor.metallic_texture) as image:assert abs(image.getpixel((0,0))[0]-64)<2
    with Image.open(output/floor.base_color_texture) as image:
        assert len(image.getcolors(20000))>20
    stage=Usd.Stage.Open(str(output/'model.usdz'))
    meshes=[UsdGeom.Mesh(p) for p in stage.Traverse() if p.IsA(UsdGeom.Mesh)]
    assert meshes and len(meshes[0].GetNormalsAttr().Get())>0
    quality=json.loads((output/'quality.json').read_text())
    assert quality['visual_review']['passed'] and len(quality['visual_review']['views'])==2
    assert calls and any(call.get('tools') for call in calls) and any(not call.get('tools') for call in calls)
    assert all(call['model']=='gpt-6.2-sol' and call['reasoning']=={'effort':'high'} for call in calls)
    for call in calls:
        if call.get('tools'):continue
        indices=[int(re.search(r'Photo index (\d+)',c['text'])[1]) for c in call['input'][0]['content'] if c['type']=='input_text' and c['text'].endswith(': SOURCE')]
        views=call['text']['format']['schema']['properties']['views']
        assert views.get('minItems')==views.get('maxItems')==len(indices)
        assert views['items']['properties']['photo_index'].get('enum')==indices
    assert result['generation_model']=='gpt-6.2-sol'
    provenance=json.loads((output/'provenance.json').read_text())
    assert provenance['generation_model']=='gpt-6.2-sol' and provenance['reasoning_effort']=='high'
    assert provenance['review_reasoning_effort']=='high'
    assert quality['spending']['ceiling_usd']==10.
    assert quality['spending']['known_cost_usd']==pytest.approx(len(calls)*.003)
    assert {entry['model'] for entry in quality['spending']['entries'].values()}=={'gpt-6.2-sol'}
    previews=list((folder/'work/threejs/project/evidence').glob('native-*.png'))
    assert previews
    for preview in previews:
        with Image.open(preview) as image:
            pixels=np.asarray(image.convert('RGB')).astype(float)
            assert np.max(pixels.std(axis=(0,1)))>10, 'Delivered asset check must render textured geometry, not only the background'
    store.finish(manifest.capture_id,'succeeded',result)
    if destination:=os.environ.get('RESPACE_TEST_EXPORT_THREEJS_FIXTURE'):
        destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
        shutil.copytree(output,destination/'assets',dirs_exist_ok=True)
        shutil.copytree(source,destination/'source',dirs_exist_ok=True)
        atomic_json(destination/'manifest.json',manifest.model_dump())
        atomic_json(destination/'result.json',result)

    # Recovered work reuses paid author/review results and exports new immutable
    # revision metadata without another API call.
    count=len(calls);again=threejs_pipeline.process_threejs(folder,2)
    assert len(calls)==count and again['revision']==2
    assert json.loads((folder/'results/2/scene.json').read_text())['reconstruction_revision']==2
    for a in again['assets']:assert digest(folder/'results/2'/a['filename'])==a['sha256']


def test_rejected_native_comparison_never_publishes(tmp_path,native,monkeypatch):
    manifest,source,_=native;store=Store(tmp_path/'jobs');folder=upload(store,manifest,source)
    calls=fake_api(monkeypatch,reject=True)
    monkeypatch.setattr(threejs_agent,'CONTEXT_ROUNDS',1)
    with pytest.raises(RuntimeError,match='Review rejected'):threejs_pipeline.process_threejs(folder,1)
    assert not (folder/'results/1/completion.json').exists()
    reports=list((folder/'work/threejs').glob('submission-*/review.json'))
    assert reports and json.loads(reports[0].read_text())['passed'] is False
    assert list((folder/'work/threejs').glob('context-*.json'))
    # The next correction sees the actual rejected export, even after context
    # refresh, rather than only prose or the differently lit authoring preview.
    evidence=list((reports[0].parent/'evidence').glob('native-*.png'))
    assert len(evidence)==2
    feedback=calls[-1]['input'][0]['content']
    labels=[c.get('text','') for c in feedback]
    assert 'Rejected native view 0: SOURCE' in labels
    assert 'Rejected native view 0: DELIVERED NATIVE ASSETS' in labels
    assert sum(c['type']=='input_image' for c in feedback)>=4


@pytest.mark.parametrize('model,review_effort',[('gpt-6.2-sol','high'),('gpt-6.1-sol','medium')])
def test_tool_batch_resumes_after_interrupt_without_rebuying_or_repeating_tools(tmp_path,native,monkeypatch,model,review_effort):
    manifest,source,_=native;store=Store(tmp_path/'jobs');folder=upload(store,manifest,source)
    calls=fake_api(monkeypatch,batch=True)
    execute=threejs_tools.AuthoringTools.execute;completed=[];interrupt=[True]
    def interrupted(self,name,args):
        if name=='crop_texture' and interrupt[0]:
            interrupt[0]=False
            raise TimeoutError('Controlled interruption between tools')
        result=execute(self,name,args);completed.append(name);return result
    monkeypatch.setattr(threejs_tools.AuthoringTools,'execute',interrupted)
    with monkeypatch.context() as initial:
        initial.setattr(threejs_agent,'MODEL',model)
        initial.setattr(threejs_agent,'REVIEW_REASONING_EFFORT',review_effort)
        with pytest.raises(TimeoutError,match='between tools'):threejs_pipeline.process_threejs(folder,1)
    assert completed==['inspect_photo']
    if model=='gpt-6.1-sol':
        # Older generations predate model settings in the agent state.
        state_path=folder/'work/threejs/agent-state.json'
        state=json.loads(state_path.read_text())
        del state['model'],state['review_reasoning_effort']
        atomic_json(state_path,state)
    result=threejs_pipeline.process_threejs(folder,2)
    assert result['status']=='succeeded'
    assert result['generation_model']==model
    assert completed.count('inspect_photo')==1 and completed.count('crop_texture')==1
    # Two ordered author batches plus review, instead of a purchase per tool.
    assert len(calls)==3
    assert [call['model'] for call in calls]==[model]*3
    assert [call['reasoning']['effort'] for call in calls]==['high','high',review_effort]
    history=calls[1]['input']
    outputs=[i for i,item in enumerate(history) if item.get('type')=='function_call_output']
    images=[i for i,item in enumerate(history) if item.get('role')=='user' and any(c.get('type')=='input_image' for c in item.get('content',[]))]
    assert len(outputs)==2 and images[-1]>outputs[-1]
    ledger=json.loads((folder/'work/threejs/spending.json').read_text())
    assert len(ledger['entries'])==3 and all(e['state']=='settled' for e in ledger['entries'].values())


def test_authored_code_cannot_write_runtime_or_read_credentials(tmp_path):
    project=tmp_path/'project';project.mkdir();tools=threejs_tools.AuthoringTools(project,lambda _:None)
    for path in ('../outside.ts','reconstruction.ts','apps/room-viewer/tools/native.ts'):
        with pytest.raises(ValueError):tools.write(path,'anything')
    for path in ('.env','../.env','node_modules/.env'):
        with pytest.raises(ValueError):tools.read(path)
    with pytest.raises(ValueError):tools.write('demos/room/items/bad.ts',"import 'node:fs'")
    env=threejs_tools.clean_environment(project);assert not any('KEY' in name or 'TOKEN' in name for name in env)


def test_context_refresh_preserves_current_source_review_and_paid_ledger(tmp_path):
    project=tmp_path/'project';module=project/'demos/room/items/current.ts';module.parent.mkdir(parents=True)
    module.write_text('export function build() {}')
    report={'passed':False,'views':[{'photo_index':7,'passed':False,'issues':['Correct the captured handle silhouette']} ]}
    (tmp_path/'submission-current').mkdir()
    atomic_json(tmp_path/'submission-current/review.json',report)
    history=[{'role':'user','content':'old authoring history'}]
    state={'round':80,'history':history,'pending':[],'tool_index':0,'submitted':None}
    ledger=astra_spending.Spending(tmp_path/'spending.json')
    ledger.data['entries']['prior']={'state':'settled','reserved_units':1000,'cost_units':500}
    ledger.save();before=ledger.path.read_bytes()
    contact={'type':'input_image','image_url':'retained-contact-sheet'}
    tools=SimpleNamespace(project=project,contacts=lambda:[contact])
    assert threejs_agent.refresh_context(state,tools,tmp_path,ledger,'same-capture')
    assert json.loads((tmp_path/'context-0000-0080.json').read_text())['history']==history
    assert ledger.path.read_bytes()==before and module.read_text()=='export function build() {}'
    text=state['history'][0]['content'][0]['text']
    assert 'same-capture' in text and 'items/current.ts' in text and 'Correct the captured handle' in text
    assert json.loads(text.split('\n',1)[1])['remaining_generation_budget_usd']==9.9995
    assert state['history'][0]['content'][-1]==contact
    restored=json.loads((tmp_path/'agent-state.json').read_text())
    assert restored['round']==80 and restored['context_start_round']==80
    assert not threejs_agent.refresh_context(restored,tools,tmp_path,ledger,'same-capture')


@pytest.mark.parametrize('inflight',['tool','reservation','response'])
def test_context_refresh_keeps_inflight_request_identity(tmp_path,inflight):
    (tmp_path/'submission-current').mkdir()
    atomic_json(tmp_path/'submission-current/review.json',{'passed':False,'views':[]})
    state={'round':80,'history':[{'role':'user','content':'paid input'}],'pending':[]}
    ledger=astra_spending.Spending(tmp_path/'spending.json')
    if inflight=='tool':state['pending']=[{'call_id':'retained'}]
    elif inflight=='reservation':ledger.data['entries']['paid']={'state':'reserved','reserved_units':100}
    else:
        (tmp_path/'turn-0080').mkdir()
        atomic_json(tmp_path/'turn-0080/response.json',{'fingerprint':'retained'})
    before=json.dumps(state)
    assert not threejs_agent.refresh_context(state,None,tmp_path,ledger,'same-capture')
    assert json.dumps(state)==before


def test_native_review_lighting_is_invariant_under_room_frame(tmp_path):
    project=tmp_path/'preview'
    threejs_tools.source_module().template(project)
    (project/'node_modules').symlink_to(ROOT/'node_modules',target_is_directory=True)
    native=project/'data/web-assets/native'
    shutil.copytree(ROOT.parents[1]/'Tests/ReSpaceCoreTests/Fixtures/Walkthrough',native)
    scene=SceneBundle.model_validate_json((native/'scene.json').read_text())
    atomic_json(native/'scene.json',scene.model_dump())
    atomic_json(native/'measurements.json',{'transform':{'worldToRoom':np.eye(4).flatten(order='F').tolist()},
        'photos':[{'position':[0.,1.6,1.7],'forward':[0.,-.2,-1.],'up':[0.,1.,0.],'fovY':65,'aspect':1.}]})
    (project/'evidence').mkdir()
    threejs_tools.browser(project,{'operation':'capture','room':'room','source':'native','photo':0,'output':str(project/'evidence/native-0.png')})
    # Relabeling the authoring coordinate frame must not change delivered
    # lighting: the app's lights live in the original scan frame.
    measured_path=project/'data/web-assets/native/measurements.json'
    measured=json.loads(measured_path.read_text())
    rotated=json.loads(json.dumps(measured))
    rotation=np.array([[0.,0.,1.,0.],[0.,1.,0.,0.],[-1.,0.,0.,0.],[0.,0.,0.,1.]])
    old=np.array(measured['transform']['worldToRoom']).reshape(4,4,order='F')
    rotated['transform']['worldToRoom']=(rotation@old).flatten(order='F').tolist()
    for photo in rotated['photos']:
        for key in ('position','forward','up'):
            photo[key]=(rotation[:3,:3]@np.array(photo[key])).tolist()
    rotated_preview=project/'evidence/native-rotated-frame.png'
    try:
        atomic_json(measured_path,rotated)
        threejs_tools.browser(project,{'operation':'capture','room':'room','source':'native','photo':0,'output':str(rotated_preview)})
        with Image.open(project/'evidence/native-0.png') as original, Image.open(rotated_preview) as changed:
            difference=np.abs(np.asarray(original.convert('RGB')).astype(float)-np.asarray(changed.convert('RGB')).astype(float)).mean()
            assert difference<.5, f'Coordinate frame changed review lighting by {difference:.2f} RGB levels'
    finally:
        atomic_json(measured_path,measured)
