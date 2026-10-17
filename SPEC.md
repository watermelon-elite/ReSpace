# Room Redesign App: MVP Implementation Spec

> **Status:** plan only, no code yet. **Target:** a hackathon MVP that runs end-to-end on a LiDAR iPhone.
> **Guiding rule:** if it doesn't improve the demo loop (scan → intent → placed real products → buy), cut it or stub it.

---


## 0. Summary

- **Scan:** RoomPlan measures walls, doors, windows and large furniture. While the user scans, the app samples about 1 keyframe per second (photo, LiDAR depth and camera position).
- **Perception:** the server sends each keyframe to **Perceptron Mk1/Mk1.5**, which finds small items (lamps, plants, art, rugs, outlets, radiators, café counter, and so on) as points, boxes or polygons. The server turns each 2D detection into a 3D position using the camera position and depth. Perceptron finds objects and ARKit measures them. Neither model is asked for distances.
- **Planning:** **Gemini** reads the room as a compact JSON description plus 2–3 photos, and returns a plan of **what goes where**, using named reference points ("under sofa o3", "corner c2"). It never returns coordinates.
- **Placement:** the **placement solver** (Python, about 300 lines) converts those references into exact positions and checks for collisions, door clearance and aisle width.
- **Products:** a **curated catalog** (about 60 real products with pre-made 3D models) comes first. **SerpApi Google Shopping** covers everything else, shown as category stand-in models. **Playwright** fills in real dimensions in the background.
- **Rendering:** the app draws the room as a clean 3D model in **RealityKit** (not photo-real). Existing furniture is replaced by generic models scaled to the same size, so moving or removing it is reliable.
- **Backend:** FastAPI on Cloud Run, Tiger Data (managed Postgres) for data, Google Cloud Storage for images and 3D models.
- **Cash cost for the hackathon:** about $0–$45. Everything else is covered by existing credits (see §10).


**Decisions that keep the build fast:**

- **Gemini never returns coordinates.** It says what goes where ("under sofa o3", "corner c2"), and a small Python placement step works out exact positions and checks for collisions, door clearance and aisle width. This is what makes redesigns look reliable.
- **Perceptron finds objects, ARKit measures them.** Each scan photo goes through one Mk1 call while the user is still scanning, and the server turns its 2D results into 3D using the LiDAR depth or the room's walls and floor.
- **No background jobs.** The keyframe upload request waits for its own Mk1 call (about 8 s), and the phone doesn't wait on the upload.
- **Tiger Data is used as plain Postgres.** It has 5 tables, mostly JSON columns, set up from one schema.sql, with no ORM, migrations or time-series features.
- **Playwright runs on a teammate's laptop, not the server.** Stores block cloud servers much more often than home connections. Run it ahead of time on the curated catalog so the live demo never depends on scraping.
- **Designs are saved as versions**. Each chat edit makes a new version, so Undo just goes back one.

**Costs:**

- Per session: about $0.10–0.25 (one scan, one design, three edits).
- Credits: the $50 Perceptron credit covers roughly 1,500 scans if my token estimate holds; check it on day 1. Gemini and Tiger Data costs are covered by your credits.
- Cash: about $0–45. That's SerpApi Starter ($25) only if many people will test, plus about $20 for generating 3D models of the catalog products.
- The real limit is SerpApi: the free plan's 250 searches a month is about 50 designs, so the spec has a recorded-results mode for development.
**Unconfirmed, check on day 1:**

- Perceptron: whether your key gets Mk1.5 or Mk1, the exact parameter for structured output, and how many tokens each image costs. I couldn't find Perceptron's own docs, so the pricing comes from third-party listings.
- Depth during scanning: whether LiDAR depth is available while RoomPlan is running. If not, the spec falls back to using the room's walls and floor.
- SerpApi store links: whether results include direct store links or only Google product pages.


---

## 1. Scope

### In scope (MVP)
- Home and café/business modes
- Scanning with RoomPlan, plus keyframe sampling
- Small-item and wall-feature detection with Mk1, turned into 3D positions
- "Here's your room" view with "Keep" toggles
- Intent sheet: three intent cards, style chips, budget, seat target, free text
- "Find something for a spot" (tap a location)
- Gemini plan → product resolution → placement → 3D design screen
- Item actions: swap (alternatives already loaded), move (drag/rotate), remove, buy link
- Chat edits as versioned designs (undo = go back to the previous version)
- Before/After toggle, Day/Evening lighting toggle
- Top-down orbit view (default) and walk mode
- Shopping list and screenshot sharing
- Sample room mode for phones without LiDAR (and for judges)

### Out of scope (cut on purpose)
- User accounts and login. Use a device ID instead.
- Live AR placement in the camera view (stretch goal, §5.7)
- Erasing real furniture from the camera feed (not feasible)
- Textured mesh, Gaussian splats or photogrammetry of the room
- Generating 3D models on demand for live search results (stretch goal)
- Multi-room scans, checkout and payments, Android
- Amazon's product API. A new account can't get access (see the earlier research). An Amazon search link with an Associates tag is the only Amazon connection.
- Database migrations tooling, ORM, job queues, microservices, Kubernetes

---

## 2. Assumptions

- Team of 4, a hackathon of roughly 36 hours. Adjust §11 if this differs.
- Test devices: iPhone 12 Pro or newer Pro model. Minimum iOS version: **iOS 18**, which is needed for `RealityView` with a virtual camera on iPhone.
- Credits: Perceptron **$50** (direct platform API, not OpenRouter). Google/Gemini **$300 + $10/month**. Tiger Data **$1,000**.
- Whether pre-hackathon prep is allowed (accounts, API keys, catalog curation, 3D model generation) depends on the hackathon's rules. Check them. Everything in §11 "Pre-hackathon" can also be done in the first 4 hours.

---

## 3. Architecture

```
┌──────────────────────── iPhone (SwiftUI + RoomPlan + RealityKit) ───────────────────────┐
│ Welcome → Scan (RoomCaptureView) ──keyframes(jpeg+depth+pose)──┐                         │
│        → Room view → Intent sheet → Design screen / Walk mode   │   renders RoomModel +   │
│                                                                  │   Scene from backend    │
└──────────────────────────────────────────────────────────────────┼─────────────────────────┘
                                                                   ▼  HTTPS (JSON + multipart)
┌──────────────────────────────── FastAPI (Cloud Run) ─────────────────────────────────────┐
│ rooms.py      keyframe upload → Perceptron Mk1 → 2D detections (stored)                   │
│               finalize → normalize CapturedRoom → lift detections to 3D → merge → RoomModel│
│ designs.py    Gemini plan → resolve products (catalog | SerpApi + Gemini Flash pick)      │
│               → placement solver → Scene ;  chat edits → partial re-plan                  │
│ solver.py     reference points → positions (shapely), collisions, clearances           │
└───────┬───────────────────────┬─────────────────────────┬──────────────────────┬─────────┘
        ▼                       ▼                         ▼                      ▼
  Tiger Data (Postgres)   Google Cloud Storage     Perceptron API        Gemini API / SerpApi
  rooms, keyframes,       keyframes, depth,
  designs, products,      catalog USDZ models
  serp_cache
                ▲
                │ polls products where dims_status='pending'
   scripts/enrich_dims.py (Playwright, runs on a teammate's LAPTOP, not in the cloud)
```

### Tech stack

| Layer | Choice | Why / notes |
|---|---|---|
| iOS UI | SwiftUI | |
| Scan | RoomPlan `RoomCaptureView` + `RoomCaptureSession` | Includes the scanning screen and coaching for free |
| Keyframes | `roomCaptureSession.arSession.currentFrame` on a timer | Don't replace RoomPlan's AR session delegate |
| 3D | RealityKit `RealityView` (virtual camera) | SceneKit was deprecated in 2025 |
| Backend | Python 3.12, FastAPI, uvicorn, httpx, Pydantic v2 | Pydantic models double as Gemini response schemas |
| DB driver | psycopg 3 (async) with plain SQL + one `schema.sql` | No ORM and no Alembic |
| Geometry | numpy, shapely | Lifting 2D→3D, footprints, collisions |
| LLM | `google-genai` SDK | Pro-tier model for the first plan, Flash-tier for everything else |
| Perception | Perceptron platform API (SDK or HTTP) | Mk1.5 if available on your key. Same price as Mk1 per listings. |
| Products | SerpApi `google_shopping` | Cached in Postgres |
| Dimensions | Playwright (Python) script | Runs on a laptop. Cloud servers get blocked by stores. |
| Hosting | Cloud Run + GCS | Paid from the Google credits. Set **CPU always allocated** and `min-instances=1` so the first request isn't slow. |
| DB | Tiger Data (Tiger Cloud) | Used as plain managed Postgres with JSONB. No hypertables needed. |

---

## 4. User flow, end to end (what happens on each screen)

Each step lists what the **user** sees, what the **system** does, and when it's **done**.

### Step 0: Welcome
- **User:** "What space are we working on?" → **My home** / **My café or business**. A secondary link: "Try a sample room" (always visible; it's the default path on phones without LiDAR).
- **System:**
  - Check `RoomCaptureSession.isSupported`. If false, hide Scan and push the sample room.
  - Create `device_id` (UUID, stored in Keychain) on first launch.
  - `POST /v1/rooms {mode}` → `room_id`.
- **Done when:** one tap lands on the scan screen with a `room_id`.

### Step 1: Scan (60–120 s)
- **User:** RoomPlan's own scanning screen (live outline and coaching), plus a "Done" button. A small counter in the corner: "✨ 12 details found".
- **System:**
  - A keyframe sampler (§5.1) uploads about 30–40 keyframes in the background, uploading up to 4 at a time.
  - Each upload response returns that frame's Mk1 detections. The counter adds them up.
  - On Done: `CapturedRoom` is encoded to JSON → `POST /v1/rooms/{id}/finalize`.
- **Done when:** the finalize call returns a `RoomModel` (large furniture right away; small items are added as Mk1 calls finish).

### Step 2: "Here's your room"
- **User:**
  - Top-down 3D room: walls, windows, doors, and existing furniture as stand-in models with labels ("Sofa · 2.1 m").
  - Small items (lamps, plants, art, rug) appear as they finish processing.
  - Each item can be tapped: **Keep** (locked; a redesign won't move or remove it), **Remove**, or **Fix label** (stretch).
  - Primary button: "What do you want to do?"
- **System:**
  - Render the `RoomModel`.
  - Poll `GET /v1/rooms/{id}` every 2 s until `pending_keyframes == 0`, or for 20 s at most.
- **Done when:** the room looks right and Keep toggles are saved locally (they're sent with the design request).

### Step 3: Intent sheet
- **User:**
  - Three cards: ✨ **Add a few things** · 📍 **Find something for a spot** · 🔄 **Full redesign**
  - Style chips (multi-select): Cozy · Minimal · Japandi · Industrial · Boho · Mid-century · Match what I have
  - Budget slider
  - Business mode only: **Seats** stepper and a "Keep aisles clear" toggle (on by default)
  - Text field: "Or just tell us…"
  - Any combination is valid. Text alone is valid too, with intent inferred (default: "add").
- **"Find something for a spot":** goes back to the room view → user taps a floor or wall point → bottom sheet "What goes here?" (chips: lamp / plant / chair / shelf / art / table / anything + text).
- **Done when:** `POST /v1/rooms/{id}/designs` is sent.

### Step 4: Generating (target p50 ≤ 20 s)
- **User:** progress messages that tell a story, built **on the device from the RoomModel**, so no server streaming is needed. For example: "Measuring your 3.4 m window wall…", "Keeping 1.2 m clear in front of your door…", "Finding a rug that fits under your sofa…", and for business mode "Fitting 24 seats with 91 cm aisles…".
- **System (server):**
  1. Gemini plan (§5.4)
  2. Resolve products (§5.5)
  3. Placement solver (§5.6)
  4. Save the design version
  5. Return the `Scene`
- **Done when:** the Scene is returned. On failure: "Couldn't finish that design, try again or simplify your request", and the intent sheet keeps what the user entered.

### Step 5: Design screen (the main screen)
- **User:**
  - 3D room with the design applied. Moved items animate to their new spots; removed items fade to 20% opacity ("ghost").
  - **Before / After** toggle. **Day / Evening** toggle.
  - Bottom sheet: item cards (photo, title, store, price, a "Why:" line from Gemini, a 📏 *verified* badge when dimensions were scraped) and a total ("$612 · 7 items").
  - Tap an item card or a 3D item:
    - **Swap**: 3 alternatives, instant, no server call
    - **Move**: drag on the floor, rotate with two fingers, wall items slide along the wall
    - **Remove**
    - **Buy**: opens the store link; secondary "Find on Amazon" link
  - Chat bar: "cheaper rug", "make it warmer", "move the sofa to the window wall" → `POST /v1/designs/{id}/chat` → new version. An **Undo** pill goes back to the previous version.
- **Done when:** the user can edit and see the total change.

### Step 6: Walk mode
- **User:** toggle in the top bar. Joystick on the left moves, dragging on the right looks around, and the camera stays at 1.5 m eye height. Tapping the floor jumps there. The user can't walk through walls (the camera position is kept inside the floor outline).
- **System:** the same RealityKit scene, a different camera controller. No server calls.

### Step 7: Save / share
- **User:**
  - Designs auto-save (one list per room on a simple "My spaces" screen).
  - **Share** opens the system share sheet with a screenshot of the scene and a text shopping list grouped by store (title, price, link).
- **System:** a RealityKit snapshot plus a text list. No hosted web share page in the MVP.

---

## 5. Pipeline details

### 5.1 Keyframe capture (iOS)
- **Trigger:** every 1.5 s, **or** after moving more than 0.5 m, **or** after turning more than 20° since the last keyframe. **Maximum 40 per scan.** Skip frames when ARKit tracking isn't `.normal`, or when the image is blurry (simple check: camera moved more than 0.3 m/s at that moment).
- **Payload per keyframe:**
  - JPEG, longest edge 1280 px, quality 0.7 (about 150 KB). Keep the **sensor orientation**, don't rotate it.
  - Camera intrinsics (fx, fy, cx, cy), **rescaled to the 1280 px image**. This is a common bug: resize the image and forget to scale the intrinsics.
  - Camera-to-world transform (16 floats, column-major), image width and height, timestamp.
  - Depth map (`sceneDepth.depthMap`, 256×192 float16, about 100 KB) **if available while RoomPlan is running**. To verify on day 1 (§12).
- **Upload:** `POST /v1/rooms/{id}/keyframes` (multipart), up to 4 uploads at a time, retried once. The UI never waits on an upload.

### 5.2 Perceptron Mk1 perception (server)
- **One Mk1 call per keyframe**, made inside the upload request handler. The handler waits on the Mk1 call (median about 8 s), saves the result, and returns the detections. This avoids background tasks. Cloud Run must allow concurrent requests (keep the default concurrency of 80).
- **Model:** Mk1.5 if the platform offers it, otherwise Mk1. Keep the model ID in an environment variable.
- **Prompt, mode-dependent label list:**
  - Home: `lamp, floor_lamp, plant, wall_art, mirror, rug, curtain, shelf, tv, ceiling_light, outlet, light_switch, radiator, vent`
  - Café adds: `counter, espresso_machine, menu_board, register, display_case, pendant_light, bar_stool, trash_bin`
  - Ask for **boxes** for objects, **polygons** for rugs, and **points** for outlets, switches and vents, using the platform's structured-annotation option (`annotation_format` or the SDK equivalent; confirm the exact name in Perceptron's docs).
  - Same call: "For any sofa, table, chair, bed or cabinet visible, give its color and material in ≤5 words." These attributes get attached to RoomPlan objects in §5.3.
- **Normalize the output** to `[{label, kind: box|point|polygon, coords_px, attrs?}]`. Convert from whatever coordinate format the API uses (pixels, 0–1 or 0–1000) to pixels here, once.
- **Budget guard:** stop calling Mk1 for a room after 40 keyframes. Log the token counts from every response so the cost estimate in §10 can be checked.

### 5.3 Lifting detections to 3D and merging → `RoomModel` (server, on finalize)
1. **Normalize the CapturedRoom** to a 2.5D model: every object is a **floor-plane footprint + height + rotation around the vertical axis**. The floor is at y=0. Units are meters. Floor coordinates are (x, z).
   - Walls become line segments `a→b`. Doors and windows become openings on a wall (offset, width, sill height, height).
   - Objects become (id, category, center, yaw, size). Each object is linked to a wall if it's within 0.3 m and parallel to it.
   - Corners are named `c1…cn` from where walls meet.
2. **Ray for each detection:** take the box's bottom-center (for floor items) or center (for wall items), or the point, and build a camera-space direction from the intrinsics. Transform it to world space with that keyframe's camera transform.
3. **Find the 3D position:**
   - **(a) Depth first:** median depth of a 5×5 patch at that pixel (with pixel coordinates scaled to the depth map). Use it if the value is valid and under 5 m.
   - **(b) Fallback, ray casting:** intersect the ray with the RoomModel's surfaces (floor plane, wall rectangles, tops of furniture boxes) and keep the nearest hit.
   - Rugs: intersect each polygon corner with the floor plane.
4. **Estimate size** from the box width × distance / fx. Use category defaults when that's implausible.
5. **Merge:** cluster by label within 0.4 m (0.2 m for outlets and switches) and average the positions. Keep a cluster if it was **seen in ≥2 keyframes**. Rugs, art and counters are kept after one sighting.
6. **Wall features:** snap to the nearest wall within 0.15 m and store (wall_id, offset along the wall, height).
7. **Attach attributes** (color, material) from §5.2 to the nearest RoomPlan object of the same category. Gemini uses them for "Match what I have"; the renderer uses them to tint stand-in models.
8. **Business mode zones:** a `keep_clear` area 1.2 m deep in front of the counter and register and around each door (door width plus 0.9 m).
- **Debug overlay (P0 for the team, hidden in the demo):** draw RoomPlan's box corners and the 3D-lifted detections back onto a keyframe image. If they don't line up, every later step will be wrong. This is the first test to pass.

### 5.4 Gemini planning
- **Model:** Pro-tier, with thinking enabled, for the **first design**. Flash-tier for chat edits, product picking and dimension extraction.
- **Input:**
  - The compact `RoomModel` (about 2–3 K tokens; contract in §6)
  - The user's request (intent, chips, budget, seats, text, Keep IDs, spot)
  - 2–3 keyframes, picked as the most spread-out camera positions, so Gemini can read style, colors and floor material
  - The **curated catalog list** (id, title, category, price, size, style tags; about 60 items × about 40 tokens ≈ 2.5 K)
- **Output:** the `DesignPlan` JSON (§6), enforced with Gemini's response schema built from the Pydantic model. **Keep the reference-point object flat** (`type` plus optional fields). Gemini schemas handle "one of several types" poorly.
- **Prompt rules (system prompt):**
  1. Refer only to IDs that exist in the input. Never return coordinates.
  2. Pick reference points from the allowed list (§5.6).
  3. Respect Keep: never move or remove kept items.
  4. Intent limits: *add* = 1–5 new items, no moves or removes. *spot* = exactly 1 item, at the chosen spot. *redesign* = 5–20 items, moves and removes allowed.
  5. The total of `max_price` across items must be ≤ the budget.
  6. Business mode: meet the seat target with seating groups; never place anything inside `keep_clear` zones.
  7. Prefer catalog items (`catalog_ids`). Otherwise return a precise shopping `query` (include size words, e.g. "8x10 jute rug").
  8. Each item gets a one-line `reason`, shown in the UI as "Why:".
- **Validation:** check every ID against the room and catalog. Drop invalid items and log them; retry once only if more than half of the items are invalid.

### 5.5 Product resolution
For each item to add, in parallel:
1. **If it has `catalog_ids`:** load from `products` (`source='catalog'`). The first is the pick; the rest are alternatives. These have true 3D models and verified dimensions.
2. **Otherwise, SerpApi:**
   - Search `google_shopping` with the query. Check `serp_cache` first; it's keyed by the normalized query and kept for 7 days.
   - Take the top 10 results and filter by `max_price`.
   - **One Gemini Flash call for all non-catalog items together:** "For each item, pick the best product plus 2 alternatives, and estimate W×D×H in cm from the title and category." Its output schema includes `dims_cm` and `dims_confidence`.
   - Upsert into `products` with `dims_source='estimated'` and `dims_status='pending'`, so the Playwright script (§5.9) picks them up.
3. **Swap list:** each design item stores the IDs of its pick and alternatives. Swap is then a client-side change persisted with `PATCH`.
4. **Links:**
   - **Buy** uses the SerpApi `link` or `product_link`. Day-1 check: whether results include a direct store URL or only a Google product page. If only Google, that's fine for Buy, and Playwright resolves the store URL (§5.9).
   - **"Find on Amazon"** is `https://www.amazon.com/s?k=<title>&tag=<associates-tag>`. No API needed.
5. **SerpApi budget:**
   - Free plan: 250 searches/month. Starter: $25 for 1,000.
   - About 3–6 searches per design after the cache. Chat edits cost 0–2.
   - **During development, use a recorded-response mode** (`SERPAPI_MODE=fixture`) so you don't burn the quota.

### 5.6 Placement solver (server, deterministic, unit-testable)
- **Reference points:**
  - Floor items: `against_wall(wall, align=left|center|right, offset?)`, `corner(corner)`, `under(object)` (rugs), `next_to(object, side=left|right|front)`, `facing(object, distance?)`, `in_front_of_window(opening)`, `room_center`, `at_spot(x,z)` (spot intent).
  - Wall items: `on_wall(wall, align, height?)`.
  - Tabletop items: `on_top_of(object)`.
  - Business mode: `seating_group(zone|wall, count, layout=2top|4top|bar)`.
- **Algorithm:**
  1. Apply removes, then moves, then adds, largest footprint first.
  2. Compute a candidate position and rotation from the reference point. Items against a wall face away from it; chairs and sofas face their `facing` target.
  3. Check the footprint (shapely polygon, plus a 5 cm margin) against walls, all other footprints, door clearance zones and `keep_clear` zones.
     - Rugs can sit under furniture, and wall items only collide with other wall items and openings.
  4. If it collides, try nudges: slide along the wall in ±0.1 m steps up to ±1.0 m, then rotate 90°, then the next-best reference point (e.g. a free corner). If nothing fits, **drop the item** and add a warning ("Couldn't fit the bookshelf, no free wall space"). Show it as a chip, not an error.
  5. **Aisle check (business mode and redesign):** take the free floor area and shrink it by half the minimum aisle width (0.45 m for 0.9 m aisles). If the doors are no longer connected to the free area, remove the lowest-priority item and repeat.
  6. Lamps get a bonus for being within 1.5 m of an outlet.
- **Output:** the `Scene` (§6).
- **Tests:** pytest with the 2–3 recorded rooms, asserting no overlaps, doors clear and seat counts met. This is the only part of the system that really needs tests.

### 5.7 Rendering and interaction (iOS)
- **Room:**
  - Walls are thin boxes built from the RoomModel segments, colored from the style hints (default warm off-white).
  - Floor is a polygon mesh with a wood or concrete material picked from the style hints.
  - Windows are translucent light-blue panels; doors are darker panels.
  - Cut away (or fade) the walls facing the camera in top-down view.
- **Furniture:**
  - **Existing:** a generic model of its category, scaled non-uniformly to the RoomPlan size and tinted with the Mk1 color.
  - **Catalog:** the real USDZ from GCS, cached on the device.
  - **SerpApi results:** a category stand-in tinted with the product photo's dominant color (computed on the server with Pillow). Rugs, wall art and mirrors are flat panels textured with the product photo.
- **Cameras:**
  - Orbit/top-down (default): pinch, pan, rotate.
  - Walk: joystick and look-drag at 1.5 m.
- **Gestures:**
  - Tap → raycast to an item → select it.
  - Drag a selected item → raycast onto the floor plane (or the wall plane for wall items) → move it.
  - Two-finger rotate → rotate it.
  - On release, run a client-side overlap check (red highlight if it overlaps) and send `PATCH` to save.
- **Lighting:**
  - Image-based lighting from one neutral indoor environment, plus a **directional "sun"** pointing in from the largest window.
  - `GroundingShadowComponent` on every item.
  - **Evening:** sun intensity × 0.1, warmer ambient light, and each lamp item gets a warm point light (or a spot light for pendants and floor lamps that should cast shadows).
- **Before/After:** keep both the original and new transforms; the toggle animates between them and hides new items.
- **Stretch: "See it in AR"** is only possible right after a scan, before the AR session closes. Run RealityKit on `captureSession.arSession`; the coordinates already line up. Only new items are shown.

### 5.8 Chat edits, versions, manual edits
- **Designs are versions that never change after creation:** `designs.parent_id`. A chat message creates a child version. Undo = load the parent.
- **Chat:** one Gemini Flash call with the current design (compact list: item ID, category, title, price, reference point), the RoomModel summary and the message.
  - It returns **edit operations**: `replace_item(item_id, query|catalog_id, max_price?)`, `add_item(item)`, `remove_item(item_id)`, `move_item(item_id, reference point)`, `move_existing(object_id, reference point)`.
  - The server resolves only the changed items (§5.5), re-runs the solver with every other item fixed, and saves a child version.
  - Target: ≤ 8 s.
- **Manual edits** (drag, rotate, remove, swap) update the current version with `PATCH`. Manual changes are small; versioning them isn't worth it.

### 5.9 Dimension enrichment (Playwright, background, best-effort)
- `scripts/enrich_dims.py` runs on a **laptop**: home IP addresses are blocked much less often than cloud IPs. It uses Playwright with the real Chrome channel, headless.
- **Loop:**
  1. Fetch up to 5 products with `dims_status='pending'`.
  2. If there's only a Google product URL, open it and follow the first store offer to get the store URL.
  3. On the store page, try in order:
     - **(a)** structured product data in `application/ld+json` (`Product.width/depth/height`)
     - **(b)** the visible text of the specs or details section → a Gemini Flash extraction returning `{w,d,h,unit,source: item|package,confidence}`
     - **(c)** give up
  4. **Range check** per category (sofa 1.4–3.2 m wide, rug thickness under 3 cm, etc.). Reject package dimensions. Width, depth and height are in a different order on each store's page; map them using the field labels.
  5. Write `dims_cm` and `dims_source='scraped'`, and set `dims_status='done'` (or `'failed'`).
- **The app** picks up the new dimensions when the design is next loaded: the item is resized and gets a 📏 badge. Live rescaling while the screen is open is not needed.
- **Run it on the curated catalog before the demo**, so catalog items always have verified dimensions. The live demo never depends on scraping.
- **Amazon's terms prohibit scraping.** Fine for a demo, not for production.

### 5.10 Assets
- **Stand-in library, bundled in the app:**
  - About 20 categories: sofa, armchair, chair, stool, dining table, coffee table, side table, desk, bed, bookshelf, cabinet, TV stand, floor lamp, table lamp, pendant, plant (2 sizes), mirror, wall art panel, rug panel, counter.
  - Source: the **Kenney Furniture Kit (CC0)**, converted to USDZ with Reality Converter. Normalize every model to a 1×1×1 m box with its origin at the bottom-center facing +z, so scaling to any size is trivial.
- **Curated catalog** (about 60 products, `scripts/build_catalog.py` + a hand-edited `catalog.yaml`):
  1. Pick real products across the categories plus café items (stools, 2-top tables, pendants, menu boards, planters), mixing styles and prices.
  2. For each one: title, store URL, price, photo, verified dimensions, style tags.
  3. Generate a 3D model with **Tripo or Meshy** from the photo. Export or convert it to USDZ, scale it to the real dimensions, and keep it under 3 MB (reduce the polygon count if needed).
  4. Upload to GCS and upsert into `products`.

---

## 6. Data contracts (freeze these in hour 0–4; both sides build against the examples)

**RoomModel** (server → app; also sent to Gemini). Floor coordinates are (x, z) in meters; y is up; the floor is at y=0.
```json
{
  "room_id": "r_8f2",
  "mode": "home",
  "height": 2.6,
  "floor": { "polygon": [[0,0],[4.2,0],[4.2,3.6],[0,3.6]], "area_m2": 15.1 },
  "walls":   [{ "id": "w1", "a": [0,0], "b": [4.2,0], "length": 4.2 }],
  "corners": [{ "id": "c1", "at": [0,0], "walls": ["w4","w1"] }],
  "openings":[{ "id": "win1", "type": "window", "wall": "w1", "offset": 0.8, "width": 1.4, "sill": 0.9, "height": 1.2 },
              { "id": "d1",   "type": "door",   "wall": "w3", "offset": 0.2, "width": 0.85 }],
  "objects": [{ "id": "o3", "category": "sofa", "source": "roomplan", "center": [2.1,3.1], "yaw": 3.14,
                "size": [2.1,0.9,0.8], "against_wall": "w3", "attrs": { "color": "grey", "material": "fabric" } },
              { "id": "s1", "category": "floor_lamp", "source": "mk1", "center": [0.3,0.4], "yaw": 0,
                "size": [0.4,0.4,1.6], "sightings": 4 }],
  "wall_features": [{ "id": "f1", "type": "outlet", "wall": "w1", "offset": 2.9, "height": 0.3 }],
  "zones":   [{ "id": "z1", "type": "keep_clear", "reason": "door", "polygon": [[...]] }],
  "style_hints": { "floor": "light oak", "walls": "white" },
  "status": { "pending_keyframes": 0 }
}
```
(`size` is [width, depth, height].)

**DesignRequest** (app → server)
```json
{ "intent": "add | spot | redesign", "styles": ["japandi","cozy"], "budget": 800, "seats": null,
  "text": "warm reading nook by the window", "keep_ids": ["o3"], "spot": { "x": 1.2, "z": 0.6, "wall": null } }
```

**DesignPlan** (Gemini output; the reference-point object is flat)
```json
{ "summary": "Warm Japandi reading corner by the window",
  "moves":   [{ "object_id": "o5", "anchor": { "type": "against_wall", "wall": "w2", "align": "center" }, "reason": "…" }],
  "removes": [{ "object_id": "o7", "reason": "…" }],
  "adds":    [{ "slot_id": "a1", "category": "rug", "catalog_ids": ["cat_rug_04","cat_rug_09"], "query": null,
                "max_price": 150, "qty": 1, "anchor": { "type": "under", "object": "o3" }, "reason": "Grounds the seating area" },
              { "slot_id": "a2", "category": "floor_lamp", "catalog_ids": [], "query": "paper lantern floor lamp",
                "max_price": 90, "qty": 1, "anchor": { "type": "corner", "corner": "c2" }, "reason": "…" }] }
```

**Scene** (server → app)
```json
{ "design_id": "d_31", "parent_id": null, "summary": "…", "total_price": 612.40, "warnings": ["Couldn't fit the bookshelf"],
  "items": [{ "id": "i1", "status": "new | moved | removed | existing", "object_id": null, "slot_id": "a1",
              "product": { "id": "p_9", "title": "…", "store": "Target", "price": 129.0, "url": "…", "amazon_search_url": "…",
                           "image_url": "…", "dims_source": "scraped" },
              "alternatives": ["p_10","p_11"], "reason": "…",
              "render": { "kind": "catalog | standin | panel", "model_url": "…", "standin": "rug", "tint": "#C9B79C", "texture_url": "…" },
              "position": [1.9, 0.0, 2.4], "yaw": 3.14, "size": [2.4, 3.0, 0.01],
              "original": { "position": [0.5,0,0.5], "yaw": 0 } }] }
```

---

## 7. API (FastAPI, prefix `/v1`)

Auth: an `X-Device-Id` header plus a shared `X-App-Key` (a static secret, only to stop casual abuse). No accounts.

| Method & path | Purpose | Notes |
|---|---|---|
| `POST /rooms` | Create a room `{mode}` → `{room_id}` | |
| `POST /rooms/{id}/keyframes` | Multipart: jpeg, depth?, meta → stores to GCS, calls Mk1, returns detections | About 8 s; the app fires it without waiting |
| `POST /rooms/{id}/finalize` | Body: the raw `CapturedRoom` JSON → `RoomModel` | Lifting and merging run here and run again when late keyframes arrive |
| `GET /rooms/{id}` | `RoomModel` + status | The app polls this during Step 2 |
| `GET /rooms?device_id=` | "My spaces" list | |
| `POST /rooms/{id}/designs` | `DesignRequest` → `Scene` | Waits for the result, 10–30 s. Set the client timeout to 60 s. |
| `GET /designs/{id}` | `Scene` (with current dimensions) | |
| `POST /designs/{id}/chat` | `{message}` → child `Scene` | |
| `PATCH /designs/{id}/items/{item_id}` | `{position?, yaw?, removed?, product_id?}` | Manual move, remove or swap |
| `GET /catalog/manifest` | Catalog IDs → model URLs and versions | So the app can prefetch models |
| `GET /health` | | |

---

## 8. Database (Tiger Data / Postgres)

The whole database is one `schema.sql`, run by hand. JSONB columns hold anything that's only ever read or written as a whole.

| Table | Columns (main ones) | Notes |
|---|---|---|
| `rooms` | `id`, `device_id`, `mode`, `name`, `captured_room` jsonb (raw), `room_model` jsonb, `created_at` | `room_model` is recomputed on finalize and when late keyframes arrive |
| `keyframes` | `id`, `room_id`, `idx`, `image_url`, `depth_url`, `intrinsics` jsonb, `transform` jsonb, `w`, `h`, `mk1_status`, `mk1_result` jsonb, `mk1_tokens` int | `mk1_result` holds the normalized 2D detections |
| `designs` | `id`, `room_id`, `parent_id`, `request` jsonb, `plan` jsonb, `scene` jsonb, `total_price`, `created_at` | A chat edit adds a new row; a PATCH updates `scene` |
| `products` | `id`, `source` (catalog/serpapi), `source_key` (unique per source), `title`, `store`, `price`, `url`, `store_url`, `image_url`, `category`, `style_tags` text[], `dims_cm` jsonb, `dims_source`, `dims_status`, `model_url`, `tint`, `updated_at` | One table for both catalog and live results |
| `serp_cache` | `query` (pk, normalized), `results` jsonb, `fetched_at` | Kept 7 days |

- **Indexes:** `rooms(device_id)`, `designs(room_id)`, `products(dims_status)`, `products(category)`.
- **Not used in the MVP:** hypertables, pgvector. Add pgvector (available on Tiger Cloud) only if the catalog grows past a few hundred items, so it no longer fits in the prompt.
- **Connection:** SSL is required. Pool size of 5 per Cloud Run instance.

---

## 9. Requirements

### Functional (P0 = demo-critical, P1 = should have, P2 = stretch)

| ID | Requirement | Pri |
|---|---|---|
| FR-01 | Choose home or business mode; phones without LiDAR get the sample room | P0 |
| FR-02 | Scan a room with RoomPlan and send it to the backend | P0 |
| FR-03 | Sample and upload ≤40 keyframes during the scan without the UI stuttering | P0 |
| FR-04 | Mk1 detects the small-item and wall-feature labels and returns structured coordinates | P0 |
| FR-05 | Detections are lifted to 3D, merged and added to the RoomModel | P0 |
| FR-06 | Room view renders walls, openings, existing objects and small objects with labels; tap for Keep | P0 |
| FR-07 | Intent sheet (cards, chips, budget, text); business mode adds a seat count | P0 |
| FR-08 | Gemini returns a valid DesignPlan that respects the intent limits, Keep and budget | P0 |
| FR-09 | Products are resolved: catalog first, otherwise SerpApi + Flash pick, with 2 alternatives each | P0 |
| FR-10 | Solver places items without overlaps, with doors clear; items that don't fit are dropped with a warning | P0 |
| FR-11 | Design screen: 3D scene, item cards, total, Buy link | P0 |
| FR-12 | Swap (instant), Move (drag/rotate), Remove, saved with PATCH | P0 |
| FR-13 | Chat edits create versions; Undo | P1 |
| FR-14 | "Find something for a spot" intent | P1 |
| FR-15 | Before/After toggle; moved items animate | P1 |
| FR-16 | Walk mode | P1 |
| FR-17 | Day/Evening lighting with lamp lights | P1 |
| FR-18 | Business mode: seat target, aisle check, `keep_clear` zones from counter, register and doors | P1 |
| FR-19 | Playwright dimension enrichment and 📏 badge | P1 |
| FR-20 | Share: screenshot + shopping list | P1 |
| FR-21 | "Find on Amazon" search link with Associates tag | P1 |
| FR-22 | "See it in AR" right after the scan | P2 |
| FR-23 | Generate a 3D model on demand for a SerpApi item | P2 |
| FR-24 | Gemini photo-real "inspiration preview" image from a keyframe | P2 |
| FR-25 | Mk1 check of the rendered design ("anything blocking a door or walkway?") | P2 |

### Non-functional

| ID | Requirement |
|---|---|
| NFR-01 | Room view shows large furniture ≤3 s after Done; all small items within ≤15 s |
| NFR-02 | First design p50 ≤20 s, p95 ≤35 s. Chat edit ≤8 s. Swap and manual edits under 300 ms (local) |
| NFR-03 | ≥30 fps on an iPhone 13 Pro with ≤40 items in the scene |
| NFR-04 | Small-item position error ≤15 cm (checked with the debug overlay and a tape measure on one room) |
| NFR-05 | 0 overlapping footprints and 0 blocked doors in solver output (asserted in tests) |
| NFR-06 | Variable API cost ≤$0.20 per session (scan + first design + 3 edits) |
| NFR-07 | Every external call has a timeout and a fallback: Mk1 failure → RoomPlan-only room; SerpApi failure → catalog only; Gemini failure → one retry, then an error message |
| NFR-08 | Keyframes are stored in a private bucket; product images and models in a public one |

---

## 10. Costs

Prices are approximate. Third-party listings were used where official pages weren't found; check them on day 1 against each provider's usage dashboard.

### Per-unit assumptions

| Service | Price used | Source / note |
|---|---|---|
| Perceptron Mk1 / Mk1.5 | about $0.15 / M input tokens, $1.50 / M output tokens | Third-party listings; same for Mk1.5. Median latency is about 8 s. |
| Gemini | Pro-tier for the first plan, Flash-tier for the rest | Covered by the **$300 + $10/month** Google credits |
| SerpApi | Free plan: 250 searches/month. Starter: $25 / 1,000 | Third-party pricing pages |
| Tiger Data | Smallest Performance service, roughly $30–60/month | Covered by the **$1,000** credits. Check when the credits expire. |
| Cloud Run + GCS | Pennies at hackathon scale | Covered by the Google credits |
| Tripo / Meshy (catalog 3D models) | About $20 for one month of a paid plan ≈ enough for 60+ models | Free tiers give only a handful |
| Kenney Furniture Kit | Free (CC0) | |
| Apple Developer Program | $0 (free personal team) / $99 a year | $99 only if you need TestFlight for judges or teammates |

### Per session (1 scan + 1 first design + 3 chat edits)

| Step | Estimate |
|---|---|
| Mk1: 40 keyframes × (about 1.5 K input + 300 output tokens) | ≈ $0.01 + $0.02 = **~$0.03** |
| Gemini Pro first plan (about 12 K input incl. 3 images, about 4 K output incl. thinking) | **~$0.05–0.08** |
| Gemini Flash product pick + 3 edits + dimension extraction | **~$0.01** |
| SerpApi: about 5 searches (fewer once cached) | $0 on the free plan / about $0.13 on Starter |
| **Total variable cost** | **≈ $0.10–0.25 per session** |

### Credit runway

- **Perceptron $50** lasts about 1,500 scans, or about 500 if image tokens are 3× higher than assumed. Development won't come close.
- **Google $300** lasts several thousand sessions. Not a constraint.
- **Tiger Data $1,000** lasts more than a year on the smallest service, if the credits don't expire sooner.
- **SerpApi** is the real limit: the free plan's 250 searches/month is about 50 designs. Use the fixture mode during development, and buy **Starter ($25)** for demo week if many people will be testing.

### Cash spend for the hackathon: **≈ $0–$45** (SerpApi Starter $25 if needed + about $20 for 3D model generation; plus $99 Apple Developer only if you need TestFlight)

---

## 11. Build plan (4 people, about 36 h)

### Pre-hackathon (or hours 0–2 if prep isn't allowed)
- Accounts and keys: Perceptron, Gemini (AI Studio or Vertex), SerpApi, Tiger Data service, GCP project (Cloud Run + 2 buckets), Amazon Associates tag (optional).
- Repo: `ios/`, `server/`, `scripts/`, `fixtures/`, plus `SPEC.md`.
- Curate `catalog.yaml` (60 items) and generate 3D models (§5.10). This is slow, so start it first.
- Convert the Kenney stand-ins and normalize them to 1 m boxes.

### Roles
- **A: iOS Capture.** Welcome, RoomPlan scan, keyframe sampler and uploads, LiDAR check, **records the fixture room** (raw CapturedRoom JSON + 40 keyframes with poses and depth) in hour 1–2.
- **B: iOS Render/UX.** RealityView scene built from RoomModel and Scene, cameras, gestures, all screens, lighting.
- **C: Backend AI.** FastAPI skeleton, Mk1 client and normalization, lifting and merging, Gemini plan and chat prompts, debug overlay.
- **D: Backend Data/Placement.** schema.sql, solver + tests, SerpApi + cache, product resolution, catalog loader, Playwright script.

### Milestones

| Hours | Goal (each ends with something that runs) |
|---|---|
| 0–4 | **Contracts frozen** (§6 examples in `fixtures/`). Fixture room recorded. Day-1 checks done (§12). DB live. Server deployed with `/health`. |
| 4–12 | **Vertical slice on the fixture:** finalize → RoomModel → app renders it in the Simulator → design request → Gemini plan (catalog only) → solver → app renders the placed catalog models. |
| 12–20 | **Perception and live products:** Mk1 calls + lifting + debug overlay verified on the real fixture. SerpApi + Flash pick + stand-ins + item cards + Buy + Swap. **Scan on a real device works end-to-end.** |
| 20–28 | **Editing and the experience:** Move/Remove/PATCH, chat edits + undo, Before/After, walk mode, Day/Evening, business mode (seats, aisles, zones), spot intent. |
| 28–32 | **Polish:** progress messages, Playwright enrichment run on the catalog and recent products, share sheet, empty and error states. |
| 32–36 | **Freeze.** Bug fixes only. Rehearse the demo three times. Record a backup video. |

**Cut order if behind schedule:** FR-25/24/23/22 → walk mode → Day/Evening → spot intent → chat edits. **Never cut:** scan → room view → intent → placed real products → Buy.

---

## 12. Risks and day-1 checks

| # | Risk | Day-1 check (hours 0–4) | Fallback |
|---|---|---|---|
| 1 | `sceneDepth` not available while RoomPlan runs | Read `arSession.currentFrame?.sceneDepth` during a scan | Ray casting only (§5.3 b) |
| 2 | Keyframe camera positions and the CapturedRoom use different coordinate frames | Debug overlay: project RoomPlan box corners into 3 keyframes | Find the transform once and apply it |
| 3 | Mk1 API details (auth, annotation parameter, coordinate format, tokens per image, latency) | Call it with 5 fixture keyframes; log the raw response and usage | Fall back to Gemini for detection (it can also return boxes) |
| 4 | Mk1 latency makes small items show up late | Measure p50/p95 | The room view shows large furniture first; small items pop in |
| 5 | Gemini returns invalid IDs or ignores limits | Run 10 prompts on the fixture | Validation + drop + one retry; the solver is the safety net |
| 6 | SerpApi gives no store URL / missing prices | Run 5 queries; inspect the fields | Use the Google product link for Buy; Playwright finds the store URL |
| 7 | Playwright blocked by stores | Try 10 product URLs from the laptop | Gemini's size estimate; the catalog already has verified dimensions |
| 8 | RealityView virtual camera + gestures harder than expected | Render a USDZ in an orbit camera on iOS 18 | Top-down view only; drag on a 2D overlay |
| 9 | Big or glassy café spaces scan badly | Scan a café corner | Demo in a normal room / a defined café corner |
| 10 | Venue Wi-Fi | — | Phone hotspot; sample room mode works with only the server reachable |

---

## 13. Demo plan (3 minutes)
1. **Home, "add a few things":** live scan of a corner (about 45 s) → room view shows the detected lamp, plant and outlet → "Cozy, $300, warm reading nook" → design with a rug under the sofa and a lamp placed near the outlet (say this out loud) → swap the rug → Buy link opens.
2. **Café, "full redesign":** load a **pre-scanned** café room → "Industrial, 24 seats" → tables and chairs in seating groups with clear aisles, counter queue area left empty → walk mode → Evening toggle.
3. **Backup:** the sample room plus a recorded video, in case the live scan or network fails.

---

## 14. Open questions
- How long is the hackathon, how big is the team, and is pre-work allowed? This changes §11.
- Is $99 for the Apple Developer Program needed (TestFlight for judges)?
- Do we have an Amazon Associates tag?
- Which Gemini models are available on the key or project (exact Pro and Flash model IDs)?
- Perceptron: Mk1 or Mk1.5 on our platform key, and the exact structured-annotation parameter.
- App name and branding.
