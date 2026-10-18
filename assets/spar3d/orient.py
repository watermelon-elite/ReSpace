"""Work out the yaw and pitch that pose a SPAR3D reconstruction for prepare.py.

A reconstruction arrives in the camera's frame, not the room's, with three
errors that have one cause each:

  facing    SPAR3D puts the photographed side at -Z, and product photographs
            show the front. Measured on all 30 test reconstructions: the view
            from -Z matched the source photograph every time. So the front
            needs a fixed 180 degree turn to face +Z.
  turned    Product photographs are three-quarter views. Every boxy test
            product came back turned 12-29 degrees off the axes, all the same
            way. prepare.py sizes the axis-aligned box, so an unstraightened
            model is stretched to the wrong width and depth.
  tipped    The camera looks down, so models lean. Chairs rest on their front
            legs with the back feet in the air, 17-22 degrees off level.

Levelling uses one of two estimates. The resting face is the side of the
convex hull the object would settle on under gravity: the hull face nearest to
level whose plane contains the centroid's projection. It reads feet and legs,
where upright.py's base-plane fit declines as too narrow. The base-plane fit is
kept for lamps, where it was checked by eye and reads slightly better on the
ARSTID and STOCKHOLM lamps. Each falls back to the other when it declines.

Roll, a sideways lean, is corrected too, from the resting face, after pitch.
upright.py refuses roll because solving its base-plane fit for the full normal
skewed slab reconstructions; the resting face reads 3.4 degrees of roll at most
across the 30 test products, under 2.5 on the shelf units, so that failure does
not recur here. A correction larger than ROLL_FLAG_DEGREES is applied and
flagged, because nothing measured so far leans that far sideways. Everything
here is a proposal recorded in the asset record, and the grading sheet is still
where a person confirms it.
"""

import math

import numpy as np
from scipy.spatial import ConvexHull

import upright

FRONT_YAW_DEGREES = 180.0
LAMP_CATEGORIES = frozenset(("lamp", "floor_lamp", "table_lamp", "ceiling_light"))
LIMIT_DEGREES = upright.LIMIT_DEGREES
# A straightening angle near 45 degrees cannot tell the front from a side.
AMBIGUOUS_DEGREES = 38.0
ROLL_FLAG_DEGREES = 8.0
# Hull area over minimum-rectangle area is pi/4 = 0.785 for a circle and 1 for
# a box. Both conditions, because an oval table is round-edged but still long.
ROUND_FILL = 0.82
ROUND_ASPECT = 1.15
# Hull faces this close to the resting face are averaged into it, so four
# slightly uneven feet read as one floor rather than as one tilted triangle.
MERGE_DEGREES = 3.0


def resting_normal(vertices):
    """Outward unit normal of the face the object rests on, or None."""
    hull = ConvexHull(vertices)
    centre = vertices.mean(axis=0)
    best, best_tilt = None, None
    for simplex, equation in zip(hull.simplices, hull.equations):
        normal = equation[:3]
        tilt = math.degrees(math.acos(np.clip(-normal[1], -1, 1)))
        if tilt > LIMIT_DEGREES or (best_tilt is not None and tilt >= best_tilt):
            continue
        # Stable only if the centroid, dropped onto this face, lands inside it.
        a, b, c = vertices[simplex]
        point = centre - normal * (centre @ normal + equation[3])
        u, v, w = b - a, c - a, point - a
        uu, uv, vv, wu, wv = u @ u, u @ v, v @ v, w @ u, w @ v
        denominator = uu * vv - uv * uv
        if denominator <= 0:
            continue
        s, t = (vv * wu - uv * wv) / denominator, (uu * wv - uv * wu) / denominator
        if s >= -1e-9 and t >= -1e-9 and s + t <= 1 + 1e-9:
            best, best_tilt = normal, tilt
    if best is None:
        return None
    normals, areas = [], []
    for simplex, equation in zip(hull.simplices, hull.equations):
        if math.degrees(math.acos(np.clip(equation[:3] @ best, -1, 1))) <= MERGE_DEGREES:
            a, b, c = vertices[simplex]
            normals.append(equation[:3])
            areas.append(np.linalg.norm(np.cross(b - a, c - a)) / 2)
    normal = np.average(normals, axis=0, weights=areas)
    return normal / np.linalg.norm(normal)


def _resting_pitch(vertices):
    normal = resting_normal(vertices)
    if normal is None:
        return 0.0, f"no stable face within {LIMIT_DEGREES:.0f} deg"
    # The rotation about +X that turns the normal straight down.
    return round(math.degrees(math.atan2(normal[2], -normal[1])), 1), "ok"


def roll_rotation(degrees):
    """Right-handed rotation about +Z, matching prepare.py --roll."""
    angle = np.radians(degrees)
    cosine, sine = np.cos(angle), np.sin(angle)
    return np.array([[cosine, -sine, 0], [sine, cosine, 0], [0, 0, 1]])


def _roll(vertices):
    """The rotation about +Z that turns the resting face's normal straight down."""
    normal = resting_normal(vertices)
    return 0.0 if normal is None else round(math.degrees(math.atan2(-normal[0], -normal[1])), 1)


def level(vertices, category):
    """Pitch and roll in degrees, applied in that order, and the pitch estimate used."""
    estimates = [("resting_face", _resting_pitch), ("base_plane", upright.estimate)]
    if category in LAMP_CATEGORIES:
        estimates.reverse()
    reasons = []
    for method, estimate in estimates:
        pitch, reason = estimate(vertices)
        if pitch or reason == "ok":
            levelled = vertices @ upright.rotation(pitch).T
            return {"pitch": pitch, "method": method, "roll": _roll(levelled)}
        reasons.append(f"{method}: {reason}")
    return {"pitch": 0.0, "method": "none", "roll": 0.0, "reasons": reasons}


def straighten(vertices):
    """Yaw in degrees that squares the footprint to the axes, and why."""
    plan = vertices[:, [0, 2]]
    outline = ConvexHull(plan)
    corners = plan[outline.vertices]
    best = None
    for i in range(len(corners)):
        edge = corners[(i + 1) % len(corners)] - corners[i]
        angle = math.atan2(edge[1], edge[0])
        c, s = math.cos(angle), math.sin(angle)
        turned = corners @ np.array([[c, -s], [s, c]])
        extent = np.ptp(turned, axis=0)
        area = extent[0] * extent[1]
        if best is None or area < best[0]:
            best = (area, angle, extent)
    area, angle, extent = best
    # ConvexHull.volume is area in two dimensions.
    if outline.volume / area < ROUND_FILL and extent.max() / extent.min() < ROUND_ASPECT:
        return 0.0, "round footprint"
    degrees = math.degrees(angle) % 90
    if degrees > 45:
        degrees -= 90
    return round(degrees, 1), "ok"


def orient(vertices, category):
    """The pose prepare.py applies, with everything a reviewer needs to check it."""
    vertices = np.asarray(vertices, dtype=float)
    levelled = level(vertices, category)
    upright_vertices = vertices @ upright.rotation(levelled["pitch"]).T @ roll_rotation(levelled["roll"]).T
    turn, turn_reason = straighten(upright_vertices)
    flags = []
    if levelled["method"] == "none":
        flags.append("not levelled: " + "; ".join(levelled["reasons"]))
    if abs(levelled["roll"]) > ROLL_FLAG_DEGREES:
        flags.append(f"sideways lean of {levelled['roll']} deg corrected; more than any product measured")
    if abs(turn) > AMBIGUOUS_DEGREES:
        flags.append(f"footprint turned {turn} deg, too close to 45 deg to be sure of the front")
    return {"method": "spar3d_auto", "pitch_degrees": levelled["pitch"],
            "yaw_degrees": round(turn + FRONT_YAW_DEGREES, 1),
            "level_method": levelled["method"], "roll_degrees": levelled["roll"],
            "straighten_degrees": turn, "straighten_reason": turn_reason,
            "front_yaw_degrees": FRONT_YAW_DEGREES, "flags": flags}
