import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_BYTES = 2 * 1024**3
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class Artifact(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9-]{1,64}$")
    type: Literal["jpeg", "depth", "confidence", "metadata", "roomplan", "thumbnail", "scene_mesh"]
    filename: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    byte_length: int = Field(gt=0, le=128 * 1024**2)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class Metadata(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    schema_version: Literal[1] = 1
    id: str
    capture_id: str
    timestamp: float
    width: int = Field(gt=0, le=8192)
    height: int = Field(gt=0, le=8192)
    orientation: Literal["sensor"] = "sensor"
    intrinsics: list[float] = Field(min_length=4, max_length=4)
    camera_to_scan_transform: list[float] = Field(min_length=16, max_length=16)
    depth_width: int | None = Field(default=None, gt=0, le=4096)
    depth_height: int | None = Field(default=None, gt=0, le=4096)
    depth_format: Literal["float16_le_meters"] | None = None
    confidence_width: int | None = Field(default=None, gt=0, le=4096)
    confidence_height: int | None = Field(default=None, gt=0, le=4096)
    confidence_format: Literal["uint8_arkit"] | None = None

    @model_validator(mode="after")
    def calibration(self):
        if self.intrinsics[0] <= 0 or self.intrinsics[1] <= 0:
            raise ValueError("Invalid camera focal length")
        m = self.camera_to_scan_transform
        if any(abs(m[i]) > 1e-4 for i in (3, 7, 11)) or abs(m[15] - 1) > 1e-4:
            raise ValueError("Invalid camera transform")
        axes = [m[i:i+3] for i in (0, 4, 8)]
        for i, a in enumerate(axes):
            for j, b in enumerate(axes):
                if abs(sum(x*y for x, y in zip(a, b)) - (1 if i == j else 0)) > .01:
                    raise ValueError("Camera transform must be rigid")
        a, b, c = axes
        det = a[0]*(b[1]*c[2]-b[2]*c[1])-b[0]*(a[1]*c[2]-a[2]*c[1])+c[0]*(a[1]*b[2]-a[2]*b[1])
        if abs(det - 1) > .01:
            raise ValueError("Reflected camera transform")
        return self


class Frame(BaseModel):
    id: str
    metadata: Metadata
    artifacts: list[Artifact] = Field(min_length=1, max_length=4)


class Manifest(BaseModel):
    schema_version: Literal[1]
    capture_id: str = Field(pattern=r"^[A-Za-z0-9-]{1,64}$")
    state: Literal["completed", "local_saved"]
    frames: list[Frame] = Field(min_length=1, max_length=900)
    scene_mesh: Artifact
    room_export: Artifact
    thumbnail: Artifact | None = None

    @property
    def artifacts(self):
        return [a for f in self.frames for a in f.artifacts] + [self.scene_mesh, self.room_export] + ([self.thumbnail] if self.thumbnail else [])

    @model_validator(mode="after")
    def consistency(self):
        artifacts = self.artifacts
        if len({a.id for a in artifacts}) != len(artifacts) or len({a.filename for a in artifacts}) != len(artifacts):
            raise ValueError("Artifact identities and filenames must be unique")
        if sum(a.byte_length for a in artifacts) > MAX_BYTES:
            raise ValueError("Capture exceeds 2 GiB")
        if self.scene_mesh.type != "scene_mesh" or self.room_export.type != "roomplan":
            raise ValueError("Incorrect mesh or RoomPlan artifact type")
        if self.thumbnail and self.thumbnail.type != "thumbnail":
            raise ValueError("Incorrect thumbnail type")
        if len({f.id for f in self.frames}) != len(self.frames):
            raise ValueError("Duplicate frame")
        for f in self.frames:
            if f.id != f.metadata.id or f.metadata.capture_id != self.capture_id:
                raise ValueError("Frame belongs to another capture")
            types = {a.type: a for a in f.artifacts}
            if len(types) != len(f.artifacts) or not {"jpeg", "metadata"} <= types.keys():
                raise ValueError("Frame requires unique JPEG and metadata artifacts")
            if set(types) - {"jpeg", "metadata", "depth", "confidence"}:
                raise ValueError("Unexpected frame artifact")
            meta = f.metadata
            if "depth" in types:
                if not meta.depth_width or not meta.depth_height or meta.depth_format is None or types["depth"].byte_length != meta.depth_width * meta.depth_height * 2:
                    raise ValueError("Depth dimensions/format do not match bytes")
            if "confidence" in types:
                if "depth" not in types or not meta.confidence_width or not meta.confidence_height or meta.confidence_format is None or types["confidence"].byte_length != meta.confidence_width * meta.confidence_height:
                    raise ValueError("Confidence dimensions/format do not match bytes")
        return self
