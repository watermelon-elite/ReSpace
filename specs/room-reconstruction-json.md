# Restricted reconstruction format and historical proposal

## Current planning reader (2026-10-18)

`backend/respace/reconstruction.py` consumes the restricted version-2 contract below. The remainder of this document preserves the earlier proposal as historical rationale, not wire-field authority. The newer exporter contract is [ROOM_JSON.md](../docs/reconstruction/ROOM_JSON.md); it is deliberately richer and is not wholly accepted by this reader.

| Record | Accepted fields and meaning |
|---|---|
| Root | `schema_version: 2`, `units: meters`, `up_axis: +Y`, positive `height`, rigid column-major `room_from_world`, `node_pivot: bottom_center` or `box_center`; floor polygon has positive winding. All numeric evidence must be finite. |
| Wall | `id`, endpoints `a`/`b` in X/Z, `length`, `inward_normal`, `virtual`, optional `node_name`; at least three walls close one loop. |
| Protrusion | `depth` greater than zero and less than one meter, `bottom`, `top`, `from_a`, `to_a`, optional `entity_id`. Larger protrusions remain unsupported in this restricted reader. |
| Opening | `id`, type door/window/opening, `wall_id`, `offset` to near edge, `width`, `bottom`, `height`, optional `node_name`. The wire key is `offset`, not the earlier `offset_from_a`. |
| Entity | `id`, category, `center: [x,z]`, `base_y`, `yaw`, `size: [width,depth,height]`, scalar `mount` floor/wall/tabletop/ceiling, optional `node_name`, `fixed_in_place`, `wall_id`/`support_id`. The earlier `position` and object-shaped mount examples are not accepted. |
| Other category | Requires explicit collision class floor/wall/tabletop/ceiling/none; retained as stationary obstacles. |
| Surface | `top`, optional polygon and holes, positive `clearance_above` when supplied, optional `clearance_limited_by`. |

Inset mounts, zero clearance, and logical groups (`member_ids`, including a counter without physical geometry) remain deferred by user decision. Unsupported input yields `validity.usable: false` with reasons; it must not become a fabricated valid placement. Door/opening zones reserve 1.2 m depth and 0.45 m on each side, clipped to the wall and floor. Source USDZ nodes must already be in the documented room frame; composition rejects mismatches.

The `sample_room_2/room.json` diagnostic pair carries `planning_eligible: false`: the wall attachment and USDZ frame disagree. Re-export both files from the original capture before clearing quarantine. Its measurements are intentionally retained. The old kitchenette v1 import remains Product planning context only.

## Historical proposal


Status of the historical proposal below: superseded by the current reader contract above. `SPEC.md` remains governing.

The team plans to use the JSON that ships with the sample room reconstruction
(`sample_kitchen_room/kitchenette.json`, untracked) as the standard room format.
This document records what that format is missing for placing Products into the
room, and proposes the fields to add.

Evidence: three SPAR3D Product reconstructions were placed into the sample room,
checked for fit and packaged into one USDZ. Placement only succeeded by reading
geometry out of the USD file and measuring meshes, because the JSON alone could
not answer "where is this, which way does it face, how big is it, and what can I
put on it?"

## Summary

The JSON says what each thing in the room is, but not exactly where it is, which
way it faces or how big it really is. A Product placement pipeline needs all
three. The fix is to add a small number of fields that the room exporter already
knows, because it built the 3D model, and to align names with `SPEC.md` and
`CONTEXT.md`.

## What the sample format contains today

```json
{
  "schema_version": 1,
  "coordinate_system": "meters_y_up_floor_zero",
  "translation_from_scan": [1.108, 1.498, 5.886],
  "bounds_min": [0, 0, 0], "bounds_max": [3.969, 3.128, 6.008],
  "entities": [
    {"id": "base-cabinets", "label": "Main wood base-cabinet run",
     "kind": "fixed", "category": "cabinet", "move_ready": false,
     "node_name": "scan_base_cabinets",
     "bounds_min": [0.020, 0.000, 3.046], "bounds_max": [1.367, 0.865, 5.489]}
  ]
}
```

Walls, windows and shades also carry `center`, `inward_normal` and `cutaway`.
Every other entity has only the fields above.

What already works and should be kept: meters, Y up, floor at Y=0, a stable `id`
per entity, a `node_name` that links each entity to its USD node, and USD nodes
whose local +Z is the entity's front. These match `SPEC.md` §9.1.

## Problems

### 1. Boxes are not the real size or shape

`bounds_min` and `bounds_max` are boxes aligned to the file's X and Z axes. This
room is turned about 19° (71.2° for the cabinet run), so every box is larger than
the thing inside it. The base cabinet run is really 2.37 m × 0.62 m, but its JSON
box is 1.35 m × 2.44 m. Collision checks against these boxes reject valid
placements, and the real size cannot be recovered from them.

### 2. No facing direction

No entity records which way it faces (yaw). The solver needs it to put things
against cabinets, next to Objects or facing them. Today it can only be read from
the USD node's rotation matrix.

### 3. Position is a box centre, not a base

The USD nodes are positioned at the centre of each box. A base cabinet 0.865 m
tall sits at Y = 0.433. `SPEC.md` §9.1 and every Product asset position things
at their bottom centre. Mixing the two puts a Product half in the floor or
floating. The JSON does not say which rule it uses.

### 4. No usable surface height

`on_top_of` needs the height of the surface you actually set things on. The
countertop's box top is 1.016 m because it includes the backsplash. The real
work surface is at 0.908 m. Using the box top floats a lamp 11 cm in the air.

### 5. No headroom above surfaces

Nothing records how much space there is above a surface. Under the upper
cabinets, the countertop has 0.51 m of clearance to the under-cabinet light. A
0.56 m lamp does not fit, and the only way to find out today is to measure every
mesh above the counter.

### 6. Walls have no endpoints

Walls carry a centre and an inward normal, but not their two endpoints or their
length. `SPEC.md` §12.5 requires endpoints A and B in a fixed winding, and
`against_wall` alignment and offsets are measured from those ends.

### 7. No floor outline

The floor outline exists only as a triangulated mesh in the USD file.
`SPEC.md` §9.3 requires an ordered polygon, which is also needed to check that a
placement stays inside the room.

### 8. No door or window records

There is no door record at all. The doorway is visible only as "metal protection
plates at doorway jamb bases". The window is an ordinary entity, with no wall,
offset, width or sill height. Without these, there are no keep-clear zones in
front of doors (`SPEC.md` §9.5) and no `in_front_of_window` anchor. In the test,
the entrance keep-clear zone had to be drawn by hand.

### 9. Protruding parts of walls are not described

The window sill sticks out 18 cm along almost the whole window wall, at
0.77–0.84 m. A tall item placed against that wall collides with it. The sill is
an entity, but nothing says it belongs to that wall or how far it protrudes,
which `against_wall` needs to know. The 2.5 cm baseboard causes the same problem
at floor level.

### 10. Categories are not the shared registry

`SPEC.md` §9.4 requires one category list shared by perception, planning,
Products and rendering (`backend/respace/categories.py`). The sample uses its own
categories instead:

| Sample | Registry has |
|---|---|
| `appliance` (refrigerators, microwaves, kettle) | `refrigerator`; nothing for small appliances |
| `functional_equipment` (outlets, switch, thermostat, sensors) | `outlet`, `light_switch`, `vent` |
| `countertop` | `counter` |
| `faucet`, `plumbing_fixture`, `architectural_detail` | none |

Two refrigerators labelled `appliance` lose that they are refrigerators. Outlets
labelled `functional_equipment` are no longer Wall features, which is what lets
planning put a lamp near power.

### 11. "Fixed" means something different in the glossary

The sample uses `kind: "fixed"` for anything permanent and `"furniture"` for
anything movable, including a kettle and a wet-floor sign. In `CONTEXT.md`,
**Fixed** means "cannot move in one particular placement calculation", which is
a different idea. `SPEC.md` §12.5 calls the permanent property `fixed_in_place`.
`move_ready` looks like its opposite, but this is not documented.

### 12. The link to the original scan is a shift only

`translation_from_scan` is a shift with no rotation. `SPEC.md` §9.1 requires a
full 4×4 `room_from_world` transform. A shift happens to be enough today because
normalization does not rotate, but nothing records that assumption. The origin is
also the corner of the reconstruction's own floor box, after walls were extended.
The backend's `normalize_room` computes its own origin from RoomPlan walls, and
nobody has checked that the two agree.

## Proposed format

Version 2 keeps everything that works and adds what is missing. Names follow
`SPEC.md` §12.5 wherever it already defines one. Values below are real, taken from
the sample room.

### Top level

```json
{
  "schema_version": 2,
  "room_id": "…",
  "capture_id": "E5022320-E920-411D-A2B9-7BAB20277320",
  "units": "meters",
  "up_axis": "+Y",
  "node_pivot": "bottom_center",
  "room_from_world": [1,0,0,0, 0,1,0,0, 0,0,1,0, 1.108,1.498,5.886,1],
  "height": 3.128,
  "floor": {"polygon": [[3.958,0.532], [2.092,6.008], "…"], "area": "…"},
  "walls": ["…"],
  "openings": ["…"],
  "entities": ["…"],
  "zones": ["…"]
}
```

- `room_from_world` is column-major, as `SPEC.md` §9.2 requires. It replaces
  `translation_from_scan`.
- `node_pivot` states where USD entity nodes are positioned. The recommendation is
  `bottom_center`, to match Products. If the exporter keeps box centres, it must
  say `box_center` and readers convert.
- `floor.polygon` is ordered so that the signed area is positive (`SPEC.md` §9.3).
  The values shown are the window wall's two ends. The full ordered outline is
  left to the exporter.

### Walls

```json
{"id": "wall-97e82580aac993abf164", "node_name": "scan_wall_97e82580aac993abf164",
 "a": [3.958, 0.532], "b": [2.092, 6.008], "length": 5.785, "height": 3.128,
 "inward_normal": [-0.9466, -0.3225], "virtual": false,
 "protrusions": [
   {"entity_id": "window-sill", "depth": 0.18, "bottom": 0.773, "top": 0.843,
    "from_a": 0.03, "to_a": 5.18},
   {"entity_id": "window-wall-skirting", "depth": 0.025, "bottom": 0.0, "top": 0.1,
    "from_a": 0.01, "to_a": 5.77}
 ]}
```

- `a` → `b` follows `SPEC.md` §9.3, so the inward normal is `(-dz, dx) / length`.
  This was checked against the sample's existing normal.
- `offset_from_a` on openings is measured to the opening's nearer edge.
  `SPEC.md` §12.5 does not say whether the offset is to the edge or the centre,
  so this needs agreeing.
- `protrusions` lists anything attached to the wall that juts into the room
  (sills, baseboards, radiators), with how far along the wall it runs, measured
  from end A. This lets `against_wall` clear them without measuring meshes.

### Openings

```json
{"id": "window-assembly", "type": "window", "wall_id": "wall-97e82580aac993abf164",
 "offset_from_a": 0.05, "width": 5.114, "bottom": 0.845, "height": 1.967,
 "node_name": "scan_window_assembly"}
```

The same record is used for `door` and open `opening`, as in `SPEC.md` §12.5. The
door into this kitchenette needs a record that the sample does not have.

### Entities

```json
{"id": "main-countertop", "label": "Continuous gray countertop with end and rear upstands",
 "node_name": "scan_main_countertop",
 "category": "counter",
 "fixed_in_place": true,
 "position": [0.896, 0.863, 3.673],
 "yaw": 1.2427,
 "size": [3.624, 0.650, 0.152],
 "mount": "floor",
 "wall_id": "wall-687159d16597d3f99eb4",
 "support_id": null,
 "surfaces": [
   {"top": 0.908, "polygon": [["…"]], "clearance_above": 0.51,
    "clearance_limited_by": "undercabinet-light"}
 ],
 "cutaway": null,
 "source": "roomplan"}
```

| Field | Meaning | Replaces |
|---|---|---|
| `position` | Bottom centre of the oriented box, `[x, y, z]`, room frame | `bounds_min`/`bounds_max` |
| `yaw` | Radians about +Y, zero faces +Z (`SPEC.md` §9.1) | nothing; read from USD today |
| `size` | `[width, depth, height]` along local X, Z, Y | box size |
| `category` | An ID from `backend/respace/categories.py` | free-text categories |
| `fixed_in_place` | Permanent; never moved by planning | `kind: "fixed"`, `move_ready` |
| `mount` | `floor`, `wall`, `ceiling` or `object` (`CONTEXT.md` **Mount**) | nothing |
| `wall_id`, `support_id` | What it is against or standing on | nothing |
| `surfaces` | Usable tops: real height, footprint, headroom above | nothing |
| `source` | `roomplan`, `mk1` or `refined` (`SPEC.md` §12.5) | `geometry_source` text |

Values shown are from the sample. For the countertop, position Y is 0.863 and the
height is 0.152 because the box includes the upstands. The work-surface height of
0.908 comes from the measured mesh. The 0.51 m clearance is the gap from that
surface to the under-cabinet light. `surfaces[].polygon` is a placeholder.

- Keep `bounds_min`/`bounds_max` only as an optional convenience, clearly marked
  axis-aligned and never used for collision.
- Things the registry lacks (kettle, faucet, sandwich grill, thermostat) need a
  decision. Either add registry categories, or allow `category: "other"` with a
  `collision_class`, so they still block placement.
- Walls, the floor and the ceiling move out of `entities` into their own sections.
  Their `kind` field is then no longer needed.

### Zones

```json
{"id": "keep-clear-entrance", "type": "keep_clear", "reason": "door",
 "opening_id": "door-entrance", "polygon": [["…"]]}
```

The exporter can derive these from door records (`SPEC.md` §9.5), or the backend
can compute them. Either way, they depend on the door record existing.

## Validation on load

A placement pipeline should reject a room file, not guess, when:

- Any entity's `position`, `yaw` and `size` disagree with its USD node by more than
  1 cm or 1°.
- A wall's `inward_normal` disagrees with its endpoints and winding.
- An entity that is `fixed_in_place` or wall-mounted has no `wall_id`.
- An entity with `mount: "object"` has no `support_id`.
- A category is not in the registry and has no `collision_class`.
- The floor polygon is not closed, or its area is not positive.
- `room_from_world` is not a rigid transform.

## Related findings outside this format

These came out of the same test but are not room JSON problems:

- `SPEC.md` §10.2 puts `against_wall` items 5 cm from the wall, and §10.3 requires
  5 cm clearance from everything. They meet at exactly 5 cm, so any baseboard
  breaks them. The test treated walls as the room boundary instead, and pushed
  items off the wall in 5 cm steps when a protrusion was in the way. That rule is
  not in `SPEC.md` and needs a decision.
- SPAR3D chair reconstructions rest tipped 17–22° forward. At real size, their back
  feet are 8–14 cm off the floor. `assets/spar3d/README.md` says chairs need no
  correction; its tilt measure cannot see this lean. Levelling by the feet fixed it
  in the test, and should become a `prepare.py` step.
- The LISABO reconstruction faces −Z and needs `--yaw 180`. Facing has to be
  checked per Product, as the SPAR3D README already notes.
- `SPEC.md` §11.1 describes building the room from the measured outline with
  stand-ins. The reconstruction branch replaces that with a fully modelled room.
  §11.1 needs updating when that branch lands.
