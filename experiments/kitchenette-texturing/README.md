# Kitchenette texture projection experiment

This experiment keeps the kitchenette already bundled in ReSpace as a real 3D
model and bakes the earlier photorealistic image into surface textures. It is
isolated from the app. The original model is read from
`ReSpace/Resources/ImportedKitchenette/kitchenette.usdz` and is never overwritten.

## Results

- `output/kitchenette-hybrid.usdz`: selected projection on cabinet runs, walls,
  floor, countertop and shades; compatible sampled finish textures in uncovered
  regions; conventional materials on the remaining Objects, metal and glass.
- `output/kitchenette-projected.usdz`: broad direct projection for comparison,
  with baked appearance stored as emission to avoid lighting it a second time.
- `output/hybrid/`, `output/projected/`, `output/baseline/`: identical source,
  left, right and reverse camera renders, inspected under soft lighting.
- `output/report.json`: source hashes, exact camera matrices, per-mesh coverage,
  alignment exclusions and geometry-preservation results.
- `output/surface-ids.png`, `output/accepted-image-mask.png`,
  `output/visibility.npz`: visibility/acceptance diagnostics.

The two USDZs are ordinary portable 3D assets with embedded textures. Open them
in macOS Quick Look, Reality Composer Pro or another USDZ viewer to orbit them.
The output folder is generated and ignored by Git; the implementation and input
image/camera remain in this folder.

## Input image data

`inputs/photorealistic.png` is the generated 1505×1045 image from the earlier
render-guided kitchenette experiment, copied here so it no longer depends on
another chat's output folder. It is resized to the 1440×1000 source viewport.
`inputs/camera.json` records the exact SceneKit projection and world-to-camera
matrix. `inputs/source.png` is a new render of the unchanged model from that
camera. No new image-generation call or API credential was needed.

A new camera/image pair needs the same calibration, crop and orientation
relationship. More views would improve uncovered areas. Raw LiDAR depth is not
required for this experiment because the existing mesh provides rendered
visibility. Generated content can still move relative to the input geometry.

## Run

From the repository root, using its existing local Python environment (NumPy,
Pillow and usd-core):

```sh
# Recreate the source-camera record and baseline source render on macOS.
swift -module-cache-path /private/tmp/respace-texture-swift-cache \
  experiments/kitchenette-texturing/scene.swift \
  ReSpace/Resources/ImportedKitchenette/kitchenette.usdz \
  experiments/kitchenette-texturing/inputs capture

# Bake and package both models; no network calls.
.local/venv/bin/python experiments/kitchenette-texturing/bake.py

# Render four inspection cameras. Substitute projected/baseline paths as needed.
swift -module-cache-path /private/tmp/respace-texture-swift-cache \
  experiments/kitchenette-texturing/scene.swift \
  experiments/kitchenette-texturing/output/kitchenette-hybrid.usdz \
  experiments/kitchenette-texturing/output/hybrid preview

.local/venv/bin/python -m unittest discover \
  -s experiments/kitchenette-texturing -p 'test_*.py'
```

SceneKit rendering needs access to the local graphics system; a restricted
execution sandbox can return an empty snapshot. The Python bake runs without
that graphics access. OpenUSD on this machine prints a cache-line warning and
asset-localization warnings during packaging; the final ZIP entries and texture
references are checked explicitly, and the exported USDZs are rendered again.

## How it works

`bake.py` reads the existing USD geometry and transforms, clips all triangles
against the source camera, and constructs a whole-room depth/mesh-ID buffer.
It groups coplanar triangles into planar UV patches and packs them into atlases.
For every covered atlas texel it recovers the surface position, projects through
the exact source camera, and checks depth and mesh identity before sampling RGB.
It uses bilinear sampling, interior masks, slight seam feathering and gutters.
UVs and materials change; mesh points, topology, names and world transforms are
checked against the original after reopening the packaged output.

`alignment.json` contains conservative manually chosen rectangles around the
generated dispenser, taps/kettle and appliances that shifted. The hybrid applies
these exclusions to walls/countertop, where those Objects could otherwise become
duplicated paint. This is a room-specific mask, not an automatic alignment model.
Cabinet surfaces keep their projected appearance. The source image's handles and
panel divisions remain painted details unless the original mesh supplies depth.

For uncovered hybrid surfaces, small source-image swatches provide wood, stone,
floor finish and a backsplash band. They repeat at explicit physical scales;
these are inferred finishes, not recovered unseen photographs. The backsplash
fallback is limited to the relevant wall and height band. Other walls keep their
original neutral base material. Crop/scale choices live in `finish_samples`.

The direct comparison uses photo RGB on every eligible visible mesh, with
constant-color continuation into unseen portions of each patch. It intentionally
exposes the geometric drift and frozen reflections that motivate the hybrid.

## Validation and limitations

The source has 117 meshes and 3,140 triangles. Packaging checks reopen both
results and verify identical points, topology, mesh paths and world positions;
every referenced image must be present and nonempty in its USDZ. Unit checks
cover camera orientation/perspective, foreground occlusion, partly visible
triangles, rejection of hidden surfaces and the backsplash fallback region.

This is a single-view appearance experiment. Sideways movement reveals material
fallbacks and projection boundaries. Repeated swatches can show seams, and the
generated image contains lighting that remains partly baked into the hybrid's
base color. The direct comparison also freezes reflections. Fine generated
detail can be blurry or misregistered. The sink remains the original solid
geometry. No on-device performance or app integration was tested.

These limitations are visible in the translated/reverse renders; the model is
not claimed to reproduce the generated image perfectly from every angle.
