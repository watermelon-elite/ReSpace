"""Atomic publication of one complete immutable result."""
from copy import deepcopy
from .operations import identity, now, require


class Publisher:
    def __init__(self, store, operations, validate_scene):
        self.store,self.operations,self.validate_scene=store,operations,validate_scene

    def publish(self, operation_id, snapshot, selection, plan, candidate):
        with self.store.transaction():
            operation=self.store.get('operations',operation_id)
            if operation and operation['state']=='succeeded':
                return operation
            operation,room=self.operations.guard(operation_id)
            require(not candidate.get('conflicts') and candidate.get('scene') is not None,'invalid_scene','Unresolved placement conflicts prevent publication.')
            scene=deepcopy(candidate['scene'])
            if scene.get('purchase_summary'):
                from .products import money
                purchases=scene['purchase_summary']
                require(money(purchases['total'])<=money(purchases['approved_ceiling']),'budget_conflict','Saved purchases exceed the approved ceiling.')
            measured=snapshot.get('room',snapshot.get('room_model',{}))
            require(measured.get('validity',{}).get('usable',False),'invalid_room','A usable measured boundary is required.')
            require(not self.validate_scene(measured,scene),'invalid_scene','The final Scene failed validation.')
            if operation['kind']!='generation' and not any(action['outcome']=='applied' for action in candidate.get('action_outcomes',[])):
                return self.operations.finish(operation_id,'rejected',{'result_kind':'no_effective_change','action_outcomes':candidate.get('action_outcomes',[]),'message_ids':[]})
            snapshot_id=snapshot['snapshot_id']
            require(self.store.get('snapshots',snapshot_id)==snapshot,'stale_snapshot','The immutable snapshot is unavailable.')
            design_id,message_id=identity(),identity()
            scene.update(design_id=design_id,parent_id=room.get('active_design_id'),room=deepcopy(measured),action_outcomes=candidate.get('action_outcomes',[]))
            design={'schema_version':1,'design_id':design_id,'parent_id':room.get('active_design_id'),'room_id':room['room_id'],'capture_id':snapshot['capture_id'],'snapshot_id':snapshot_id,'planning_snapshot':deepcopy(candidate.get('planning_snapshot',self.store.get('planning',room['room_id']))),'decision_snapshot':deepcopy(operation['answer_history']),'selection_snapshot':deepcopy(selection),'generation_inputs':deepcopy(operation['request']),'plan':deepcopy(plan),'scene':scene,'created_at':now()}
            entry={'message_id':message_id,'room_id':room['room_id'],'context':'design','role':'assistant','event_kind':'outcome','text':scene.get('summary','Design saved.'),'created_at':now(),'operation_id':operation_id,'base_context':operation['base_context'],'result_version_id':design_id}
            self.store.put('designs',design_id,design)
            self.store.put('messages',message_id,entry)
            room.update(active_design_id=design_id,active_revision=room['active_revision']+1,latest_snapshot_id=snapshot_id,current_operation_id=None)
            operation.update(state='succeeded',phase='complete',updated_at=now(),outcome={'result_kind':'design','design_id':design_id,'snapshot_id':snapshot_id,'active_revision':room['active_revision'],'message_ids':[message_id],'action_outcomes':candidate.get('action_outcomes',[]),'warnings':candidate.get('warnings',[])})
            self.store.put('rooms',room['room_id'],room)
            self.store.put('operations',operation_id,operation)
            return operation
