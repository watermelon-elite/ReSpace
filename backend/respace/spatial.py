"""Deferred spatial pipeline. External calls stop at every cancellation guard."""
import asyncio
from copy import deepcopy
from typing import Any
from .operations import DomainError, identity, now, require
from .products import ProductError, calculate_purchases, stable_id
from .publication import Publisher


class SpatialPipeline:
    def __init__(self, store, operations, storage, detector=None, planner=None, *, products=None):
        self.store,self.operations,self.storage=store,operations,storage
        self.detector,self.planner=detector,planner
        self.products=products

    async def __call__(self, operation_id, selection, *, bounded=False):
        from .solver import solve, validate_scene
        from .spatial_planning import GeminiSpatialPlanner, repair_candidate, validate_plan
        operation,room=self.operations.guard(operation_id)
        data=operation.get('spatial',{})
        if 'snapshot' not in data:
            snapshot_id=operation['request'].get('snapshot_id')
            if snapshot_id:
                snapshot=self.store.get('snapshots',snapshot_id)
                require(snapshot and snapshot.get('room_id')==room['room_id'] and snapshot.get('capture_id')==operation['request']['capture_id'],'invalid_snapshot','The requested snapshot is unavailable for this Room and capture.',422)
                require(snapshot.get('room',{}).get('validity',{}).get('usable',False),'invalid_room','The requested Room snapshot is unusable. Choose a valid snapshot or rescan this Room.',422)
                with self.store.transaction():self._save(operation_id,'snapshot',snapshot)
            else:
                snapshot=await self.process_snapshot(operation_id,bounded=bounded)
                if snapshot is None:return
            data['snapshot']=snapshot
            if bounded:return
        snapshot=data['snapshot']
        selections=data.get('candidate_selections') or {record['selection_id']:record for record in selection['selected']}
        planning=self.store.get('planning',room['room_id']) or {'instructions':[]}
        instructions={}
        for entry in planning['instructions']:
            native_id=entry['target']['id']
            mapping=snapshot['identity_map'].get(native_id)
            require(mapping is not None,'unresolved_identity','A planning Object could not be mapped into the processed Room.')
            require(not isinstance(mapping,dict) or mapping.get('kind')=='object','unresolved_identity','A planning Object is unresolved in this snapshot. Review the instruction before generating.')
            normalized_id=mapping.get('id') if isinstance(mapping,dict) else mapping
            require(isinstance(normalized_id,str),'unresolved_identity','A planning identity mapping is ambiguous.')
            instructions[normalized_id]=entry['instruction']
        constraints=deepcopy(data.get('candidate_constraints') or {'intent':selection.get('approved_intent',operation['request']['intent']),'instructions':instructions,'approved_ceiling':selection['approved_ceiling'],'decision_revision':operation['decision_revision'],'base':operation['base_context'],'must_have_selection_ids':[key for key,record in selections.items() if record.get('must_have')],'explicit_selection_ids':[key for key,record in selections.items() if record.get('explicit_choice') or record.get('requirements_text')],'required_product_attributes':{key:record['requirements'] for key,record in selections.items() if record.get('requirements')}})
        if 'plan' not in data:
            constraints['user_request']={'text':operation['request'].get('text',''),
                'answers':self.operations.effective_answers(operation),'assumptions':selection.get('assumptions',[])}
            if selected_id:=operation['request'].get('selected_object_id'):
                mapping=snapshot['identity_map'].get(selected_id)
                normalized_id=mapping.get('id') if isinstance(mapping,dict) and mapping.get('kind')=='object' else mapping if isinstance(mapping,str) else None
                require(isinstance(normalized_id,str),'unresolved_identity','The selected Object could not be mapped into the processed Room. Select it again before generating.')
                constraints['user_request']['selected_object_id']=normalized_id
            self.operations.checkpoint(operation_id,'planning_layout')
            photos=[]
            frames=sorted([frame for frame in self.store.list('keyframes',room['room_id']) if frame['capture_id']==room['latest_capture_id']],key=lambda frame:frame['idx'])
            indices=sorted(set([0,len(frames)//2,len(frames)-1])) if frames else []
            for index in indices:
                descriptor=next(d for d in frames[index]['artifacts'] if d['kind']=='jpeg')
                artifact=self.store.get('artifacts',descriptor['artifact_id'])
                photos.append(await asyncio.to_thread(self.storage.get,artifact['storage_key']))
            planner=self.planner or GeminiSpatialPlanner()
            try:
                result=await planner.plan(snapshot,selections,instructions,photos,constraints)
            except Exception as error:
                raise DomainError(getattr(error,'code','planning_provider_failure'),'Spatial planning could not finish. Your capture and choices are preserved.',502,True) from None
            require(not result.get('hard_errors'),'invalid_spatial_plan','The spatial plan did not preserve required constraints.')
            with self.store.transaction():
                self._save(operation_id,'planner_diagnostics',{k:v for k,v in result.items() if k!='plan'})
                self._save(operation_id,'plan',result['plan'])
            data['plan']=result['plan']
            if bounded:return
        plan=deepcopy(data['plan'])
        constraints.setdefault('must_have_add_ids',[a['add_id'] for a in plan.get('adds',[]) if a['selection_id'] in constraints.get('must_have_selection_ids',[])+constraints.get('explicit_selection_ids',[])])
        if data.get('repair_question'):
            stopped,plan,constraints= self._consume_repair_answer(operation_id,data,plan,constraints)
            if stopped:
                return
            operation,_=self.operations.guard(operation_id)
        plan['decision_revision']=operation['decision_revision']
        constraints['decision_revision']=operation['decision_revision']
        validation=validate_plan(plan,snapshot,selections,constraints)
        require(not validation['hard_errors'] and not validation['invalid_count'],'invalid_spatial_plan','The retained spatial plan no longer satisfies approved constraints.')
        self.operations.checkpoint(operation_id,'validating_placement')
        result=solve(snapshot,plan,selections,constraints)
        if result.get('conflicts'):
            equivalents=data.get('verified_equivalents')
            if equivalents is None:
                equivalents=await self._verified_equivalents(operation_id,selections,constraints,bounded=bounded)
                if equivalents is None:return
                with self.store.transaction():
                    self._save(operation_id,'verified_equivalents',equivalents)
                data['verified_equivalents']=equivalents
            repair=repair_candidate(snapshot,plan,selections,constraints,result,equivalents,approved_repair=data.get('approved_repair'))
            if repair['state']=='awaiting_question':
                draft=repair['question']
                choices=[{'choice_id':choice['id'],'label':choice['label'],**({'selection':choice['selection'],'variant_id':choice['selection']['variant_id']} if choice.get('selection') else {})} for choice in draft.get('choices',[])]
                choices.append({'choice_id':'cancel_generation','label':'Cancel generation'})
                with self.store.transaction():
                    self._save(operation_id,'plan',repair['plan'])
                    self._save(operation_id,'candidate_selections',repair['selections'])
                    self._save(operation_id,'candidate_constraints',repair.get('constraints',constraints))
                    self._save(operation_id,'private_candidate',repair['solve_result'])
                    self._save(operation_id,'repair_diagnostics',repair['diagnostics'])
                    question=self.operations.ask(operation_id,{'kind':'listing_choice' if draft['kind']=='spatial_tradeoff' else 'single_choice','context':'repair','text':draft['text'],'choices':choices,'allow_skip':False,'allow_delegate':False,'repair_context':draft})
                    current=self.store.get('operations',operation_id)
                    current['spatial']['repair_question']=question
                    self.store.put('operations',operation_id,current)
                return
            result,plan,selections=repair['solve_result'],repair['plan'],repair['selections']
            constraints=repair.get('constraints',constraints)
            if result.get('conflicts'):
                self.operations.finish(operation_id,'rejected',{'result_kind':'spatial_conflict','conflicts':result['conflicts'],'warnings':result.get('warnings',[]),'message_ids':[]})
                return
        for omission in data.get('approved_omissions',[]):
            result['action_outcomes'].append(omission)
            result['warnings'].append({'code':'user_approved_omission','message':omission['reason'],'action_id':omission['action_id']})
        final_validation=validate_plan(plan,snapshot,selections,constraints)
        require(not final_validation['hard_errors'] and not final_validation['invalid_count'],'invalid_spatial_plan','The repaired plan did not preserve approved requirements.')
        scene=result['scene']
        if data.get('approved_omissions'):
            scene['summary']='The arrangement preserves your approved changes. Some Additions were omitted with your explicit approval.'
        scene['purchase_summary']=calculate_purchases(scene['items'],{record['offer_id']:record['offer'] for record in selections.values()},selection['approved_ceiling'])
        require(scene['purchase_summary']['within_budget'],'budget_conflict','Placed Products exceed the approved ceiling.')
        scene['selections']=deepcopy(selections)
        used={addition['selection_id'] for addition in plan.get('adds',[])}
        if set(used)!={r['selection_id'] for r in selection['selected']} or operation['decision_revision']!=selection['decision_revision']:
            selection={**deepcopy(selection),'selection_snapshot_id':identity(),'decision_revision':operation['decision_revision'],
                       'selected':[deepcopy(record) for key,record in selections.items() if key in used],
                       'purchases':deepcopy(scene['purchase_summary']),'created_at':now()}
            with self.store.transaction():
                self.operations.guard(operation_id)
                self.store.put('selections',selection['selection_snapshot_id'],selection)
                current=self.store.get('operations',operation_id)
                current['controller']['selection']=selection
                self.store.put('operations',operation_id,current)
        with self.store.transaction():
            self._save(operation_id,'plan',plan)
            self._save(operation_id,'candidate_selections',selections)
            self._save(operation_id,'candidate_constraints',constraints)
            self._save(operation_id,'private_candidate',result)
        self.operations.checkpoint(operation_id,'saving')
        Publisher(self.store,self.operations,lambda room,scene:validate_scene(room,scene,constraints)).publish(operation_id,snapshot,selection,plan,result)

    async def process_snapshot(self,operation_id,*,bounded=False):
        from io import BytesIO
        import numpy as np
        from PIL import Image
        from .geometry import normalize_room
        from .lifting import decode_depth,lift_keyframe
        from .merging import merge
        from .perception import PerceptronAdapter
        operation,room=self.operations.guard(operation_id)
        capture=self.store.get('captures',room['latest_capture_id'])
        self.operations.checkpoint(operation_id,'processing_room')
        measured=normalize_room(capture['raw_export'],room['latest_capture_id'],room['room_id'])
        require(measured['validity']['usable'],'invalid_room','A usable room boundary could not be established. Rescan this Room.')
        frames=sorted([frame for frame in self.store.list('keyframes',room['room_id']) if frame['capture_id']==room['latest_capture_id']],key=lambda frame:frame['idx'])
        lifts=[];outcomes=[];references=[]
        for frame in frames:
            self.operations.guard(operation_id)
            async def artifact_bytes(kind):
                descriptor=next(d for d in frame['artifacts'] if d['kind']==kind)
                artifact=self.store.get('artifacts',descriptor['artifact_id'])
                return await asyncio.to_thread(self.storage.get,artifact['storage_key'])
            outcome=self.store.get('detection_outcomes',frame['frame_id'])
            if outcome is None:
                jpeg=await artifact_bytes('jpeg')
                outcome=await (self.detector or PerceptronAdapter()).detect(jpeg,frame['w'],frame['h'],frame['frame_id'])
                outcome.update(room_id=room['room_id'],capture_id=room['latest_capture_id'],frame_id=frame['frame_id'])
                with self.store.transaction():
                    self.operations.guard(operation_id)
                    self.store.put('detection_outcomes',frame['frame_id'],outcome)
                if bounded:return None
            input_fingerprint=stable_id('lift_input',[2,capture['raw_export'],frame,outcome])
            lift_id=stable_id('lift',[frame['frame_id'],input_fingerprint])
            lift=self.store.get('keyframe_lifts',lift_id)
            if lift is None:
                rgb=np.asarray(Image.open(BytesIO(await artifact_bytes('jpeg'))).convert('RGB'))
                depth=None
                if any(d['kind']=='depth' for d in frame['artifacts']):
                    confidence=await artifact_bytes('confidence') if any(d['kind']=='confidence' for d in frame['artifacts']) else None
                    depth=decode_depth(await artifact_bytes('depth'),confidence,frame['depth_w'],frame['depth_h'],depth_format=frame['depth_format'],confidence_format=frame.get('confidence_format','uint8'))
                succeeded=outcome.get('state')=='succeeded'
                lift=lift_keyframe(measured,frame,outcome.get('detections',[]) if succeeded else [],rgb,depth)
                if not succeeded:
                    lift.update(state='failed',diagnostics=[{'code':'detection_failed'}])
                lift.update(lift_id=lift_id,room_id=room['room_id'],input_fingerprint=input_fingerprint)
                with self.store.transaction():
                    self.operations.guard(operation_id)
                    self.store.put('keyframe_lifts',lift_id,lift)
                if bounded:return None
            lifts.append(lift);outcomes.append(outcome);references.append({'frame_id':frame['frame_id'],'lift_id':lift_id})
        fingerprint=stable_id('snapshot_input',[2,capture['raw_export'],references])
        previous=self.store.get('snapshots',room.get('latest_snapshot_id'))
        if previous and previous['capture_id']==room['latest_capture_id'] and previous.get('input_fingerprint')==fingerprint:
            snapshot=previous
        else:
            prior=previous['room'] if previous and previous['capture_id']==room['latest_capture_id'] else None
            measured=merge(measured,lifts,prior)
            measured['processing'].update(outcomes=outcomes,lift_refs=references)
            snapshot={'schema_version':1,'snapshot_id':identity(),'revision':previous.get('revision',0)+1 if previous else 1,'room_id':room['room_id'],'capture_id':room['latest_capture_id'],'created_at':now(),'input_fingerprint':fingerprint,'room':measured,'identity_map':measured['identity_map'],'validity':measured['validity'],'processing':measured['processing']}
        with self.store.transaction():
            self.operations.guard(operation_id)
            if self.store.get('snapshots',snapshot['snapshot_id']) is None:self.store.put('snapshots',snapshot['snapshot_id'],snapshot)
            self._save(operation_id,'snapshot',snapshot)
        return snapshot

    async def _verified_equivalents(self, operation_id, selections, constraints, *, bounded=False):
        from .planning import PlanningController

        operation,_=self.operations.guard(operation_id)
        known=PlanningController._known_choices(operation)
        progress=operation.get('spatial',{}).get('equivalent_progress',{'completed':[],'equivalents':{key:[] for key in selections}})
        equivalents: dict[str, list[dict[str, Any]]] = progress['equivalents']
        if self.products is None:
            return equivalents
        for selection_id,selected in selections.items():
            seen=set()
            for choice in known:
                reference=(choice.get('variant_id'),choice.get('offer_id'))
                if choice.get('category')!=selected['category'] or reference in seen or reference==(selected['variant_id'],selected['offer_id']):
                    continue
                seen.add(reference)
                verification_id=stable_id('equivalent',[operation_id,selection_id,*reference])
                if verification_id in progress['completed']:continue
                self.operations.guard(operation_id)
                request={**deepcopy(choice),'selection_id':stable_id('repair_selection',[selection_id,*reference]),'quantity':selected.get('quantity',1)}
                try:
                    if bounded:
                        checked=await asyncio.to_thread(self.products.verify_selection,[request],constraints['approved_ceiling'],bounded=True,verification_id=verification_id,context={'room_id':operation['room_id'],'operation_id':operation_id})
                        if checked['state']=='running':return None
                        verified=checked['selected']
                    else:verified=await asyncio.to_thread(self.products.verify_selection,[request],constraints['approved_ceiling'])
                except ProductError:
                    verified=[]
                self.operations.guard(operation_id)
                for record in verified:
                    if record['category']==selected['category']:
                        record.update(must_have=selected.get('must_have',False),explicit_choice=selected.get('explicit_choice',False))
                        equivalents[selection_id].append(record)
                progress['completed'].append(verification_id)
                with self.store.transaction():self._save(operation_id,'equivalent_progress',progress)
                if bounded:return None
        return equivalents

    def _consume_repair_answer(self, operation_id, data, plan, constraints):
        operation,_=self.operations.guard(operation_id)
        question=data['repair_question']
        reply=next((a for a in operation['answer_history'] if a['question_id']==question['question_id']),None)
        if reply is None:
            raise DomainError('awaiting_answer','The exact repair question must be answered before continuing.')
        choices=reply['request'].get('choice_ids',[])
        require(len(choices)==1,'invalid_repair_answer','Choose an explicit repair option or cancel generation.',422)
        choice=choices[0]
        if choice=='cancel_generation':
            self.operations.cancel(operation['device_id'],operation_id,reply['reply_id'])
            return True,plan,constraints
        draft=question['repair_context']
        if choice=='omit_requirement':
            removed=next((a for a in plan['adds'] if a['add_id']==draft['add_id']),None)
            if removed is None:
                raise DomainError('invalid_repair_answer','The requested Addition is no longer in this private candidate.')
            dependents=[a for a in plan['adds'] if a['anchor'].get('target',{}).get('add_id')==removed['add_id']]
            require(not dependents,'support_dependency','This Addition supports other required choices. Cancel and revise the requirements.',422)
            plan['adds'].remove(removed)
            constraints['must_have_add_ids']=[key for key in constraints.get('must_have_add_ids',[]) if key!=removed['add_id']]
            constraints['must_have_selection_ids']=[key for key in constraints.get('must_have_selection_ids',[]) if key!=removed['selection_id']]
            constraints['explicit_selection_ids']=[key for key in constraints.get('explicit_selection_ids',[]) if key!=removed['selection_id']]
            constraints['must_have_categories']=[key for key in constraints.get('must_have_categories',[]) if key!=removed['category']]
            data.setdefault('approved_omissions',[]).append({'action_id':removed['action_id'],'type':'add','outcome':'no_op','code':'user_approved_omission','reason':'User explicitly approved continuing without this Addition.','affected_item_ids':[]})
        else:
            require(any(option['id']==choice and option.get('selection') for option in draft['choices']),'invalid_repair_answer','The selected repair was not a verified option.',422)
            data['approved_repair']={'add_id':draft['add_id'],'selection_id':choice}
        plan['decision_revision']=operation['decision_revision']
        constraints['decision_revision']=operation['decision_revision']
        with self.store.transaction():
            self._save(operation_id,'plan',plan)
            self._save(operation_id,'candidate_constraints',constraints)
            self._save(operation_id,'approved_repair',data.get('approved_repair'))
            self._save(operation_id,'approved_omissions',data.get('approved_omissions',[]))
            self._save(operation_id,'repair_question',None)
        data['repair_question']=None
        return False,plan,constraints

    def _save(self, operation_id, key, value):
        operation,_=self.operations.guard(operation_id)
        operation.setdefault('spatial',{})[key]=deepcopy(value)
        self.store.put('operations',operation_id,operation)
