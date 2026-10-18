"""Planning-only Object instructions, independent of captured and saved geometry."""
import os
import re
from .operations import DomainError, identity, now, require


async def review_command(store, operations, operation_id):
    operation,room=operations.guard(operation_id)
    request=operation['request']
    capture=store.get('captures',room['latest_capture_id'])
    objects=capture.get('measured_context',{}).get('objects',[]) if capture else []
    target=request.get('selected_object')
    if operation['answer_history']:
        answer=operation['answer_history'][-1]['request']
        selected=answer.get('choice_ids',[])
        if selected:
            target={'kind':'native_object','id':selected[0],'capture_id':room['latest_capture_id']}
    if target is None:
        if not objects:
            operations.finish(operation_id,'rejected',{'result_kind':'no_match','message':'No measured Objects are available for this instruction.','message_ids':[]})
            return
        operations.ask(operation_id,{'kind':'single_choice','context':'command','text':'Which Object do you mean?','choices':[{'choice_id':obj['id'],'label':obj['category']} for obj in objects],'allow_skip':False,'allow_delegate':False})
        return
    require(target.get('kind')=='native_object' and target.get('capture_id')==room['latest_capture_id'],'unresolved_identity','Choose an Object from this capture.')
    obj=next((obj for obj in objects if obj['id']==target.get('id')),None)
    if obj is None: raise DomainError('unresolved_identity','The selected Object is no longer available.')
    text=request['text'].lower().strip()
    exact={
        'keep this in place':('keep',False),
        'remove this from the design':('remove',False),
        'explicitly unlock this and let the design decide':('decide',True),
        'unlock and remove this':('remove',True),
        'unlock and remove this from the design':('remove',True),
    }
    if text in exact:
        instruction,unlock=exact[text]
    else:
        from pydantic import BaseModel
        from typing import Literal
        class Instruction(BaseModel):
            instruction: Literal['keep','decide','remove','unsupported']
            explicit_unlock: bool
            reason: str
        try:
            from google import genai
            model=os.environ.get('GEMINI_EXTRACTION_MODEL')
            require(bool(model),'unavailable_capability','Configure GEMINI_EXTRACTION_MODEL.',503)
            from google.genai import types
            client=genai.Client(http_options=types.HttpOptions(timeout=30000,retry_options=types.HttpRetryOptions(attempts=1)))
            try:
                parsed=None
                for attempt in range(2):
                    try:
                        result=await client.aio.models.generate_content(model=model,contents='Interpret this user planning instruction for the selected existing Object. Respect negation. Keep protects presence/position; removing a Kept Object requires an explicit unlock. Return unsupported for geometry edits or unrelated requests. Never infer an unlock from a move/remove request. User text: '+request['text'],config={'response_mime_type':'application/json','response_schema':Instruction})
                        parsed=Instruction.model_validate_json(result.text)
                        break
                    except Exception:
                        if attempt: raise
                assert parsed is not None
                instruction,unlock=parsed.instruction,parsed.explicit_unlock
            finally:
                await client.aio.aclose()
        except Exception:
            operations.finish(operation_id,'failed',failure={'code':'unavailable_capability','message':'Language interpretation could not finish. Use the Object planning controls or retry.','retryable':True})
            return
        if instruction=='unsupported':
            operations.finish(operation_id,'rejected',{'result_kind':'unavailable_capability','message':'Room review updates planning instructions; generate or reopen a design to change placements.','message_ids':[]})
            return
    with store.transaction():
        operation,room=operations.guard(operation_id)
        planning=store.get('planning',room['room_id'])
        current=next((entry['instruction'] for entry in planning['instructions'] if entry['target']['id']==obj['id']),'decide')
        if current=='keep' and instruction!='keep' and not unlock:
            operations.finish(operation_id,'rejected',{'result_kind':'kept_object','message':'Explicitly unlock this Object before changing Keep.','message_ids':[]})
            return
        if obj.get('fixed_in_place') and instruction=='remove':
            operations.finish(operation_id,'rejected',{'result_kind':'permanent_fixture','message':'This permanent fixture cannot be removed.','message_ids':[]})
            return
        planning['instructions']=[entry for entry in planning['instructions'] if entry['target']['id']!=obj['id']]
        planning['instructions'].append({'target':target,'instruction':instruction})
        planning['planning_revision']+=1
        room['planning_revision']=planning['planning_revision']
        message_id=identity()
        store.put('messages',message_id,{'message_id':message_id,'room_id':room['room_id'],'context':'review','role':'assistant','event_kind':'outcome','text':f"{obj['category']}: {instruction}.",'created_at':now(),'operation_id':operation_id,'base_context':operation['base_context']})
        store.put('planning',room['room_id'],planning)
        # The final compare happened above; commit outcome and new revision together.
        room['current_operation_id']=None
        operation.update(state='succeeded',phase='complete',updated_at=now(),outcome={'result_kind':'planning','planning_revision':planning['planning_revision'],'message_ids':[message_id]})
        store.put('rooms',room['room_id'],room)
        store.put('operations',operation_id,operation)
