import base64
import io
import json

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from respace_reconstruction import renditions
from respace_reconstruction.app import create_app
from respace_reconstruction.renditions import RenditionRequest, Renditions
from respace_reconstruction.scene import SceneBundle
from respace_reconstruction.store import atomic_json
from test_scene import scene_data


def image_bytes(format="JPEG"):
    stream = io.BytesIO()
    Image.new("RGB", (1536, 1024), (120, 125, 130)).save(stream, format=format)
    return stream.getvalue()


def body():
    data = scene_data(); data["ready"] = True; data["entities"][0]["move_ready"] = True
    return RenditionRequest(image_base64=base64.b64encode(image_bytes()).decode(), scene=SceneBundle.model_validate(data))


def test_single_render_edit_is_persisted_and_never_repurchased(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-private-key")
    service = Renditions(tmp_path)
    directory = service.directory(tmp_path/"capture", 1, "a"*64)
    calls = []
    def generate(request, key):
        calls.append(request)
        assert json.loads((directory/"receipt.json").read_text())["state"] == "generating"
        assert key == "test-private-key"
        assert request["model"] == "gpt-image-2" and request["n"] == 1
        assert len(request["images"]) == 1 and request["size"] == "1536x1024"
        assert base64.b64decode(request["images"][0]["image_url"].split(",")[1]) == image_bytes()
        return {"data": [{"b64_json": base64.b64encode(image_bytes("PNG")).decode()}]}
    monkeypatch.setattr(renditions, "call_image", generate)
    assert service.prepare(directory, body(), "capture", 1)[1]
    assert json.loads((directory/"receipt.json").read_text())["view"] == "corner_room_view_v2"
    assert not service.prepare(directory, body(), "capture", 1)[1]
    service.generate(directory)
    assert service.status(directory)["state"] == "succeeded"
    assert not service.prepare(directory, body(), "capture", 1)[1]
    assert len(calls) == 1 and (directory/"image.png").read_bytes() == image_bytes("PNG")
    assert "test-private-key" not in (directory/"receipt.json").read_text()


def test_interrupted_request_remains_failed_after_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-private-key")
    service = Renditions(tmp_path)
    directory = service.directory(tmp_path/"capture", 1, "a"*64)
    service.prepare(directory, body(), "capture", 1)
    reopened = Renditions(tmp_path); reopened.recover()
    assert "billing may be unknown" in reopened.status(directory)["error"]
    assert not reopened.prepare(directory, body(), "capture", 1)[1]


def test_invalid_images_and_changed_design_keys_do_not_generate(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-private-key")
    service = Renditions(tmp_path)
    directory = service.directory(tmp_path, 1, "a"*64)
    invalid = body(); invalid.image_base64 = "bad image"
    with pytest.raises(ValueError): service.prepare(directory, invalid, "capture", 1)
    assert not directory.exists()
    service.prepare(directory, body(), "capture", 1)
    changed = body(); changed.scene.entities[0].visible = False
    with pytest.raises(ValueError, match="another design"):
        service.prepare(directory, changed, "capture", 1)


def test_authenticated_endpoints_serve_only_finished_images(tmp_path, capture, monkeypatch):
    manifest, _ = capture
    monkeypatch.setenv("OPENAI_API_KEY", "test-private-key")
    monkeypatch.setattr(renditions, "call_image", lambda *args: {"data": [{"b64_json": base64.b64encode(image_bytes("PNG")).decode()}]})
    app = create_app(tmp_path, "test-reconstruction-token", start_worker=False)
    app.state.store.create(manifest)
    result = app.state.store.folder(manifest.capture_id)/"results/1"; result.mkdir(parents=True)
    atomic_json(result/"completion.json", {"status": "succeeded"})
    request = body(); request.scene.capture_id = manifest.capture_id
    path = f"/v1/reconstructions/{manifest.capture_id}/results/1/renditions/"+"a"*64
    with TestClient(app) as client:
        assert client.post(path, json=request.model_dump()).status_code == 401
        client.headers["Authorization"] = "Bearer test-reconstruction-token"
        assert client.get(path).status_code == client.get(path+"/image").status_code == 404
        assert client.post(path, json=request.model_dump()).status_code == 202
        assert client.get(path).json()["state"] == "succeeded"
        assert client.get(path+"/image").content == image_bytes("PNG")
        assert client.post(path, json=request.model_dump()).json()["state"] == "succeeded"
        assert client.get(path.replace("/results/1/", "/results/2/")).status_code == 404


def test_image_edit_transport_uses_json_and_never_exposes_the_api_key(monkeypatch):
    requests = []
    def urlopen(request, timeout):
        requests.append(request)
        assert request.full_url == "https://api.openai.com/v1/images/edits"
        assert request.get_header("Authorization") == "Bearer private-key"
        assert request.get_header("Content-type") == "application/json" and timeout == 900
        payload = json.loads(request.data)
        assert payload["images"][0]["image_url"].startswith("data:image/jpeg;base64,")
        assert "private-key" not in request.data.decode()
        return io.BytesIO(b'{"data":[]}')
    monkeypatch.setattr(renditions.urllib.request, "urlopen", urlopen)
    payload = {"model": "gpt-image-2", "images": [{"image_url": "data:image/jpeg;base64,"+body().image_base64}]}
    assert renditions.call_image(payload, "private-key") == {"data": []}
    assert len(requests) == 1
