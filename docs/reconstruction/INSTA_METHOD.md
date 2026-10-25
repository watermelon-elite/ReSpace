# Wes Bos's Scan to Three.js workflow

Scope: the user's 24 October 2026 instruction on `instaMethod`, limited to
scan-to-model generation. The earlier primitive JSON/API worker is documented separately in
[API_APPROXIMATION.md](API_APPROXIMATION.md). The active native automation is
documented in [the worker README](../../services/reconstruction/README.md).

## Sources and review coverage

- [YouTube implementation walkthrough](https://www.youtube.com/watch?v=JGQCcCzuS88):
  reviewed the full 8:51 English transcript and key visuals at 6:12, 7:05 and 7:25.
  The comparison and texture demonstrations were inspected visually; this is not
  a claim that every video frame was reviewed.
- [Source repository](https://github.com/wesbos/3d-model-anything/tree/31b2dc9da3fb541e501f2f0936e55b32afb70ee8),
  pinned to `31b2dc9da3fb541e501f2f0936e55b32afb70ee8`.
  Read its README, capture/export implementation, complete skill, all four skill
  references, conversion scripts, viewer and runtime. The supplied
  `/Users/kdieguez/Downloads/SKILL.md` matches the pinned skill byte for byte.
- [Vendored skill](../../services/scan-to-threejs/.agents/skills/scan-to-threejs/SKILL.md)
  and [provenance manifest](../../services/scan-to-threejs/UPSTREAM.json).
  Tests verify all 59 copied source files against their Git blob hashes.

Source statements below are confirmed by those materials. ReSpace's adapter,
private-workspace preparation and baseline scaffolding are integration choices;
they are distinguished from the unchanged upstream implementation.

## The actual method

1. **Capture metric evidence, not just photos** (video 3:25–6:27). His iPhone app
   combines RoomPlan, ARKit LiDAR mesh, depth/confidence and many posed photos in
   one session coordinate frame. Preserve the photo's sensor pixels, pose,
   intrinsics and quality metadata. The current source also supports steady,
   coverage-driven photos, manual detail photos, high-resolution stills and
   white-balance control. LiDAR supplies scale and layout; its jagged mesh is a
   measurement/reference layer rather than the finished visual model.
2. **Prepare the evidence using the skill** (6:29–6:57). Detect the export format;
   select the actual session and original room index. Run `bundle_to_room.py`,
   establish floor zero and wall-aligned room coordinates, and apply the same
   transform to mesh, cameras and later modeled geometry. Run `prepare_photos.py`
   once: its upright images use the converted photo-array order, not sorted
   original filenames. `reconstruct_bundle.py` produces a photo-colored LiDAR
   reference for scan/model comparisons. `house_to_rooms.py` handles aligned
   active sessions when whole-house evidence is needed.
3. **Have Codex author detailed Three.js source** (6:29–7:21). Inspect the plan,
   mesh and photos from useful views. Build the shell and then modular areas and
   Objects from measured bounds and visual evidence. RoomPlan boxes establish
   bounds; detailed geometry includes custom profiles, bevels, extrusions, lathed
   surfaces, tubes, upholstery, hardware and contents. The skill defines the
   process; it does not contain a general automatic object-reconstruction model.
4. **Recreate the actual finishes and graphics** (7:22–7:42). Rectify photo crops
   for artwork, labels, screens and other distinctive graphics. Use procedural
   or canvas patterns and suitable PBR maps for wood, fabric and other surfaces,
   matching scale, orientation and repeat. Remove baked shadows/seams when
   preparing repeating material maps. The skill includes a CC0 texture fetcher.
   Place lights from observed fixtures and inspect the full PBR rendering.
5. **Render from the source camera and correct the code** (6:58–7:54). The
   capture page uses each photo's room-space pose, upright field of view and
   aspect. `cmp_photo.sh` produces original/render pairs; orthographic scan/model
   comparisons expose dimensions and placement. Inspect each comparison, fix
   specific discrepancies and repeat, including closeups and translated views.
   Scripts capture and stitch evidence; they do not judge likeness. The author
   sometimes needs human direction to continue. There is no fixed three-attempt
   loop or 20-part Object schema in this method.
6. **Retain the authored scene**. The result is a Three.js room module with its
   own geometry, materials, texture assets and lighting. Build success and visual
   fidelity are separate checks. The source does not establish survey accuracy,
   recover unseen detail or promise identical quality for every captured room.

The current comparison script preserves the whole rendered canvas, including
black pixels. A reference paragraph still mentions cropped margins; the pinned
script's actual behavior takes precedence. Its camera uses the upstream centered
perspective/FOV convention, not full lens distortion or off-center principal-point
calibration. Original calibration remains available for measurement.

## Implementation in this branch

[services/scan-to-threejs/README.md](../../services/scan-to-threejs/README.md)
contains runnable commands. The preparation CLI accepts the upstream session
folder/ZIP or a fresh ReSpace capture that wraps that native bundle. It creates a new
private project with the original skill, helpers, viewer, runtime, source
evidence, upright photos, plan, reference mesh, modular authoring entry point
and a room-specific brief. Source inputs are unchanged. Prepared source,
photos, textures and comparisons are ignored by Git.

The shell supplied by the adapter is a **measured baseline**, with neutral
materials, a labeled 10 cm wall-thickness assumption, authoring fill lighting
and an inferred flat ceiling. It is not a detailed reconstruction. Its
`workflow.json` stays at `stage=awaiting_modeling`, `ready=false`; the agent must
inspect evidence and author/refine the real room. No furniture is copied from
the public demo. Upstream's runtime, skill and helper bytes are preserved; local
build configuration excludes its office-specific playground dependency.

### Fresh capture, implemented 24 October

New local scans use `ReSpace/Capture/Source/SourceCaptureRecorder.swift`, rather
than the earlier timer/movement sampler or its adapter. They write
`house-capture/5` directly under the app-managed capture directory. Passing that
directory to preparation selects the native child bundle without translating any
photos, poses or camera metadata. Shared ZIPs contain the native bundle itself.
A whole-house root still uses the upstream house importer; this app change is
one fresh Room/session rather than multi-house continuation/relocalization.

The source coverage engine, camera control and adaptive budget/quality code are
byte-identical to the pinned revision. [Capture provenance](../../services/scan-to-threejs/UPSTREAM_CAPTURE.json)
identifies the ported controller/view/recording sections and integration changes.
The implementation keeps:

- A shared ARSession with headless RoomPlan, classified LiDAR mesh and sceneDepth;
  configuration upgrades use no tracking reset and leave RoomPlan's delegate alone.
- Raw `CapturedRoomData` archive attempted before RoomBuilder, the upstream `.beautifyObjects`
  layout pass, optional parametric/detail USDZ previews and independent measured
  LiDAR. RoomPlan's beautified bounds are evidence, not the final Object geometry.
  Like upstream, an encoding rejection of the opaque raw recovery archive does
  not skip RoomBuilder: record `rawRoomDataError`, omit the absent `data` reference,
  and continue with the original in-memory capture. Disk-write failures remain fatal.
  If RoomBuilder fails, the capture is still retained/shareable with an explicit
  layout warning; authoring preparation requests layout recovery rather than
  inventing room geometry. Missing mesh can be reconstructed from recorded depth.
- Coverage-gain/novelty admission, exposure/pose-based blur estimates, copied
  sharpest-frame candidates and the original high-resolution still selection.
- Sensor JPEGs up to 3024 px, quality 0.85, EXIF 6; original 3×3 intrinsics and
  camera-to-session matrices. Useful high-resolution stills replace nearby video
  candidates only when the source view/sharpness checks pass. Manual detail photos
  use the source manual-shot path, rather than pretending every tap is a still.
- White-balance locking after settling, automatic exposure, ISO/shutter/gains,
  light estimates, tracking, manual/auto, blur and actual `highRes` metadata.
- Independent motion-triggered depth/confidence/RGB recording, normally up to
  5 Hz, adaptive thermal/memory throttling, and the source red/green photo-detail
  mesh overlay. Reported percent measures photographed observed mesh, not total
  room completeness.

Integration choices: high-resolution auto photos are enabled by default (the
upstream UI makes them optional and defaults them off); the toggle remains
available. Storage failures are surfaced, `.f16z` never silently contains raw
bytes, calibration is scaled by actual dimensions, accepted writes are drained
and the native files are sealed/verified before sharing. These safeguards do not
replace the source photo-selection algorithm. There is no old 60-second minimum,
900-frame cap, forced 30-fps/max-resolution configuration or fixed-speed sampler
in the fresh capture path. Quality guidance remains advisory.

The shared native records in `ReSpace/Domain/SourceCaptureRecords.swift` omit
nonfinite optional camera/exposure/blur estimates when encoding JSON, treating
them as unavailable rather than inventing values or failing the entire scan.
Valid estimates and required pose/calibration data keep their original values.
Required invalid data still fails; native JSON errors identify the file and
coding path, and depth-write errors identify the frame. Regression tests cover
both photo/depth indexes, finite-value preservation and atomic-write failure.
Those checks reproduce one format-error class. A subsequent device failure
identified a separate root-level `CapturedRoomData` encoding rejection. The
integration had made that optional archive mandatory, unlike the pinned source;
regression tests now cover continuing after its encoding rejection, truthful
archive availability and fatal disk errors. Real RoomBuilder processing still
requires a device capture and is not simulated by these tests.

Fresh captures now offer **Create walkthrough**, plus **Share original scan**
for manual authoring/recovery. The button uploads the original native files; it
does not invoke the earlier capture adapter or primitive JSON worker. Layout
failure keeps the original acquisition shareable but disables automatic modeling.
The capture's measured preview is never labeled as the completed reconstruction.

The 15 legacy Mac service scans/cache (1,686,925,151 bytes) were deleted at the
user's request. On the updated app's first local-library load, a one-time
migration removes old on-device capture folders while preserving new native
captures and unrelated planning/shopping data. Installing/running the updated
build is required for that device cleanup. Historical adapter conversion is
disabled by default and requires explicit `--legacy-capture`; its missing old
metadata is never fabricated.

The video likewise demonstrates a capture app followed by Codex modeling work.

## OpenAI and completion

The video uses Astra through Codex and describes his Codex subscription at 7:55.
Manual preparation/conversion/rendering makes no OpenAI API call. Interactive
modeling uses the coding agent's configured account.

The user's later **25 October Create walkthrough integration** adds a Responses
API coding harness, which is an application integration choice rather than
upstream code. It loads the unchanged skill/all four references, sees contact
sheets for every photo, reads measurements, writes actual Three.js modules and
uses source-camera/orthographic renders to revise. Its tools can rectify photo
patches, create modular source/canvas patterns and fetch CC0 PBR maps through the
original helper. It is not the earlier bounded primitive JSON schema. Tool calls,
reasoning state, responses and budget reservations are retained for recovery;
unknown billing outcomes stop further paid calls. The explicit generation has a
$10 model-token ceiling. Walkthrough authoring uses `gpt-6.1-sol` with high
reasoning and independent photo review uses Sol 6.1 with medium reasoning
(user-directed 25 October 2026); the existing
quality gates and shared cap remain in force. Failed reviews or exhausted limits retain the work;
there is no baseline/default-material publication fallback.

A dedicated headless Chromium executes generated Three.js without provider keys,
service tokens, shell access or external browser networking. Tool writes are
restricted to authored modules and textures; trusted converters/runtime/exporter
cannot be edited by the agent. Final type-checking and mesh export preserve
curved/indexed geometry, normals, UVs/repeats, photo/canvas bitmap pixels, tint,
roughness, metalness, normal maps, emission, alpha and unlit graphics. Instancing,
custom shaders and unsupported physical features require an explicit supported
geometry/bitmap bake. SceneKit uses its own ambient/directional lighting; source
fixture lights, bloom and the complete Three.js render pipeline are not identical
on the phone. Do not claim exact renderer equivalence or survey accuracy.

Before publication an independent page loads delivered OBJ/MTL/PNG files without
any authored modules and renders up to twelve source cameras distributed across
the original route. A separate vision review must cover every selected view and
pass. Rejections return discrepancies to the coding agent. The source/code hash,
texture provenance, visual review, spending and remaining uncertainties accompany
the exported scene. The prepared scaffold's `workflow.json` remains explicitly
`ready=false`; only a reviewed worker result becomes a native ready scene.

The worker now runs on the Mac and the app configuration points to the Mac's
local-network address. Runpod is not required or started by this integration.
`OPENAI_API_KEY` stays in `services/reconstruction/.env`. The phone holds only the
Mac address/service token, uploads on explicit action and verifies every result
asset before opening. The iPhone and awake Mac must share a reachable network.
See the [worker README](../../services/reconstruction/README.md) for setup,
resumable uploads, model limits and restart behavior.

Verification distinguishes functionality from fidelity: real Chromium renders,
source-photo crops, curved authored geometry, PNG/OBJ export, independent native
asset reload and ARKit-compliant USDZ packaging are exercised on a synthetic
room with mocked paid author/reviewer responses. The Swift suite covers native
file identity/upload, integrity and import validation; Simulator builds cover
the button and native material renderer. OpenAI accepted a non-generating model
availability and actual tool-schema token-count check. No paid real-room model
was generated. Real camera/LiDAR acquisition, high-resolution still availability,
device performance and real-room appearance remain to be checked on the user's
fresh iPhone scan; a synthetic scene cannot establish those.
