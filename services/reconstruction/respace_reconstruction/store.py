import hashlib
import json
import os
import sqlite3
import threading
import uuid
from pathlib import Path

from .models import Manifest, Metadata


def atomic_json(path: Path, data):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as f:
        json.dump(data, f, allow_nan=False, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    temporary.replace(path)


def digest(path: Path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def generation_working_directory(folder: Path, generation_id=None):
    if generation_id is None:
        return folder/"work"
    return folder/"work"/"runs"/str(uuid.UUID(generation_id))


class Store:
    """SQLite owns job state; immutable files own inputs and versioned results."""
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = root / "jobs.sqlite3"
        with self.connect() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, manifest TEXT NOT NULL, state TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0, stage TEXT NOT NULL DEFAULT 'uploading', error TEXT, result TEXT)")
            if "generation_id" not in {row[1] for row in c.execute("PRAGMA table_info(jobs)")}:
                c.execute("ALTER TABLE jobs ADD COLUMN generation_id TEXT")
            c.execute("CREATE TABLE IF NOT EXISTS generation_requests (job_id TEXT NOT NULL, request_id TEXT NOT NULL, PRIMARY KEY(job_id, request_id))")

    def connect(self):
        c = sqlite3.connect(self.db, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    def folder(self, job_id):
        # Distinct IDs must remain distinct on the Mac's case-insensitive filesystem.
        return self.root / hashlib.sha256(job_id.encode()).hexdigest()

    def create(self, manifest: Manifest):
        encoded = manifest.model_dump_json()
        with self.lock, self.connect() as c:
            row = c.execute("SELECT manifest FROM jobs WHERE id=?", (manifest.capture_id,)).fetchone()
            if row and row[0] != encoded:
                raise ValueError("This capture ID already has different inputs")
            if not row:
                folder = self.folder(manifest.capture_id)
                (folder / "inputs").mkdir(parents=True, exist_ok=True)
                atomic_json(folder / "manifest.json", manifest.model_dump())
                c.execute("INSERT INTO jobs(id,manifest,state) VALUES(?,?,'uploading')", (manifest.capture_id, encoded))
        return self.get(manifest.capture_id)

    def get(self, job_id):
        with self.connect() as c:
            row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        data = dict(row)
        manifest = Manifest.model_validate_json(data.pop("manifest"))
        data["result"] = json.loads(data["result"]) if data["result"] else None
        data["schema_version"] = 1
        data["missing_artifact_ids"] = [a.id for a in manifest.artifacts if not (self.folder(job_id) / "inputs" / a.filename).is_file()]
        return data

    def manifest(self, job_id):
        self.get(job_id)
        return Manifest.model_validate_json((self.folder(job_id) / "manifest.json").read_text())

    def queue(self, job_id, retry=False, restart_id=None):
        with self.lock, self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            job = self.get(job_id)
            if restart_id is not None:
                restart_id = str(uuid.UUID(restart_id))
                if c.execute("SELECT 1 FROM generation_requests WHERE job_id=? AND request_id=?", (job_id, restart_id)).fetchone():
                    return job
                if job["state"] in ("queued", "running"):
                    raise ValueError("Wait for the current generation to finish before starting from scratch")
            else:
                if job["state"] in ("queued", "running") or (job["state"] == "succeeded" and not retry):
                    return job
                if job["state"] in ("failed", "partially_processed") and not retry:
                    return job
            if job["missing_artifact_ids"]:
                raise ValueError("Upload all artifacts before starting")
            # Revalidate immutable bytes before each execution, including a retry.
            for a in self.manifest(job_id).artifacts:
                p = self.folder(job_id) / "inputs" / a.filename
                if p.stat().st_size != a.byte_length or digest(p) != a.sha256:
                    raise ValueError("Retained input failed integrity verification")
            manifest = self.manifest(job_id)
            for frame in manifest.frames:
                metadata = next(a for a in frame.artifacts if a.type == "metadata")
                stored = Metadata.model_validate_json((self.folder(job_id) / "inputs" / metadata.filename).read_text())
                if stored != frame.metadata:
                    raise ValueError("Frame metadata artifact disagrees with manifest calibration")
            if restart_id is not None:
                c.execute("INSERT INTO generation_requests(job_id,request_id) VALUES(?,?)", (job_id, restart_id))
                c.execute("UPDATE jobs SET generation_id=? WHERE id=?", (restart_id, job_id))
            elif retry:
                # Only an explicit retry may repeat an API request interrupted by
                # a crash. Automatic queue recovery leaves this marker intact.
                working = generation_working_directory(self.folder(job_id), job.get("generation_id"))
                (working / "astra-inflight.json").unlink(missing_ok=True)
                rejected = working / "astra-room-rejected.json"
                if rejected.exists():
                    (rejected.parent / "astra-room-response.json").unlink(missing_ok=True)
                    rejected.unlink()
            c.execute("UPDATE jobs SET state='queued',stage='queued',error=NULL WHERE id=?", (job_id,))
        return self.get(job_id)

    def recover(self):
        with self.connect() as c:
            c.execute("UPDATE jobs SET state='queued',stage='recovering' WHERE state='running'")

    def claim(self):
        with self.lock, self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT id FROM jobs WHERE state='queued' ORDER BY rowid LIMIT 1").fetchone()
            if row:
                c.execute("UPDATE jobs SET state='running',stage='starting',revision=revision+1 WHERE id=?", (row[0],))
        return self.get(row[0]) if row else None

    def finish(self, job_id, state, result=None, error=None):
        with self.connect() as c:
            c.execute("UPDATE jobs SET state=?,stage='finished',result=COALESCE(?,result),error=? WHERE id=?", (state, json.dumps(result, allow_nan=False) if result else None, error, job_id))

    def progress(self, job_id, stage):
        with self.connect() as c:
            c.execute("UPDATE jobs SET stage=? WHERE id=?", (stage, job_id))
