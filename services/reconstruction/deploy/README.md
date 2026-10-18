# Google Cloud reconstruction server

This deployment moves processing off the Mac onto one Ubuntu 24.04 x86_64 Compute Engine VM. It keeps the current FastAPI/SQLite/file worker, adds systemd restart recovery, puts Caddy HTTPS in front, and uses a persistent boot disk. The iPhone sends saved scans directly to the remote HTTPS endpoint after the app configuration changes. Existing captures on the phone remain reusable; no scan files are transferred by the deployment script itself.

## Required account step

Sign in through Google's browser flow in your own terminal:

```sh
gcloud auth login
```

Choose an existing Google Cloud **project ID** with billing enabled. The deploying account needs permission to enable Compute/IAP APIs, create the resources below and use IAP SSH/instance SSH metadata. Do not paste access tokens, service-account keys or passwords into chat. No cloud login or billing-enabled project was configured when this deployment was prepared.

## Deploy

From the repository root:

```sh
python3 services/reconstruction/deploy/deploy_gce.py --project YOUR_PROJECT_ID --print-plan
python3 services/reconstruction/deploy/deploy_gce.py --project YOUR_PROJECT_ID
```

The script uses a dedicated VPC/subnet, reserved external IPv4, a single `e2-standard-4` instance (4 vCPU / 16GB), and a 50GB balanced persistent disk in `us-central1-a`. Public ingress is limited to HTTP/HTTPS for Caddy; SSH is allowed only from Google's IAP tunnel range. The worker listens on localhost:8008. The VM has no Google service account or API scopes. All scan/job/result data lives under `/var/lib/respace-reconstruction` with a non-login worker user and restrictive permissions. Only one processing subprocess runs at a time; jobs have no application processing deadline.

Compute list pricing in Iowa was about **$0.134/hour**, approximately **$98/month** if left running continuously, plus disk, external IP and network charges. Verify current [Google pricing](https://cloud.google.com/products/compute/pricing/general-purpose). Creating the VM starts billing; a stopped VM still incurs retained disk and reserved-address charges.

Without `--domain`, the HTTPS name is `PUBLIC_IP.sslip.io`, using that public wildcard DNS service and Caddy's automatic public certificate provisioning. A custom `--domain` must already point to the reserved IP. The source archive has an explicit allowlist and excludes local captures, existing credentials, environments and tool installations. A separate random development bearer token is transferred over IAP SSH, installed as a root-readable environment file and retained locally only in ignored `deploy/.state/`. It is never put in instance metadata or printed.

The script waits for an authenticated **HTTPS** health check before updating `Configuration/Local.xcconfig` with the new origin/token. If provisioning or certificate readiness fails, the app remains on its previous configuration and any created cloud resources remain for inspection/retry. Re-running uses resources with this deployment's exact description; it refuses same-named resources that belong to something else.

Before deploying this Astra branch, add `OPENAI_API_KEY` to the ignored `deploy/.state/<deployment-hash>/server.env` for the existing deployment. This private file is transferred separately over IAP SSH and installed as `/etc/respace-reconstruction.env`; its values are never included in the source archive or app configuration. New deployments create that file on their first run; configure the key and rerun, or edit the server environment directly and restart the worker. Optional settings are `RESPACE_SCENE_GENERATOR=astra` (default) and `RESPACE_ASTRA_IMAGE_LIMIT=32`. Redeployment replaces the server environment with the retained state file, so keep the private state file's settings current. Missing keys retain a partial measured result that can be retried after configuration.

After successful deployment, rebuild the app on the iPhone, reopen the saved room, and tap **Generate AI model**. The phone must upload the retained scan to the new server. Its previous Mac upload is not a completed cloud job. Selected photos, LiDAR samples and mesh geometry are then sent from the worker to OpenAI; see the [Astra configuration and behavior](../README.md#astra-configuration-and-behavior) for budgets, validation, caching and inference limits.

## Operations

The deployment prints the exact stop command. For the default name/zone:

```sh
gcloud compute ssh respace-reconstruction --zone us-central1-a --project YOUR_PROJECT_ID --tunnel-through-iap --command 'sudo journalctl -u respace-reconstruction -n 80 --no-pager'
gcloud compute ssh respace-reconstruction --zone us-central1-a --project YOUR_PROJECT_ID --tunnel-through-iap --command 'sudo journalctl -u caddy -n 50 --no-pager'
gcloud compute instances stop respace-reconstruction --zone us-central1-a --project YOUR_PROJECT_ID
```

Restarting the instance preserves the reserved IP and boot-disk data. Updating the worker stops its unit and resumes retained running jobs at next startup. The worker uses conservative memory limits; a scan exceeding RAM can fail while preserving its original input and checkpoints. Development bearer authentication is sufficient for this private prototype, not a production multi-user identity/authorization system.

Deleting the VM/disk removes retained scans and results. Releasing the reserved IP changes the endpoint. The deployment does not automate deletion or silently modify existing project IAM policies. Remove the dedicated instance/disk/address/firewall/subnet/network explicitly when finished if no longer needed, after preserving any results you want.

## Verification status

Deployed October 17, 2026 to project `respace-512003`, instance `respace-reconstruction`, zone `us-central1-a`. The endpoint is `https://35.184.65.54.sslip.io`; its token remains in ignored local configuration/state and the root-readable server environment.

Verified public HTTPS, authenticated health (200), unauthorized rejection (401), and the actual Swift client's synthetic scan upload → Open3D/OpenMVS reconstruction → checksum-verified result download (37.5 seconds, zero test failures). The updated arm64 iOS simulator app builds successfully. Both services are active and enabled at startup. The completed job remained available after restarting the worker. Local service/deployment tests passed: 14 passed, one opt-in live test skipped; the Swift remote integration ran separately. Real-room quality and a physical iPhone upload still require device acceptance; the synthetic fixture does not establish those.

The Astra update was deployed October 17, 2026 after configuring the server-side API key. A real Astra access check succeeded, and the actual Swift client completed synthetic scan upload → Open3D/OpenMVS → Astra → checksum-verified `astra.obj` download in 45.17 seconds. The physical iPhone target also builds with signing disabled. The synthetic scene required no inferred additions; this verifies integration rather than real-room generation quality.

That first live generation exposed unused vertices retained by mesh decimation: 20,667 vertices accompanied just 1,200 triangles, inflating the request to 321,204 input tokens. The deployed fix now sends only the 1,309 referenced vertices, reducing the saved test's geometry/calibration JSON from 513,996 to 67,004 bytes (87%). A pre-request 256 KiB text guard and regression tests protect against recurrence. The fix was verified against saved evidence and deployed without another paid generation call. Its per-room API cost must be measured on subsequent scans; the text reduction is not a measured reduction in total billable tokens.
