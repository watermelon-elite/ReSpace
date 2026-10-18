# H2: Perception & Spatial: Sub-spec

> **Owner:** H2 (builder #2). **Covers:** `server/perception/`, `server/geometry/`, `server/solver/`, `server/tests/`, `fixtures/contracts/categories.json`, the synthetic rooms, the debug tools.
> **Status:** decisions settled in a design review on 2026-10-17. This is a **sub-spec**: it does not edit `SPEC.md`. All three sub-specs (H1, H2, H3) will be merged later, and conflicts resolved then.
> **Vocabulary:** terms in **bold capitals** (Object, Addition, Anchor, Item, …) are defined in the [Glossary](#glossary) below. Each sub-spec carries its own glossary; they are merged with the specs.
> **Research behind the facts used here:** [`H2-research/roomplan-arkit-facts.md`](H2-research/roomplan-arkit-facts.md), [`H2-research/perceptron-facts.md`](H2-research/perceptron-facts.md).

---

## ⚠️ IMPORTANT: Changes to SPEC.md

**Read this section before merging.** Every row is a place where this sub-spec departs from `SPEC.md`. Line numbers refer to `SPEC.md` at commit `a265086`.

**Severity:**
- 🔴 **Contract**: breaks other people's code if they don't follow it.
- 🟠 **Behavior**: changes what the system does.
- ⚪ **Clarification**: fills a gap `SPEC.md` left open.

> **C0: Which spec governs (resolved).** H2 builds against `SPEC.md` only. The competing `SCANNING_RECONSTRUCTION_SPEC.md` (textured mesh, no backend) was deleted in commit `0058efe`, and `BUILDER_1_SPEC.md` also names `SPEC.md` as its sole source.

### 🔴 Contract changes (other people's code must follow)

| # | SPEC.md says | H2 decided | Affects | Details |
|---|---|---|---|---|
| C1 | Handoff signatures `detect`, `normalize_room`, `lift_and_merge`, `solve`, `check_overlaps` (566–571, 626–631) | New signatures. `lift_and_merge` is split into `lift_keyframe` (once per keyframe) and `merge` (cheap, re-run often). `solve` takes the request and an optional base Scene. `check_overlaps` takes the room. New `decode_depth` helper. | H3 | [§2](#2-python-interface-handoffs-to-h3) |
| C2 | Depth: "256×192 float16, about 100 KB" (215); multipart `jpeg, depth?, meta` (426) | Depth is **Float32** little-endian, row-major, sensor orientation (196 KB), **plus a UInt8 confidence map** as a second part (49 KB). `meta` gains `depth_w`, `depth_h`. | H1, H3 | [§3.4](#34-keyframe-upload-h1--h3--h2) |
| C3 | `keyframes` table (447) | New column `detections_3d jsonb`, which stores the `KeyframeLift` result for that keyframe | H3 | [§2](#2-python-interface-handoffs-to-h3) |
| C4 | RoomModel contract (364–386) | Added: `frame`, `walls[].normal`, `walls[].virtual`, walls in a fixed counter-clockwise order, `objects[].mount`, `objects[].fixed_in_place`, `story_business`, door/opening `keep_clear` zones in **every** mode. Removed: `attrs.material`. Changed: `attrs.color` is a hex value sampled from pixels. | H1, H3 | [§3.1](#31-roommodel) |
| C5 | DesignPlan contract (394–403); anchors `at_spot(x,z)` and `seating_group(zone\|wall, count, layout)` (284, 287) | `slot_id` → **`add_id`**. New **`priority`** on each Addition. `at_spot` has **no coordinates**. `seating_group` becomes `{group, layout, wall?}`, shared by a table Addition and a chair Addition. | H3 | [§3.2](#32-designplan-gemini-output) |
| C6 | Scene contract (405–415) | `slot_id` → `add_id`. Item IDs are deterministic (`i_<object_id>`, `i_<add_id>_<n>`). Exact meaning of `position`, `yaw` and `size` written down. | H1, H3 | [§3.3](#33-scene) |
| C7 | (none) | New shared file **`fixtures/contracts/categories.json`**, owned by H2: one row per category. It is the single list of category strings for RoomPlan, Mk1, stand-ins, catalog and Gemini. | H1, H3 | [§3.5](#35-categoriesjson) |
| C8 | PATCH returns `{overlaps, warnings}` (316, 433) | `check_overlaps` returns Item IDs **plus pseudo-IDs** `"wall"`, `"door:d1"` and `"keep_clear:z1"` | H1, H3 | [§2](#2-python-interface-handoffs-to-h3) |

### 🟠 Behavior changes

| # | SPEC.md says | H2 decided | Affects | Details |
|---|---|---|---|---|
| C9 | "Depth first", ray casting as the fallback (12, 24, 39, 236–237, 602, 658) | **Ray casting is the primary method**; depth only refines it. Research found `sceneDepth` is often nil during RoomPlan. H1 spends ≤30 min trying the "re-run config with `.sceneDepth`" workaround. | H1 | [§5.3](#53-lift_keyframe-detections--3d) |
| C10 | Boxes, polygons for rugs, points for outlets in one call; color/material in the same call; output kinds `box\|point\|polygon` (224–226) | Mk1.5 accepts **one** `annotation_format` per request. So: **one boxes-only call** per keyframe. Points are box centers; rugs are fitted from boxes. No color or material asked. | H3 (types only) | [§5.2](#52-detect-mk1) |
| C11 | Mk1 label lists (222–223) | Removed `tv`, `shelf` and `bar_stool`, because RoomPlan already sees them. `lamp` renamed to `table_lamp`. | (none) | [§5.2](#52-detect-mk1) |
| C12 | Color as Mk1 text, attached by nearest category (225, 242, 376) | Color is **sampled from keyframe pixels on the server** for RoomPlan and Mk1 Objects alike, using a box-based visibility mask. **No phone work** and no contract field. | H3 (passes the decoded JPEG) | [§5.4](#54-color-sampling) |
| C13 | `attrs.material` from Mk1 (242, 376) | Dropped. Gemini infers material from the 2–3 photos it already gets. | H3 (prompt) | (none) |
| C14 | Door clearance vague; business "door width plus 0.9 m" (243, 291) | Swing-aware rectangle on the room side for every door and opening, in every mode | (none) | [§5.1.4](#514-keep-clear-zones) |
| C15 | Place "largest footprint first"; aisle check removes "lowest-priority item" (289, 294) | Place by **priority**, with size breaking ties. Remove by reverse priority. Until H3 sets it, priority = plan order, with a log line. | H3 (to fill `priority`) | [§6.3](#63-algorithm) |
| C16 | "Lamps get a bonus within 1.5 m of an outlet" (295, 603); demo line "lamp placed near the outlet (say this out loud)" (673) | **Removed** from the solver. The demo line holds only if Gemini picks an Anchor near an outlet, or it is cut from the script. | H3, demo | (none) |
| C17 | Items that don't fit are dropped (293) | A **moved Object** that doesn't fit is **left in place** with a warning. It can't be dropped. | H1 (show warning) | [§6.3](#63-algorithm) |
| C18 | Story includes "Fitting 24 seats…" from the server (173, 382, 554) | Seats are only known per request. `story` holds room-only lines; `story_business` holds one template that **the app** fills with `{seats}`. | H1 | [§5.5](#55-story-lines) |
| C19 | Rugs as polygons from polygon corners (224, 238) | Rugs come from boxes: two bottom corners and the top-center are cast onto the floor, and a rectangle is fitted across keyframes | (none) | [§5.3](#53-lift_keyframe-detections--3d) |
| C20 | H2 schedule by hours; solver v2 at H18–26 (598–604) | Ordered task list, no hours. Solver v2 (business mode and re-solve) comes **before** the chat feature needs it. | H3 | [§8](#8-build-order) |

### ⚪ Clarifications (gaps filled)

| # | Topic (SPEC.md lines) | H2 decided | Details |
|---|---|---|---|
| C21 | Room coordinates (230) | Translation only: floor → y=0, floor bounding-box min → (0, 0). No rotation. Stored in `frame`. | [§5.1.1](#511-coordinate-frame) |
| C22 | Walls and corners (231, 233) | Floor polygon built from walls. Gaps closed with `virtual` walls. Curved walls become ≤0.5 m pieces (max 8). A corner exists only where walls meet at 45°–135°. | [§5.1.2](#512-walls-floor-corners) |
| C23 | Object IDs | Stable across recomputes. RoomPlan → `o#` in a deterministic order. Mk1 clusters reuse previous IDs; numbers are never reused. | [§5.6](#56-merge) |
| C24 | Mk1 vs RoomPlan duplicates | A Mk1 cluster inside a compatible RoomPlan footprint is absorbed: its label refines that Object's category. | [§5.6](#56-merge) |
| C25 | Anchor semantics (284–286, 290) | Exact definitions | [§6.1](#61-anchors) |
| C26 | Collisions (291–292) | Collision rules per class | [§6.2](#62-collision-rules) |
| C27 | Product sizes | Playwright-scraped sizes are trusted. Estimated or missing sizes are clamped to the category range or replaced by the default. | [§6.3](#63-algorithm) |
| C28 | Outside-room detections (new) | Mirror and window reflections are thrown out by a per-Mount position check | [§5.3](#53-lift_keyframe-detections--3d) |
| C29 | Objects vs wall features (379) | Wall features = outlet, light_switch, vent only. Art, mirror, TV and curtain are wall-mounted **Objects**. A radiator is a floor Object with `fixed_in_place`. | [§4](#4-domain-objects-vs-wall-features) |
| C30 | Vocabulary | "reference point" → **Anchor**; "slot" → **Addition**; "sighting" → **3D detection**; "Kept" ≠ "Fixed" | [Glossary](#glossary) |

---

## Glossary

H2's domain terms. Use these words in code, docs and prompts; the _Avoid_ lists name the synonyms to retire. Merged with the other sub-specs' glossaries later.

### The scanned room

**Object**:
Something that already exists in the scanned room, such as a sofa, a lamp or a framed print, found by RoomPlan or by Mk1.
_Avoid_: Furniture, existing item

**Wall feature**:
A fixed building fixture on a wall (outlet, light switch, vent) that is never redesigned and only informs where things go.
_Avoid_: Wall object, fixture

**Mount**:
Where an Object or new thing physically rests: on the floor, on a wall, on the ceiling, or on top of another Object.
_Avoid_: Placement type, surface

**Detection**:
A single result from Mk1 on one keyframe: a label and a 2D location in that image.
_Avoid_: Annotation, hit

**3D detection**:
One Detection placed in the room in 3D. An Object found by Mk1 is a cluster of 3D detections of the same thing seen from several keyframes.
_Avoid_: Sighting, lifted detection

**Kept**:
An Object the user has locked, which a redesign may not move or remove.
_Avoid_: Locked, pinned, fixed

### The design

**Anchor**:
A named relationship that says where something goes relative to the room ("against wall w2", "under sofa o3", "corner c2"), never a coordinate.
_Avoid_: Reference point, location, position

**Addition**:
A new thing the plan asks for, described by a category and an Anchor, before a Product is chosen for it. One Addition can ask for several units ("8 chairs").
_Avoid_: Slot, placeholder, request

**Priority**:
How important an Addition is to the design, ranked by Gemini (1 = most important). More important Additions are placed first and dropped last.
_Avoid_: Rank, score, weight

**Keep-clear zone**:
Floor area where nothing may stand except rugs and wall-mounted things: in front of every door and opening, and in business mode in front of the counter and register.
_Avoid_: Clearance zone, no-go area, door zone

**Item**:
One entry in a design: either an Object (left alone, moved or removed) or one unit of an Addition.
_Avoid_: Element, entry

**Product**:
A real thing the user can buy, from the curated catalog or a live shopping search.
_Avoid_: Listing, SKU, result

**Fixed**:
An Item the placement solver may not move in this solve: Kept Objects, Objects the plan doesn't mention, permanent fixtures like radiators, and, during a chat re-solve, every Item from the previous version.
_Avoid_: Locked, kept, frozen

---

## 1. What H2 delivers

1. `detect()`: one Mk1.5 call per keyframe, returning boxes in pixels.
2. `normalize_room()`: Apple `CapturedRoom` JSON → base RoomModel (RoomPlan Objects only), with story lines.
3. `lift_keyframe()`: one keyframe's Detections → 3D detections and color samples.
4. `merge()`: base room + all keyframe lifts → full RoomModel (Mk1 Objects, wall features, colors, story).
5. `solve()` and `check_overlaps()`: the placement solver.
6. `decode_depth()`: helper H3 uses to turn upload bytes into arrays.
7. `fixtures/contracts/categories.json`, the 3 synthetic RoomModels, and the test and debug tools (§7).

**Purity rule:** only `detect()` does I/O (it is `async`, over HTTP to Perceptron). Everything else is **synchronous, deterministic and pure**: Pydantic models and numpy arrays in, Pydantic models out. H3 loads from Postgres and GCS and passes the data in. Everything H2 writes is testable with pytest and no network.

---

## 2. Python interface (handoffs to H3)

```python
# server/perception/detect.py
async def detect(image_jpeg: bytes, mode: Literal["home", "cafe"]) -> list[Detection]

# server/geometry/depth.py
def decode_depth(depth_bytes: bytes, conf_bytes: bytes | None, w: int, h: int) -> DepthFrame
    # DepthFrame: depth float32[h, w] meters, conf uint8[h, w] (0 low, 1 medium, 2 high) or None

# server/geometry/normalize.py
def normalize_room(captured_room: dict, mode: str) -> RoomModel
    # RoomPlan Objects only; computes frame, walls, corners, openings, zones, story

# server/geometry/lift.py
def lift_keyframe(room: RoomModel, kf: Keyframe, detections: list[Detection],
                  image: np.ndarray,            # decoded JPEG, H×W×3 uint8, sensor orientation
                  depth: DepthFrame | None) -> KeyframeLift
    # KeyframeLift = {kf_idx, detections_3d: [...], color_samples: [...], rejected: [...]}
    # H3 stores the result in keyframes.detections_3d (jsonb)

# server/geometry/merge.py
def merge(base_room: RoomModel, lifts: list[KeyframeLift],
          previous_room: RoomModel | None = None) -> RoomModel
    # previous_room keeps Mk1 Object IDs stable across recomputes

# server/solver/solve.py
def solve(room: RoomModel, plan: DesignPlan, products: dict[str, Product],  # keyed by add_id
          request: DesignRequest, base: Scene | None = None) -> Scene
    # base given ⇒ every Item in base is Fixed, and plan is a delta (chat edit)

def check_overlaps(room: RoomModel, scene: Scene, item_id: str) -> list[str]
    # Item IDs plus pseudo-IDs: "wall", "door:d1", "keep_clear:z1"
```

**When H3 calls them:**
- **Keyframe upload, before finalize:** `detect()` only. Store the Detections.
- **Finalize:**
  1. `normalize_room()`.
  2. `lift_keyframe()` for every keyframe already stored (the backlog).
  3. `merge()`.
- **Keyframe upload, after finalize:** `detect()`, then `lift_keyframe()` for that one keyframe, then `merge(base_room, all_lifts, previous_room)`.

> **Flag for H3 (not decided here):** two late keyframes finishing at once can race on writing `room_model`: each reads the lift results, then writes, and the last write wins with stale input. A row lock on the room, or recomputing in `GET /rooms/{id}`, avoids it. Also measure whether finalize, including the backlog lift, fits NFR-01's 3 s. If not, return the base room first and let small items arrive on the poll.

**Internal types** (H2 owns them in `server/perception/types.py` and `server/geometry/types.py`):

```python
class Detection(BaseModel):     # 2D, one keyframe
    label: str                  # a category id from categories.json
    box_px: tuple[float, float, float, float]   # x1, y1, x2, y2 in the uploaded image's pixels

class Detection3D(BaseModel):   # one Detection placed in the room
    label: str
    kf_idx: int
    position: tuple[float, float, float]        # room frame, meters
    size: tuple[float, float, float] | None     # [w, d, h] estimate
    wall: str | None                            # for wall Mount / wall features
    floor_points: list[tuple[float, float]] | None  # rugs only: cast corner points
    method: Literal["raycast", "raycast+depth"]

class ColorSample(BaseModel):
    target: str                 # object_id (RoomPlan) or "det:<index into detections_3d>"
    rgb: tuple[int, int, int]   # median of the masked pixels in this keyframe
    n_px: int
```

---

## 3. Contracts

### 3.1 RoomModel

Changes from SPEC.md §6 are marked `// NEW` or `// CHANGED`.

```jsonc
{
  "room_id": "r_8f2",
  "mode": "home",
  "height": 2.6,
  "frame": { "room_from_world": [1,0,0,0, 0,1,0,0, 0,0,1,0, 1.99,1.33,-0.18,1] }, // NEW: 4×4, column-major (same layout as Apple's)
  "floor": { "polygon": [[0,0],[4.2,0],[4.2,3.6],[0,3.6]], "area_m2": 15.1 },
  "walls": [                                                   // CHANGED: counter-clockwise order (see §5.1.2)
    { "id": "w1", "a": [0,0], "b": [4.2,0], "length": 4.2,
      "normal": [0,1],                                         // NEW: unit (nx, nz), points INTO the room
      "virtual": false }                                       // NEW: true = gap filler; never used by Anchors
  ],
  "corners": [{ "id": "c1", "at": [0,0], "walls": ["w4","w1"] }],
  "openings": [
    { "id": "win1", "type": "window", "wall": "w1", "offset": 0.8, "width": 1.4, "sill": 0.9, "height": 1.2 },
    { "id": "d1", "type": "door", "wall": "w3", "offset": 0.2, "width": 0.85 },
    { "id": "op1", "type": "opening", "wall": "w2", "offset": 1.0, "width": 1.6 }  // doorless; RoomPlan "opening"
  ],
  "objects": [
    { "id": "o3", "category": "sofa", "source": "roomplan", "center": [2.1,3.1], "yaw": 3.14,
      "size": [2.1,0.9,0.8], "against_wall": "w3",
      "mount": "floor",                                        // NEW: floor | wall | ceiling | tabletop
      "attrs": { "color": "#8A8D91" } },                       // CHANGED: hex from pixels; no "material"
    { "id": "s1", "category": "floor_lamp", "source": "mk1", "center": [0.3,0.4], "yaw": 0,
      "size": [0.4,0.4,1.6], "sightings": 4, "mount": "floor", "attrs": { "color": "#D9CBB0" } },
    { "id": "s2", "category": "radiator", "source": "mk1", "center": [3.9,1.2], "yaw": 4.71,
      "size": [1.0,0.1,0.6], "sightings": 3, "mount": "floor",
      "fixed_in_place": true }                                 // NEW: blocks placement; plan can't move/remove
  ],
  "wall_features": [{ "id": "f1", "type": "outlet", "wall": "w1", "offset": 2.9, "height": 0.3 }],
  "zones": [                                                   // CHANGED: door/opening zones in EVERY mode
    { "id": "z1", "type": "keep_clear", "reason": "door", "polygon": [[...]] },
    { "id": "z2", "type": "keep_clear", "reason": "counter", "polygon": [[...]] }  // business mode only
  ],
  "style_hints": { "floor": "light oak", "walls": "white" },
  "story": ["Measuring your 3.4 m window wall…", "Keeping 0.9 m clear in front of your door…"],
  "story_business": "Fitting {seats} seats with 91 cm aisles…", // NEW: app replaces {seats}
  "status": { "pending_keyframes": 0 }
}
```

- `sightings` keeps its SPEC.md name in the JSON. In the glossary it means "number of 3D detections in the cluster".
- `center` is (x, z) and `size` is `[w, d, h]`, as in SPEC.md.

### 3.2 DesignPlan (Gemini output)

```jsonc
{ "summary": "Warm Japandi reading corner by the window",
  "moves":   [{ "object_id": "o5", "anchor": { "type": "against_wall", "wall": "w2", "align": "center" }, "reason": "…" }],
  "removes": [{ "object_id": "o7", "reason": "…" }],
  "adds": [
    { "add_id": "a1",                    // CHANGED: was slot_id
      "priority": 1,                     // NEW: 1 = most important. Missing → plan order + log line
      "category": "rug", "catalog_ids": ["cat_rug_04","cat_rug_09"], "query": null,
      "max_price": 150, "qty": 1, "anchor": { "type": "under", "object": "o3" }, "reason": "Grounds the seating area" },
    { "add_id": "a2", "priority": 2, "category": "table_lamp", "catalog_ids": [], "query": "ceramic table lamp",
      "max_price": 60, "qty": 1, "anchor": { "type": "on_top_of", "object": "o4" }, "reason": "…" },
    { "add_id": "a3", "priority": 3, "category": "plant", "qty": 1,
      "anchor": { "type": "at_spot" }, "reason": "…" }       // CHANGED: no coordinates; solver reads request.spot
  ] }
```

**Business seating group.** Two Additions share one Anchor:

```jsonc
{ "add_id": "a4", "priority": 1, "category": "dining_table", "qty": 6,
  "anchor": { "type": "seating_group", "group": "g1", "layout": "4top", "wall": null } },
{ "add_id": "a5", "priority": 1, "category": "chair", "qty": 24,
  "anchor": { "type": "seating_group", "group": "g1", "layout": "4top", "wall": null } }
```

- `layout`: `2top | 4top`.
- Bar seating is a single stool Addition anchored with `against_wall` or `next_to` the counter, with `qty` = stools.
- **Gemini schema (H3):** the Anchor object stays **flat**. All fields are optional except `type`: `type, wall, align, offset, corner, object, side, distance, opening, height, group, layout`.

### 3.3 Scene

```jsonc
{ "design_id": "d_31", "parent_id": null, "summary": "…", "total_price": 612.40,
  "warnings": ["Couldn't fit the bookshelf", "Couldn't move the sofa to the window wall, left it in place"],
  "items": [
    { "id": "i_a1_1",                    // CHANGED: deterministic. New: i_<add_id>_<n>. Existing: i_<object_id>
      "status": "new", "object_id": null, "add_id": "a1",   // CHANGED: was slot_id
      "product": { … }, "alternatives": ["p_10","p_11"], "reason": "…", "render": { … },
      "position": [1.9, 0.0, 2.4], "yaw": 3.14, "size": [2.4, 3.0, 0.01],
      "original": null },
    { "id": "i_o3", "status": "existing", "object_id": "o3", "add_id": null,
      "position": [2.1, 0.0, 3.1], "yaw": 3.14, "size": [2.1, 0.9, 0.8], "original": { "position": [2.1,0,3.1], "yaw": 3.14 } }
  ] }
```

**Position and orientation conventions (H1 renders by these):**
- **`position`** = `[x, y, z]` of the Item's **bottom-center**, in the room frame. This matches the stand-in origin in SPEC.md §5.10.
  - `y = 0` for floor items.
  - `y` = the surface top for `on_top_of` items.
  - `y` = the bottom edge for wall items.
- **`yaw`** is in radians, a rotation about **+y by the right-hand rule**. At `yaw = 0` the Item's front faces **+z**. Front direction = `(sin yaw, cos yaw)` in (x, z). Positive yaw turns counter-clockwise seen from above.
- **`size`** = `[w, d, h]` in the Item's own axes. For wall items, `d` is the thickness.
- Every Object appears as an Item:
  - `existing` = untouched (Fixed).
  - `moved` = moved by the plan.
  - `removed` = removed; H1 shows it as a ghost.

### 3.4 Keyframe upload (H1 → H3 → H2)

`POST /v1/rooms/{id}/keyframes` multipart:

| Part | Format |
|---|---|
| `jpeg` | Longest edge 1280 px, sensor orientation (landscape, **not rotated**) |
| `depth` (optional) | Raw **Float32** LE, row-major, `depth_w × depth_h` (usually 256×192), sensor orientation, meters |
| `confidence` (optional, with depth) | Raw **UInt8**, same size: 0 low, 1 medium, 2 high |
| `meta` | `{idx, w, h, intrinsics: {fx, fy, cx, cy} rescaled to the 1280 px image, transform: [16 floats column-major camera-to-world], timestamp, depth_w?, depth_h?}` |

- Depth intrinsics are derived on the server: scale by `depth_w / w`.
- Only pixels with confidence = 2 and depth < 5 m are used.

### 3.5 categories.json

`fixtures/contracts/categories.json` is owned by H2 and written during the contracts session. Each component reads it:
- **H3:** loads the `id` list as Gemini's category enum.
- **H1:** looks up `standin` and `default_tint`.
- **H2:** uses everything else.

```jsonc
[
  { "id": "sofa", "mount": "floor", "collision_class": "floor",
    "default_size_m": [2.0, 0.9, 0.8], "size_range_m": [[1.2,0.7,0.6],[3.2,1.8,1.1]],
    "standin": "sofa", "default_tint": "#9A9590",
    "roomplan_sources": ["sofa"], "mk1_label": null, "absorbs_into": [] },
  { "id": "shelf", "mount": "floor", "collision_class": "floor",
    "default_size_m": [0.8, 0.35, 1.8], "size_range_m": [[0.3,0.2,0.4],[2.5,0.6,2.6]],
    "standin": "bookshelf", "default_tint": "#B08D63",
    "roomplan_sources": ["storage"], "mk1_label": null, "absorbs_into": [] },
  { "id": "counter", "mount": "floor", "collision_class": "floor",
    "default_size_m": [2.0, 0.7, 1.05], "size_range_m": [[0.8,0.4,0.8],[6.0,1.2,1.2]],
    "standin": "counter", "default_tint": "#7A6A58",
    "roomplan_sources": [], "mk1_label": "counter", "absorbs_into": ["table", "storage"] },
  { "id": "table_lamp", "mount": "tabletop", "collision_class": "tabletop",
    "default_size_m": [0.3, 0.3, 0.5], "size_range_m": [[0.12,0.12,0.2],[0.6,0.6,0.9]],
    "standin": "table_lamp", "default_tint": "#E8DCC4",
    "roomplan_sources": [], "mk1_label": "table_lamp", "absorbs_into": [] },
  { "id": "outlet", "mount": "wall", "collision_class": "none", "wall_feature": true,
    "mk1_label": "outlet", "roomplan_sources": [] }
]
```

| Field | Meaning |
|---|---|
| `mount` | `floor \| wall \| ceiling \| tabletop` |
| `collision_class` | `floor \| rug \| wall \| tabletop \| ceiling \| none` (rules in §6.2) |
| `default_size_m`, `size_range_m` | `[w, d, h]`. Used when a Product's size is estimated or missing (§6.3), and for sanity checks on 3D detections |
| `roomplan_sources` | RoomPlan categories that map to this id. Uses iOS 17 attributes where useful (`storage` + `StorageType.shelf` → `shelf`, `chair` + `ChairType.stool` → `stool`) |
| `absorbs_into` | RoomPlan-derived categories this Mk1 label may refine (§5.6) |
| `wall_feature` | `true` only for outlet, light_switch and vent |

---

## 4. Domain: Objects vs wall features

- **Wall feature:** a fixed building fixture that is never redesigned. Only `outlet`, `light_switch` and `vent`. Stored in `wall_features` as (wall, offset, height). Used only as a hint for Gemini.
- **Object:** everything else. Each has a `mount`:
  - `wall`: wall_art, mirror, tv, curtain. They can be moved, removed or Kept.
  - `ceiling`: ceiling_light, pendant_light. They never block floor placement.
  - `floor`: everything else. A radiator is a floor Object with `fixed_in_place: true`: it blocks placement, but the plan can't move or remove it.

---

## 5. Perception and room building

### 5.1 `normalize_room`: CapturedRoom → base RoomModel

**Parsing Apple's JSON** (see [research §1–3](H2-research/roomplan-arkit-facts.md)):
- **Transforms:** `transform` is **16 floats, column-major**. `M = np.array(t).reshape(4,4).T`. Also accept a nested 4×4 array, defensively.
- **Enums:** they encode as `{"case": {payload}}`. Take the single key. A door is `{"door": {"isOpen": true}}`.
- **Unknown keys:** ignore them, especially the large `coreModel` blob. Parse `attributes` leniently.
- **Walls:** column 0 of the transform is along the wall, column 1 is up, column 3 is the center. `dimensions = (width, height, 0)`.
- **Objects:** `dimensions = (width, height, depth)`, which must be **reordered** to our `[w, d, h]`.
- **Doors and windows:** link to their wall via `parentIdentifier` (iOS 17+). Openings without a parent go to the nearest wall.
- **Multiple floors or sections:** take the largest.

#### 5.1.1 Coordinate frame
- Floor height = the floor transform's y, or wall center y − height/2. It is roughly −1.3 m in practice, **not 0**.
- `room_from_world` = translation only: floor → y=0, floor polygon bounding-box min → (0, 0). **No rotation.**
- Applied to every RoomPlan transform here, and to every camera pose in `lift_keyframe`.

#### 5.1.2 Walls, floor, corners
1. Project wall segments onto (x, z) and snap endpoints that lie within 0.3 m of each other.
2. **Build the floor polygon from the walls.** RoomPlan's `floors[].polygonCorners` is only a cross-check, because its local axes are undocumented and reported to be confusing.
3. **Gaps:** if the walls don't close, join consecutive endpoints with `virtual: true` walls. Virtual walls bound the floor but are never used by `against_wall` or `on_wall`.
4. **Curved walls** (`curve` ≠ null): split into straight pieces about 0.5 m long (max 8). Each piece gets its own sequential wall ID. If `curve` can't be parsed, use the straight line between the ends.
5. **Order and normals:** order the walls **counter-clockwise**, meaning the signed area `½·Σ(xᵢ·zᵢ₊₁ − xᵢ₊₁·zᵢ)` is > 0. Number them `w1…` starting from the wall nearest the (0, 0) corner. `normal = (−dz, dx)/len` for direction `a→b`. This points into the room.
6. **Corners:** `c1…` only where two **real** walls meet at an angle between 45° and 135°.

#### 5.1.3 Objects
- Category comes from `roomplan_sources` in categories.json (with iOS 17 attributes). The parser reorders `size` to `[w, d, h]` and sets `yaw` from the transform.
- **Facing check (day 1):** verify with the overlay that RoomPlan Objects face their local +z (for example, a sofa's seat side). If they don't, add a fixed correction here, once.
- `against_wall`: an Object within 0.3 m of a real wall and parallel to it.
- **IDs:** `o1…`, ordered by (category, x, z), assigned here. Deterministic, so finalize always yields the same IDs.

#### 5.1.4 Keep-clear zones
- **Every door and opening**, in every mode, gets a rectangle on the room side (along `normal`):
  - **Width** = the opening width + 0.15 m on each side.
  - **Depth** = max(mode minimum, swing depth).
    - Mode minimum: **0.9 m** home, **1.2 m** business.
    - Swing depth for a **door**: the full width (assume a single hinged door swinging in, because RoomPlan never reports the door type or swing). If the width is > **1.2 m**, assume a double door: half the width.
    - Swing depth for an **opening** (doorless): 0.
- Trimmed to the floor polygon. `type: keep_clear`, `reason: "door"` or `"opening"`.
- **Business mode also:** 1.2 m deep in front of the counter and register (`reason: "counter"` or `"register"`). These are added by `merge`, because counters often come from Mk1.
- Only **rugs** and **wall-mounted** items may overlap a keep-clear zone.

### 5.2 `detect` (Mk1)

- **Model:** `perceptron-mk1.5` (env `PERCEPTRON_MODEL`). Fallback `perceptron-mk1`. Isaac models are retired.
- **API:** base `https://api.perceptron.inc/v1`, `Authorization: Bearer`. SDK `perceptron` v0.4.0 (`AsyncClient`).
- **One boxes-only call per keyframe:**
  1. **First choice:** `POST /v1/detect` with `categories` = the label list. It returns **pixel** boxes as JSON. **Spike check:** it says it uses "its own supported model"; confirm it is good enough.
  2. **Otherwise:** chat completions with `vision_config={"annotation_format": "box"}`, parsed with `response.annotations()`. Coordinates are on a **0–1000 grid, origin top-left** → `px = x·W/1000`, `py = y·H/1000`.
- **No color or material in the prompt.** Mk1 is used only for what RoomPlan can't see.
- **Labels:**
  - Home: `table_lamp, floor_lamp, plant, wall_art, mirror, rug, curtain, ceiling_light, outlet, light_switch, radiator, vent`
  - Café adds: `counter, espresso_machine, menu_board, register, display_case, pendant_light, trash_bin`
- **Output:** `list[Detection]` (boxes in pixels of the uploaded image). Point-like labels (outlet, switch, vent) use the box center later.
- **Limits:**
  - Max 40 keyframes per room.
  - Timeout ~20 s; on failure return `[]` (NFR-07).
  - Log `usage` tokens.
  - Perceptron's default limit is 300 req/min per organization, with a 120 s budget per request. The SDK does **not** retry; retry once on 429 using `Retry-After`.

### 5.3 `lift_keyframe`: Detections → 3D

**Camera math (ARKit convention):**
- The camera looks down **−z**, y up. Pixel v grows downward.
- Ray in camera space with unit forward component: `r = ((u−cx)/fx, −(v−cy)/fy, −1)`.
- World direction = `R_cam · r`. Then apply `room_from_world` to both the origin and the direction.
- **Depth is z-depth** (distance along the optical axis), so the depth point = camera origin + `d · (R_cam · r)` with no cosine factor. This is confirmed in Apple's docs; the overlay double-checks it.
- **Depth pixel** = image pixel × `depth_w / w`.

**Which pixel and which surface:** chosen by the category's Mount.

| Category | Ray pixel | Surfaces the ray may hit |
|---|---|---|
| Wall Mount, wall features | box center | real wall rectangles only |
| Ceiling Mount (pendant, ceiling light) | **box top-center** | ceiling plane `y = height` |
| `CAN_SIT_ON_SURFACE = {table_lamp, plant, decor}` | box bottom-center | the top face of an Object whose category is in `SURFACES = {table, desk, nightstand, dresser, counter, shelf}` if the ray hits it first, else the floor plane |
| Every other floor Mount (floor_lamp, radiator, …) | box bottom-center | floor plane `y = 0` only. Never a surface, whatever the ray passes. |
| Rug | bottom-left, bottom-right and top-center of the box | floor plane; points stored in `floor_points` |

- **Depth refinement:** when a depth pixel has confidence 2 and is < 5 m, take its point. If it is within **0.3 m** of the ray-cast point, use the depth point's (x, z) and keep the surface's y. Otherwise the ray cast wins. `method` records which happened.
- **Hidden base:** accepted. If a sofa hides a lamp's base, the floor hit is too close. Averaging across keyframes mostly corrects it.
- **Size estimate:** width ≈ box width × distance / fx, height ≈ box height × distance / fy. Out of `size_range_m` → `default_size_m`.
- **Outside-room filter:** catches reflections in mirrors and windows. Every rejection is logged with label and `kf_idx`.
  - Floor, tabletop and ceiling Mounts: must lie inside the floor polygon shrunk by **0.05 m**.
  - Wall Mount and wall features: must lie within **0.15 m** of a **real** wall along its normal, and between its ends.
- Also produces this keyframe's color samples (§5.4).

### 5.4 Color sampling

The goal is a tint for stand-ins and input for "Match what I have". The color is what the camera saw, not the true surface color: white balance and shadows shift it.

- **RoomPlan Objects:**
  1. Render a **z-buffer** at about 160×120 of the RoomModel's walls and Object boxes from this keyframe's camera. Each pixel gets the ID of the nearest box.
  2. Erode each Object's mask by 2 px.
  3. If depth is present, also keep only pixels whose depth is within ±0.15 m of the z-buffer depth.
  4. Emit the median RGB of the masked pixels as a `ColorSample` if the mask has ≥ 1 px. `merge` decides which views count.
- **Mk1 Objects:** take the median RGB of the **center 50%** of the Detection box.
- **Bonus:** the same z-buffer, drawn over the keyframe, is the alignment check between RoomPlan and the camera poses (research §7).

### 5.5 Story lines

These are fill-in templates. Each is used **only if the room has what it mentions**. Show 3–5 lines, always ending with a generic one. Recomputed in `merge` so they can mention small items.

1. "Measuring your {len} m window wall…" uses the longest wall with a window.
2. "Keeping {depth} m clear in front of your door…" uses the largest door zone.
3. "Finding a rug that fits under your {sofa|bed}…" if the room has a sofa or bed.
4. "Working around your {n} m² of floor…" is always available.
5. "Checking walkways…" is always last.

`story_business` = `"Fitting {seats} seats with 91 cm aisles…"`. **The app** fills in `{seats}`.

### 5.6 `merge`

1. Collect the 3D detections from all `KeyframeLift`s.
2. **Cluster** by label within **0.4 m** (0.2 m for wall features). Average the positions.
   - Keep a cluster if it has ≥ 2 3D detections. Rugs, wall_art and counter need only 1.
   - **Rugs:** fit `minimum_rotated_rectangle` over all of the cluster's `floor_points`.
3. **Absorb duplicates:** if a cluster lies inside a RoomPlan Object's footprint expanded by 0.2 m, and the Object's category is in the label's `absorbs_into`, refine that Object's category (for example `storage` → `display_case`). No new Object is created.
4. **Wall features** snap to the nearest real wall within 0.15 m → (wall, offset, height).
5. **Stable IDs:** reuse the ID from `previous_room` when a cluster has the same category and lies within 0.4 m of an old Object. Otherwise allocate the next `s#`. **Numbers are never reused** within a room.
6. **Colors:** for each target, take the median across its best **3–5** samples, ranked by `n_px`. RoomPlan Objects need ≥ 200 px in total, otherwise no color, and H1 uses `default_tint`. Write `attrs.color` as `#RRGGBB`. (Optional later: a second color from 2-means for multi-colored Objects.)
7. Add business keep-clear zones (counter, register), then the story lines.

---

## 6. Placement solver

### 6.1 Anchors

| Anchor | Meaning |
|---|---|
| `against_wall(wall, align, offset?)` | Back of the Item 5 cm from the wall, facing along its normal (`yaw = atan2(nx, nz)`). `align` is judged by someone standing in the room facing that wall. `offset` = meters from that end (default 0; ignored for `center`). Real walls only. |
| `corner(corner)` | Pushed into the corner with 5 cm gaps. Seating faces along the bisector into the room; anything else lines up with the longer wall. |
| `under(object)` | Rugs only. Centered on the Object's footprint, same yaw. |
| `next_to(object, side)` | `left` and `right` are the Object's own left and right; `front` is the direction it faces. 10 cm gap. Same yaw as the Object, except `front`, which faces it. |
| `facing(object, distance?)` | In front of the Object, facing it. Default gap between footprints: 0.45 m for tables, 0.8 m for seating. |
| `in_front_of_window(opening)` | `against_wall` on the window's wall, centered on the window. If the Item is taller than the sill, use nudges; if it still doesn't fit, drop it. |
| `room_center` | Centroid of the floor polygon, aligned with the longest wall |
| `on_wall(wall, align, height?)` | Default center height 1.45 m, or 0.25 m above the top of any furniture directly below, whichever is higher. Real walls only. |
| `on_top_of(object)` | Centered on the top of an Object in `SURFACES`. Fails if the Item's footprint is larger than that top. Gemini chooses this for new table lamps. |
| `at_spot` | `request.spot` (room frame, from the app's tap). If `spot.wall` is set, the solver treats it as `on_wall` at that offset and height. |
| `seating_group(group, layout, wall?)` | Pairs the table and chair Additions of a `group`. Builds one table-with-chairs unit (`2top`/`4top`) and repeats it in rows across the free floor, or along `wall`. |

### 6.2 Collision rules

Each Item uses its category's `collision_class`. Every check adds a **5 cm margin**.

| Class | Collides with |
|---|---|
| `floor` | floor Items, walls, keep-clear zones. Existing Mk1 small Objects (lamps, plants) count: a corner holding a plant is not free. |
| `rug` | other rugs and walls only. Can sit under furniture and in keep-clear zones. |
| `wall` | wall Items, openings, and floor Items against the same wall that are taller than this Item's bottom edge |
| `tabletop` | other Items on the same top only |
| `ceiling`, `none` | nothing |

### 6.3 Algorithm

1. **Fixed Items:** every Object not in `moves`/`removes`, every **Kept** Object, every `fixed_in_place` Object, and, when `base` is given, every Item in `base`.
2. **Priority:** if an Addition has no `priority`, set it from its position in the plan and log `priority missing, using plan order` once. H3 fills it in later.
3. **Sizes:**
   - Product `dims_source = scraped`: trusted as-is (Playwright already range-checks them, SPEC.md §5.9).
   - Estimated sizes: clamped to `size_range_m`.
   - Missing sizes: `default_size_m`.
   - Product dims are read as width (the Item's left-right), depth (front-back), height.
4. **Order:**
   1. Apply removes.
   2. Apply moves.
   3. Place Additions by **priority**, with the larger footprint first on ties. `qty > 1` expands into units `i_<add_id>_1…n`.
5. **Each placement:** compute the candidate from the Anchor and check collisions (§6.2). On collision, try nudges in this order:
   1. Slide along the wall in ±0.1 m steps up to ±1.0 m.
   2. Rotate 90°.
   3. Try the next-best Anchor (for example, a free corner).
6. **If nothing fits:**
   - **New Item:** drop it, with a warning ("Couldn't fit the bookshelf, no free wall space").
   - **Moved Object:** leave it at its **original position** with `status: "existing"`, and add a warning ("Couldn't move the sofa to the window wall, left it in place").
7. **Aisle check** (business mode and redesign):
   1. Shrink the free floor by 0.45 m (half of a 0.9 m aisle).
   2. If any door's keep-clear zone is no longer connected to the free area, remove the **lowest-priority** new Item and repeat. A seating group loses a whole table-with-chairs unit at a time. Objects are never removed.
   3. Each removal adds a warning.
8. **Output:** a `Scene` with every Object as an Item, plus the placed new Items.

**Chat re-solve:** `solve(..., base=previous_scene)`. Every Item in `base` is Fixed; `plan` holds only the delta (new `add_id`s are never reused; H3 makes sure of this).

**`check_overlaps(room, scene, item_id)`:** after a manual drag, it only reports and never moves. Return values:
- overlapping Item IDs, plus
- `"wall"`
- `"door:<opening_id>"`
- `"keep_clear:<zone_id>"`

---

## 7. Tests and debug tools

| Tool | What it does |
|---|---|
| **Camera round-trip test** | Pick known 3D points, project them through a synthetic ARKit camera to Detections (and a depth map), run `lift_keyframe`, and assert the points come back within **1 cm**. Catches the flipped image y-axis, unscaled intrinsics, row/column-major transforms and the missing floor offset, before any real data. No images needed. |
| **Top-down plot** | `python -m server.geometry.plot room.json [scene.json] -o out.png` (matplotlib). Draws walls (with normals and a `virtual` style), openings, keep-clear zones, Object and Item footprints with IDs, and Anchor targets. |
| **Debug overlay** (P0 for the team, SPEC.md §5.3) | Draws the RoomPlan box corners, the z-buffer mask and the 3D detections back onto a keyframe. If they don't line up, every later step is wrong. |
| **Solver tests** (pytest) | On the 3 synthetic rooms and the recorded rooms, assert no overlapping footprints, keep-clear zones empty except for rugs and wall items, seat targets met, deterministic Item IDs, the priority fallback works, and failed moves stay in place. |
| **Synthetic RoomModels** | Rectangular living room, L-shaped room, 8×6 m café with counter and 2 doors. |
| **Backup real data** | If H1's recordings are late: Apple **ARKitScenes** (real LiDAR captures with poses, intrinsics, depth and labelled 3D boxes). Downloaded room meshes were considered and rejected: they need rendering and give nothing for the `CapturedRoom` parser. |

---

## 8. Build order

These steps are ordered, not timed. **External handoffs are in bold.**

1. Contracts session: write `categories.json` and hand-write the 3 synthetic RoomModels. **Synthetic rooms and categories.json → H1, H3.**
2. Mk1 spike:
   - Check whether `/v1/detect` quality is enough, else use chat with `annotation_format=box`.
   - Confirm the coordinate format, latency and tokens per image.
   - Write `detect()`. **`detect()` → H3.**
3. Top-down plot and camera round-trip test.
4. Solver v1:
   - Anchors except `seating_group`; collisions; nudges; drop and warn; keep-clear zones.
   - Priority with its fallback; failed moves left in place.
   - `check_overlaps()`.
   - **`solve()` v1 → H3.**
5. `normalize_room()` on H1's real recording:
   - Wall order and normals; gap filling; curved walls; corners.
   - Stable IDs; the frame transform; keep-clear zones; story lines.
   - Check object facing and frame alignment with the overlay.
   - **`normalize_room()` → H3.**
6. `lift_keyframe()` and `merge()`:
   - Ray casting by Mount, with depth refinement; the outside-room filter.
   - Clustering, absorbing duplicates, stable IDs.
   - Color sampling with the z-buffer mask; debug overlay.
   - **`lift_keyframe()` and `merge()` → H3** (replaces the old `lift_and_merge` handoff).
7. Solver v2: `seating_group`, the aisle check, business keep-clear zones, re-solve with `base`. **Solver v2 → H3, before the chat feature needs it.**
8. Tuning on the café recording and live scans. Stretch: FR-25.

**Cut order if behind:**
1. Second color per Object.
2. Mk1 Object colors.
3. Curved walls (use the straight line between the ends).
4. Seating-group layout polish.

---

## 9. Day-1 checks

| Check | Who | If it fails |
|---|---|---|
| Real iOS 18 `CapturedRoom` JSON with a **door and window**: key names, enum encoding, `curve` and `attributes` format | H1 records → H2 parses | Parser adjusts. No public full sample exists. |
| RoomBuilder output and live camera poses share one world frame (overlay) | H2 | Find the transform once and store it in `frame` |
| RoomPlan Objects face local +z | H2 (overlay) | Fixed correction in `normalize_room` |
| `sceneDepth` during RoomPlan; the re-run-with-`.sceneDepth` workaround (≤30 min) | H1 | Ray casting only (already the primary method) |
| Depth is z-depth (overlay: items near image edges land at the right distance) | H2 | Switch to ray-length depth |
| `/v1/detect` model quality vs chat `annotation_format=box`; tokens per image; latency | H2 | Use chat completions |
| Collect keyframe poses only after `captureSession(_:didStartWith:)`, in the same run (origin can reset per `run`) | H1 | Poses don't line up |
