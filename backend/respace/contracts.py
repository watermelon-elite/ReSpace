"""Version-one mutation inputs shared by the native HTTP client."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, field_validator

ID = Annotated[str, Field(min_length=1,max_length=160,pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]*$')]


class Request(BaseModel):
    model_config=ConfigDict(extra='forbid')
    schema_version: Literal[1]=1
    operation_id: ID


class CreateRoom(Request):
    name: str | None=Field(default=None,max_length=100)


class RenameRoom(Request):
    name: str=Field(min_length=1,max_length=100)
    expected_metadata_revision: int=Field(ge=0)


class Generation(Request):
    capture_id: ID
    snapshot_id: ID | None=None
    planning_revision: int=Field(ge=0)
    expected_active_design_id: ID | None=None
    expected_active_revision: int=Field(ge=0)
    intent: Literal['add','redesign']='add'
    styles: list[str]=Field(default_factory=lambda:['Match what I have'],max_length=6)
    budget: str
    currency: Literal['USD']='USD'
    text: str=Field(default='',max_length=10000)

    @field_validator('styles')
    @classmethod
    def styles_allowed(cls, styles):
        named={'Cozy','Minimal','Japandi','Industrial','Boho','Mid-century'}
        if styles==['Match what I have'] or styles==['match']:
            return styles
        if not styles or len(set(styles))!=len(styles) or not set(styles)<=named:
            raise ValueError('Choose Match what I have or distinct supported named styles')
        return styles


class PlanningCommand(Request):
    capture_id: ID
    planning_revision: int=Field(ge=0)
    text: str=Field(min_length=1,max_length=10000)
    selected_object: dict | None=None


class Answer(BaseModel):
    model_config=ConfigDict(extra='forbid')
    schema_version: Literal[1]=1
    operation_id: ID
    question_id: ID
    reply_id: ID
    expected_decision_revision: int=Field(ge=0)
    expected_question_revision: int=Field(ge=0)
    choice_ids: list[ID]=Field(default_factory=list,max_length=100)
    text: str | None=Field(default=None,max_length=10000)
    number: FiniteFloat | None=None
    action: Literal['answer','skip','delegate']='answer'
    budget_approval: dict | None=None
    revision_of_answer_id: ID | None=None


class Dismissal(BaseModel):
    schema_version: Literal[1]=1
    operation_id: ID
    question_id: ID
    dismissal_id: ID


class Cancellation(BaseModel):
    schema_version: Literal[1]=1
    operation_id: ID
    cancellation_id: ID


class ArtifactDescriptor(BaseModel):
    model_config=ConfigDict(extra='forbid')
    artifact_id: ID
    capture_id: ID
    frame_id: ID | None=None
    kind: Literal['jpeg','depth','confidence','roomplan']
    format: Literal['image/jpeg','float32_le_m','uint8','application/json']
    byte_length: int=Field(gt=0,le=12000000)
    checksum: str=Field(pattern=r'^[a-f0-9]{64}$')
    w: int | None=Field(default=None,gt=0,le=4096)
    h: int | None=Field(default=None,gt=0,le=4096)
    orientation: Literal['sensor_landscape'] | None=None


class FrameRef(BaseModel):
    frame_id: ID
    idx: int=Field(ge=0,lt=40)


class CaptureManifest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    room_id: ID
    capture_id: ID
    final_export_artifact_id: ID
    frames: list[FrameRef]=Field(max_length=40)
    artifacts: list[ArtifactDescriptor]=Field(max_length=121)
    completion_id: ID
    started_at: str
    completed_at: str

    @field_validator('started_at','completed_at')
    @classmethod
    def utc_timestamp(cls,value):
        from datetime import datetime,timedelta
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        if parsed.utcoffset()!=timedelta(0): raise ValueError('Capture timestamps must be UTC')
        return value


class Finalize(Request):
    capture_id: ID
    raw_export_base64: str=Field(max_length=16000000)
    export_descriptor: ArtifactDescriptor
    manifest: CaptureManifest


class FindMore(Request):
    item_id: ID
    refinements: str=Field(default='',max_length=10000)
    expected_active_design_id: ID
    expected_active_revision: int=Field(ge=0)


def validate_frame(meta, parts):
    import math
    from io import BytesIO
    from PIL import Image
    from .operations import require
    require(meta.get('schema_version')==1,'schema_version','Unsupported schema version.',422)
    for field in ('operation_id','capture_id','frame_id'):
        from pydantic import TypeAdapter
        TypeAdapter(ID).validate_python(meta.get(field))
    require(isinstance(meta.get('idx'),int) and not isinstance(meta['idx'],bool) and 0<=meta['idx']<40,'invalid_frame','Invalid frame index.',422)
    require(meta.get('orientation')=='sensor_landscape','invalid_frame','Preserve native sensor orientation.',422)
    require(isinstance(meta.get('timestamp'),(int,float)) and math.isfinite(meta['timestamp']),'invalid_frame','Frame timestamp is required.',422)
    transform=meta.get('transform',[])
    require(len(transform)==16 and all(isinstance(n,(int,float)) and not isinstance(n,bool) and math.isfinite(n) for n in transform),'invalid_frame','Camera transform needs sixteen finite column-major values.',422)
    intrinsics=meta.get('intrinsics',{})
    require(all(isinstance(intrinsics.get(k),(int,float)) and math.isfinite(intrinsics[k]) for k in ('fx','fy','cx','cy')) and intrinsics['fx']>0 and intrinsics['fy']>0,'invalid_frame','Valid calibrated intrinsics are required.',422)
    try:
        image=Image.open(BytesIO(parts['jpeg']))
        require(image.format=='JPEG' and image.size==(meta['w'],meta['h']) and max(image.size)<=1280 and min(image.size)>0,'invalid_image','JPEG dimensions must match calibrated metadata and be at most 1280 px.',422)
        image.verify()
    except (OSError,KeyError,ValueError):
        require(False,'invalid_image','Invalid JPEG evidence.',422)
    require('confidence' not in parts or 'depth' in parts,'invalid_depth','Confidence requires matching depth.',422)
    if 'depth' in parts:
        w,h=meta.get('depth_w'),meta.get('depth_h')
        require(isinstance(w,int) and isinstance(h,int) and 0<w<=4096 and 0<h<=4096 and meta.get('depth_format')=='float32_le_m' and len(parts['depth'])==w*h*4,'invalid_depth','Depth dimensions/format/bytes disagree.',422)
        if 'confidence' in parts:
            require(meta.get('confidence_format')=='uint8' and len(parts['confidence'])==w*h and all(v<=2 for v in parts['confidence']),'invalid_depth','Confidence bytes must match depth and contain 0, 1 or 2.',422)
    require(isinstance(meta.get('artifacts'),list) and len(meta['artifacts'])==len(parts),'invalid_artifact','Expected artifact descriptors.',422)
    for descriptor in meta['artifacts']:
        from pydantic import TypeAdapter
        TypeAdapter(ID).validate_python(descriptor.get('artifact_id'))
        require(descriptor.get('frame_id')==meta['frame_id'],'invalid_artifact','Artifact frame identity differs.',422)


class Undo(Request):
    expected_active_design_id: ID
    expected_active_revision: int=Field(ge=0)


class Edit(Undo):
    text: str=Field(min_length=1,max_length=10000)
    selected_item_id: ID | None=None


class Remove(Undo):
    item_id: ID


class Swap(Undo):
    item_id: ID
    variant_id: ID
    offer_id: ID
    search_id: ID
    selection_id: ID | None=None
