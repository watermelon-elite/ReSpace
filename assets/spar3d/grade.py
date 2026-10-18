"""Run every reconstruction through assets/prepare.py and build comparison sheets.

Two independent questions per product:

  1. Does prepare.py package it? That is pass/fail and the script answers it,
     including whether the baked texture actually survives into the USDZ.
  2. Does it look like the product, facing forward and standing level? That
     needs eyes, so this only lays the evidence out: source photograph beside
     front, side and back views, textured and as untextured clay, with the
     orientation prepare.py --auto-orient chose and any flags it raised.

Dimensions here preserve the mesh's own proportions scaled to one metre. They
are NOT measurements. These are scraped test inputs with no dimension evidence,
so every record is tagged TEST and must never reach the catalog.

Needs the preparation environment, not the reconstruction one, because
prepare.py pins a newer trimesh than SPAR3D runs on:

    $SPAR3D_LAB/.venv-prepare/bin/python assets/spar3d/grade.py [slug-substring]

Writes sheets and a report to $SPAR3D_LAB/grade/, replacing the previous run.
Runs on CPU in about 2.5 min for all 30; it never loads SPAR3D, so it will not
disturb anyone using the machine.
"""

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
import orient  # noqa: E402
import upright  # noqa: E402
from render import render  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
LAB = Path(os.environ.get("SPAR3D_LAB", Path.home() / "spar3d-lab"))
# Output is generated and bulky, so it belongs with the meshes in the lab, never
# beside the scripts in the repository.
WORK = LAB / "grade"
TILE = 300
# Meshes are posed by orient.py first, so +Z is the front. render.py's camera
# sits at -Z for azimuth 0, which makes 180 the front view.
VIEWS = ((180, "front"), (90, "side"), (0, "back"), (270, "side"))


def label(image, text):
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, image.height - 18, image.width, image.height], fill=(30, 30, 30))
    draw.text((6, image.height - 15), text, fill=(245, 245, 245))
    return image


def fit(image, size):
    """Letterbox onto a square so the sheet's columns line up."""
    image = image.convert("RGB")
    image.thumbnail((size, size), Image.LANCZOS)
    canvas = Image.new("RGB", (size, size), (250, 250, 250))
    canvas.paste(image, ((size - image.width) // 2, (size - image.height) // 2))
    return canvas


def tilt(mesh):
    """Degrees between vertical and the mesh's own top-to-bottom axis.

    Deciles rather than extremes, so one stray vertex cannot swing it. Honest
    only for tall shapes with a single axis: on a wide table the top decile is
    the top surface and the bottom decile the feet, which exaggerates any
    asymmetry. Read it for lamps, corroborate it by eye for everything else.
    """
    height = mesh.vertices[:, 1]
    low, high = np.quantile(height, [0.10, 0.90])
    axis = mesh.vertices[height >= high].mean(axis=0) - mesh.vertices[height <= low].mean(axis=0)
    return round(float(np.degrees(np.arctan2(np.linalg.norm(axis[[0, 2]]), axis[1]))), 1)


def convert(slug, source, mesh):
    """Package to USDZ at the mesh's own proportions, then verify the texture.

    `mesh` must already carry the orientation, because the proportions passed
    as --dimensions have to describe the model prepare.py will actually measure
    after it works out and applies the same rotation.
    """
    extent = mesh.bounds[1] - mesh.bounds[0]
    k = 1.0 / float(extent.max())
    width, height, depth = (extent * k).tolist()
    destination = WORK / "usdz" / f"{slug}.usdz"
    result = subprocess.run(
        [
            sys.executable, str(REPO / "assets/prepare.py"),
            str(source), str(destination), "--category", slug.split("_")[0],
            "--auto-orient",
            "--dimensions", f"{width:.6f}", f"{depth:.6f}", f"{height:.6f}",
            "--variant-id", f"TEST-{slug}", "--evidence-id", "TEST-NO-EVIDENCE",
        ],
        capture_output=True, text=True, cwd=REPO,
    )
    if result.returncode != 0:
        return {"ok": False, "error": result.stderr.strip().splitlines()[-1]}

    record = json.loads(result.stdout)
    with zipfile.ZipFile(destination) as package:
        names = package.namelist()
    textures = [n for n in names if n.endswith(".png")]
    return {
        "ok": True,
        "orientation": record["orientation"],
        "bytes": record["byte_count"],
        "under_3_mb": record["under_3_mb"],
        "triangles": record["conversion"]["triangles"],
        "textured": bool(textures),
        "package": names,
    }


def main():
    (WORK / "usdz").mkdir(parents=True, exist_ok=True)
    (WORK / "sheets").mkdir(parents=True, exist_ok=True)
    manifest = {Path(m["file"]).stem: m for m in json.loads((LAB / "manifest.json").read_text())}

    only = sys.argv[1] if len(sys.argv) > 1 else ""

    report = []
    for slug in sorted(manifest):
        source = LAB / "out" / slug / "mesh.glb"
        if only not in slug or not source.exists():
            continue
        meta = manifest[slug]
        mesh = trimesh.load_scene(source, process=False).dump()[0]
        row = {"slug": slug, "category": meta["category"], "name": meta["name"],
               "type": meta["type_name"], "vertices": int(len(mesh.vertices)),
               "tilt_before": tilt(mesh)}

        # The same estimate prepare.py --auto-orient makes, applied here so the
        # proportions and the sheet describe the model that gets packaged.
        pose = orient.orient(mesh.vertices, meta["category"])
        mesh = mesh.copy()
        mesh.vertices = (np.asarray(mesh.vertices) @ upright.rotation(pose["pitch_degrees"]).T
                         @ orient.roll_rotation(pose["roll_degrees"]).T)
        mesh.apply_transform(trimesh.transformations.rotation_matrix(np.radians(pose["yaw_degrees"]), [0, 1, 0]))
        row["tilt_after"] = tilt(mesh)
        row.update(convert(slug, source, mesh))
        pose = row.get("orientation", pose)
        row["pitch_degrees"], row["yaw_degrees"] = pose["pitch_degrees"], pose["yaw_degrees"]

        sheet = Image.new("RGB", (TILE * 5, TILE * 2), (250, 250, 250))
        photo = fit(Image.open(LAB / "images" / meta["file"]), TILE)
        sheet.paste(label(photo, f"SOURCE  {meta['name']}  {meta['type_name']}"), (0, 0))
        note = Image.new("RGB", (TILE, TILE), (250, 250, 250))
        draw = ImageDraw.Draw(note)
        lines = [f"pitch {pose['pitch_degrees']} deg ({pose['level_method']})",
                 f"straighten {pose['straighten_degrees']} deg ({pose['straighten_reason']})",
                 f"sideways {pose['roll_degrees']} deg", *pose["flags"]]
        for i, line in enumerate(lines):
            draw.text((8, 10 + 16 * i), line[:46], fill=(160, 0, 0) if i >= 3 else (30, 30, 30))
        caption = f"{row['vertices']}v  usdz={'ok' if row['ok'] else 'FAIL'}"
        sheet.paste(label(note, caption), (0, TILE))
        for column, (azimuth, name) in enumerate(VIEWS, start=1):
            view = render(mesh, size=TILE, azimuth=azimuth)
            sheet.paste(label(view, f"texture {name}"), (TILE * column, 0))
            view = render(mesh, size=TILE, azimuth=azimuth, clay=True)
            sheet.paste(label(view, f"clay {name}"), (TILE * column, TILE))
        sheet.save(WORK / "sheets" / f"{slug}.png")

        report.append(row)
        print(f"{slug:42s} {'ok  ' if row['ok'] else 'FAIL'} "
              f"{'tex' if row.get('textured') else 'NO-TEX':6s} "
              f"{row.get('bytes', 0) // 1024:>6} KB  pitch {row['pitch_degrees']:>6}  "
              f"yaw {row['yaw_degrees']:>6}  {'; '.join(pose['flags'])}"
              f"{row.get('error', '')}", flush=True)

    # A filtered run is a spot check, so it must not clobber the full report.
    name = "report.json" if not only else f"report-{only}.json"
    (WORK / name).write_text(json.dumps(report, indent=2))
    ok = sum(1 for r in report if r["ok"])
    tex = sum(1 for r in report if r.get("textured"))
    big = sum(1 for r in report if not r.get("under_3_mb", True))
    print(f"\n{ok}/{len(report)} packaged, {tex}/{len(report)} kept their texture, "
          f"{big} over 3 MB\nsheets in {WORK / 'sheets'}")


if __name__ == "__main__":
    main()
