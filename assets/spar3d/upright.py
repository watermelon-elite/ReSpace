"""Estimate the pitch that stands a SPAR3D reconstruction upright.

Reconstructions are not upright. Product photography shoots from slightly above
and SPAR3D reconstructs in camera space, so the mesh inherits the camera's
downward look as a backwards lean of roughly 10 degrees. `prepare.py --yaw`
rotates about the vertical axis and cannot correct it.

The cue is that furniture rests on a flat floor: fit a plane to the vertices the
object stands on and measure how far its normal is from vertical. The fit is
iterated, because while the mesh is tilted the lowest vertices are not quite the
resting surface, and each pass improves the selection for the next.

Only pitch is returned, never roll. The error has a known single cause, a camera
looking down, which is one rotation about the horizontal axis across the view.
Solving for the full normal also rolls the model sideways, which was measured to
skew slab-like reconstructions that were not leaning that way to begin with.

Reliable where the object has a genuine flat base and a vertical body: verified
to visibly straighten all six test lamps. Unreliable where the reconstruction's
underside is itself slanted, which over-corrects it; the BILLY bookcases, which
are rejected in favour of stand-ins anyway, are the measured example. Treat the
number as a proposal and check it on a grading sheet before trusting it.

    python assets/spar3d/upright.py            # suggest pitch for every mesh
"""

import json
import os
import sys
from pathlib import Path

import numpy as np
import trimesh

LAB = Path(os.environ.get("SPAR3D_LAB", Path.home() / "spar3d-lab"))
BAND = 0.08
PASSES = 4
LIMIT_DEGREES = 30.0
MINIMUM_BASE_VERTICES = 24


def _resting_normal(points):
    """Up-facing normal of the least-squares plane y = ax + bz + c."""
    design = np.c_[points[:, 0], points[:, 2], np.ones(len(points))]
    coefficients, *_ = np.linalg.lstsq(design, points[:, 1], rcond=None)
    residual = points[:, 1] - design @ coefficients
    spread = np.std(residual)
    if spread > 1e-9:
        # One reweight, to drop feet, castors and floating fragments that would
        # otherwise drag the plane away from the surface the object rests on.
        keep = np.abs(residual) <= 2 * spread
        if keep.sum() >= 12:
            design, points = design[keep], points[keep]
            coefficients, *_ = np.linalg.lstsq(design, points[:, 1], rcond=None)
    normal = np.array([-coefficients[0], 1.0, -coefficients[1]])
    return normal / np.linalg.norm(normal)


def rotation(degrees):
    """Right-handed rotation about +X, matching prepare.py --pitch."""
    angle = np.radians(degrees)
    cosine, sine = np.cos(angle), np.sin(angle)
    return np.array([[1, 0, 0], [0, cosine, -sine], [0, sine, cosine]])


def estimate(vertices):
    """Suggested pitch in degrees, and why, or 0.0 when it should not be applied.

    Refusing is deliberate. A wrong correction tips an acceptable model over,
    which is worse than a lean somebody already knows about.
    """
    vertices = np.asarray(vertices, dtype=float)
    footprint = np.ptp(vertices[:, [0, 2]], axis=0)
    total = 0.0
    current = vertices
    for _ in range(PASSES):
        height = current[:, 1]
        span = height.max() - height.min()
        if span <= 0:
            return 0.0, "degenerate height"
        base = current[height <= height.min() + BAND * span]
        if len(base) < MINIMUM_BASE_VERTICES:
            return 0.0, "too few base vertices"
        # A resting surface has to be wide. One leg tip or a floating fragment
        # gives a plane fit that is numerically fine and physically meaningless.
        if np.any(np.ptp(base[:, [0, 2]], axis=0) < 0.15 * footprint):
            return 0.0, "base too narrow to define a plane"
        normal = _resting_normal(base)
        step = -float(np.degrees(np.arctan2(normal[2], normal[1])))
        current = current @ rotation(step).T
        total += step
        if abs(step) < 0.01:
            break

    if abs(total) > LIMIT_DEGREES:
        return 0.0, f"refused, {total:.1f} deg exceeds the {LIMIT_DEGREES:.0f} deg limit"
    return round(total, 1), "ok"


def main():
    manifest = json.loads((LAB / "manifest.json").read_text())
    rows = {}
    for entry in sorted(manifest, key=lambda m: m["file"]):
        slug = Path(entry["file"]).stem
        source = LAB / "out" / slug / "mesh.glb"
        if not source.exists():
            continue
        mesh = trimesh.load_scene(source, process=False).dump()[0]
        degrees, reason = estimate(mesh.vertices)
        rows[slug] = degrees
        print(f"{slug:42s} --pitch {degrees:>6}   {reason}")
    (LAB / "pitch.json").write_text(json.dumps(rows, indent=2))
    applied = sum(1 for v in rows.values() if v)
    print(f"\n{applied}/{len(rows)} corrected, written to {LAB / 'pitch.json'}")


if __name__ == "__main__":
    sys.exit(main())
