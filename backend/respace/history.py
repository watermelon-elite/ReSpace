"""Undo changes only the persisted active pointer and its conversation event."""
from .operations import identity,now,require,TERMINAL


class HistoryService:
    def __init__(self,store,operations):
        self.store,self.operations=store,operations

    def undo(self,device_id,room_id,request):
        with self.store.transaction():
            operation=self.operations.submit(device_id,room_id,'undo',request)
            if operation['state'] in TERMINAL:return operation
            operation,room=self.operations.guard(operation['operation_id'])
            active=self.store.get('designs',room.get('active_design_id')) if room.get('active_design_id') else None
            if not active or not active.get('parent_id'):
                return self.operations.finish(operation['operation_id'],'rejected',{'result_kind':'no_parent','message':'This design has no parent to restore.','message_ids':[]})
            parent=self.store.get('designs',active['parent_id'])
            require(parent and parent['room_id']==room_id,'invalid_lineage','The saved parent is unavailable.')
            event_id=identity()
            self.store.put('messages',event_id,{'message_id':event_id,'room_id':room_id,'context':'design','role':'assistant','event_kind':'undo','text':'Restored the previous saved design.','created_at':now(),'operation_id':operation['operation_id'],'base_context':operation['base_context'],'from_version_id':active['design_id'],'to_version_id':parent['design_id'],'result_version_id':parent['design_id']})
            result=self.operations.finish(operation['operation_id'],'succeeded',{'result_kind':'undo','design_id':parent['design_id'],'snapshot_id':parent['snapshot_id'],'active_revision':room['active_revision']+1,'message_ids':[event_id]})
            room.update(active_design_id=parent['design_id'],active_revision=room['active_revision']+1,latest_snapshot_id=parent['snapshot_id'],current_operation_id=None)
            self.store.put('rooms',room_id,room)
            return result
