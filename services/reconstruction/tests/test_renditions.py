import base64
import io
import json
import threading
import time
import urllib.error

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


def completed_response():
    return {"id": "resp_room", "status": "completed", "output": [{"type": "image_generation_call",
        "status": "completed", "result": base64.b64encode(image_bytes("PNG")).decode()}], "usage": {"total_tokens": 100}}


def wait_for(predicate):
    deadline = time.monotonic()+3
    while not predicate():
        assert time.monotonic() < deadline, "Rendition did not complete"
        time.sleep(.005)


def test_single_render_edit_is_persisted_and_never_repurchased(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-private-key")
    service = Renditions(tmp_path)
    directory = service.directory(tmp_path/"capture", 1, "a"*64)
    calls = []
    def generate(request, key):
        calls.append(request)
        assert json.loads((directory/"receipt.json").read_text())["state"] == "generating"
        assert key == "test-private-key"
        assert request["model"] == "gpt-6-sol" and request["reasoning"] == {"effort": "high"}
        assert request["background"] is request["store"] is True
        assert request["tool_choice"] == {"type": "image_generation"}
        assert request["max_tool_calls"] == 1
        assert request["tools"] == [{"type": "image_generation", "model": "gpt-image-2", "action": "generate",
            "size": "1536x1024", "quality": "high", "output_format": "png"}]
        inputs = request["input"][0]["content"]
        assert len(inputs) == 2 and inputs[1]["type"] == "input_image"
        assert base64.b64decode(inputs[1]["image_url"].split(",")[1]) == image_bytes()
        assert "iPhone rear main camera" in request["instructions"]
        return completed_response()
    monkeypatch.setattr(renditions, "call_response", generate)
    assert service.prepare(directory, body(), "capture", 1)[1]
    assert json.loads((directory/"receipt.json").read_text())["view"] == "corner_room_view_v5_iphone_photo_references"
    assert not service.prepare(directory, body(), "capture", 1)[1]
    service.generate(directory)
    assert service.status(directory)["state"] == "succeeded"
    assert not service.prepare(directory, body(), "capture", 1)[1]
    assert len(calls) == 1 and (directory/"image.png").read_bytes() == image_bytes("PNG")
    assert "test-private-key" not in (directory/"receipt.json").read_text()
    assert json.loads((directory/"receipt.json").read_text())["response_id"] == "resp_room"


@pytest.mark.parametrize("refresh_fails", [False, True])
def test_explicit_refresh_uses_original_render_and_preserves_previous_image(tmp_path, monkeypatch, refresh_fails):
    monkeypatch.setenv("OPENAI_API_KEY", "test-private-key")
    service = Renditions(tmp_path)
    original = service.directory(tmp_path/"capture", 1, "a"*64)
    refreshed = service.directory(tmp_path/"capture", 1, "b"*64)
    calls = []
    def generate(request, key):
        calls.append(request)
        source = request["input"][0]["content"][1]["image_url"]
        assert base64.b64decode(source.split(",")[1]) == image_bytes()  # Always the 3D render, not the prior PNG.
        if refresh_fails and len(calls) == 2:
            raise renditions.ResponseConnectionError("Submission timed out")
        return completed_response()
    monkeypatch.setattr(renditions, "call_response", generate)
    assert service.prepare(original, body(), "capture", 1)[1]
    service.generate(original)
    previous = (original/"image.png").read_bytes()
    assert service.prepare(refreshed, body(), "capture", 1)[1]
    assert not service.prepare(refreshed, body(), "capture", 1)[1]
    service.generate(refreshed)
    assert service.status(refreshed)["state"] == ("failed" if refresh_fails else "succeeded")
    assert not service.prepare(refreshed, body(), "capture", 1)[1]
    assert service.status(original)["state"] == "succeeded"
    assert (original/"image.png").read_bytes() == previous
    assert len(calls) == 2


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


def test_scan_photo_references_are_selected_snapshotted_and_sent_with_distinct_roles(tmp_path, capture, monkeypatch):
    manifest, payloads = capture
    monkeypatch.setenv("OPENAI_API_KEY", "test-private-key")
    folder = tmp_path/"capture"; inputs = folder/"inputs"; inputs.mkdir(parents=True)
    atomic_json(folder/"manifest.json", manifest.model_dump())
    for filename, data in payloads.items():
        (inputs/filename).write_bytes(data)
    result = folder/"results/1"; result.mkdir(parents=True)
    used_ids = [frame.id for frame in manifest.frames[1:4]]
    atomic_json(result/"provenance.json", {"selected_frame_ids": used_ids})
    service = Renditions(tmp_path)
    directory = service.directory(folder, 1, "a"*64)
    request = body(); request.scene.capture_id = manifest.capture_id
    request.scene.materials[0].finish = "paint"
    request.scene.materials[0].base_color = [.2, .4, .6]
    assert service.prepare(directory, request, manifest.capture_id, 1, capture_folder=folder)[1]
    references = json.loads((directory/"references.json").read_text())
    assert 1 < len(references) <= renditions.REFERENCE_PHOTO_LIMIT
    assert {r["frame_id"] for r in references} <= set(used_ids)
    assert json.loads((directory/"receipt.json").read_text())["reference_frame_ids"] == [r["frame_id"] for r in references]
    # A restart uses the saved reference copies, independent of later source changes.
    for filename in payloads:
        (inputs/filename).unlink()
    assert not service.prepare(directory, request, manifest.capture_id, 1, capture_folder=folder)[1]
    calls = []
    def generate(provider_request, key):
        calls.append(provider_request)
        content = provider_request["input"][0]["content"]
        assert content[0]["text"].startswith("Image 1: 3D composition guide.")
        context = json.loads(content[0]["text"].split("Scene context: ")[1])
        assert context["objects"][0]["finish_overrides"] == [{"finish": "paint", "color_rgb": [.2, .4, .6]}]
        assert len(content) == 2 + 2*len(references)
        assert base64.b64decode(content[1]["image_url"].split(",")[1]) == image_bytes()
        for index, reference in enumerate(references):
            assert content[2+2*index]["text"].startswith(f"Image {index+2}: original scan photo; appearance reference only.")
            photo = base64.b64decode(content[3+2*index]["image_url"].split(",")[1])
            assert photo == (directory/reference["filename"]).read_bytes()
            with Image.open(io.BytesIO(photo)) as image:
                assert image.format == "JPEG" and max(image.size) <= 1280
        assert provider_request["tools"][0]["action"] == "generate"
        return completed_response()
    monkeypatch.setattr(renditions, "call_response", generate)
    reopened = Renditions(tmp_path); reopened.generate(directory)
    assert reopened.status(directory)["state"] == "succeeded"
    assert len(calls) == 1


def test_corrupted_original_photo_cannot_start_a_paid_generation(tmp_path, capture, monkeypatch):
    manifest, payloads = capture
    monkeypatch.setenv("OPENAI_API_KEY", "test-private-key")
    folder = tmp_path/"capture"; inputs = folder/"inputs"; inputs.mkdir(parents=True)
    atomic_json(folder/"manifest.json", manifest.model_dump())
    for filename, data in payloads.items():
        (inputs/filename).write_bytes(data)
    # Keep a decodable JPEG but break its retained content hash/length.
    for frame in manifest.frames:
        photo = next(a for a in frame.artifacts if a.type == "jpeg")
        with (inputs/photo.filename).open("ab") as stream:
            stream.write(b"changed")
    service = Renditions(tmp_path)
    directory = service.directory(folder, 1, "a"*64)
    request = body(); request.scene.capture_id = manifest.capture_id
    with pytest.raises(ValueError, match="integrity check"):
        service.prepare(directory, request, manifest.capture_id, 1, capture_folder=folder)
    assert not (directory/"receipt.json").exists()


def test_portrait_sensor_photos_are_oriented_upright_from_camera_pose(tmp_path, capture):
    manifest, payloads = capture
    # The world-up vector points left in the raw sensor image; rotate clockwise.
    pose = [0., -1., 0., 0., 1., 0., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1.]
    manifest.frames = manifest.frames[:1]
    manifest.frames[0].metadata.camera_to_scan_transform = pose
    inputs = tmp_path/"inputs"; inputs.mkdir()
    atomic_json(tmp_path/"manifest.json", manifest.model_dump())
    for filename, data in payloads.items():
        (inputs/filename).write_bytes(data)
    photos = renditions.reference_photos(tmp_path, manifest.capture_id, 1)
    assert len(photos) == 1
    with Image.open(io.BytesIO(photos[0][1])) as image:
        assert image.size == (480, 640)


def test_authenticated_endpoints_serve_only_finished_images(tmp_path, capture, monkeypatch):
    manifest, payloads = capture
    monkeypatch.setenv("OPENAI_API_KEY", "test-private-key")
    monkeypatch.setattr(renditions, "call_response", lambda *args: completed_response())
    app = create_app(tmp_path, "test-reconstruction-token", start_worker=False)
    app.state.store.create(manifest)
    inputs = app.state.store.folder(manifest.capture_id)/"inputs"; inputs.mkdir(exist_ok=True)
    for filename, data in payloads.items():
        (inputs/filename).write_bytes(data)
    result = app.state.store.folder(manifest.capture_id)/"results/1"; result.mkdir(parents=True)
    atomic_json(result/"completion.json", {"status": "succeeded"})
    request = body(); request.scene.capture_id = manifest.capture_id
    path = f"/v1/reconstructions/{manifest.capture_id}/results/1/renditions/"+"a"*64
    with TestClient(app) as client:
        assert client.post(path, json=request.model_dump()).status_code == 401
        client.headers["Authorization"] = "Bearer test-reconstruction-token"
        assert client.get(path).status_code == client.get(path+"/image").status_code == 404
        assert client.post(path, json=request.model_dump()).status_code == 202
        wait_for(lambda: client.get(path).json()["state"] == "succeeded")
        assert client.get(path).json()["state"] == "succeeded"
        assert client.get(path+"/image").content == image_bytes("PNG")
        assert client.post(path, json=request.model_dump()).json()["state"] == "succeeded"
        assert client.get(path.replace("/results/1/", "/results/2/")).status_code == 404


def test_response_transport_uses_short_background_requests_and_get_for_polling(monkeypatch):
    requests = []
    def urlopen(request, timeout):
        requests.append(request)
        assert request.full_url.startswith("https://api.openai.com/v1/responses")
        assert request.get_header("Authorization") == "Bearer private-key"
        assert request.get_header("Content-type") == "application/json" and timeout == 60
        if request.get_method() == "POST":
            assert json.loads(request.data)["model"] == "gpt-6-sol"
            assert "private-key" not in request.data.decode()
        else:
            assert request.full_url.endswith("/resp_room") and request.data is None
        return io.BytesIO(b'{"id":"resp_room","status":"queued"}')
    monkeypatch.setattr(renditions.urllib.request, "urlopen", urlopen)
    payload = {"model": "gpt-6-sol", "background": True}
    assert renditions.call_response(payload, "private-key")["status"] == "queued"
    renditions.call_response(None, "private-key", "resp_room")
    assert len(requests) == 2


def test_saved_background_response_survives_restart_and_read_timeouts(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-private-key")
    monkeypatch.setattr(renditions, "POLL_SECONDS", .001)
    service = Renditions(tmp_path)
    directory = service.directory(tmp_path/"capture", 1, "a"*64)
    service.prepare(directory, body(), "capture", 1)
    path = directory/"receipt.json"
    receipt = json.loads(path.read_text()); receipt["response_id"] = "resp_room"; atomic_json(path, receipt)
    calls = []
    def retrieve(request, key, response_id=None):
        calls.append(response_id)
        assert request is None and response_id == "resp_room"  # No paid POST on recovery.
        if len(calls) == 1:
            raise renditions.ResponseConnectionError("Read timed out")
        return completed_response()
    monkeypatch.setattr(renditions, "call_response", retrieve)
    restarted = Renditions(tmp_path)
    try:
        restarted.recover()
        wait_for(lambda: restarted.status(directory)["state"] == "succeeded")
        assert len(calls) == 2
        assert (directory/"image.png").read_bytes() == image_bytes("PNG")
        assert not restarted.prepare(directory, body(), "capture", 1)[1]
    finally:
        restarted.close()


def test_ambiguous_provider_submission_is_never_automatically_repeated(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-private-key")
    service = Renditions(tmp_path)
    directory = service.directory(tmp_path, 1, "a"*64)
    service.prepare(directory, body(), "capture", 1)
    calls = []
    def interrupted(*args):
        calls.append(args)
        raise renditions.ResponseConnectionError("Submission timed out; billing may be unknown.")
    monkeypatch.setattr(renditions, "call_response", interrupted)
    service.generate(directory)
    assert service.status(directory)["state"] == "failed"
    assert not service.prepare(directory, body(), "capture", 1)[1]
    assert len(calls) == 1


def test_acceptance_and_status_are_available_while_provider_generation_is_blocked(tmp_path, capture, monkeypatch):
    manifest, payloads = capture
    monkeypatch.setenv("OPENAI_API_KEY", "test-private-key")
    release, entered = threading.Event(), threading.Event()
    calls = []
    def delayed(*args):
        calls.append(args); entered.set()
        assert release.wait(3)
        return completed_response()
    monkeypatch.setattr(renditions, "call_response", delayed)
    app = create_app(tmp_path, "test-reconstruction-token", start_worker=False)
    app.state.store.create(manifest)
    inputs = app.state.store.folder(manifest.capture_id)/"inputs"; inputs.mkdir(exist_ok=True)
    for filename, data in payloads.items():
        (inputs/filename).write_bytes(data)
    result = app.state.store.folder(manifest.capture_id)/"results/1"; result.mkdir(parents=True)
    atomic_json(result/"completion.json", {"status": "succeeded"})
    request = body(); request.scene.capture_id = manifest.capture_id
    path = f"/v1/reconstructions/{manifest.capture_id}/results/1/renditions/"+"a"*64
    with TestClient(app, headers={"Authorization": "Bearer test-reconstruction-token"}) as client:
        try:
            assert client.post(path, json=request.model_dump()).status_code == 202
            assert entered.wait(1)
            assert not release.is_set() and client.get(path).json()["state"] == "generating"
            assert client.post(path, json=request.model_dump()).status_code == 202
            assert len(calls) == 1
        finally:
            release.set()
        wait_for(lambda: client.get(path).json()["state"] == "succeeded")
        assert client.get(path+"/image").content == image_bytes("PNG")


@pytest.mark.parametrize("status", ["failed", "cancelled", "incomplete"])
def test_terminal_provider_failures_are_displayable_instead_of_polling_forever(tmp_path, monkeypatch, status):
    monkeypatch.setenv("OPENAI_API_KEY", "test-private-key")
    monkeypatch.setattr(renditions, "call_response", lambda *args: {"id": "resp_room", "status": status, "error": {"message": "Provider detail"}})
    service = Renditions(tmp_path)
    directory = service.directory(tmp_path, 1, "a"*64)
    service.prepare(directory, body(), "capture", 1); service.generate(directory)
    assert service.status(directory)["state"] == "failed"
    assert "Provider detail" in service.status(directory)["error"]


def test_provider_rejection_reports_the_reason_without_credentials(monkeypatch):
    def rejected(*args, **kwargs):
        raise urllib.error.HTTPError("https://api.openai.com/v1/responses", 400, "Bad request", {},
            io.BytesIO(b'{"error":{"message":"Unsupported field for private-key"}}'))
    monkeypatch.setattr(renditions.urllib.request, "urlopen", rejected)
    with pytest.raises(RuntimeError, match="Unsupported field") as error:
        renditions.call_response({}, "private-key")
    assert "private-key" not in str(error.value)
