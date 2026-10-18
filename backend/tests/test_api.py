import base64
import hashlib
import json
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from respace.api import create_app


class MemoryStorage:
    def __init__(self): self.blobs={}
    def put(self,key,data,content_type):
        if key in self.blobs: assert self.blobs[key]==data
        self.blobs[key]=data
    def get(self,key): return self.blobs[key]
    def delete_prefix(self,prefix): self.blobs={k:v for k,v in self.blobs.items() if not k.startswith(prefix)}


class EmptyProducts:
    def search(self,*args): return {'state':'no_match','displayed_choices':[]}


class QuestionModel:
    async def act(self,context):
        return {'action':'ask_user','payload':{'kind':'single_choice','text':'What matters most?','choices':[{'choice_id':'relax','label':'Relaxation'}],'allow_skip':True,'allow_delegate':True}}


@pytest.fixture
def api(store):
    app=create_app(store,MemoryStorage(),products=EmptyProducts(),model=QuestionModel(),spatial=lambda *args:None)
    return TestClient(app,headers={'X-Device-Id':'device'})


def descriptor(artifact_id,capture_id,kind,data,frame_id=None):
    return {'artifact_id':artifact_id,'capture_id':capture_id,'frame_id':frame_id,'kind':kind,'format':'application/json' if kind=='roomplan' else 'image/jpeg','byte_length':len(data),'checksum':hashlib.sha256(data).hexdigest()}


def complete_room(api):
    created=api.post('/v1/rooms',json={'schema_version':1,'operation_id':'create'}).json()
    room_id,capture_id=created['room']['room_id'],created['capture_id']
    from test_geometry import native_room
    raw=native_room()
    data=json.dumps(raw).encode()
    desc=descriptor('export',capture_id,'roomplan',data)
    body={'schema_version':1,'operation_id':'finalize','capture_id':capture_id,'raw_export_base64':base64.b64encode(data).decode(),'export_descriptor':desc,'manifest':{'room_id':room_id,'capture_id':capture_id,'final_export_artifact_id':'export','frames':[],'artifacts':[desc],'completion_id':'finalize','started_at':'2026-10-18T00:00:00Z','completed_at':'2026-10-18T00:01:00Z'}}
    response=api.post(f'/v1/rooms/{room_id}/finalize',json=body)
    assert response.status_code==200,response.text
    assert response.json()['capture_status']['state']=='complete'
    assert api.post(f'/v1/rooms/{room_id}/finalize',json=body).json()==response.json()
    return room_id,capture_id


def test_public_create_finalize_question_cancel_delete_reconciliation(api,store):
    room_id,capture_id=complete_room(api)
    body={'schema_version':1,'operation_id':'generate','capture_id':capture_id,'planning_revision':0,'expected_active_design_id':None,'expected_active_revision':0,'intent':'add','styles':['Minimal'],'budget':'200.00','currency':'USD','text':''}
    response=api.post(f'/v1/rooms/{room_id}/designs',json=body)
    assert response.status_code==202,response.text
    pending=api.get('/v1/operations/generate').json()['operation']
    assert pending['state']=='needs_clarification'
    assert pending['pending_question']['text']=='What matters most?'
    assert api.get('/v1/rooms/'+room_id).json()['current_operation']['operation_id']=='generate'
    assert api.patch('/v1/rooms/'+room_id,json={'schema_version':1,'operation_id':'rename','name':'Study','expected_metadata_revision':0}).status_code==200
    assert store.get('rooms',room_id)['active_revision']==0
    assert api.post('/v1/operations/generate/dismiss-clarification',json={'operation_id':'generate','question_id':pending['pending_question']['question_id'],'dismissal_id':'dismiss'}).status_code==409
    cancelled=api.post('/v1/operations/generate/cancel',json={'operation_id':'generate','cancellation_id':'cancel'}).json()['operation']
    assert cancelled['state']=='cancelled'
    assert api.get('/v1/operations/unknown').json()['error']['code']=='unknown_operation'
    assert api.delete('/v1/rooms/'+room_id,params={'operation_id':'delete'}).json()['deletion']['state']=='deleted'
    assert api.get('/v1/rooms/'+room_id).status_code==410
    assert api.get('/v1/rooms').json()['rooms']==[]


def test_multipart_receipts_validate_image_and_defer_detection(api,store):
    created=api.post('/v1/rooms',json={'operation_id':'create'}).json()
    room_id,capture_id=created['room']['room_id'],created['capture_id']
    buffer=BytesIO();Image.new('RGB',(8,6)).save(buffer,'JPEG');jpeg=buffer.getvalue()
    meta={'schema_version':1,'operation_id':'upload','capture_id':capture_id,'frame_id':'frame','idx':0,'w':8,'h':6,'orientation':'sensor_landscape','intrinsics':{'fx':10,'fy':10,'cx':4,'cy':3},'transform':[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],'timestamp':1.5,'timestamp_source':'ar_session_seconds','artifacts':[descriptor('photo',capture_id,'jpeg',jpeg,'frame')]}
    response=api.post(f'/v1/rooms/{room_id}/keyframes',data={'meta':json.dumps(meta)},files={'jpeg':('frame.jpg',jpeg,'image/jpeg')})
    assert response.status_code==200,response.text
    assert response.json()['processing']['state']=='not_started'
    assert response.json()['receipts'][0]['durable'] is True
    assert store.list('detection_outcomes')==[]
    assert api.post(f'/v1/rooms/{room_id}/keyframes',data={'meta':json.dumps(meta)},files={'jpeg':('frame.jpg',jpeg,'image/jpeg')}).json()==response.json()
    meta['w']=100
    assert api.post(f'/v1/rooms/{room_id}/keyframes',data={'meta':json.dumps(meta)},files={'jpeg':('frame.jpg',jpeg,'image/jpeg')}).status_code==422


def test_device_grouping_and_invalid_budget(api):
    room_id,capture_id=complete_room(api)
    assert api.get('/v1/rooms/'+room_id,headers={'X-Device-Id':'another'}).status_code==404
    body={'operation_id':'bad','capture_id':capture_id,'planning_revision':0,'expected_active_revision':0,'budget':'0.00'}
    assert api.post(f'/v1/rooms/{room_id}/designs',json=body).status_code==422


def test_deferred_pipeline_publishes_once_and_reopens_saved_transport(store):
    from respace.spatial import SpatialPipeline
    from respace.operations import OperationService
    from test_geometry import native_room
    from test_products import offer
    from test_solver import selection,plan
    selected=selection()
    selected.update(quantity=1,offer=offer('v','50.00',1),offer_id='o_v',candidate_id='candidate')
    selected['dimension_evidence'].update(dimensions=selected['dimensions'],variant_id=selected['variant_id'],source_url='https://example.com/desk',verified_at='2026-10-18T00:00:00Z',expires_at='2026-10-25T00:00:00Z',original_measurements=[{'axis':axis,'label':axis.title(),'value':str(value),'unit':'m'} for axis,value in zip(('width','depth','height'),selected['dimensions'])])
    selected['offer']['pack_contents']['components'][0]['dimensions']=selected['dimensions']
    selected['variant']={'variant_id':'v','title':'Verified desk','category':'desk','image_references':['https://example.com/desk.jpg']}
    selected['render']={'kind':'standin','category':'desk','scaling_mode':'normalized','authored_bounds':[1,1,1],'units':'meters','pivot':'bottom_center','forward_axis':'+Z'}
    class Products:
        def search(self,*args): return {'state':'completed','displayed_choices':[selected]}
        def verify_selection(self,choices,budget): return choices
    class Model:
        async def act(self,context): return {'action':'finalize_selection','payload':{'selected':[{'variant_id':'v','offer_id':'o_v','selection_id':'sel','quantity':1}]}}
    class Detector:
        async def detect(self,jpeg,w,h,frame): return {'state':'succeeded','detections':[],'frame_id':frame}
    class Planner:
        async def plan(self,snapshot,selections,instructions,photos,constraints):
            assert len(photos)==2
            return {'plan':{**plan(),'decision_revision':constraints['decision_revision'],'base':constraints['base']},'hard_errors':[],'attempts':[{'outcome':'received'}]}
    storage=MemoryStorage()
    ops=OperationService(store)
    pipeline=SpatialPipeline(store,ops,storage,Detector(),Planner())
    api=TestClient(create_app(store,storage,Products(),Model(),pipeline),headers={'X-Device-Id':'device'})
    created=api.post('/v1/rooms',json={'operation_id':'create'}).json()
    room_id,capture_id=created['room']['room_id'],created['capture_id']
    buffer=BytesIO();Image.new('RGB',(8,6)).save(buffer,'JPEG');jpeg=buffer.getvalue()
    descriptors=[]
    for index in range(2):
        frame=f'frame{index}'
        desc=descriptor(f'photo{index}',capture_id,'jpeg',jpeg,frame)
        descriptors.append(desc)
        meta={'schema_version':1,'operation_id':f'upload{index}','capture_id':capture_id,'frame_id':frame,'idx':index,'w':8,'h':6,'orientation':'sensor_landscape','intrinsics':{'fx':10,'fy':10,'cx':4,'cy':3},'transform':[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],'timestamp':index+1.5,'artifacts':[desc]}
        result=api.post(f'/v1/rooms/{room_id}/keyframes',data={'meta':json.dumps(meta)},files={'jpeg':('frame.jpg',jpeg,'image/jpeg')})
        assert result.status_code==200,result.text
    raw=json.dumps(native_room()).encode()
    export=descriptor('export',capture_id,'roomplan',raw)
    body={'schema_version':1,'operation_id':'finalize','capture_id':capture_id,'raw_export_base64':base64.b64encode(raw).decode(),'export_descriptor':export,'manifest':{'room_id':room_id,'capture_id':capture_id,'final_export_artifact_id':'export','frames':[{'frame_id':f'frame{i}','idx':i} for i in range(2)],'artifacts':descriptors+[export],'completion_id':'finalize','started_at':'2026-10-18T00:00:00Z','completed_at':'2026-10-18T00:01:00Z'}}
    assert api.post(f'/v1/rooms/{room_id}/finalize',json=body).status_code==200
    generation={'operation_id':'generate','capture_id':capture_id,'planning_revision':0,'expected_active_revision':0,'budget':'200.00','text':'chair'}
    assert api.post(f'/v1/rooms/{room_id}/designs',json=generation).status_code==202
    operation=api.get('/v1/operations/generate').json()['operation']
    assert operation['state']=='succeeded',operation
    design_id=operation['outcome']['design_id']
    design=api.get('/v1/designs/'+design_id).json()['design']
    assert design['scene']['purchase_summary']['total']=='50.00'
    assert design['scene']['selections']['sel']['offer_id']=='o_v'
    assert design['scene']['room']['processing']['succeeded']==2
    assert api.post(f'/v1/rooms/{room_id}/designs',json=generation).json()['operation']['outcome']['design_id']==design_id
    assert len(store.list('designs',room_id))==1
    assert api.get('/v1/designs/'+design_id).json()['design']==design
