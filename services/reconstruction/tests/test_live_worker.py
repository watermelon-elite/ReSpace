"""Opt-in end-to-end check against a running local service, including OpenMVS."""
import os
import time
from pathlib import Path

import httpx
import pytest


@pytest.mark.skipif(not os.environ.get("RESPACE_TEST_LIVE"), reason="requires running local service")
def test_live_worker(capture):
    manifest, payloads = capture
    settings = dict(line.split("=", 1) for line in (Path(__file__).parents[1] / ".env").read_text().splitlines() if "=" in line)
    origin = os.environ.get("RESPACE_TEST_ORIGIN", "http://127.0.0.1:8008")
    with httpx.Client(base_url=origin, headers={"Authorization": "Bearer " + settings["RESPACE_RECONSTRUCTION_TOKEN"]}, timeout=30, trust_env=False) as client:
        assert client.get("/health").status_code == 200
        path = "/v1/reconstructions/" + manifest.capture_id
        r = client.put(path, json=manifest.model_dump())
        r.raise_for_status()
        missing = set(r.json()["missing_artifact_ids"])
        for a in manifest.artifacts:
            if a.id in missing:
                client.put(path + "/artifacts/" + a.id, content=payloads[a.filename]).raise_for_status()
        job = client.post(path + "/run").json()
        deadline = time.monotonic() + 120
        while job["state"] in ("queued", "running") and time.monotonic() < deadline:
            time.sleep(.5)
            job = client.get(path).json()
        assert job["state"] == "succeeded", job
        result = job["result"]
        assert result["model_filename"] == "photo.obj"
        for asset in result["assets"]:
            import hashlib
            response = client.get(path + f'/results/{result["revision"]}/assets/{asset["filename"]}')
            response.raise_for_status()
            assert len(response.content) == asset["byte_length"]
            assert hashlib.sha256(response.content).hexdigest() == asset["sha256"]
