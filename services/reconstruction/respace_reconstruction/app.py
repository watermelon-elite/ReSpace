import asyncio
from contextlib import asynccontextmanager
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, ValidationError

from .models import Manifest
from .store import Store, digest
from .renditions import Renditions, RenditionRequest


class RestartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: uuid.UUID


class Worker:
    def __init__(self, store):
        self.store = store
        self.stop = threading.Event()
        self.process_lock = threading.Lock()
        self.process = None
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        while not self.stop.is_set():
            job = self.store.claim()
            if not job:
                self.stop.wait(1)
                continue
            folder = self.store.folder(job["id"])
            command = [sys.executable, "-m", "respace_reconstruction.pipeline", "--job", str(folder), "--revision", str(job["revision"])]
            if job.get("generation_id"):
                command.extend(["--generation-id", job["generation_id"]])
            timer=None
            expired=threading.Event()
            try:
                with self.process_lock:
                    if self.stop.is_set():
                        return
                    self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
                    active=self.process
                    def expire(process=active):
                        if process.poll() is None:
                            expired.set()
                            try:os.killpg(process.pid,signal.SIGTERM)
                            except ProcessLookupError:pass
                            def hard_stop():
                                if process.poll() is None:
                                    try:os.killpg(process.pid,signal.SIGKILL)
                                    except ProcessLookupError:pass
                            escalation=threading.Timer(5,hard_stop);escalation.daemon=True;escalation.start()
                    timeout=float(os.environ.get("RESPACE_ROOM_TIMEOUT_SECONDS","3600"))
                    if not 1<=timeout<=86400:raise ValueError("Invalid room timeout")
                    timer=threading.Timer(timeout,expire);timer.daemon=True;timer.start()
                with (folder / "worker.log").open("a") as log:
                    for line in self.process.stdout:
                        log.write(line)
                        log.flush()
                        try:
                            event = json.loads(line)
                            if "stage" in event:
                                self.store.progress(job["id"], event["stage"])
                        except (ValueError, TypeError):
                            pass
                code = self.process.wait()
                timer.cancel()
                self.process = None
                if self.stop.is_set():
                    return  # Restart recovers the running job; never mark it complete.
                completion = folder / "results" / str(job["revision"]) / "completion.json"
                if code or not completion.is_file():
                    if expired.is_set():raise RuntimeError("Processing exceeded its configured time budget. The scan is retained.")
                    failure=folder/"work"/"failure.json"
                    if failure.is_file():
                        info=json.loads(failure.read_text())
                        if info.get("revision")==job["revision"]:
                            prefix="Rescan required: " if info.get("rescan_required") else "Processing unavailable: "
                            raise RuntimeError(prefix+info["message"])
                    raise RuntimeError("Reconstruction worker exited without a usable result; see worker.log")
                result = json.loads(completion.read_text())
                if result.get("scene_schema_version")==2:
                    from .scene import SceneBundle
                    if result["status"]!="succeeded" or result["revision"]!=job["revision"]:
                        raise RuntimeError("Only a completed matching scene revision may be published")
                    bundle=SceneBundle.model_validate_json((completion.parent/result["scene_filename"]).read_text())
                    if not bundle.ready or bundle.capture_id!=job["id"] or bundle.reconstruction_revision!=job["revision"]:
                        raise RuntimeError("Scene identity/readiness validation failed")
                    bundle.validate_files(completion.parent,{a["filename"] for a in result["assets"]})
                    if json.loads((completion.parent/bundle.quality_filename).read_text()).get("ready") is not True:
                        raise RuntimeError("Scene quality validation did not pass")
                for asset in result["assets"]:
                    p = completion.parent / asset["filename"]
                    if p.stat().st_size != asset["byte_length"] or digest(p) != asset["sha256"]:
                        raise RuntimeError("Worker result failed integrity verification")
                self.store.finish(job["id"], result["status"], result, result.get("error"))
            except Exception as exc:
                if not self.stop.is_set():
                    self.store.finish(job["id"], "failed", error=str(exc))
            finally:
                if timer:timer.cancel()
                if self.process and self.process.poll() is None:
                    try:os.killpg(self.process.pid,signal.SIGTERM)
                    except ProcessLookupError:pass
                    try:self.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        try:os.killpg(self.process.pid,signal.SIGKILL)
                        except ProcessLookupError:pass
                        self.process.wait()
                self.process=None

    def close(self):
        with self.process_lock:
            self.stop.set()
            process = self.process
            if process and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        self.thread.join(timeout=10)
        if self.thread.is_alive() and process and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.thread.join(timeout=5)


def create_app(root: Path | None = None, token: str | None = None, start_worker=True):
    root = root or Path(os.environ.get("RESPACE_RECONSTRUCTION_DATA", "./data"))
    secret = token if token is not None else os.environ.get("RESPACE_RECONSTRUCTION_TOKEN", "")
    store = Store(root.resolve())
    renditions = Renditions(store.root)
    locks: dict[str, asyncio.Lock] = {}

    @asynccontextmanager
    async def lifespan(app):
        if len(secret) < 16:
            raise RuntimeError("Set RESPACE_RECONSTRUCTION_TOKEN to a random token of at least 16 characters")
        lock_file = (store.root / "service.lock").open("w")
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock_file.close()
            raise RuntimeError("Run exactly one service process for this data directory")
        store.recover()
        renditions.recover()
        worker = Worker(store) if start_worker else None
        if worker:
            worker.thread.start()
        try:
            yield
        finally:
            renditions.close()
            if worker:
                await asyncio.to_thread(worker.close)
            lock_file.close()

    app = FastAPI(title="ReSpace local reconstruction", version="1", lifespan=lifespan)
    app.state.store = store

    def authorize(request: Request):
        supplied = request.headers.get("authorization", "")
        if not secret or not hmac.compare_digest(supplied, "Bearer " + secret):
            raise HTTPException(401, "Invalid reconstruction token")

    def get(job_id):
        try:
            return store.get(job_id)
        except KeyError:
            raise HTTPException(404, "Unknown reconstruction")

    @app.get("/health", dependencies=[Depends(authorize)])
    def health():
        return {"schema_version": 1, "status": "ok"}

    @app.put("/v1/reconstructions/{job_id}", dependencies=[Depends(authorize)])
    async def create(job_id: str, request: Request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 8 * 1024**2:
                raise HTTPException(413, "Manifest is too large")
        try:
            manifest = Manifest.model_validate_json(bytes(body))
            if manifest.capture_id != job_id:
                raise HTTPException(422, "Capture identity mismatch")
            return store.create(manifest)
        except ValidationError as exc:
            raise HTTPException(422, str(exc))
        except ValueError as exc:
            raise HTTPException(409, str(exc))

    @app.put("/v1/reconstructions/{job_id}/artifacts/{artifact_id}", dependencies=[Depends(authorize)])
    async def upload(job_id: str, artifact_id: str, request: Request):
        async with locks.setdefault(job_id, asyncio.Lock()):
            job = get(job_id)
            manifest = store.manifest(job_id)
            artifact = next((a for a in manifest.artifacts if a.id == artifact_id), None)
            if not artifact:
                raise HTTPException(404, "Unknown artifact")
            destination = store.folder(job_id) / "inputs" / artifact.filename
            if destination.is_file():
                return {"stored": True}  # Committed file is immutable and already verified.
            if job["state"] != "uploading":
                raise HTTPException(409, "Inputs are immutable after submission")
            temporary = destination.with_name("upload-" + str(uuid.uuid4()) + ".tmp")
            size, checksum = 0, hashlib.sha256()
            try:
                with temporary.open("wb") as f:
                    async for chunk in request.stream():
                        size += len(chunk)
                        if size > artifact.byte_length:
                            raise HTTPException(413, "Artifact exceeds declared size")
                        checksum.update(chunk)
                        f.write(chunk)
                    f.flush()
                    os.fsync(f.fileno())
                if size != artifact.byte_length or checksum.hexdigest() != artifact.sha256:
                    raise HTTPException(422, "Artifact size or SHA-256 mismatch")
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
            return {"stored": True}

    @app.get("/v1/reconstructions/{job_id}", dependencies=[Depends(authorize)])
    def status(job_id: str):
        return get(job_id)

    async def enqueue(job_id, retry, restart_id=None):
        async with locks.setdefault(job_id, asyncio.Lock()):
            get(job_id)
            try:
                return await asyncio.to_thread(store.queue, job_id, retry, restart_id)
            except ValueError as exc:
                raise HTTPException(409, str(exc))

    @app.post("/v1/reconstructions/{job_id}/run", dependencies=[Depends(authorize)])
    async def run(job_id: str):
        return await enqueue(job_id, False)

    @app.post("/v1/reconstructions/{job_id}/retry", dependencies=[Depends(authorize)])
    async def retry(job_id: str):
        return await enqueue(job_id, True)

    @app.post("/v1/reconstructions/{job_id}/restart", dependencies=[Depends(authorize)])
    async def restart(job_id: str, body: RestartRequest):
        if os.environ.get("RESPACE_PIPELINE", "astra") != "astra":
            raise HTTPException(409, "Start the direct OpenAI service to generate from scratch")
        return await enqueue(job_id, True, str(body.request_id))

    @app.get("/v1/reconstructions/{job_id}/results/{revision}/assets/{filename}", dependencies=[Depends(authorize)])
    def asset(job_id: str, revision: int, filename: str):
        job = get(job_id)
        result = job.get("result")
        if not result or result["revision"] != revision or filename not in {a["filename"] for a in result["assets"]}:
            raise HTTPException(404, "Unknown result asset")
        if result.get("scene_schema_version")==2 and (job["state"]!="succeeded" or job["revision"]!=revision):
            raise HTTPException(404,"This scene revision is not published")
        return FileResponse(store.folder(job_id) / "results" / str(revision) / filename,
                            media_type="model/vnd.usdz+zip" if filename.endswith(".usdz") else None)

    def rendition_directory(job_id, revision, key):
        get(job_id)
        try:
            directory = renditions.directory(store.folder(job_id), revision, key)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        result = store.folder(job_id)/"results"/str(revision)/"completion.json"
        if not result.is_file() or json.loads(result.read_text()).get("status") != "succeeded":
            raise HTTPException(404, "Unknown completed room revision")
        return directory

    @app.post("/v1/reconstructions/{job_id}/results/{revision}/renditions/{key}", dependencies=[Depends(authorize)], status_code=202)
    async def create_rendition(job_id: str, revision: int, key: str, request: Request):
        directory = rendition_directory(job_id, revision, key)
        encoded = bytearray()
        async for chunk in request.stream():
            encoded.extend(chunk)
            if len(encoded) > 6*1024**2:
                raise HTTPException(413, "Room image request is too large")
        try:
            body = RenditionRequest.model_validate_json(bytes(encoded))
            status, started = renditions.prepare(directory, body, job_id, revision, capture_folder=store.folder(job_id))
        except OSError:
            raise HTTPException(409, "Original scan photos are unavailable. Restore the saved capture inputs before generating a room image.")
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        except RuntimeError as exc:
            raise HTTPException(503, str(exc))
        if started:
            renditions.start(directory)
        return status

    @app.get("/v1/reconstructions/{job_id}/results/{revision}/renditions/{key}", dependencies=[Depends(authorize)])
    def rendition_status(job_id: str, revision: int, key: str):
        try:
            return renditions.status(rendition_directory(job_id, revision, key))
        except FileNotFoundError:
            raise HTTPException(404, "Unknown rendition")

    @app.get("/v1/reconstructions/{job_id}/results/{revision}/renditions/{key}/image", dependencies=[Depends(authorize)])
    def rendition_image(job_id: str, revision: int, key: str):
        directory = rendition_directory(job_id, revision, key)
        try:
            status = renditions.status(directory)
        except FileNotFoundError:
            raise HTTPException(404, "Unknown rendition")
        if status["state"] != "succeeded" or not (directory/"image.png").is_file():
            raise HTTPException(404, "Rendition image is not ready")
        return FileResponse(directory/"image.png", media_type="image/png")

    return app
