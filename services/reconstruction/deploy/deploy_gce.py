#!/usr/bin/env python3
"""Deploy the existing worker to a single persistent, HTTPS-fronted Google VM.

Credentials come from gcloud's user login. No credentials or scan data are packed
into the source archive. The prototype's bearer token is copied separately over
IAP SSH and is never printed or placed in cloud instance metadata.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.request

SERVICE = Path(__file__).resolve().parents[1]
REPO = SERVICE.parents[1]
DESCRIPTION = "ReSpace reconstruction deployment (managed)"


def run(project, args, *, capture=False):
    return subprocess.run(["gcloud", "--project", project, "--quiet", *args], check=True,
        text=True, stdout=subprocess.PIPE if capture else None)


def describe(project, args):
    result = subprocess.run(["gcloud", "--project", project, "--quiet", *args, "--format=json"],
        text=True, capture_output=True)
    if result.returncode == 0:
        return json.loads(result.stdout)
    if re.search(r"was not found|does not exist|NOT_FOUND", result.stderr, re.IGNORECASE):
        return None
    raise RuntimeError(result.stderr.strip())


def ensure(project, query, creation):
    existing = describe(project, query)
    if existing is not None:
        if existing.get("description") != DESCRIPTION:
            raise RuntimeError("A same-named cloud resource is not owned by this deployment; choose another --name")
        return existing
    run(project, creation + ["--description", DESCRIPTION])
    return describe(project, query)


def build_archive(destination):
    paths = ["respace_reconstruction", "pyproject.toml", "requirements.lock", "setup-segmentation.sh", "setup-detection.sh", "deploy/bootstrap-linux.sh", "deploy/respace-reconstruction.service"]
    with tarfile.open(destination, "w:gz") as archive:
        for name in paths:
            archive.add(SERVICE / name, arcname=name,
                filter=lambda item: None if "__pycache__" in Path(item.name).parts else item)


def configure_app(origin, token):
    config = REPO / "Configuration" / "Local.xcconfig"
    text = config.read_text() if config.exists() else ""
    values = {"RESPACE_LOCAL_CAPTURE": "YES", "RESPACE_RECONSTRUCTION_URL": origin.replace("https://", "https:/$()/", 1),
        "RESPACE_RECONSTRUCTION_TOKEN": token}
    for name, value in values.items():
        pattern = re.compile(r"^" + name + r"\s*=.*$", re.MULTILINE)
        line = name + " = " + value
        text = pattern.sub(lambda _: line, text) if pattern.search(text) else text.rstrip() + "\n" + line + "\n"
    config.write_text(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="Existing billing-enabled Google Cloud project ID")
    parser.add_argument("--zone", default="us-central1-a")
    parser.add_argument("--name", default="respace-reconstruction")
    parser.add_argument("--domain", help="Optional DNS name already pointed at the reserved server IP; defaults to IP.sslip.io")
    parser.add_argument("--print-plan", action="store_true", help="Show resources without making cloud calls")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", args.project):
        parser.error("Provide a Google Cloud project ID, not its display name")
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,34}", args.name) or not re.fullmatch(r"[a-z]+-[a-z]+[0-9]-[a-z]", args.zone):
        parser.error("Invalid instance name or zone")
    if args.domain and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]+\.[A-Za-z]{2,}", args.domain):
        parser.error("Invalid domain")
    region = args.zone.rsplit("-", 1)[0]
    print(f"Project: {args.project}; zone: {args.zone}", flush=True)
    print("Plan: one e2-standard-4 VM (4 vCPU/16GB), 50GB balanced persistent boot disk, reserved IPv4, dedicated VPC/subnet, HTTPS on 80/443, IAP-only SSH. No scan files are transferred by deployment.", flush=True)
    if args.print_plan:
        return
    active = run(args.project, ["auth", "list", "--filter=status:ACTIVE", "--format=value(account)"], capture=True).stdout.strip()
    if not active:
        raise RuntimeError("Run gcloud auth login first, then deploy with your billing-enabled project ID")
    billing = describe(args.project, ["billing", "projects", "describe", args.project])
    if not billing or not billing.get("billingEnabled"):
        raise RuntimeError("Enable billing for this existing project in Google Cloud before deployment")
    run(args.project, ["services", "enable", "compute.googleapis.com", "iap.googleapis.com"])
    name = args.name
    network, subnet = name + "-net", name + "-subnet"
    ensure(args.project, ["compute", "networks", "describe", network],
        ["compute", "networks", "create", network, "--subnet-mode=custom"])
    ensure(args.project, ["compute", "networks", "subnets", "describe", subnet, "--region", region],
        ["compute", "networks", "subnets", "create", subnet, "--region", region, "--network", network, "--range=10.85.0.0/24"])
    ensure(args.project, ["compute", "firewall-rules", "describe", name + "-web"],
        ["compute", "firewall-rules", "create", name + "-web", "--network", network, "--allow=tcp:80,tcp:443", "--source-ranges=0.0.0.0/0", "--target-tags", name])
    ensure(args.project, ["compute", "firewall-rules", "describe", name + "-iap-ssh"],
        ["compute", "firewall-rules", "create", name + "-iap-ssh", "--network", network, "--allow=tcp:22", "--source-ranges=35.235.240.0/20", "--target-tags", name])
    address = ensure(args.project, ["compute", "addresses", "describe", name + "-ip", "--region", region],
        ["compute", "addresses", "create", name + "-ip", "--region", region])
    ip = address["address"]
    expected_user = f"/zones/{args.zone}/instances/{name}"
    if any(not user.endswith(expected_user) for user in address.get("users", [])):
        raise RuntimeError("Reserved address is attached to another instance; refusing to reassign it")
    instance = ensure(args.project, ["compute", "instances", "describe", name, "--zone", args.zone],
        ["compute", "instances", "create", name, "--zone", args.zone, "--machine-type=e2-standard-4",
         "--image-family=ubuntu-2404-lts-amd64", "--image-project=ubuntu-os-cloud", "--boot-disk-size=50GB", "--boot-disk-type=pd-balanced",
         "--subnet", subnet, "--address", ip, "--tags", name, "--no-service-account", "--no-scopes",
         "--metadata=block-project-ssh-keys=TRUE", "--labels=managed_by=respace,respace_component=reconstruction"])
    if not instance["machineType"].endswith("/e2-standard-4"):
        raise RuntimeError("Existing instance has a different machine type; refusing to change it")
    if instance["status"] == "TERMINATED":
        run(args.project, ["compute", "instances", "start", name, "--zone", args.zone])
    domain = args.domain or ip + ".sslip.io"
    origin = "https://" + domain
    state = SERVICE / "deploy" / ".state" / hashlib.sha256(f"{args.project}/{args.zone}/{name}".encode()).hexdigest()
    state.mkdir(parents=True, exist_ok=True)
    os.chmod(state, 0o700)
    env_file = state / "server.env"
    if env_file.exists():
        settings = dict(line.split("=", 1) for line in env_file.read_text().splitlines() if "=" in line)
        token = settings["RESPACE_RECONSTRUCTION_TOKEN"]
    else:
        token = secrets.token_hex(32)
        env_file.write_text("RESPACE_RECONSTRUCTION_TOKEN=" + token + "\nRESPACE_RECONSTRUCTION_DATA=/var/lib/respace-reconstruction\nRESPACE_OPENMVS_BIN=/opt/respace-reconstruction/openmvs\n")
    os.chmod(env_file, 0o600)
    remote = "/tmp/respace-deploy-" + secrets.token_hex(8)
    ssh_args = ["compute", "ssh", name, "--zone", args.zone, "--tunnel-through-iap"]
    # A new VM may still be bringing up SSH/IAP. Only this readiness phase is bounded.
    for attempt in range(30):
        result = subprocess.run(["gcloud", "--project", args.project, "--quiet", *ssh_args, "--command", "true"], text=True, capture_output=True)
        if result.returncode == 0:
            break
        time.sleep(5)
    else:
        raise RuntimeError("SSH through IAP is not ready. Verify project IAP tunnel access/Compute metadata permissions, then rerun; created resources are retained")
    run(args.project, ssh_args + ["--command", shlex.join(["install", "-d", "-m", "0700", remote])])
    with tempfile.TemporaryDirectory(prefix="respace-deploy-") as temporary:
        archive = Path(temporary) / "source.tar.gz"
        build_archive(archive)
        run(args.project, ["compute", "scp", "--zone", args.zone, "--tunnel-through-iap", str(archive), str(env_file), name + ":" + remote + "/"])
    command = " && ".join([
        shlex.join(["tar", "xzf", remote + "/source.tar.gz", "-C", remote]),
        shlex.join(["sudo", "bash", remote + "/deploy/bootstrap-linux.sh", remote, domain, remote + "/server.env"]),
        shlex.join(["rm", "-rf", "--", remote]),
    ])
    run(args.project, ssh_args + ["--command", command])
    request = urllib.request.Request(origin + "/health", headers={"Authorization": "Bearer " + token})
    for attempt in range(60):
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                if json.load(response).get("status") == "ok":
                    break
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(5)
    else:
        raise RuntimeError("Server installed but HTTPS is not ready. Check DNS, Caddy logs and ports 80/443. The app configuration has not changed")
    configure_app(origin, token)
    (state / "deployment.json").write_text(json.dumps({"project": args.project, "zone": args.zone, "instance": name, "origin": origin}, indent=2))
    print("Healthy reconstruction endpoint: " + origin, flush=True)
    print("Local.xcconfig updated. Rebuild the iPhone app, reopen the saved scan and choose Create walkthrough.", flush=True)
    print("Stop compute charges when finished: " + shlex.join(["gcloud", "compute", "instances", "stop", name, "--zone", args.zone, "--project", args.project]), flush=True)
    print("Stopped instances still incur disk and reserved-address charges until those resources are deleted.", flush=True)


if __name__ == "__main__":
    main()
