"""Versioned public API. Run with uvicorn respace.api:create_app --factory."""
import json
import os
import asyncio
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, Header, Request as HTTPRequest
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from . import contracts
from .capture import CaptureService
from .operations import DomainError, OperationService, require
from .planning import GeminiPlanningModel, PlanningController
from .products import ProductError, money


class LazyProductModels:
    def __init__(self): self.model=None
    def _get(self):
        if self.model is None:
            from .discovery import GeminiProductModels
            self.model=GeminiProductModels()
        return self.model
    def extract(self,*args): return self._get().extract(*args)
    def score(self,*args): return self._get().score(*args)
    def select_batch(self,*args,**kwargs): return self._get().select_batch(*args,**kwargs)
    def extract_batch(self,*args): return self._get().extract_batch(*args)
    def score_batch(self,*args): return self._get().score_batch(*args)


class LazyPlanningModel:
    async def act(self,context):
        require(bool(os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY')),'unavailable_capability','Gemini planning is not configured.',503)
        model=GeminiPlanningModel()
        try: return await model.act(context)
        finally: await model.client.aio.aclose()


def create_app(store=None, storage=None, products=None, model=None, spatial=None, *, edit_model=None, local=False, allow_review_model=None):
    allow_review_model = not local if allow_review_model is None else allow_review_model
    if store is None:
        from .store import PostgresStore
        store=PostgresStore(os.environ['DATABASE_URL'])
    if storage is None:
        from .storage import CaptureStorage
        storage=CaptureStorage(os.environ['CAPTURE_BUCKET'])
    operations=OperationService(store)
    if products is None:
        from .discovery import ProductService, SerpAPIShopping, PlaywrightVerifier
        models=LazyProductModels()
        def guard_product_output(record):
            context=record.get('intended_context') or record.get('context') or {}
            operations.guard(context.get('operation_id',record.get('operation_id')))
        products=ProductService(store,SerpAPIShopping(),PlaywrightVerifier(models),models,guard=guard_product_output)
    captures=CaptureService(store,operations,storage)
    if spatial is None:
        from .spatial import SpatialPipeline
        spatial=SpatialPipeline(store,operations,storage,products=products)
    controller=PlanningController(store,operations,products,model or LazyPlanningModel(),spatial)
    from .edits import EditController
    editor=EditController(store,operations,products,edit_model)
    async def step(kind,operation_id,*,bounded=True):
        if kind in {'generation','find_more'}:await controller.run(operation_id,bounded=bounded)
        elif kind in {'edit','swap'}:await editor.run(operation_id,bounded=bounded)
        elif kind=='planning_command':
            from .review import review_command
            try:await review_command(store,operations,operation_id,allow_model=allow_review_model)
            except DomainError as error:
                operations.finish(operation_id,'failed' if error.retryable else 'rejected',failure={'code':error.code,'message':error.message,'retryable':error.retryable})
        else:raise DomainError('unavailable_capability','This operation cannot be continued by a worker.',422)

    @asynccontextmanager
    async def local_lifespan(app):
        tasks=[]
        for operation in store.list('operations'):
            room=store.get('rooms',operation['room_id'])
            if (operation['state'] in {'queued','running'} and not operation.get('pending_question')
                    and room and room.get('current_operation_id')==operation['operation_id']
                    and store.get('deletions',operation['room_id']) is None):
                tasks.append(asyncio.create_task(step(operation['kind'],operation['operation_id'],bounded=False)))
        try:
            yield
        finally:
            for task in tasks:task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)

    app=FastAPI(title='ReSpace',version='1',lifespan=local_lifespan if local else None)
    app.state.store,app.state.operations,app.state.controller=store,operations,controller
    app.state.storage=storage
    role='api' if local else os.environ.get('RESPACE_SERVICE_ROLE','api')
    require(role in {'api','worker'},'invalid_configuration','Configure RESPACE_SERVICE_ROLE as api or worker.',500)
    workers=None
    if not local and (os.environ.get('CLOUD_TASKS_QUEUE') or role=='worker'):
        from .workers import GoogleCloudTasksDispatcher,WorkerService
        workers=WorkerService(store,GoogleCloudTasksDispatcher.from_env(),step)
    app.state.workers=workers

    def schedule(background,operation):
        if workers is not None:workers.enqueue(operation['operation_id'])
        elif operation['kind']=='planning_command':
            from .review import review_command
            background.add_task(review_command,store,operations,operation['operation_id'],allow_model=allow_review_model)
        else:background.add_task(editor.run if operation['kind'] in {'edit','swap'} else controller.run,operation['operation_id'])

    @app.middleware('http')
    async def bound_body(request, call_next):
        content_length=request.headers.get('content-length')
        if content_length and (not content_length.isdigit() or int(content_length)>18000000):
            return JSONResponse({'schema_version':1,'error':{'code':'request_too_large','message':'Request exceeds the evidence upload limit.','retryable':False}},status_code=413)
        return await call_next(request)

    @app.exception_handler(DomainError)
    async def domain_error(request, error):
        return JSONResponse({'schema_version':1,'error':{'code':error.code,'message':error.message,'retryable':error.retryable,'details':error.details}},status_code=error.status)

    @app.exception_handler(ProductError)
    async def product_error(request, error):
        return JSONResponse({'schema_version':1,'error':{'code':error.code,'message':str(error),'retryable':False}},status_code=422)

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    async def validation_error(request, error):
        fields=[{'field':'.'.join(str(k) for k in entry['loc']),'message':entry['msg']} for entry in error.errors()]
        return JSONResponse({'schema_version':1,'error':{'code':'invalid_request','message':'Request fields are invalid.','retryable':False,'details':fields}},status_code=422)

    def device(value):
        from pydantic import TypeAdapter
        return TypeAdapter(contracts.ID).validate_python(value)

    def operation_response(operation):
        return {'schema_version':1,'operation':{**{k:v for k,v in operation.items() if k not in {'device_id','spatial','edit'}},'answer_revision_allowed':operations.can_revise(operation)}}

    if role=='worker':
        from pydantic import BaseModel,Field
        class Delivery(BaseModel):
            operation_id: contracts.ID
            generation: int=Field(ge=1)
        @app.post('/internal/work')
        async def work(body:Delivery):
            assert workers is not None
            result=await workers.deliver(body.operation_id,body.generation)
            return JSONResponse(result,status_code=503 if result['state']=='busy' else 200)
        @app.post('/internal/recover')
        def recover():
            assert workers is not None
            return workers.recover()
        return app

    @app.get('/v1/health')
    def health(): return {'schema_version':1,'status':'ok'}

    @app.post('/v1/rooms')
    def create_room(body:contracts.CreateRoom, x_device_id:str=Header()):
        return captures.create(device(x_device_id),body.model_dump(exclude_none=True))

    @app.post('/v1/rooms/imported')
    def import_room(body:contracts.ImportedRoom,x_device_id:str=Header()):
        return captures.import_context(device(x_device_id),body.model_dump(exclude_none=True))

    @app.get('/v1/rooms')
    def rooms(x_device_id:str=Header()):
        current_device=device(x_device_id)
        records=[captures.summary(room) for room in store.list('rooms') if room['device_id']==current_device]
        return {'schema_version':1,'rooms':sorted(records,key=lambda room:room['created_at'],reverse=True),'next_cursor':None}

    @app.get('/v1/rooms/{room_id}')
    def room_detail(room_id:contracts.ID,x_device_id:str=Header()):
        detail=captures.detail(device(x_device_id),room_id)
        if detail['current_operation'] is not None:
            detail['current_operation']=operation_response(detail['current_operation'])['operation']
        return detail

    @app.patch('/v1/rooms/{room_id}')
    def rename_room(room_id:contracts.ID,body:contracts.RenameRoom,x_device_id:str=Header()): return captures.rename(device(x_device_id),room_id,body.model_dump())

    @app.delete('/v1/rooms/{room_id}')
    def delete_room(room_id:contracts.ID,operation_id:contracts.ID,x_device_id:str=Header()):
        result=operations.delete_room(device(x_device_id),room_id,operation_id,storage)
        return JSONResponse({'schema_version':1,'deletion':result},status_code=200 if result['state']=='deleted' else 202)

    @app.post('/v1/rooms/{room_id}/keyframes')
    async def keyframe(room_id:contracts.ID,request:HTTPRequest,x_device_id:str=Header()):
        form=await request.form(max_files=3,max_fields=1,max_part_size=100000)
        require(set(form.keys())<= {'jpeg','depth','confidence','meta'} and 'jpeg' in form and isinstance(form.get('meta'),str),'invalid_keyframe','Expected calibrated multipart evidence.',422)
        try: meta=json.loads(form['meta'],parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except ValueError: raise DomainError('invalid_keyframe','Frame metadata must be valid finite JSON.',422) from None
        parts={}
        for kind in ('jpeg','depth','confidence'):
            if kind in form:
                upload=form[kind]
                require(hasattr(upload,'read'),'invalid_keyframe','Evidence parts must be files.',422)
                parts[kind]=await upload.read(4000001)
                require(len(parts[kind])<=4000000,'request_too_large','A frame artifact exceeds the upload limit.',413)
        contracts.validate_frame(meta,parts)
        return captures.upload(device(x_device_id),room_id,meta,parts)

    @app.post('/v1/rooms/{room_id}/finalize')
    def finalize(room_id:contracts.ID,body:contracts.Finalize,x_device_id:str=Header()): return captures.finalize(device(x_device_id),room_id,body.model_dump())

    @app.get('/v1/rooms/{room_id}/artifacts/{artifact_id}')
    def artifact(room_id:contracts.ID,artifact_id:contracts.ID,x_device_id:str=Header()):
        operations.room(device(x_device_id),room_id)
        saved=store.get('artifacts',artifact_id)
        require(saved and saved['room_id']==room_id,'unknown_artifact','Capture artifact was not found.',404)
        return Response(storage.get(saved['storage_key']),media_type=saved['descriptor']['format'])

    @app.get('/v1/rooms/{room_id}/snapshots/{snapshot_id}')
    def snapshot(room_id:contracts.ID,snapshot_id:contracts.ID,x_device_id:str=Header()):
        operations.room(device(x_device_id),room_id)
        saved=store.get('snapshots',snapshot_id)
        require(saved and saved['room_id']==room_id,'unknown_snapshot','Processed snapshot was not found.',404)
        return {'schema_version':1,'snapshot':saved}

    @app.get('/v1/rooms/{room_id}/conversation')
    def conversation(room_id:contracts.ID,x_device_id:str=Header()):
        operations.room(device(x_device_id),room_id)
        return {'schema_version':1,'entries':sorted(store.list('messages',room_id),key=lambda entry:entry['created_at']),'next_cursor':None}

    @app.get('/v1/rooms/{room_id}/snapshots/{snapshot_id}/overlays/{frame_id}')
    def overlay(room_id:contracts.ID,snapshot_id:contracts.ID,frame_id:contracts.ID,x_device_id:str=Header()):
        from .lifting import calibrated_overlay_svg
        operations.room(device(x_device_id),room_id)
        saved=store.get('snapshots',snapshot_id)
        require(saved and saved['room_id']==room_id,'unknown_snapshot','Processed snapshot was not found.',404)
        ref=next((ref for ref in saved.get('processing',{}).get('lift_refs',[]) if ref['frame_id']==frame_id),None)
        if ref is None:raise DomainError('unknown_frame','This frame is not part of the saved snapshot.',404)
        lift=store.get('keyframe_lifts',ref['lift_id']);frame=store.get('keyframes',frame_id)
        return Response(calibrated_overlay_svg(saved['room'],frame,lift),media_type='image/svg+xml')

    @app.post('/v1/rooms/{room_id}/planning-commands')
    async def planning_command(room_id:contracts.ID,body:contracts.PlanningCommand,background:BackgroundTasks,x_device_id:str=Header()):
        from .review import review_command
        require(bool(body.text.strip()),'invalid_command','Enter a planning instruction.',422)
        operation=operations.submit(device(x_device_id),room_id,'planning_command',body.model_dump())
        if operation['state'] not in {'succeeded','rejected','failed','cancelled','needs_clarification'}:
            if workers is not None:schedule(background,operation)
            else:
                try:
                    await review_command(store,operations,operation['operation_id'],allow_model=allow_review_model)
                except DomainError as error:
                    operations.finish(operation['operation_id'],'rejected',{'result_kind':error.code,'message':error.message,'message_ids':[]})
        return operation_response(operations.get(device(x_device_id),body.operation_id))

    @app.post('/v1/rooms/{room_id}/designs')
    def generate(room_id:contracts.ID,body:contracts.Generation,background:BackgroundTasks,x_device_id:str=Header()):
        if body.budget is not None: money(body.budget,positive=body.intent!='auto')
        room=operations.room(device(x_device_id),room_id)
        require(room['capture_state']=='complete','capture_incomplete','Complete this capture before generating.')
        if body.selected_object_id:
            capture=store.get('captures',room['latest_capture_id'])
            require(any(body.selected_object_id in {obj.get('id'),obj.get('native_id')} for obj in capture.get('measured_context',{}).get('objects',[])),
                'unknown_object','Select an Object from this Room.',422)
        request=body.model_dump()
        if request['snapshot_id'] is None:del request['snapshot_id']
        operation=operations.submit(device(x_device_id),room_id,'generation',request)
        schedule(background,operation)
        return JSONResponse(operation_response(operation),status_code=202 if operation['state'] not in {'succeeded','rejected','failed','cancelled'} else 200)

    @app.get('/v1/operations/{operation_id}')
    def operation_status(operation_id:contracts.ID,background:BackgroundTasks,x_device_id:str=Header()):
        operation=operations.get(device(x_device_id),operation_id)
        if operation['kind'] in {'generation','find_more','edit','swap','planning_command'} and operation['state'] in {'queued','running'} and not operation.get('pending_question'):
            schedule(background,operation)
        return operation_response(operation)

    @app.post('/v1/operations/{operation_id}/answers')
    def answer(operation_id:contracts.ID,body:contracts.Answer,background:BackgroundTasks,x_device_id:str=Header()):
        require(body.operation_id==operation_id,'wrong_operation','Answer operation identity differs.',422)
        result=operations.answer(device(x_device_id),operation_id,body.model_dump(exclude_none=True))
        schedule(background,result)
        return operation_response(result)

    @app.post('/v1/operations/{operation_id}/dismiss-clarification')
    def dismiss(operation_id:contracts.ID,body:contracts.Dismissal,x_device_id:str=Header()):
        require(body.operation_id==operation_id,'wrong_operation','Dismissal identity differs.',422)
        return operation_response(operations.dismiss(device(x_device_id),operation_id,body.model_dump()))

    @app.post('/v1/operations/{operation_id}/cancel')
    def cancel(operation_id:contracts.ID,body:contracts.Cancellation,x_device_id:str=Header()):
        require(body.operation_id==operation_id,'wrong_operation','Cancellation identity differs.',422)
        return operation_response(operations.cancel(device(x_device_id),operation_id,body.cancellation_id))

    @app.post('/v1/rooms/{room_id}/undo')
    def undo(room_id:contracts.ID,body:contracts.Undo,x_device_id:str=Header()):
        from .history import HistoryService
        return operation_response(HistoryService(store,operations).undo(device(x_device_id),room_id,body.model_dump()))

    @app.get('/v1/designs/{design_id}')
    def design(design_id:contracts.ID,x_device_id:str=Header()):
        saved=store.get('designs',design_id)
        require(saved is not None,'unknown_design','Design was not found.',404)
        operations.room(device(x_device_id),saved['room_id'])
        return {'schema_version':1,'design':saved}

    @app.post('/v1/designs/{design_id}/find-more')
    def find_more(design_id:contracts.ID,body:contracts.FindMore,background:BackgroundTasks,x_device_id:str=Header()):
        saved=store.get('designs',design_id)
        require(saved is not None and body.expected_active_design_id==design_id,'unknown_design','Design was not found.',404)
        operation=operations.submit(device(x_device_id),saved['room_id'],'find_more',body.model_dump())
        schedule(background,operation)
        return JSONResponse(operation_response(operation),status_code=202)

    def submit_edit(design_id,body,kind,background,current_device):
        saved=store.get('designs',design_id)
        require(saved is not None and body.expected_active_design_id==design_id,'unknown_design','Design was not found.',404)
        operation=operations.submit(current_device,saved['room_id'],kind,body.model_dump(exclude_none=True))
        schedule(background,operation)
        return JSONResponse(operation_response(operation),status_code=202 if operation['state'] not in {'succeeded','rejected','failed','cancelled'} else 200)

    @app.post('/v1/designs/{design_id}/chat')
    def edit(design_id:contracts.ID,body:contracts.Edit,background:BackgroundTasks,x_device_id:str=Header()):
        require(bool(body.text.strip()),'invalid_command','Enter a design instruction.',422)
        return submit_edit(design_id,body,'edit',background,device(x_device_id))

    @app.post('/v1/designs/{design_id}/remove')
    def remove(design_id:contracts.ID,body:contracts.Remove,background:BackgroundTasks,x_device_id:str=Header()):
        return submit_edit(design_id,body,'edit',background,device(x_device_id))

    @app.post('/v1/designs/{design_id}/swap')
    def swap(design_id:contracts.ID,body:contracts.Swap,background:BackgroundTasks,x_device_id:str=Header()):
        return submit_edit(design_id,body,'swap',background,device(x_device_id))

    @app.get('/v1/searches/{search_id}')
    def search(search_id:contracts.ID,x_device_id:str=Header()):
        saved=products.get_search(search_id)
        operations.room(device(x_device_id),saved['room_id'])
        return {'schema_version':1,'search':saved}

    @app.get('/v1/catalog/manifest')
    def manifest(revision:str|None=None):
        from .assets import manifest
        return manifest(revision)

    @app.get('/v1/catalog/assets/{asset_id}/{revision}')
    def asset(asset_id:contracts.ID,revision:contracts.ID):
        from fastapi.responses import FileResponse
        from .assets import asset_path
        return FileResponse(asset_path(asset_id,revision),media_type='model/vnd.usdz+zip',headers={'Cache-Control':'public,max-age=31536000,immutable'})

    return app
