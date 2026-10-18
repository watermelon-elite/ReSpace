# assets

Render assets and the offline tools that produce them.

**Most of this folder ships.** The one exception is `spar3d/`, which is a
laboratory. The table below is the boundary; read it before assuming a file
here is either production or scratch, because both are present.

| Path | Status | What it is |
|---|---|---|
| `models/` | **ships** | The 21 category stand-in USDZ the client loads and renders |
| `manifest.json` | **ships** | The catalog manifest the client reads; one entry per asset, with immutable `asset_id` and `revision` |
| `manifests/` | **ships** | Per-asset conversion records |
| `prepare.py` | **ships** | The converter. GLB/OBJ to normalized or dimensioned USDZ |
| `assemble_scan.py` | **ships** | Assembles a segmented scan into one named, textured USDZ scene |
| `sources/kenney/` | **ships** | Source GLBs and the retained CC0 licence, kept as a licensing obligation |
| `proof.json` | **ships** | Verification record for the stand-in pipeline |
| `evidence/` | sample | A captured dimension-evidence record, for reference |
| `requirements.txt` | offline only | Pinned for preparation; never installed in the request-time API image |
| `spar3d/` | **laboratory** | Image-to-mesh reconstruction. Nothing it produces is shippable today |

## Nothing in `spar3d/` is a catalog asset

`spar3d/` reconstructs 3D meshes from product photographs. It is a capability
under evaluation, not a source of assets, and the distinction is enforced in
three ways rather than trusted to documentation:

- **Output lives outside the repository.** Every mesh, package and grading sheet
  is written to `$SPAR3D_LAB` (`~/spar3d-lab` by default). No reconstruction is
  committed here, and none should be.
- **Inputs carry no dimension evidence.** The test products are scraped search
  results. A reconstruction establishes appearance only; physical size must come
  from verified Product evidence, which these do not have.
- **Conversions are tagged.** Every test package is written with
  `--variant-id TEST-<slug> --evidence-id TEST-NO-EVIDENCE`, so a test record is
  identifiable on sight and cannot be mistaken for a catalog conversion.

Reconstruction quality is also graded per category and several categories fail:
shelf units and plants must use stand-ins, tables and desks need a per-Product
check, and colour is unreliable on dark and saturated finishes. See
[`spar3d/README.md`](spar3d/README.md) before deciding whether a category gets a
reconstruction or a stand-in.

## Promoting a reconstruction

Not yet done for any Product, and not a formality. It requires, at minimum:
verified exact-variant dimension evidence from the Product source, a category
whose grading supports a mesh, conversion with `--auto-orient`, and a colour
check against the source photograph. `--auto-orient` turns the model to face
`+Z`, squares it to the axes so the verified width and depth land on the right
box, and levels it; a person still confirms the result and clears any flags on
the grading sheet. Colour is a judgement made by eye; no automated check
catches it.

## Conventions

Every packaged asset is meters, `+Y` up, `+Z` forward, pivoted bottom-center,
and under SPEC's 3 MB ceiling. `prepare.py` validates bounds and pivot by
reopening the package it just wrote, and refuses a catalog conversion that lacks
dimensions, a variant ID and an evidence ID together.

```sh
python assets/prepare.py input.glb output.usdz --category chair --yaw 180   # authored source
python assets/prepare.py mesh.glb output.usdz --category chair --auto-orient # SPAR3D reconstruction
```

Preparation needs `requirements.txt` installed in its own environment. It is
deliberately absent from the API image: nothing here runs at request time.
