import importlib.util
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest


@pytest.fixture
def deployment():
    script = Path(__file__).parents[1] / "deploy" / "deploy_gce.py"
    spec = importlib.util.spec_from_file_location("respace_deployment", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_bundle_excludes_credentials_captures_and_local_tools(tmp_path, deployment):
    archive = tmp_path / "source.tar.gz"
    deployment.build_archive(archive)
    with tarfile.open(archive) as bundle:
        names = bundle.getnames()
    assert "respace_reconstruction/pipeline.py" in names
    assert "deploy/bootstrap-linux.sh" in names
    assert "deploy/respace-reconstruction.service" in names
    assert not any(part in name.split("/") for name in names for part in (".env", "data", ".state", ".venv", ".tools", "__pycache__"))


def test_cloud_configuration_keeps_other_app_settings(tmp_path, deployment, monkeypatch):
    (tmp_path / "Configuration").mkdir()
    config = tmp_path / "Configuration/Local.xcconfig"
    config.write_text("RESPACE_APP_KEY = existing-test-setting\nRESPACE_RECONSTRUCTION_URL = old\n")
    monkeypatch.setattr(deployment, "REPO", tmp_path)
    deployment.configure_app("https://worker.example.com", "a" * 64)
    text = config.read_text()
    assert "RESPACE_APP_KEY = existing-test-setting" in text
    assert "RESPACE_RECONSTRUCTION_URL = https:/$()/worker.example.com" in text
    assert text.count("RESPACE_RECONSTRUCTION_URL") == 1
    assert "RESPACE_LOCAL_CAPTURE = YES" in text


def test_deployment_plan_runs_without_login_or_creating_resources(deployment):
    result = subprocess.run([sys.executable, deployment.__file__, "--project", "respace-test-project", "--print-plan"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "e2-standard-4" in result.stdout
    assert "No scan files are transferred" in result.stdout
    assert "Healthy reconstruction endpoint" not in result.stdout


def test_permission_error_does_not_get_treated_as_missing_resource(deployment, monkeypatch):
    monkeypatch.setattr(deployment.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 1, "", "PERMISSION_DENIED: resource access denied"))
    with pytest.raises(RuntimeError, match="PERMISSION_DENIED"):
        deployment.describe("respace-test-project", ["compute", "instances", "describe", "worker"])
