# Local reconstruction implementation plan

Current scope update, October 17, 2026: the new [editable walkthrough pipeline](EDITABLE_WALKTHROUGH_PIPELINE.md) is under requirements interview. Accepted updates are permanent single-room scope; actual captured furniture and decor (including posters, paintings and whiteboards) as movable items with fixed room structure; texture-based finish changes; seamless generated completion without visible estimate markers; final-product-only presentation; no lighting requirement; rescan on a broken reconstruction; and a $5-per-room ceiling with a 30-minute processing target. These supersede the earlier geometric-only/completion and preview product assumptions for the new pipeline. The implementation evidence below describes the existing baseline, not implementation of those new requirements.

Approved scope: a visually complete photo-textured room viewer; retain original metric scan and RoomPlan semantics. Geometric patching only; no generative furniture completion. Capture has a hard three-minute minimum. Processing initially ran on the local Mac behind FastAPI; the user subsequently approved Google Cloud hosting, now deployed as described below. No processing deadline.

1. Expand local capture to high-quality 2560px JPEG keyframes, calibrated poses, registered depth/confidence; replace the 40-frame cap with bounded 900-frame / 2GiB retention and low-disk protection. Preserve legacy connected-mode limits. Enforce 180 seconds before Done, show duration and coverage guidance.
2. Add a separate configurable reconstruction client. Stream individual checksum-verified artifacts, commit an immutable manifest, start an idempotent background job, poll persistent state, retain verified derived assets. Keep original captures/measurements intact.
3. Add a lightweight FastAPI service with disk storage, SQLite job queue, a single worker and durable checkpoints. Restart unfinished jobs, support retries, expose progress and useful stage failures. Use authentication for local network access.
4. Implement registered RGB-D Open3D TSDF fusion in ARKit metric coordinates, mild smoothing, bounded planar-hole repair and missing RoomPlan wall/floor cells with explicit patch provenance; preserve identified openings. Refine and texture the mesh with OpenMVS calibrated imagery. Keep the depth result as a usable partial result when photo processing fails.
5. Deliver an OBJ/material/texture viewer asset and quality report. Compare original/derived dimensions using the approved max(5cm, 2%) threshold; flag drift without discarding the result. Report measured-surface displacement separately. Viewing the original remains available and measurements use that original.
6. Verify API upload integrity/idempotency/restart/retry/partial results; run synthetic depth reconstruction, repair/provenance and coordinate checks; run Swift core tests and an iOS simulator build. Document setup, dependency availability, commands and limitations. Real-room visual acceptance requires scans from a LiDAR iPhone.

Routine choices: explicit Improve model action on saved scans; upload sequentially using files; one processing subprocess at a time on the 8GB Mac; resumable immutable jobs; keep data until explicit deletion. Lightweight means no message broker, container orchestrator, separate database server or cloud dependency.

## Implementation evidence

Implemented in `services/reconstruction` and the separate iOS reconstruction client/viewer flow. Dependencies and official OpenMVS arm64 binaries are installed in ignored local directories; service/app local address and token are configured without changing existing room-service settings. The local Mac service runs on port 8008.

Verification: Swift core tests, arm64 iOS simulator build, service tests (including real synthetic TSDF, opening protection, concave floor completion, upload integrity and restart/retry), live HTTP worker job through OpenMVS with asset checksum verification, and Apple Model I/O loading of generated textured OBJ. See service README for reproducible commands and the real-device acceptance checklist. No real-room scan quality or device capture performance is claimed from these checks.

Implementation choices: stable OpenMVS 2.4 lacks the newer ARKit importer, so the worker exports calibrated COLMAP text directly without requiring COLMAP. All depth frames are fused; photo optimization selects up to 240 frames spread over the scan to bound memory. Hole repair uses explicit planar geometry rather than adding a CGAL dependency. Original capture files and semantic RoomPlan data remain separate from versioned processed assets.

## Google Cloud deployment

At the user's request, deployed the existing worker on October 17, 2026 in `respace-512003` on one `e2-standard-4` VM with a 50GB persistent disk, reserved IPv4, Caddy HTTPS and systemd restart recovery. The app's ignored configuration now uses `https://35.184.65.54.sslip.io`. Deployment transferred code and a separate token; existing room captures were not copied. The phone uploads its retained scan when Improve model is selected after rebuilding the app.

Verified HTTPS/authentication, actual Swift synthetic upload/reconstruction/download through Open3D and OpenMVS, retention after a worker restart, and the updated iOS simulator build. The remote integration passed in 37.5 seconds. See `services/reconstruction/deploy/README.md` for deployment and stop commands. Physical-device upload and real-room visual acceptance remain unverified.
