import hashlib
import io
import json
import plistlib
import uuid

import numpy as np
from PIL import Image
import pytest

from respace_reconstruction.models import Manifest


@pytest.fixture(autouse=True)
def offline_generation(monkeypatch):
    # Normal tests must never send captures to a paid API, even on a configured host.
    monkeypatch.setenv("RESPACE_SCENE_GENERATOR", "measured")
    monkeypatch.setenv("RESPACE_PIPELINE", "legacy")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


@pytest.fixture
def capture():
    """Analytic textured plane viewed from calibrated, translated ARKit cameras."""
    capture_id = str(uuid.uuid4())
    payloads = {}
    serial = 0

    def artifact(kind, data, suffix):
        nonlocal serial
        serial += 1
        identity = f"artifact-{serial}"
        name = identity + "." + suffix
        payloads[name] = data
        return {"id": identity, "type": kind, "filename": name, "byte_length": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    frames = []
    width, height, fx, fy = 640, 480, 480., 480.
    for i, x in enumerate([-.4, -.2, 0, .2, .4]):
        pose = np.eye(4)
        pose[0, 3] = x
        meta = {"schema_version": 1, "id": f"frame-{i}", "capture_id": capture_id, "timestamp": i*45.,
            "width": width, "height": height, "orientation": "sensor", "intrinsics": [fx, fy, width/2, height/2],
            "camera_to_scan_transform": pose.flatten(order="F").tolist(), "depth_width": 160, "depth_height": 120,
            "depth_format": "float16_le_meters", "confidence_width": 160, "confidence_height": 120, "confidence_format": "uint8_arkit"}
        u, v = np.meshgrid(np.arange(width), np.arange(height))
        worldx, worldy = x+(u-width/2)*2/fx, -(v-height/2)*2/fy
        checker = ((np.floor(worldx*8) + np.floor(worldy*8)) % 2)*150 + 50
        rgb = np.stack([checker, np.mod(worldx*70+128, 255), np.mod(worldy*70+128, 255)], axis=2).astype(np.uint8)
        jpeg = io.BytesIO()
        Image.fromarray(rgb).save(jpeg, format="JPEG", quality=95)
        assets = [artifact("jpeg", jpeg.getvalue(), "jpg"),
            artifact("depth", np.full((120, 160), 2, dtype="<f2").tobytes(), "bin"),
            artifact("confidence", np.full((120, 160), 2, dtype=np.uint8).tobytes(), "bin"),
            artifact("metadata", json.dumps(meta).encode(), "json")]
        frames.append({"id": meta["id"], "metadata": meta, "artifacts": assets})
    vertices = np.array([[-1.7, -1, -2], [1.7, -1, -2], [1.7, 1, -2], [-1.7, 1, -2]], dtype="<f4")
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype="<u4")
    scan = {"schemaVersion": 1, "captureId": capture_id, "coordinateSystem": "arkit_scan_meters_y_up", "timestamp": 180.,
        "anchors": [{"id": "mesh", "transform": np.eye(4).flatten(order="F").tolist(), "vertexCount": 4,
        "triangleCount": 2, "positions": vertices.tobytes(), "triangles": faces.tobytes(),
        "normals": np.tile([0, 0, 1], (4, 1)).astype("<f4").tobytes()}]}
    mesh = artifact("scene_mesh", plistlib.dumps(scan, fmt=plistlib.FMT_BINARY), "mesh")
    room = artifact("roomplan", b'{"doors":[],"windows":[],"openings":[]}', "json")
    manifest = Manifest.model_validate({"schema_version": 1, "capture_id": capture_id, "state": "local_saved",
        "frames": frames, "scene_mesh": mesh, "room_export": room})
    return manifest, payloads
