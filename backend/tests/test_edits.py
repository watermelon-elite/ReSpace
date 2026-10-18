from copy import deepcopy

from fastapi.testclient import TestClient
import pytest
from respace.api import create_app
from respace.geometry import normalize_room
from respace.solver import solve
from test_api import MemoryStorage, QuestionModel
from test_geometry import native_room
from test_products import offer
from test_solver import plan, selection


class Products:
    def verify_selection(self, choices, budget): return deepcopy(choices)
    def get_search(self, search_id): return self.store.get('searches', search_id)


class Editor:
    def __init__(self, result): self.result=result;self.contexts=[]
    async def act(self, context): self.contexts.append(deepcopy(context));return deepcopy(self.result)


def setup_edit(store, result):
    room=normalize_room(native_room(),'capture','room')
    selected=selection();selected.update(quantity=1,offer=offer('v','50.00',1),offer_id='o_v',search_id='initial')
    selected['dimension_evidence']['dimensions']=deepcopy(selected['dimensions'])
    selected['offer']['pack_contents']['components'][0]['dimensions']=selected['dimensions']
    selected['variant']={'variant_id':'v','title':'Desk','category':'desk','image_references':[]}
    selected['render']={'kind':'standin','category':'desk','scaling_mode':'normalized','authored_bounds':[1,1,1],'units':'meters','pivot':'bottom_center','forward_axis':'+Z'}
    from respace.products import calculate_purchases
    scene=solve(room,plan(),{'sel':selected},{'intent':'add'})['scene']
    scene.update(design_id='parent',parent_id=None,selections={'sel':selected},purchase_summary=calculate_purchases(scene['items'],{'o_v':selected['offer']},'200.00'))
    snapshot={'schema_version':1,'snapshot_id':'snapshot','room_id':'room','capture_id':'capture','revision':1,'room':room,'identity_map':room['identity_map']}
    design={'schema_version':1,'design_id':'parent','parent_id':None,'room_id':'room','capture_id':'capture','snapshot_id':'snapshot','planning_snapshot':{'instructions':[]},'scene':scene,'selection_snapshot':{'selected':[selected]},'created_at':'2026-10-18T00:00:00Z'}
    with store.transaction():
        store.put('rooms','room',{'room_id':'room','device_id':'device','latest_capture_id':'capture','latest_snapshot_id':'snapshot','active_design_id':'parent','active_revision':1,'planning_revision':0,'current_operation_id':None,'capture_state':'complete'})
        store.put('snapshots','snapshot',snapshot);store.put('designs','parent',design)
        store.put('planning','room',{'room_id':'room','revision':0,'instructions':[]})
        store.put('searches','initial',{'search_id':'initial','room_id':'room','state':'completed','displayed_choices':[selected],'intended_context':{'capture_id':'capture','planning_revision':0}})
    products=Products();products.store=store
    editor=Editor(result)
    api=TestClient(create_app(store,MemoryStorage(),products,QuestionModel(),lambda *args:None,edit_model=editor),headers={'X-Device-Id':'device'})
    return api,editor,design


def base_request(operation_id='edit'):
    return {'operation_id':operation_id,'expected_active_design_id':'parent','expected_active_revision':1}


def move(wall='w_3'):
    return {'action_id':'move','target':{'kind':'item','id':'i_a_0'},'anchor':{'type':'against_wall','wall_id':wall,'alignment':'center'},'reason':'Requested move'}


def test_language_edit_publishes_successful_subset_once_and_preserves_failed_product(store):
    large={**selection((10,10,1)),'selection_id':'large','variant_id':'large','offer_id':'o_large','quantity':1,'offer':offer('large','60.00',1),'candidate_id':'candidate-large'}
    result={'action':'execute_plan','payload':{'plan':{'summary':'Moved desk; large desk could not fit','moves':[move()],'adds':[{**plan()['adds'][0],'add_id':'large','action_id':'large','selection_id':'large'}]},'selected':[{'variant_id':'large','offer_id':'o_large','selection_id':'large','quantity':1}]}}
    api,_,parent=setup_edit(store,result)
    with store.transaction():
        search=store.get('searches','initial');search['displayed_choices'].append(large);store.put('searches','initial',search)
    request={**base_request(),'text':'Move the desk and add a large desk.'}
    response=api.post('/v1/designs/parent/chat',json=request)
    assert response.status_code==202,response.text
    saved=api.get('/v1/operations/edit').json()['operation']
    assert saved['state']=='succeeded',saved
    child=store.get('designs',saved['outcome']['design_id'])
    assert child['scene']['items'][0]['placement']['position']==[2,0,2.7]
    assert {r['action_id']:r['outcome'] for r in saved['outcome']['action_outcomes']}=={'move':'applied','large':'failed'}
    assert child['scene']['purchase_summary']['total']=='50.00'
    assert store.get('designs','parent')==parent
    assert api.post('/v1/designs/parent/chat',json=request).json()['operation']['outcome']==saved['outcome']
    assert len(store.list('designs','room'))==2


def test_all_failed_edit_and_stale_base_create_no_child(store):
    api,_,parent=setup_edit(store,{'action':'execute_plan','payload':{'plan':{'summary':'No change','moves':[move('missing')]}}})
    assert api.post('/v1/designs/parent/chat',json={**base_request(),'text':'Move the desk.'}).status_code==202
    operation=api.get('/v1/operations/edit').json()['operation']
    assert operation['state']=='rejected' and operation['outcome']['result_kind']=='no_effective_change'
    assert store.get('designs','parent')==parent and len(store.list('designs','room'))==1
    assert api.post('/v1/designs/parent/chat',json={**base_request('stale'),'expected_active_revision':0,'text':'Move desk'}).status_code==409


def swap_choice(store, *, dimensions=(.8,.4,.7), context=None):
    selected=deepcopy(store.get('designs','parent')['scene']['selections']['sel'])
    selected.update(selection_id='swap-choice',variant_id='alternative',offer_id='o_alternative',dimensions=list(dimensions),search_id='more')
    selected['offer']=offer('alternative','70.00',1)
    selected['dimension_evidence']['dimensions']=list(dimensions)
    selected['dimension_evidence']['variant_id']='alternative'
    selected['variant']['variant_id']='alternative'
    with store.transaction():store.put('searches','more',{'search_id':'more','room_id':'room','state':'completed','displayed_choices':[selected],'intended_context':context or {'design_id':'parent','item_id':'i_a_0','active_revision':1}})
    return {**base_request('swap'),'item_id':'i_a_0','variant_id':'alternative','offer_id':'o_alternative','search_id':'more'}


def test_same_pose_swap_saves_exact_choice_and_preserves_parent_on_failed_fit(store):
    api,_,parent=setup_edit(store,{})
    request=swap_choice(store)
    response=api.post('/v1/designs/parent/swap',json=request)
    assert response.status_code==202,response.text
    op=api.get('/v1/operations/swap').json()['operation']
    assert op['state']=='succeeded',op
    child=store.get('designs',op['outcome']['design_id'])
    item=child['scene']['items'][0]
    assert item['id']=='i_a_0' and item['variant_id']=='alternative'
    assert item['placement']['position']==parent['scene']['items'][0]['placement']['position']
    assert child['scene']['purchase_summary']['total']=='70.00'
    assert store.get('designs','parent')==parent
    assert api.post('/v1/designs/parent/swap',json=request).json()['operation']['outcome']==op['outcome']


def test_swap_rejects_stale_find_more_context_and_oversized_choice(store):
    api,_,parent=setup_edit(store,{})
    request=swap_choice(store,context={'design_id':'old','item_id':'i_a_0','active_revision':0})
    api.post('/v1/designs/parent/swap',json=request)
    op=api.get('/v1/operations/swap').json()['operation']
    assert op['state']=='rejected' and op['failure']['code']=='stale_search_context'
    request=swap_choice(store,dimensions=(10,10,1));request['operation_id']='oversized'
    api.post('/v1/designs/parent/swap',json=request)
    op=api.get('/v1/operations/oversized').json()['operation']
    assert op['state']=='rejected'
    assert store.get('rooms','room')['active_design_id']=='parent' and store.get('designs','parent')==parent
    assert len(store.list('designs','room'))==1


def test_explicit_named_target_wins_and_ambiguous_work_stays_private(store):
    api,model,parent=setup_edit(store,{'action':'execute_plan','payload':{'plan':{'summary':'Move desk','moves':[move()]}}})
    response=api.post('/v1/designs/parent/chat',json={**base_request(),'text':'Move the desk.','selected_item_id':'stale-other'})
    assert response.status_code==202
    assert model.contexts[0]['explicit_target_ids']==['i_a_0']
    assert api.get('/v1/operations/edit').json()['operation']['state']=='succeeded'
    # A separate base contains two desks. The selected context cannot resolve the explicit ambiguity.
    from respace.operations import OperationService
    operations=OperationService(store)
    current=store.get('rooms','room');design=store.get('designs',current['active_design_id'])
    duplicate=deepcopy(design['scene']['items'][0]);duplicate.update(id='second-desk');duplicate['placement']['position']=[.8,0,1.5]
    with store.transaction():
        design['design_id']='two-desks';design['scene']['design_id']='two-desks';design['scene']['items'].append(duplicate)
        store.put('designs','two-desks',design);current['active_design_id']='two-desks';store.put('rooms','room',current)
    result=api.post('/v1/designs/two-desks/chat',json={**base_request('ambiguous'),'expected_active_design_id':'two-desks','expected_active_revision':current['active_revision'],'text':'Move the desk.','selected_item_id':'i_a_0'})
    assert result.status_code==202,result.text
    pending=operations.get('device','ambiguous')
    assert pending['state']=='needs_clarification' and pending['pending_question']['context']=='command'
    assert store.get('rooms','room')['active_design_id']=='two-desks'
    assert len(model.contexts)==1


def test_over_budget_addition_is_not_charged_and_independent_move_survives(store):
    result={'action':'execute_plan','payload':{'plan':{'summary':'Move and add','moves':[move()],'adds':[{**plan()['adds'][0],'add_id':'extra','action_id':'extra','selection_id':'extra','anchor':{'type':'room_center'}}]},'selected':[{'variant_id':'expensive','offer_id':'o_expensive','selection_id':'extra','quantity':1}]}}
    api,_,_=setup_edit(store,result)
    expensive=deepcopy(store.get('designs','parent')['scene']['selections']['sel'])
    expensive.update(variant_id='expensive',offer_id='o_expensive',offer=offer('expensive','190.00',1))
    expensive['dimension_evidence']['variant_id']='expensive'
    with store.transaction():
        search=store.get('searches','initial');search['displayed_choices'].append(expensive);store.put('searches','initial',search)
    api.post('/v1/designs/parent/chat',json={**base_request(),'text':'Move the desk and add a desk.'})
    op=api.get('/v1/operations/edit').json()['operation']
    assert op['state']=='succeeded',op
    assert any(o['action_id']=='extra' and o['code']=='budget_conflict' for o in op['outcome']['action_outcomes'])
    child=store.get('designs',op['outcome']['design_id'])
    assert child['scene']['purchase_summary']['total']=='50.00' and len(child['scene']['items'])==1


def test_shared_api_fixture_validates_requests_and_exact_saved_scenes():
    import json
    from pathlib import Path
    from respace.contracts import Answer,Swap
    from respace.solver import validate_scene
    fixture=json.loads((Path(__file__).parent/'fixtures/api/wave2.json').read_text())
    Answer.model_validate(fixture['revision_request']);Swap.model_validate(fixture['swap_request'])
    for key in ('swap_parent','swap_child'):
        scene=fixture[key]['design']['scene']
        assert validate_scene(scene['room'],scene)==[]
        from respace.products import calculate_purchases
        assert scene['purchase_summary']==calculate_purchases(scene['items'],{s['offer_id']:s['offer'] for s in scene['selections'].values()},scene['purchase_summary']['approved_ceiling'])


def test_repeated_unaffected_selection_preserves_historical_offer_without_verification(store):
    result={'action':'execute_plan','payload':{'plan':{'summary':'Move desk','moves':[move()]},'selected':[{'selection_id':'sel','variant_id':'v','offer_id':'o_v','quantity':1}]}}
    api,_,parent=setup_edit(store,result)
    def must_not_verify(*args,**kwargs):raise AssertionError('A move does not refresh Product evidence')
    # Access the actual injected collaborator through the edit controller's closure-independent API fixture.
    from respace.edits import EditController
    from respace.operations import OperationService
    products=Products();products.verify_selection=must_not_verify
    editor=EditController(store,OperationService(store),products,Editor(result))
    editor.operations.submit('device','room','edit',{**base_request(),'text':'Move the desk.'})
    import asyncio
    asyncio.run(editor.run('edit'))
    operation=editor.operations.get('device','edit')
    assert operation['state']=='succeeded',operation
    child=store.get('designs',operation['outcome']['design_id'])
    assert child['scene']['purchase_summary']==parent['scene']['purchase_summary']
    assert child['scene']['selections']==parent['scene']['selections']


@pytest.mark.parametrize('kind',['move','swap'])
def test_must_have_base_item_does_not_block_its_move_or_same_pose_swap(store,kind):
    api,_,_=setup_edit(store,{'action':'execute_plan','payload':{'plan':{'summary':'Move','moves':[move()]}}})
    with store.transaction():
        parent=store.get('designs','parent');parent['scene']['selections']['sel']['must_have']=True;store.put('designs','parent',parent)
    if kind=='move':
        api.post('/v1/designs/parent/chat',json={**base_request(),'text':'Move the desk.'})
        operation_id='edit'
    else:
        api.post('/v1/designs/parent/swap',json=swap_choice(store))
        operation_id='swap'
    assert api.get('/v1/operations/'+operation_id).json()['operation']['state']=='succeeded'


def test_cloud_api_queues_room_review_commands_without_using_provider_credentials(store,monkeypatch):
    from respace.workers import GoogleCloudTasksDispatcher
    from test_workers import Queue
    from test_api import complete_room
    queue=Queue()
    monkeypatch.setenv('CLOUD_TASKS_QUEUE','test-queue')
    monkeypatch.setattr(GoogleCloudTasksDispatcher,'from_env',classmethod(lambda cls:queue))
    app=create_app(store,MemoryStorage(),Products(),QuestionModel(),lambda *args:None)
    api=TestClient(app,headers={'X-Device-Id':'device'})
    room_id,capture_id=complete_room(api)
    response=api.post(f'/v1/rooms/{room_id}/planning-commands',json={'operation_id':'review','capture_id':capture_id,'planning_revision':0,'text':'Please preserve this.'})
    assert response.status_code==200 and response.json()['operation']['state']=='queued'
    assert len(queue.tasks)==1
    assert store.get('worker_outbox','review:1')['state']=='dispatched'


def test_unlock_authorization_is_target_specific_and_negation_is_not_approval(store):
    result={'action':'execute_plan','payload':{'plan':{'summary':'Unlock sofa','unlocks':[{'action_id':'unlock','target':{'kind':'item','id':'sofa'},'explicit_user_unlock_context':'Unlock the desk','reason':'Requested'}]}}}
    api,_,_=setup_edit(store,result)
    with store.transaction():
        parent=store.get('designs','parent');parent['scene']['items'][0]['instruction']='keep'
        sofa=deepcopy(parent['scene']['items'][0]);sofa.update(id='sofa',category='sofa',instruction='keep');sofa['placement']['position']=[.8,0,1.5]
        parent['scene']['items'].append(sofa);store.put('designs','parent',parent)
    api.post('/v1/designs/parent/chat',json={**base_request(),'text':'Unlock the desk and move the sofa.'})
    operation=api.get('/v1/operations/edit').json()['operation']
    assert operation['state']=='rejected' and operation['outcome']['result_kind']=='no_effective_change'
    assert store.get('rooms','room')['active_design_id']=='parent'
    from respace.edits import EditController,affirmative_matches
    assert EditController._named_targets("Don't unlock the desk.",parent['scene'],'unlock|unkeep',combined=True)==([],[])
    assert affirmative_matches(r'\bunlock\s+this\b',"Don't unlock this.")==[]


def test_replacement_of_original_remains_eligible_for_swap(store):
    api,_,_=setup_edit(store,{})
    with store.transaction():
        parent=store.get('designs','parent');item=parent['scene']['items'][0]
        item.update(origin='existing',object_id='original',replacement_of_object_id='original')
        obj={'id':'original','category':'desk','center':[2,.3],'base_y':0,'size':[1,.5,.7],'yaw':0,'mount':'floor','source':'roomplan','source_ids':['original'],'observation_count':0,'attrs':{},'fixed_in_place':False}
        parent['scene']['room']['objects']=[obj]
        snapshot=store.get('snapshots','snapshot');snapshot['room']['objects']=[obj]
        store.put('snapshots','snapshot',snapshot);store.put('designs','parent',parent)
    api.post('/v1/designs/parent/swap',json=swap_choice(store))
    operation=api.get('/v1/operations/swap').json()['operation']
    assert operation['state']=='succeeded',operation
    child=store.get('designs',operation['outcome']['design_id'])
    assert child['scene']['items'][0]['object_id']=='original' and child['scene']['purchase_summary']['total']=='70.00'


@pytest.mark.parametrize('kind',['swap','language_replace'])
def test_replacement_retains_required_addition_when_alternative_lacks_must_have(store,kind):
    result={'action':'execute_plan','payload':{'plan':{'summary':'Replace','replaces':[{'action_id':'replace','target_item_id':'i_a_0','selection_id':'alternative','reason':'Requested'}]},'selected':[{'selection_id':'alternative','variant_id':'alternative','offer_id':'o_alternative','quantity':1}]}}
    api,model,_=setup_edit(store,result)
    request=swap_choice(store)
    with store.transaction():
        parent=store.get('designs','parent');parent['scene']['selections']['sel']['must_have']=True;store.put('designs','parent',parent)
        more=store.get('searches','more');more['displayed_choices'][0].pop('must_have',None);store.put('searches','more',more)
        initial=store.get('searches','initial');initial['displayed_choices'].append(more['displayed_choices'][0]);store.put('searches','initial',initial)
    if kind=='swap':api.post('/v1/designs/parent/swap',json=request);operation_id='swap'
    else:api.post('/v1/designs/parent/chat',json={**base_request(),'text':'Replace the desk.'});operation_id='edit'
    operation=api.get('/v1/operations/'+operation_id).json()['operation']
    assert operation['state']=='succeeded',operation
    child=store.get('designs',operation['outcome']['design_id']);item=child['scene']['items'][0]
    assert child['scene']['selections'][item['selection_id']]['must_have'] is True
    model.result={'action':'execute_plan','payload':{'plan':{'summary':'Remove','removes':[{'action_id':'remove','target':{'kind':'item','id':item['id']},'reason':'Requested'}]}}}
    api.post(f'/v1/designs/{child["design_id"]}/chat',json={'operation_id':'remove-required','expected_active_design_id':child['design_id'],'expected_active_revision':2,'text':'Remove the desk.'})
    removal=api.get('/v1/operations/remove-required').json()['operation']
    assert removal['state']=='rejected'
    assert removal['outcome']['action_outcomes'][0]['code']=='protected_requirement'


@pytest.mark.parametrize('constraint,value',[('requirements',{'material':'wood'}),('avoid',{'material':'plastic'})])
def test_swap_cannot_weaken_saved_product_attributes(store,constraint,value):
    api,_,_=setup_edit(store,{})
    request=swap_choice(store)
    with store.transaction():
        parent=store.get('designs','parent');parent['scene']['selections']['sel'][constraint]=value;store.put('designs','parent',parent)
        more=store.get('searches','more');more['displayed_choices'][0]['features']={'material':'plastic'};store.put('searches','more',more)
    api.post('/v1/designs/parent/swap',json=request)
    operation=api.get('/v1/operations/swap').json()['operation']
    assert operation['state']=='rejected'
    assert operation['outcome']['action_outcomes'][0]['code']=='protected_requirement'
    assert store.get('rooms','room')['active_design_id']=='parent'
