"""One durable operation and question lifecycle for every room mutation."""
import json
import math
from datetime import datetime, timezone
from uuid import uuid4
from . import tracing


def now():
    return datetime.now(timezone.utc).isoformat()


def identity():
    return str(uuid4())


class DomainError(Exception):
    def __init__(self, code, message, status=409, retryable=False, details=None):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status
        self.retryable, self.details = retryable, details


def require(condition, code, message, status=409, details=None):
    if not condition:
        raise DomainError(code,message,status,details=details)


TERMINAL = {'succeeded','rejected','failed','cancelled'}


class OperationService:
    def __init__(self, store):
        self.store=store

    def room(self, device_id, room_id):
        require(self.store.get('deletions',room_id) is None, 'room_deleted','This Room is being deleted.',410)
        room=self.store.get('rooms',room_id)
        require(room is not None and room.get('device_id')==device_id,'unknown_room','Room was not found.',404)
        return room

    def get(self, device_id, operation_id):
        operation=self.store.get('operations',operation_id)
        require(operation is not None and operation.get('device_id')==device_id,'unknown_operation','No durable operation has this identity.',404)
        return operation

    def progress_message(self, operation):
        if (operation['state'] not in {'queued', 'running'} or operation.get('pending_question')
                or operation['phase'] not in {'preparing_context', 'searching_products'}):
            return None
        # Local searches persist their cursor before returning a result to the controller.
        searches = [search for search in self.store.list('searches', operation['room_id'])
                    if search.get('intended_context', {}).get('operation_id') == operation['operation_id']
                    and search['state'] == 'running']
        if not searches:
            return None
        search = max(searches, key=lambda entry: entry['created_at'])
        cursor = search.get('continuation', {})
        phase = search['phase']
        pools = search.get('source_candidate_pools', {})
        total = len(set(pools.get('stored', []) + pools.get('live', [])))
        if phase == 'discovery':
            return f"Searching products · {len(search.get('queries', []))} searches completed · {total} candidates found"
        if phase == 'verification':
            message = 'Checking merchant listings'
            index = cursor.get('candidate_index', 0)
            if index < total:
                message += f' · product {index + 1} of {total}'
            work = search.get('verification_work', {})
            listings = work.get('listings') or []
            listing_index = work.get('listing_index', 0)
            if listing_index < len(listings):
                message += f' · listing {listing_index + 1} of {len(listings)}'
            if work.get('attempt'):
                message += ' · retrying'
            return message
        if phase == 'extraction':
            return f"Reading product details · {cursor.get('extraction_index', 0)} of {len(cursor.get('capture_ids', []))} pages processed"
        if phase == 'ranking':
            return 'Comparing verified products'
        if phase in {'refresh', 'refresh_verification'}:
            return 'Rechecking prices and availability'
        return None

    def _base(self, room):
        return {'room_id':room['room_id'],'capture_id':room.get('latest_capture_id'),'snapshot_id':room.get('latest_snapshot_id'),'planning_revision':room.get('planning_revision'),'active_design_id':room.get('active_design_id'),'active_revision':room.get('active_revision')}

    def submit(self, device_id, room_id, kind, request):
        with self.store.transaction():
            room=self.room(device_id,room_id)
            op_id=request['operation_id']
            existing=self.store.get('operations',op_id)
            if existing:
                require(existing['device_id']==device_id and existing['room_id']==room_id and existing['kind']==kind and existing['request']==request,'identity_conflict','Operation identity already has a different payload.')
                return existing
            require(not room.get('current_operation_id'),'room_busy','This Room already has pending work.',details={'current_operation_id':room.get('current_operation_id')})
            for request_key,room_key in [('planning_revision','planning_revision'),('expected_active_revision','active_revision'),('expected_active_design_id','active_design_id'),('capture_id','latest_capture_id')]:
                if request_key in request:
                    require(request[request_key]==room.get(room_key),'stale_base','The Room changed. Refresh and submit again.',details=self._base(room))
            operation={'schema_version':1,'operation_id':op_id,'kind':kind,'room_id':room_id,'device_id':device_id,'request':request,'base_context':self._base(room),'state':'queued','phase':'queued','created_at':now(),'updated_at':now(),'decision_revision':0,'question_revision':0,'question_history':[],'answer_history':[],'pending_question':None,'outcome':None,'failure':None}
            message_id=identity()
            text=request.get('text') or ('Generate a design.' if kind=='generation' else kind.replace('_',' ').capitalize())
            self.store.put('messages',message_id,{'message_id':message_id,'room_id':room_id,'context':'review' if kind=='planning_command' else 'design','role':'user','event_kind':'command','text':text,'created_at':now(),'operation_id':op_id,'base_context':operation['base_context'],'selected':request.get('selected_object')})
            operation['command_message_id']=message_id
            self.store.put('operations',op_id,operation)
            room['current_operation_id']=op_id
            self.store.put('rooms',room_id,room)
            tracing.emit('operation.submitted', operation_id=op_id, room_id=room_id, kind=kind, request=request)
            return operation

    def guard(self, operation_id, allow_question=False):
        from .workers import assert_worker_lease
        assert_worker_lease(self.store,operation_id)
        operation=self.store.get('operations',operation_id)
        require(operation is not None,'unknown_operation','Operation no longer exists.',404)
        room=self.room(operation['device_id'],operation['room_id'])
        require(operation['state'] not in TERMINAL and room.get('current_operation_id')==operation_id,'operation_stopped','Operation is no longer active.')
        require(allow_question or operation.get('pending_question') is None,'awaiting_answer','Answer the pending question before continuing.')
        base=operation['base_context']
        for key,base_key in (('planning_revision','planning_revision'),('active_revision','active_revision'),('active_design_id','active_design_id'),('latest_capture_id','capture_id')):
            require(room.get(key)==base.get(base_key),'stale_base','The operation base changed.',details=self._base(room))
        return operation,room

    def checkpoint(self, operation_id, phase, output=None):
        with self.store.transaction():
            operation,_=self.guard(operation_id)
            operation.update(state='running',phase=phase,updated_at=now())
            if output is not None:
                operation.setdefault('steps',[]).append({'phase':phase,'output':output,'completed_at':now()})
            self.store.put('operations',operation_id,operation)
            tracing.emit('operation.phase', operation_id=operation_id, phase=phase)
            return operation

    def ask(self, operation_id, question):
        with self.store.transaction():
            operation,_=self.guard(operation_id)
            question=json.loads(json.dumps(question,allow_nan=False))
            choices=question.get('choices',[])
            ids=[choice['choice_id'] for choice in choices]
            require(len(ids)==len(set(ids)) and all(choice.get('label','').strip() for choice in choices),'invalid_question','Question choices must be distinct and labeled.',422)
            require(question.get('text','').strip(),'invalid_question','A question needs readable text.',422)
            require(question.get('kind') in {'single_choice','multi_choice','listing_choice','numeric','text','budget'},'invalid_question','Unsupported question kind.',422)
            question.update(question_id=identity(),operation_id=operation_id,base_context=operation['base_context'],decision_revision=operation['decision_revision'],question_revision=operation['question_revision']+1)
            question.setdefault('context','interview' if operation['kind']=='generation' else 'command')
            question.setdefault('allow_skip',False)
            question.setdefault('allow_delegate',False)
            question.setdefault('min_selections',1)
            question.setdefault('max_selections',len(choices) if question['kind']=='multi_choice' else 1)
            require(question['kind'] not in {'single_choice','multi_choice','listing_choice'} or bool(choices),'invalid_question','Choice questions need options.',422)
            require(not any(answer['question'].get('topic') and answer['question'].get('topic')==question.get('topic') for answer in self.effective_answers(operation)),'known_answer','This topic was already asked.')
            operation.update(state='needs_clarification',phase='awaiting_answer',pending_question=question,question_revision=question['question_revision'],updated_at=now())
            operation['question_history'].append(question)
            self.store.put('messages',question['question_id'],{'message_id':question['question_id'],'room_id':operation['room_id'],'context':'review' if operation['kind']=='planning_command' else 'design','role':'assistant','event_kind':'question','text':question['text'],'question':question,'created_at':now(),'operation_id':operation_id,'base_context':operation['base_context']})
            self.store.put('operations',operation_id,operation)
            tracing.emit('operation.question', operation_id=operation_id, question=question)
            return question

    @staticmethod
    def effective_answers(operation):
        latest={answer['question_id']:answer for answer in operation['answer_history']}
        return sorted(latest.values(),key=lambda answer:answer['question']['question_revision'])

    @staticmethod
    def can_revise(operation):
        question=operation.get('pending_question') or {}
        lease=operation.get('worker_lease') or {}
        active_lease=lease.get('expires_at') and lease['expires_at']>now()
        return bool(operation['kind']=='generation' and operation['state']=='needs_clarification' and question.get('context')=='interview' and not operation.get('controller',{}).get('selection') and not active_lease)

    def answer(self, device_id, operation_id, request):
        with self.store.transaction():
            operation=self.get(device_id,operation_id)
            existing=next((a for a in operation['answer_history'] if a['reply_id']==request['reply_id']),None)
            if existing:
                require(existing['request']==request,'identity_conflict','Reply identity already has a different payload.')
                return operation
            operation,_=self.guard(operation_id,allow_question=True)
            revision_of=request.get('revision_of_answer_id')
            if revision_of:
                require(self.can_revise(operation),'revision_boundary_required','Revise answers only while the interview is waiting at a sequential boundary.')
                original=next((answer for answer in self.effective_answers(operation) if answer['answer_id']==revision_of),None)
                if original is None:
                    raise DomainError('stale_answer_revision','Choose the latest saved answer revision.')
                question=original['question']
            else:
                question=operation.get('pending_question')
            require(question is not None,'stale_question','There is no pending question.')
            require(request.get('operation_id',operation_id)==operation_id and request['question_id']==question['question_id'] and request['expected_decision_revision']==operation['decision_revision'] and request['expected_question_revision']==question['question_revision'],'stale_question','The question or decision revision changed.')
            action=request.get('action','answer')
            require(request.get('budget_approval') is None or (question['kind']=='budget' and action=='answer'),'unexpected_budget_approval','Budget approval belongs only to an explicit pending budget question.',422)
            require(action in {'answer','skip','delegate'},'invalid_answer','Unknown answer action.',422)
            if action!='answer':
                require(question.get('allow_'+('skip' if action=='skip' else 'delegate')) and question['kind']!='budget','constraint_approval_required','This question requires an explicit answer.')
            else:
                choices=request.get('choice_ids',[])
                require(len(choices)==len(set(choices)) and set(choices)<=set(c['choice_id'] for c in question.get('choices',[])),'foreign_choice','Choose options from this question.',422)
                text=request.get('text','') or ''
                number=request.get('number')
                if question['kind'] in {'single_choice','multi_choice','listing_choice'} and not text.strip():
                    require(question['min_selections']<=len(choices)<=question['max_selections'],'invalid_answer','Choose the required number of options.',422)
                if question['kind']=='numeric':
                    require(isinstance(number,(int,float)) and not isinstance(number,bool) and math.isfinite(number),'invalid_answer','Enter a finite number.',422)
                    require(question.get('numeric_min',number)<=number<=question.get('numeric_max',number),'invalid_answer','Number is outside the allowed range.',422)
                    step=question.get('numeric_step')
                    if step:
                        require(abs((number-question.get('numeric_min',0))/step-round((number-question.get('numeric_min',0))/step))<1e-8,'invalid_answer','Number must follow the allowed step.',422)
                if question['kind']=='text':
                    require(text.strip(),'invalid_answer','Enter an answer.',422)
                if question['kind']=='budget':
                    proposal=question['budget_proposal']
                    approval=request.get('budget_approval')
                    require(isinstance(approval,dict) and {k:approval.get(k) for k in ('old_ceiling','new_ceiling','resulting_total')}=={k:proposal[k] for k in ('old_ceiling','new_ceiling','resulting_total')},'budget_approval_required','Approve this exact ceiling and purchase total explicitly.')
            answer_id=identity()
            labels=[choice['label'] for choice in question.get('choices',[]) if choice['choice_id'] in request.get('choice_ids',[])]
            answer_text=request.get('text') or ', '.join(labels) or str(request.get('number') if request.get('number') is not None else action)
            self.store.put('messages',answer_id,{'message_id':answer_id,'room_id':operation['room_id'],'context':'review' if operation['kind']=='planning_command' else 'design','role':'user','event_kind':'answer','text':answer_text,'created_at':now(),'operation_id':operation_id,'base_context':question['base_context']})
            answer={'answer_id':answer_id,'reply_id':request['reply_id'],'question_id':question['question_id'],'question':question,'request':request,'created_at':now()}
            if revision_of:
                answer['revision_of_answer_id']=revision_of
                operation.setdefault('decision_history',[]).append({'decision_revision':operation['decision_revision'],'controller':operation.get('controller',{}),'pending_question':operation['pending_question']})
                operation['controller']={}
                operation.pop('spatial',None)
            operation['answer_history'].append(answer)
            operation.update(decision_revision=operation['decision_revision']+1,pending_question=None,state='queued',phase='answer_saved',updated_at=now())
            self.store.put('operations',operation_id,operation)
            tracing.emit('operation.answer', operation_id=operation_id, answer=answer, decision_revision=operation['decision_revision'])
            return operation

    def finish(self, operation_id, state, outcome=None, failure=None):
        require(state in TERMINAL,'invalid_state','Invalid terminal state.',422)
        with self.store.transaction():
            operation,room=self.guard(operation_id)
            outcome=outcome or {'result_kind':state}
            if not outcome.get('message_ids'):
                message_id=identity()
                text=outcome.get('message') or (failure or {}).get('message') or outcome.get('result_kind',state).replace('_',' ').capitalize()
                self.store.put('messages',message_id,{'message_id':message_id,'room_id':room['room_id'],'context':'review' if operation['kind']=='planning_command' else 'design','role':'assistant','event_kind':'outcome','text':text,'created_at':now(),'operation_id':operation_id,'base_context':operation['base_context']})
                outcome['message_ids']=[message_id]
            operation.update(state=state,phase='complete' if state=='succeeded' else state,outcome=outcome,failure=failure,updated_at=now())
            room['current_operation_id']=None
            self.store.put('operations',operation_id,operation)
            self.store.put('rooms',room['room_id'],room)
            tracing.emit('operation.finished', operation_id=operation_id, state=state, outcome=outcome, failure=failure)
            return operation

    def cancel(self, device_id, operation_id, cancellation_id):
        with self.store.transaction():
            operation=self.get(device_id,operation_id)
            prior=operation.get('cancellation_id')
            if operation['state'] in TERMINAL:
                return operation
            require(prior in (None,cancellation_id),'identity_conflict','Cancellation identity differs.')
            operation['cancellation_id']=cancellation_id
            operation['pending_question']=None
            self.store.put('operations',operation_id,operation)
            return self.finish(operation_id,'cancelled',{'result_kind':'cancelled','message_ids':[]})

    def dismiss(self, device_id, operation_id, request):
        with self.store.transaction():
            operation=self.get(device_id,operation_id)
            if operation.get('dismissal')==request:
                return operation
            question=operation.get('pending_question')
            require(question and question['question_id']==request['question_id'] and question['context']=='command' and operation['kind']!='generation','cannot_dismiss','This question remains pending until answered or cancelled.')
            operation.update(pending_question=None,dismissal=request)
            self.store.put('operations',operation_id,operation)
            return self.finish(operation_id,'rejected',{'result_kind':'dismissed','message_ids':[]})

    def delete_room(self, device_id, room_id, deletion_id, storage):
        with self.store.transaction():
            deletion=self.store.get('deletions',room_id)
            if deletion:
                require(deletion['device_id']==device_id and deletion['deletion_id']==deletion_id,'identity_conflict','Deletion already has another identity.')
                if deletion['state']=='deleted':
                    return deletion
            else:
                self.room(device_id,room_id)
                deletion={'room_id':room_id,'device_id':device_id,'deletion_id':deletion_id,'state':'pending'}
                original=self.store.get('rooms',room_id)
                if original.get('creation_operation_id'): deletion['creation_operation_id']=original['creation_operation_id']
                self.store.put('deletions',room_id,deletion)
        try:
            storage.delete_prefix(f'rooms/{room_id}/')
        except Exception:
            return deletion
        with self.store.transaction():
            self.store.delete_room_records(room_id)
            deletion['state']='deleted'
            self.store.put('deletions',room_id,deletion)
        return deletion
