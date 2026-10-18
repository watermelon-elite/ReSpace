# Standard reconstruction room JSON

New direct Sol results publish `room.json` and its generated `room.schema.json`.
This implements the placement format proposed in
[`room-reconstruction-json.md`](../../room-reconstruction-json.md), with exporter field names and fallback categories described below. The native
viewer continues to use `scene.json`; both descriptions reference the same local
OBJ/MTL assets, stable identities and actual geometry.

## Integration boundary

The native viewer consumes this richer export. The planning backend currently accepts only the [restricted subset](../../specs/room-reconstruction-json.md); inset sinks, logical groups and zero-headroom surfaces are deferred. Integrated scans use original native measurements for backend planning.

## Coordinates and asset placement

- `schema_version: 2`, meters, +Y up, floor at zero.
- The origin is the minimum X/Z of the measured RoomPlan floor, not the bounds
  of extended walls. `room_from_world` is a rigid, column-major 4×4 transform
  from the original ARKit scan frame to this placement frame.
- Every exported local mesh has a bottom-center pivot. `center: [x,z]` is the
  oriented footprint center and `base_y` is the bottom elevation, including for
  elevated objects. Together with `yaw`, they place its `node_name`; yaw is
  radians about +Y, with local +Z forward. No per-item `position` field is emitted.
- `size` is `[width, depth, height]`, along local X, Z, Y. It comes from local
  mesh bounds, so rotating an item does not inflate its dimensions.
- `asset` is a local OBJ filename. For products with the same pivot/front/units,
  use `Translate(center[0], base_y, center[1]) * RotateY(yaw) * Scale(w/W, h/H, d/D)`, where W/D/H
  are the product's original local dimensions. Scene transforms use XYZ order;
  JSON sizes use width/depth/height order.
- `materials` records owner/slot bindings, `texture_family`, `base_color_texture`,
  `roughness_texture`, `normal_texture` and physical `repeat_meters`. Entities'
  `material_ids` select those bindings. Texture files are shared per family and
  included in the verified result assets. Multiply the neutral color map by
  `base_color` and the normalized roughness pattern by scalar `roughness`;
  `metallic` remains the material's scalar finish. Normal maps use tangent space.
  OBJ UVs already include the physical repeat scale, so consumers should not
  multiply them by `repeat_meters` a second time.
- Structural nodes include explicit centers/base elevations/yaws too, preserving asymmetric
  opening geometry when wall endpoint winding reverses the asset's X direction.

To insert an item, add a uniquely identified entity using a registered category,
asset/node name, footprint center, base elevation, yaw, oriented size, mount,
permanence and collision class. Use `mount: tabletop` and `support_id` for an
object resting on another object, or `mount: wall` and `wall_id`
for a wall-mounted object. An inset sink uses `mount: inset`, `support_id` for
its countertop, and `collision_class: tabletop`; its vertical span crosses the
support plane rather than starting there. Test its oriented footprint and vertical interval
against other entities, wall protrusions, room boundaries and keep-clear zones.
An axis-aligned scene box is not the placement footprint.

## Structural sections and usable space

`floor`, `ceiling`, `walls`, `openings`, `entities` and `zones` are separate.
Polygon rings are closed and have positive signed area in X/Z. Walls' A→B
direction gives inward normal `[-dz, dx] / length`. Opening `offset` is
measured to the nearer **edge**, not the center. Structural opening records are
derived from RoomPlan, including unmodeled empty doorways; `node_name` may be null
for a void with no corresponding mesh node.
The exporter orders walls end to start in one counterclockwise loop. Both joins
and the wall loop's agreement with the floor boundary must be within 2 cm.
Door widths remain measured widths; an opening outside its wall is rejected
rather than shortened. Missing measured doors remain missing; no guessed door
position, width or keep-clear region is added.

Door/open doorway keep-clear regions extend 1.2 m inward, with 0.45 m to either
side, clipped to the floor. Attached fixed entities have per-part wall protrusion
extents and height intervals: a sill's depth applies at sill height, while a
baseboard's depth applies at floor level. Wall association requires actual mesh
proximity and segment overlap, then ranks by center-to-plane distance so an edge touching a corner cannot steal the
attachment from the correct wall. A conflicting generated wall support is corrected
in the native scene too. Wall-mounted entities face the measured inward normal.
Thin floor-standing trim with yaw errors up to 10° is aligned to the wall direction. Both rotate about
their mesh center before export.
Protrusions use the resulting compiled part geometry; their depth is never
artificially reduced while leaving the mesh angled into the room. The
placement rule is 5 cm inward from the deepest overlapping protrusion's front at
the candidate's height (and along-wall interval), or 5 cm from the bare wall when
none overlap. The exported `depth`, `bottom`, `top`, `from_a` and `to_a` provide
those inputs. These remain conservative part envelopes. The external placement
solver itself is not in this checkout.

Usable tops come from horizontal faces of the exported semantic geometry, not
the axis-aligned box top or a photographic guess. Narrow upstand tops are omitted;
an object's own parts crossing the work plane and inset sink footprints are
removed. `holes` records excluded interior regions. The sink keeps its own node,
asset and identity. Ordinary occupants retain their collision geometry without
deleting the surface that supports them.

Each top is partitioned wherever the lowest overhead limiter changes. A stretch
under an upper cabinet or light therefore has its own headroom, while an uncovered
stretch is limited by the ceiling. `clearance_above` is always numeric and
`clearance_limited_by` always identifies the limiter. A fully occupied region can
have zero headroom; its physical support contact remains valid, but a new item
cannot fit there. Missing surfaces remain `[]` rather than inventing a worktop.
These are dimensions of the generated model, not a survey of the real surface.
Multi-level, sloped and disconnected floors remain outside the reconstruction contract.

A separately modeled installed countertop resting on floor-standing cabinets or
appliances also produces one logical `category: counter` support run. It has
`node_name: null`, `asset: null`, explicit `member_ids`, `mount: floor`, and
`collision_class: none`. Its bottom-centered bounds enclose those physical members,
and its surfaces come from the real countertop, including partitioned headroom
and sink holes. Appliances resting on the countertop reference the run through
`support_id`. The countertop itself references a real supporting member; inset
sinks also reference the run. Cabinets, dishwasher and countertop retain their
own records, nodes and collision geometry. Consumers must skip the logical run
when loading meshes or testing collisions; its members provide the geometry.
Groups cannot nest or refer back to themselves, and their bounds and surfaces
are checked against their members. A complete counter already modeled as one
floor-standing entity needs no additional run.

## Categories and permanence

`respace_reconstruction/categories.py` is a conservative compatibility allowlist
of IDs confirmed by the steering notes, including the backend registry corrections
in `room-json-steer-3.md`. The external backend
registry is not present here. Recognized mappings include refrigerator →
`refrigerator`, outlet → `outlet`, switch → `light_switch`, countertop → `counter`,
cabinets → `cabinet`, shades → `curtain`, ceiling light → `ceiling_light`, and
television → `tv`. Unconfirmed identities such as kettles, faucets, grills,
thermostats, sensors and microwaves use `category: other`, retain their descriptive
`label`, and have a required `collision_class`: `floor`, `wall`, `tabletop`,
`ceiling` or `none`. New appliance/electronics category IDs are not invented. `bar_stool` maps to
`stool`, `lamp` and table lamps map to `table_lamp`, and `pendant_light` maps to
`ceiling_light`. `display_case`, `espresso_machine`, `menu_board`, `register` and
`trash_bin` fall back to `other` with their mount-specific collision class.
These unsupported IDs are also absent from the exported schema enum.
Mounts use `floor`, `wall`, `tabletop`, `inset` or `ceiling`. Collision classes
normally match the mount; inset fixtures use `tabletop`, logical support groups
and rugs use `none`. Tabletop and inset items must reference another entity
with `support_id`.

`fixed_in_place` means permanent installation. It is independent of keeping a
movable item fixed for a particular placement calculation. Wall-mounted items
require a wall reference. A permanent floor-standing island or ceiling fixture
does not require an invented wall reference. Generated objects use
`source: refined`; measured structural sections retain their RoomPlan identities.

## Validation and compatibility

Use `respace_reconstruction.room_document.load_room(directory)` to load a result.
It requires explicit `node_pivot: bottom_center` and validates schema, references,
categories, closed winding, wall topology/normals, rigid transforms, support
requirements, openings and zones, then compares actual local
OBJ vertices and native node transforms with the JSON. Center, base elevation, pivot and size
must agree within 1 cm and yaw within 1°. The schema is exported alongside every
room so consumers can validate before placement.

Floor-mounted entities start within 2 cm of the floor; ceiling-mounted entities
end within 2 cm of the ceiling, including modeled suspension attachments. A
tabletop entity's base must be within 2 cm of a support surface and overlap it
in X/Z. Inset entities instead cross their support plane. Support references
must exist and be acyclic. Missing support references are inferred only from
actual horizontal surface contacts; floating geometry is rejected without moving
the captured object. Inventory contacts are checked before spending on detail
generation, and detailed objects retain their vertical bounds within 2 cm.

External readers need to accept the nullable asset/node fields for explicit
support groups, `member_ids`, and the `inset` mount. Previously generated v2
files can fail the stronger topology or contact checks; regenerate a revision
to obtain the updated export. Existing result files are not migrated in place.

The proposal references sections and files from another checkout: this repository's
current `SPEC.md` calls its room contract §6 and does not contain the referenced
backend normalization implementation. This exporter therefore records its origin
explicitly and does not assume that a separate backend chose the same origin.
Apply `room_from_world` when converting native scan coordinates to room coordinates.
The USDZ already contains room coordinates; do not apply the transform again.
The user-authored proposal is preserved unchanged. Existing completed revisions remain intact; generate a
new room revision to obtain the standard export and the semantic geometry changes.

## Portable USDZ and referenced source assets

`model.usdz` has one bottom-centered mesh prim per physical entity under `/Room`,
including structural surfaces. Logical support groups have no prim. The same
collision-safe USD identifier mapping supplies every JSON `node_name`, including
opening links. Semantic entity IDs, `wall_id` and `support_id` remain independent
of prim naming. Floor/ceiling material owners and headroom references use their
exported structural node names because those sections have no separate ID.

USD transforms equal `room_from_world @ local_to_scan_transform`. The packaged
stage is reopened and checked for named nodes, position within 1 cm, yaw within
1°, resolved texture dependencies and explicit `MaterialBindingAPI` on every
binding. Export also runs the ARKit rule set used by `usdchecker --arkit` through
`UsdUtils.ComplianceChecker(arkit=True)` from the pinned OpenUSD runtime. A failure
prevents publication. Aggregate-only legacy exports keep their scan coordinates.

The per-entity OBJ files are the editable local mesh sources used by the native
viewer, rebuilding/exporting the model, and placement asset validation. Their MTL
files and `material-v1-*.png` maps supply the current procedural base color,
roughness and normal textures. They support material/finish edits for walls and
floors as well as furniture; they are not alternate product-placement geometry.

For product placement and viewing the portable model, share `room.json` plus
`model.usdz` (and `room.schema.json` for schema validation). Textures needed by USD
materials are embedded inside the USDZ. The `asset` and material texture filename
fields in JSON refer to the separate editable source set, not files inside the
USDZ. Consumers that load those files, rebuild meshes, edit source materials, or
call `load_room` need the full OBJ/MTL/PNG source set alongside the JSON. A JSON/USDZ
pair is sufficient for consumers that resolve geometry and appearance from USD.
