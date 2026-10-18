import pytest
from respace.operations import OperationService
from respace.planning import PlanningController
from test_operations import room


@pytest.mark.asyncio
async def test_model_question_releases_work_and_resume_uses_persisted_answers(store):
    room(store)
    with store.transaction():
        store.put('captures','capture',{'capture_id':'capture','room_id':'room','state':'complete','measured_context':{'objects':[],'units':'meters'}})
        store.put('planning','room',{'room_id':'room','planning_revision':0,'instructions':[]})
    ops=OperationService(store)
    ops.submit('device','room','generation',{'operation_id':'op','capture_id':'capture','planning_revision':0,'expected_active_revision':0,'budget':'100.00','intent':'add','styles':['Minimal']})
    class Model:
        calls=[]
        async def act(self, context):
            self.calls.append(context)
            return {'action':'ask_user','payload':{'kind':'single_choice','topic':'activity','text':'What do you do here?','choices':[{'choice_id':'read','label':'Read'}],'allow_delegate':True,'allow_skip':True}}
    class Products:
        def search(self,*args): raise AssertionError('No requested category yet')
    model=Model()
    controller=PlanningController(store,ops,Products(),model,None)
    await controller.run('op')
    operation=ops.get('device','op')
    assert operation['state']=='needs_clarification'
    assert model.calls[0]['measured_context']['units']=='meters'
    assert model.calls[0]['initial_products']['state']=='empty'
    await controller.run('op')
    assert len(model.calls)==1
    assert store.get('rooms','room')['current_operation_id']=='op'


@pytest.mark.asyncio
async def test_unrecognized_model_actions_fail_without_executing_any_tool(store):
    room(store)
    with store.transaction(): store.put('captures','capture',{'state':'complete','measured_context':{},'room_id':'room'})
    ops=OperationService(store)
    ops.submit('device','room','generation',{'operation_id':'op','capture_id':'capture','planning_revision':0,'expected_active_revision':0,'budget':'100.00','intent':'add'})
    class Model:
        async def act(self,context): return {'action':'execute_shell','payload':{'command':'anything'}}
    controller=PlanningController(store,ops,None,Model(),None)
    await controller.run('op')
    assert ops.get('device','op')['state']=='failed'
    assert store.list('designs','room')==[]
