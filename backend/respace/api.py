"""Versioned public API. Run with uvicorn respace.api:create_app --factory."""
import json
import os

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


class LazyPlanningModel:
    async def act(self,context):
        require(bool(os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY')),'unavailable_capability','Gemini planning is not configured.',503)
        model=GeminiPlanningModel()
        try: return await model.act(context)
        finally: await model.client.aio.aclose()


def create_app(store=None, storage=None, products=None, model=None, spatial=None):
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
    app=FastAPI(title='ReSpace',version='1')
    app.state.store,app.state.operations,app.state.controller=store,operations,controller

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
        return {'schema_version':1,'operation':{k:v for k,v in operation.items() if k!='device_id'}}

    @app.get('/v1/health')
    def health(): return {'schema_version':1,'status':'ok'}

    @app.post('/v1/rooms')
    def create_room(body:contracts.CreateRoom, x_device_id:str=Header()):
        return captures.create(device(x_device_id),body.model_dump(exclude_none=True))

    @app.get('/v1/rooms')
    def rooms(x_device_id:str=Header()):
        current_device=device(x_device_id)
        records=[captures.summary(room) for room in store.list('rooms') if room['device_id']==current_device]
        return {'schema_version':1,'rooms':sorted(records,key=lambda room:room['created_at'],reverse=True),'next_cursor':None}

    @app.get('/v1/rooms/{room_id}')
    def room_detail(room_id:contracts.ID,x_device_id:str=Header()): return captures.detail(device(x_device_id),room_id)

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

    @app.post('/v1/rooms/{room_id}/planning-commands')
    async def planning_command(room_id:contracts.ID,body:contracts.PlanningCommand,x_device_id:str=Header()):
        from .review import review_command
        require(bool(body.text.strip()),'invalid_command','Enter a planning instruction.',422)
        operation=operations.submit(device(x_device_id),room_id,'planning_command',body.model_dump())
        if operation['state'] not in {'succeeded','rejected','failed','cancelled','needs_clarification'}:
            try:
                await review_command(store,operations,operation['operation_id'])
            except DomainError as error:
                operations.finish(operation['operation_id'],'rejected',{'result_kind':error.code,'message':error.message,'message_ids':[]})
        return operation_response(operations.get(device(x_device_id),body.operation_id))

    @app.post('/v1/rooms/{room_id}/designs')
    def generate(room_id:contracts.ID,body:contracts.Generation,background:BackgroundTasks,x_device_id:str=Header()):
        money(body.budget,positive=True)
        room=operations.room(device(x_device_id),room_id)
        require(room['capture_state']=='complete','capture_incomplete','Complete this capture before generating.')
        operation=operations.submit(device(x_device_id),room_id,'generation',body.model_dump())
        background.add_task(controller.run,body.operation_id)
        return JSONResponse(operation_response(operation),status_code=202 if operation['state'] not in {'succeeded','rejected','failed','cancelled'} else 200)

    @app.get('/v1/operations/{operation_id}')
    def operation_status(operation_id:contracts.ID,background:BackgroundTasks,x_device_id:str=Header()):
        operation=operations.get(device(x_device_id),operation_id)
        if operation['kind'] in {'generation','find_more'} and operation['state'] in {'queued','running'} and not operation.get('pending_question'):
            background.add_task(controller.run,operation_id)
        return operation_response(operation)

    @app.post('/v1/operations/{operation_id}/answers')
    def answer(operation_id:contracts.ID,body:contracts.Answer,background:BackgroundTasks,x_device_id:str=Header()):
        require(body.operation_id==operation_id,'wrong_operation','Answer operation identity differs.',422)
        result=operations.answer(device(x_device_id),operation_id,body.model_dump(exclude_none=True))
        if result['kind']=='planning_command':
            from .review import review_command
            background.add_task(review_command,store,operations,operation_id)
        else: background.add_task(controller.run,operation_id)
        return operation_response(result)

    @app.post('/v1/operations/{operation_id}/dismiss-clarification')
    def dismiss(operation_id:contracts.ID,body:contracts.Dismissal,x_device_id:str=Header()):
        require(body.operation_id==operation_id,'wrong_operation','Dismissal identity differs.',422)
        return operation_response(operations.dismiss(device(x_device_id),operation_id,body.model_dump()))

    @app.post('/v1/operations/{operation_id}/cancel')
    def cancel(operation_id:contracts.ID,body:contracts.Cancellation,x_device_id:str=Header()):
        require(body.operation_id==operation_id,'wrong_operation','Cancellation identity differs.',422)
        return operation_response(operations.cancel(device(x_device_id),operation_id,body.cancellation_id))

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
        background.add_task(controller.run,body.operation_id)
        return JSONResponse(operation_response(operation),status_code=202)

    @app.get('/v1/searches/{search_id}')
    def search(search_id:contracts.ID,x_device_id:str=Header()):
        saved=products.get_search(search_id)
        operations.room(device(x_device_id),saved['room_id'])
        return {'schema_version':1,'search':saved}

    @app.get('/v1/catalog/manifest')
    def manifest():
        from .assets import manifest
        return manifest()

    @app.get('/v1/catalog/assets/{asset_id}/{revision}')
    def asset(asset_id:contracts.ID,revision:contracts.ID):
        from fastapi.responses import FileResponse
        from .assets import asset_path
        return FileResponse(asset_path(asset_id,revision),media_type='model/vnd.usdz+zip',headers={'Cache-Control':'public,max-age=31536000,immutable'})

    return app
