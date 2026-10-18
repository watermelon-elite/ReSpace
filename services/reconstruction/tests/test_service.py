import json

from fastapi.testclient import TestClient

from respace_reconstruction.app import create_app
from respace_reconstruction.store import Store

TOKEN = "test-reconstruction-token"


def test_upload_integrity_identity_queue_and_restart(tmp_path, capture):
    manifest, payloads = capture
    app = create_app(tmp_path, TOKEN, start_worker=False)
    path = "/v1/reconstructions/" + manifest.capture_id
    with TestClient(app) as client:
        assert client.get("/health").status_code == 401
        client.headers["Authorization"] = "Bearer " + TOKEN
        created = client.put(path, json=manifest.model_dump())
        assert created.status_code == 200
        assert len(created.json()["missing_artifact_ids"]) == len(payloads)
        assert client.post(path + "/run").status_code == 409
        a = manifest.artifacts[0]
        assert client.put(path + "/artifacts/" + a.id, content=b"bad").status_code == 422
        assert not (app.state.store.folder(manifest.capture_id) / "inputs" / a.filename).exists()
        for a in manifest.artifacts:
            assert client.put(path + "/artifacts/" + a.id, content=payloads[a.filename]).status_code == 200
        assert client.put(path, json=manifest.model_dump()).json()["missing_artifact_ids"] == []
        mutated = manifest.model_dump()
        mutated["frames"][0]["metadata"]["timestamp"] += 1
        assert client.put(path, json=mutated).status_code == 409
        assert client.post(path + "/run").json()["state"] == "queued"
        assert client.post(path + "/run").json()["revision"] == 0
        store = app.state.store
        assert store.claim()["revision"] == 1
        assert store.claim() is None
        marker = store.folder(manifest.capture_id) / "work/astra-inflight.json"
        marker.parent.mkdir()
        marker.write_text('{"fingerprint":"interrupted"}')
        reopened = Store(tmp_path)
        reopened.recover()
        assert reopened.get(manifest.capture_id)["state"] == "queued"
        assert marker.exists()  # Recovery must not authorize another paid request.
        assert reopened.claim()["revision"] == 2
        reopened.finish(manifest.capture_id, "partially_processed", {"revision": 2, "assets": []}, "photo failed")
        assert client.post(path + "/run").json()["state"] == "partially_processed"
        assert client.post(path + "/retry").json()["state"] == "queued"
        assert not marker.exists()
        reopened.claim()
        reopened.finish(manifest.capture_id, "failed", error="Retry interrupted")
        assert reopened.get(manifest.capture_id)["result"]["revision"] == 2
        reopened.finish(manifest.capture_id, "succeeded", {"revision": 3, "assets": []})
        assert client.post(path + "/run").json()["state"] == "succeeded"
        # Explicit retry permits upgrading a completed measured reconstruction to Astra.
        assert client.post(path + "/retry").json()["state"] == "queued"
        assert client.post(path + "/retry").json()["state"] == "queued"


def test_reject_bad_paths_calibration_and_oversized_manifest(tmp_path, capture):
    manifest, _ = capture
    with TestClient(create_app(tmp_path, TOKEN, start_worker=False)) as client:
        client.headers["Authorization"] = "Bearer " + TOKEN
        path = "/v1/reconstructions/" + manifest.capture_id
        bad = manifest.model_dump()
        bad["scene_mesh"]["filename"] = "../outside"
        assert client.put(path, json=bad).status_code == 422
        bad = manifest.model_dump()
        bad["frames"][0]["metadata"]["camera_to_scan_transform"][0] = 2
        assert client.put(path, json=bad).status_code == 422
        assert client.put(path, content=b" " * (8*1024**2+1)).status_code == 413


def test_assets_are_limited_to_committed_revision(tmp_path, capture):
    manifest, _ = capture
    app = create_app(tmp_path, TOKEN, start_worker=False)
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer " + TOKEN
        path = "/v1/reconstructions/" + manifest.capture_id
        client.put(path, json=manifest.model_dump())
        assert client.get(path + "/results/1/assets/manifest.json").status_code == 404
        app.state.store.finish(manifest.capture_id, "succeeded", {"revision": 1, "assets": [{"filename": "model.obj"}, {"filename": "model.usdz"}]})
        output = app.state.store.folder(manifest.capture_id) / "results" / "1"
        output.mkdir(parents=True)
        (output / "model.obj").write_text("mesh")
        (output / "model.usdz").write_bytes(b"packaged-model")
        package = client.get(path + "/results/1/assets/model.usdz")
        assert package.content == b"packaged-model"
        assert package.headers["content-type"] == "model/vnd.usdz+zip"
        assert client.get(path + "/results/1/assets/model.obj").text == "mesh"
        assert client.get(path + "/results/2/assets/model.obj").status_code == 404
        assert client.get(path + "/results/1/assets/worker.log").status_code == 404


def test_failed_v2_retry_cannot_expose_retained_scene_assets(tmp_path,capture):
    manifest,payloads=capture
    app=create_app(tmp_path,TOKEN,start_worker=False)
    with TestClient(app) as client:
        client.headers["Authorization"]="Bearer "+TOKEN
        store=app.state.store;store.create(manifest)
        for name,data in payloads.items():(store.folder(manifest.capture_id)/"inputs"/name).write_bytes(data)
        store.queue(manifest.capture_id);store.claim()
        output=store.folder(manifest.capture_id)/"results/1";output.mkdir(parents=True)
        (output/"model.obj").write_text("completed mesh")
        result={"revision":1,"status":"succeeded","scene_schema_version":2,"scene_filename":"scene.json","assets":[{"filename":"model.obj"}]}
        store.finish(manifest.capture_id,"succeeded",result)
        path="/v1/reconstructions/"+manifest.capture_id+"/results/1/assets/model.obj"
        assert client.get(path).status_code==200
        store.finish(manifest.capture_id,"failed",error="retry failed")
        assert client.get(path).status_code==404


def test_fresh_generation_is_idempotent_isolated_and_preserves_inputs_and_results(tmp_path, capture, monkeypatch):
    import uuid
    monkeypatch.setenv("RESPACE_PIPELINE", "astra")
    manifest, payloads = capture
    app = create_app(tmp_path, TOKEN, start_worker=False)
    store = app.state.store
    store.create(manifest)
    folder = store.folder(manifest.capture_id)
    for name, data in payloads.items():
        (folder/"inputs"/name).write_bytes(data)
    store.queue(manifest.capture_id); store.claim()
    original = {"revision": 1, "assets": []}
    store.finish(manifest.capture_id, "succeeded", original)
    (folder/"work").mkdir()
    (folder/"work/astra-budget-v3.json").write_text('{"reserved":"old unknown outcome"}')
    path = "/v1/reconstructions/"+manifest.capture_id
    request_id = str(uuid.uuid4())
    with TestClient(app) as client:
        assert client.post(path+"/restart", json={"request_id": request_id}).status_code == 401
        client.headers["Authorization"] = "Bearer "+TOKEN
        assert client.post(path+"/restart", json={"request_id":"../../bad"}).status_code == 422
        queued = client.post(path+"/restart", json={"request_id":request_id}).json()
        assert queued["state"] == "queued" and queued["generation_id"] == request_id
        assert queued["result"] == original
        assert client.post(path+"/restart", json={"request_id":request_id}).json() == queued
        assert client.post(path+"/restart", json={"request_id":str(uuid.uuid4())}).status_code == 409
        claimed = store.claim()
        assert claimed["revision"] == 2 and claimed["generation_id"] == request_id
        # Recovery and normal Retry resume the same run; only a new restart ID resets it.
        reopened = Store(tmp_path); reopened.recover()
        assert reopened.claim()["generation_id"] == request_id
        reopened.finish(manifest.capture_id, "failed", error="test failure")
        assert client.post(path+"/restart", json={"request_id":request_id}).json()["state"] == "failed"
        assert client.post(path+"/retry").json()["generation_id"] == request_id
        reopened.claim(); reopened.finish(manifest.capture_id, "failed", error="test failure")
        next_id = str(uuid.uuid4())
        fresh = client.post(path+"/restart", json={"request_id":next_id}).json()
        assert fresh["generation_id"] == next_id and fresh["result"] == original
    assert (folder/"work/astra-budget-v3.json").read_text() == '{"reserved":"old unknown outcome"}'
    assert all((folder/"inputs"/name).read_bytes() == data for name, data in payloads.items())


def test_fresh_generation_requires_uploaded_inputs(tmp_path, capture, monkeypatch):
    import uuid
    monkeypatch.setenv("RESPACE_PIPELINE", "astra")
    manifest, _ = capture
    app = create_app(tmp_path, TOKEN, start_worker=False)
    app.state.store.create(manifest)
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer "+TOKEN
        response = client.post("/v1/reconstructions/"+manifest.capture_id+"/restart", json={"request_id":str(uuid.uuid4())})
        assert response.status_code == 409
        assert app.state.store.get(manifest.capture_id)["generation_id"] is None


def test_existing_database_upgrade_preserves_jobs_and_results(tmp_path, capture):
    import sqlite3
    manifest, _ = capture
    previous = {"revision": 7, "assets": []}
    with sqlite3.connect(tmp_path/"jobs.sqlite3") as db:
        db.execute("CREATE TABLE jobs (id TEXT PRIMARY KEY, manifest TEXT NOT NULL, state TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0, stage TEXT NOT NULL DEFAULT 'uploading', error TEXT, result TEXT)")
        db.execute("INSERT INTO jobs(id,manifest,state,revision,stage,result) VALUES(?,?,'succeeded',7,'finished',?)",
                   (manifest.capture_id, manifest.model_dump_json(), json.dumps(previous)))
    store = Store(tmp_path)
    job = store.get(manifest.capture_id)
    assert job["generation_id"] is None and job["revision"] == 7 and job["result"] == previous
    assert job["state"] == "succeeded"
    assert Store(tmp_path).get(manifest.capture_id)["result"] == previous
