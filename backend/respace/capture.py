"""Capture receipts and native review; no deferred perception runs here."""
import base64
import hashlib
import json
import math
from .operations import identity, now, require, DomainError


class CaptureService:
    def __init__(self, store, operations, storage):
        self.store,self.operations,self.storage=store,operations,storage

    def _receipt(self, device_id, operation_id, request, room_id=None):
        receipt=self.store.get('receipts',operation_id)
        if receipt:
            require(receipt['device_id']==device_id and receipt['request']==request and (room_id is None or receipt['room_id']==room_id),'identity_conflict','Mutation identity already has a different payload.')
        return receipt

    def _save_receipt(self, device_id, operation_id, request, response, room_id):
        self.store.put('receipts',operation_id,{'receipt_id':operation_id,'device_id':device_id,'room_id':room_id,'request':request,'response':response})
        return response

    def create(self, device_id, request):
        with self.store.transaction():
            require(not any(deletion.get('creation_operation_id')==request['operation_id'] and deletion['device_id']==device_id for deletion in self.store.list('deletions')),'room_deleted','This Room creation was already deleted.',410)
            receipt=self._receipt(device_id,request['operation_id'],request)
            if receipt:
                self.operations.room(device_id,receipt['room_id'])
                return receipt['response']
            room_id,capture_id=identity(),identity()
            created=now()
            default='Room '+created[:10]
            existing=[r for r in self.store.list('rooms') if r['device_id']==device_id]
            name=request.get('name') or default
            if not request.get('name'):
                suffix=2
                while any(r['name']==name for r in existing):
                    name=f'{default} ({suffix})'
                    suffix+=1
            room={'schema_version':1,'room_id':room_id,'device_id':device_id,'name':name,'metadata_revision':0,'creation_operation_id':request['operation_id'],'created_at':created,'scan_at':None,'thumbnail_url':None,'capture_state':'draft','latest_capture_id':capture_id,'latest_snapshot_id':None,'planning_revision':0,'active_design_id':None,'active_revision':0,'current_operation_id':None,'warnings':[]}
            self.store.put('rooms',room_id,room)
            self.store.put('captures',capture_id,{'capture_id':capture_id,'room_id':room_id,'state':'draft','expected_artifacts':0,'stored_artifacts':0,'missing_artifacts':0})
            self.store.put('planning',room_id,{'room_id':room_id,'capture_id':capture_id,'planning_revision':0,'instructions':[]})
            return self._save_receipt(device_id,request['operation_id'],request,{'schema_version':1,'room':self.summary(room),'capture_id':capture_id},room_id)

    def summary(self, room):
        result={k:v for k,v in room.items() if k!='device_id'}
        op=self.store.get('operations',room.get('current_operation_id')) if room.get('current_operation_id') else None
        result['current_operation_state']=op['state'] if op else None
        deletion=self.store.get('deletions',room['room_id'])
        if deletion:
            result['deletion_state']=deletion['state']
        return result

    def import_context(self, device_id, request):
        with self.store.transaction():
            created=self.create(device_id,request)
            room=self.operations.room(device_id,created['room']['room_id'])
            capture=self.store.get('captures',room['latest_capture_id'])
            if capture['state']!='complete':
                capture.update(state='complete',source='imported_scene',planning_only=True,
                    source_capture_id=request['source_capture_id'],source_scene_sha256=request['source_scene_sha256'],
                    measured_context={'source':'imported_scene','units':'meters','frame':'meters_y_up_floor_zero',
                        'objects':[entity for entity in request['entities'] if entity['kind'] not in {'wall','floor','ceiling'}],
                        'structure':[entity for entity in request['entities'] if entity['kind'] in {'wall','floor','ceiling'}],
                        'uncertainty':'Reconstructed mesh bounds, not native RoomPlan measurements. Supports and calibrated capture photos are unavailable; layout placement is not validated.'})
                room.update(capture_state='complete',source_scene_sha256=request['source_scene_sha256'],
                    warnings=[{'code':'imported_context','message':'Reconstructed scene: planning is available; validated layout changes require the original capture.'}])
                self.store.put('captures',capture['capture_id'],capture)
                self.store.put('rooms',room['room_id'],room)
            return self.detail(device_id,room['room_id'])

    def detail(self, device_id, room_id):
        room=self.operations.room(device_id,room_id)
        capture=self.store.get('captures',room['latest_capture_id'])
        op=self.store.get('operations',room.get('current_operation_id')) if room.get('current_operation_id') else None
        latest_searches={}
        for search in sorted(self.store.list('searches',room_id),key=lambda search:search.get('completed_at','')):
            context=search.get('intended_context',{})
            if search.get('state') in {'completed','no_match'} and context.get('design_id')==room.get('active_design_id') and context.get('item_id'):
                latest_searches[context['item_id']]={'search_id':search['search_id'],'design_id':context['design_id'],'item_id':context['item_id'],'completed_at':search.get('completed_at')}
        return {'schema_version':1,'product_searches':list(latest_searches.values()),'room':self.summary(room),'capture_status':capture,'measured_context':capture.get('measured_context'),'raw_export':capture.get('raw_export'),'planning':self.store.get('planning',room_id),'current_operation':op}

    def rename(self, device_id, room_id, request):
        with self.store.transaction():
            room=self.operations.room(device_id,room_id)
            receipt=self._receipt(device_id,request['operation_id'],request,room_id)
            if receipt: return receipt['response']
            require(request['expected_metadata_revision']==room['metadata_revision'],'stale_metadata','The Room name changed. Refresh and rename again.')
            require(bool(request['name'].strip()) and len(request['name'])<=100,'invalid_name','Use a Room name of 1–100 characters.',422)
            room.update(name=request['name'].strip(),metadata_revision=room['metadata_revision']+1)
            self.store.put('rooms',room_id,room)
            return self._save_receipt(device_id,request['operation_id'],request,{'schema_version':1,'room':self.summary(room)},room_id)

    def upload(self, device_id, room_id, meta, parts):
        with self.store.transaction():
            room=self.operations.room(device_id,room_id)
            require(meta['capture_id']==room['latest_capture_id'],'wrong_capture','Keyframe belongs to another capture.',422)
            prior=self._receipt(device_id,meta['operation_id'],meta,room_id)
            descriptors={d['kind']:d for d in meta['artifacts']}
            require(set(parts)==set(descriptors),'invalid_artifact','Artifact descriptors must match the supplied parts.',422)
            require(len({d['artifact_id'] for d in meta['artifacts']})==len(parts),'artifact_identity_conflict','Each artifact requires its own identity.',409)
            for kind,data in parts.items():
                descriptor=descriptors[kind]
                self.validate_descriptor(descriptor,data,meta['capture_id'])
                existing=self.store.get('artifacts',descriptor['artifact_id'])
                require(existing is None or (existing['room_id']==room_id and existing['capture_id']==meta['capture_id'] and existing['descriptor']==descriptor),'artifact_identity_conflict','Artifact identity already belongs to different evidence.',409)
            if prior: return prior['response']
            capture=self.store.get('captures',meta['capture_id'])
            require(capture['state']!='complete','capture_finalized','No new frames may change a completed capture.')
            frames=self.store.list('keyframes',room_id)
            require(meta['idx']<40 and len(frames)<40 and all(f['idx']!=meta['idx'] and f['frame_id']!=meta['frame_id'] for f in frames),'frame_conflict','Frame index or identity is already stored, or the frame cap was reached.')
            receipts=[]
            for kind,data in parts.items():
                descriptor=descriptors[kind]
                key=f"rooms/{room_id}/{meta['capture_id']}/{descriptor['artifact_id']}"
                # The transaction keeps deletion from racing a private upload.
                self.storage.put(key,data,'image/jpeg' if kind=='jpeg' else 'application/octet-stream')
                receipt={'artifact_id':descriptor['artifact_id'],'room_id':room_id,'capture_id':meta['capture_id'],'byte_length':len(data),'checksum':descriptor['checksum'],'durable':True,'outcome':'stored','stored_at':now(),'storage_key':key,'descriptor':descriptor}
                self.store.put('artifacts',descriptor['artifact_id'],receipt)
                receipts.append({k:v for k,v in receipt.items() if k not in {'storage_key','descriptor'}})
            self.store.put('keyframes',meta['frame_id'],{**meta,'room_id':room_id,'detection_state':'not_started'})
            count=len(self.store.list('artifacts',room_id))
            capture.update(state='capturing',stored_artifacts=count)
            room['capture_state']='capturing'
            if not room.get('thumbnail_url'):
                photo=descriptors['jpeg']['artifact_id']
                room['thumbnail_url']=f'/v1/rooms/{room_id}/artifacts/{photo}'
            self.store.put('captures',meta['capture_id'],capture)
            self.store.put('rooms',room_id,room)
            response={'schema_version':1,'receipts':receipts,'capture_status':capture,'processing':{'state':'not_started'}}
            return self._save_receipt(device_id,meta['operation_id'],meta,response,room_id)

    @staticmethod
    def validate_descriptor(descriptor, data, capture_id):
        require(descriptor.get('capture_id')==capture_id and descriptor.get('byte_length')==len(data) and descriptor.get('checksum')==hashlib.sha256(data).hexdigest(),'artifact_mismatch','Artifact bytes, checksum or capture identity differ.',422)

    def finalize(self, device_id, room_id, request):
        with self.store.transaction():
            room=self.operations.room(device_id,room_id)
            require(request['capture_id']==room['latest_capture_id'],'wrong_capture','Final export belongs to another capture.',422)
            receipt=self._receipt(device_id,request['operation_id'],request,room_id)
            if receipt and receipt['response']['capture_status']['state']=='complete': return receipt['response']
            try:
                data=base64.b64decode(request['raw_export_base64'],validate=True)
                raw=json.loads(data,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
            except (ValueError,TypeError):
                raise DomainError('invalid_export','Native export must contain valid finite JSON.',422) from None
            require(isinstance(raw,dict) and isinstance(raw.get('walls'),list) and isinstance(raw.get('objects',[]),list),'invalid_export','Unsupported native room export.',422)
            descriptor=request['export_descriptor']
            self.validate_descriptor(descriptor,data,request['capture_id'])
            manifest=request['manifest']
            require(manifest['room_id']==room_id and manifest['capture_id']==request['capture_id'],'wrong_capture','Manifest belongs to another Room/capture.',422)
            expected=manifest['artifacts']
            require(manifest.get('completion_id')==request['operation_id'],'invalid_manifest','Completion identity must match finalization identity.',422)
            declared_frames=manifest.get('frames',[])
            require(len(declared_frames)<=40 and len({frame['frame_id'] for frame in declared_frames})==len(declared_frames) and len({frame['idx'] for frame in declared_frames})==len(declared_frames),'invalid_manifest','Expected frames need distinct identities and indexes.',422)
            stored_frames=[frame for frame in self.store.list('keyframes',room_id) if frame['capture_id']==request['capture_id']]
            require(all(any(frame['frame_id']==entry['frame_id'] and frame['idx']==entry['idx'] for entry in declared_frames) for frame in stored_frames),'invalid_manifest','Manifest omits an accepted frame.',422)
            ids=[entry['artifact_id'] for entry in expected]
            require(len(ids)==len(set(ids)) and descriptor['artifact_id'] in ids and manifest['final_export_artifact_id']==descriptor['artifact_id'],'invalid_manifest','Manifest needs distinct artifacts and the final native export.',422)
            key=f"rooms/{room_id}/{request['capture_id']}/{descriptor['artifact_id']}"
            artifact=self.store.get('artifacts',descriptor['artifact_id'])
            if artifact:
                require(artifact['checksum']==descriptor['checksum'],'identity_conflict','Export identity has different content.')
            else:
                self.storage.put(key,data,'application/json')
                self.store.put('artifacts',descriptor['artifact_id'],{'artifact_id':descriptor['artifact_id'],'room_id':room_id,'capture_id':request['capture_id'],'checksum':descriptor['checksum'],'byte_length':len(data),'storage_key':key,'descriptor':descriptor,'durable':True,'outcome':'stored'})
            missing=[]
            for item in expected:
                artifact=self.store.get('artifacts',item['artifact_id'])
                if not artifact or artifact['room_id']!=room_id or any(artifact.get(k)!=item[k] for k in ('byte_length','checksum')):
                    missing.append(item['artifact_id'])
            capture=self.store.get('captures',request['capture_id'])
            capture.update(state='upload_pending' if missing else 'complete',expected_artifacts=len(expected),stored_artifacts=len(expected)-len(missing),missing_artifacts=len(missing),missing_artifact_ids=missing,manifest=manifest,raw_export=raw)
            room['capture_state']=capture['state']
            if not missing:
                require(len(stored_frames)==len(declared_frames),'invalid_manifest','Some expected frame metadata is not stored.',422)
                require(set(ids)=={artifact['artifact_id'] for artifact in self.store.list('artifacts',room_id) if artifact['capture_id']==request['capture_id']},'invalid_manifest','Manifest omits stored capture evidence.',422)
                capture['measured_context']=measured_context(raw,request['capture_id'],manifest['completed_at'])
                room['scan_at']=manifest['completed_at']
            self.store.put('captures',capture['capture_id'],capture)
            self.store.put('rooms',room_id,room)
            response=self.detail(device_id,room_id)
            # An incomplete manifest may be retried after its missing uploads arrive.
            self._save_receipt(device_id,request['operation_id'],request,response,room_id)
            return response


def measured_context(raw, capture_id, captured_at):
    objects=[]
    for obj in raw.get('objects',[]):
        dimensions=obj.get('dimensions',[])
        transform=obj.get('transform',[])
        require(isinstance(dimensions,list) and len(dimensions)==3 and all(isinstance(n,(int,float)) and not isinstance(n,bool) and math.isfinite(n) and n>0 for n in dimensions),'invalid_export','Native Object dimensions are invalid.',422)
        require(isinstance(transform,list) and len(transform)==16 and all(isinstance(n,(int,float)) and math.isfinite(n) for n in transform),'invalid_export','Native Object pose is invalid.',422)
        category=obj.get('category','unknown')
        if isinstance(category,dict): category=next(iter(category),'unknown')
        objects.append({'id':obj['identifier'],'native_id':obj['identifier'],'category':category,'size':[dimensions[0],dimensions[2],dimensions[1]],'transform':transform,'confidence':obj.get('confidence'),'attributes':obj.get('attributes',[])})
    return {'capture_id':capture_id,'captured_at':captured_at,'source':'roomplan','units':'meters','frame':'original_scan_world','objects':objects,'walls':raw.get('walls',[]),'openings':{k:raw.get(k,[]) for k in ('doors','windows','openings')},'height':None,'extents':None,'uncertainty':'Native measurements have not undergone deferred spatial processing.'}
