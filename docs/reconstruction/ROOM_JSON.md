# Standard reconstruction room JSON

New direct Sol results publish `room.json` and its generated `room.schema.json`.
This implements the placement format proposed in
[`room-reconstruction-json.md`](../../room-reconstruction-json.md), with the
backend field names and fallback categories clarified in `room-json-steer.md`. The native
viewer continues to use `scene.json`; both descriptions reference the same local
OBJ/MTL assets, stable identities and actual geometry.

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
for a wall-mounted object. Test its oriented footprint and vertical interval
against other entities, wall protrusions, room boundaries and keep-clear zones.
An axis-aligned scene box is not the placement footprint.

## Structural sections and usable space

`floor`, `ceiling`, `walls`, `openings`, `entities` and `zones` are separate.
Polygon rings are closed and have positive signed area in X/Z. Walls' A→B
direction gives inward normal `[-dz, dx] / length`. Opening `offset` is
measured to the nearer **edge**, not the center. Structural opening records are
derived from RoomPlan, including unmodeled empty doorways; `node_name` may be null
for a void with no corresponding mesh node.

Door/open doorway keep-clear regions extend 1.2 m inward, with 0.45 m to either
side, clipped to the floor. Attached fixed entities have per-part wall protrusion
extents and height intervals: a sill's depth applies at sill height, while a
baseboard's depth applies at floor level. Wall association uses the actual mesh
distance and segment overlap rather than an axis-aligned size estimate. The
placement rule is 5 cm inward from the deepest overlapping protrusion's front at
the candidate's height (and along-wall interval), or 5 cm from the bare wall when
none overlap. The exported `depth`, `bottom`, `top`, `from_a` and `to_a` provide
those inputs. These remain conservative part envelopes. The external placement
solver itself is not in this checkout.

Usable tops come from horizontal faces of the exported semantic geometry, not
the axis-aligned box top or a photographic guess. Narrow upstand tops are omitted;
parts crossing the work plane are removed from the usable footprint. `holes`
records any excluded interior regions. `clearance_above` is the conservative
minimum space over the remaining footprint, limited by another model surface or
the ceiling; `clearance_limited_by` names it. Missing surfaces remain `[]` rather
than inventing a worktop. These are dimensions of the generated model, not a
survey of the real surface. Multi-level, sloped and disconnected floors remain
outside the reconstruction contract.

## Categories and permanence

`respace_reconstruction/categories.py` is a conservative compatibility allowlist
of IDs named in this repository's SPEC and the steering note. The external backend
registry is not present here. Recognized mappings include refrigerator →
`refrigerator`, outlet → `outlet`, switch → `light_switch`, countertop → `counter`,
cabinets → `cabinet`, shades → `curtain`, ceiling light → `ceiling_light`, and
television → `tv`. Unconfirmed identities such as kettles, faucets, grills,
thermostats, sensors and microwaves use `category: other`, retain their descriptive
`label`, and have a required `collision_class`: `floor`, `wall`, `tabletop`,
`ceiling` or `none`. New appliance/electronics category IDs are not invented.
Mounts use `floor`, `wall`, `tabletop` or `ceiling`. Collision classes normally
match the mount; rugs use `none` so they can lie underneath furniture. A tabletop
item must reference another entity with `support_id`.

`fixed_in_place` means permanent installation. It is independent of keeping a
movable item fixed for a particular placement calculation. Wall-mounted items
require a wall reference. A permanent floor-standing island or ceiling fixture
does not require an invented wall reference. Generated objects use
`source: refined`; measured structural sections retain their RoomPlan identities.

## Validation and compatibility

Use `respace_reconstruction.room_document.load_room(directory)` to load a result.
It validates schema, references, categories, closed winding, wall normals, rigid
transforms, support requirements, openings and zones, then compares actual local
OBJ vertices and native node transforms with the JSON. Center, base elevation, pivot and size
must agree within 1 cm and yaw within 1°. The schema is exported alongside every
room so consumers can validate before placement.

The proposal references sections and files from another checkout: this repository's
current `SPEC.md` calls its room contract §6 and does not contain the referenced
backend normalization implementation. This exporter therefore records its origin
explicitly and does not assume that a separate backend chose the same origin.
Apply `room_from_world` when exchanging coordinates. The user-authored proposal
is preserved unchanged. Existing completed revisions remain intact; generate a
new room revision to obtain the standard export and the semantic geometry changes.
