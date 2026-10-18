"""Reusable seamless PBR patterns and metric UVs; no photographs or API calls.

Maps are neutral so a material's own RGB color tints a shared pattern. A room
exports only the families it uses, with three files per family regardless of
object count. All patterns are periodic, including their normal maps.
"""
from functools import lru_cache
import io
import math
from typing import Literal

import numpy as np
from PIL import Image

TextureFamily = Literal["wood", "fabric", "leather", "metal", "plastic", "stone",
                        "ceramic", "glass", "paint", "rubber", "foliage", "paper"]
# Physical repeat period (meters), color contrast, relief height (meters).
PROFILES = {"wood": (.6, .16, .0004), "fabric": (.15, .13, .0005),
            "leather": (.2, .1, .0003), "metal": (.3, .035, .00004),
            "plastic": (.2, .025, .00004), "stone": (.6, .12, .00015),
            "ceramic": (.3, .018, .00002), "glass": (.5, .004, .000002),
            "paint": (.3, .025, .00006), "rubber": (.15, .055, .0002),
            "foliage": (.15, .14, .00015), "paper": (.2, .025, .00003)}
VERSION = 1
SIZE = 256


def _noise(u, v, seed, frequencies):
    rng = np.random.default_rng(seed)
    result = np.zeros_like(u)
    for frequency in frequencies:
        for _ in range(3):
            x, y = rng.integers(-frequency, frequency+1, size=2)
            if x == y == 0:
                x = 1
            phase = rng.uniform(0, 2*math.pi)
            result += np.sin(2*math.pi*(x*u+y*v)+phase)/math.sqrt(frequency)
    return result/max(float(np.max(np.abs(result))), 1e-9)


def _leather(u, v):
    rng = np.random.default_rng(193)
    centers = rng.uniform(.15, .85, (16, 16, 2))
    x, y = u*16, v*16
    ix, iy = np.floor(x).astype(int), np.floor(y).astype(int)
    distances = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            jitter = centers[(iy+dy) % 16, (ix+dx) % 16]
            distances.append((x-ix-dx-jitter[:, :, 0])**2+(y-iy-dy-jitter[:, :, 1])**2)
    nearest = np.partition(np.stack(distances), 1, axis=0)[:2]
    return 1-np.exp(-24*(np.sqrt(nearest[1])-np.sqrt(nearest[0])))


@lru_cache(maxsize=len(PROFILES))
def texture_maps(family):
    if family not in PROFILES:
        raise ValueError("Unknown reusable material texture family")
    # Build one unique period, then duplicate its first row/column at the edge.
    u, v = np.meshgrid(np.arange(SIZE-1)/(SIZE-1), np.arange(SIZE-1)/(SIZE-1))
    broad = _noise(u, v, 17, (2, 4, 8))
    fine = _noise(u, v, 71, (24, 48, 80))
    if family == "wood":
        grain = 2*math.pi*(18*u+.65*np.sin(2*math.pi*v)+.22*broad)
        height = .45*np.sin(grain)+.18*np.sin(2*grain)+.12*fine+.2*broad
    elif family == "fabric":
        warp, weft = np.cos(2*math.pi*48*u), np.cos(2*math.pi*48*v)
        height = .45*warp*weft+.25*(warp+weft)+.05*fine
    elif family == "leather":
        height = _leather(u, v)+.08*fine
    elif family == "metal":
        height = .7*_noise(u, v*.0, 29, (32, 64, 96))+.15*fine
    elif family == "stone":
        height = .35*broad+.2*fine+.45*np.exp(-12*np.sin(2*math.pi*(2*u+v)+1.2*broad)**2)
    elif family == "foliage":
        height = .55*np.cos(2*math.pi*u)+.3*np.cos(2*math.pi*(6*v+2*np.abs(np.sin(math.pi*u))))+.1*broad
    elif family == "paper":
        height = .2*broad+.55*_noise(u, v, 33, (32, 80))
    else:
        height = .25*broad+.75*fine
    height -= height.min()
    height /= max(float(height.max()), 1e-9)
    period, contrast, relief = PROFILES[family]
    gray = 1-contrast*(1-height)
    albedo = np.repeat(gray[:, :, None], 3, axis=2)
    roughness = .88+.12*height
    dx = (np.roll(height, -1, 1)-np.roll(height, 1, 1))*(SIZE-1)/(2*period)*relief
    dy = (np.roll(height, -1, 0)-np.roll(height, 1, 0))*(SIZE-1)/(2*period)*relief
    normals = np.stack([-dx, -dy, np.ones_like(dx)], axis=2)
    normals /= np.linalg.norm(normals, axis=2, keepdims=True)
    maps = {}
    for suffix, pixels in (("color", albedo), ("roughness", roughness), ("normal", normals*.5+.5)):
        padding = [(0, 1), (0, 1)]+([(0, 0)] if pixels.ndim == 3 else [])
        pixels = np.pad(pixels, padding, mode="wrap")
        stream = io.BytesIO()
        Image.fromarray(np.round(np.clip(pixels, 0, 1)*255).astype(np.uint8)).save(stream, format="PNG")
        maps[suffix] = stream.getvalue()
    return maps


def export_textures(family, directory):
    paths = {}
    for suffix, data in texture_maps(family).items():
        name = f"material-v{VERSION}-{family}-{suffix}.png"
        if not (directory/name).exists():
            (directory/name).write_bytes(data)
        paths[suffix] = name
    return paths


def part_uvs(part, vertices, faces, period):
    """Face-corner UVs in metric part coordinates; seams never stretch a face."""
    center = np.array([part.center.x, part.center.y, part.center.z])
    c, s = math.cos(part.yaw), math.sin(part.yaw)
    rotation = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    local = (vertices-center) @ rotation
    triangles = local[faces]
    normals = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
    axes = np.argmax(np.abs(normals), axis=1)
    result = np.empty((len(faces), 3, 2))
    for axis, plane in ((0, (2, 1)), (1, (0, 2)), (2, (0, 1))):
        mask = axes == axis
        result[mask] = triangles[mask][:, :, list(plane)]/period
    if part.shape in ("cylinder", "ellipsoid"):
        size = np.array([part.size.x, part.size.y, part.size.z])
        normalized = triangles/(size/2)
        angle = np.arctan2(normalized[:, :, 2], normalized[:, :, 0])/(2*math.pi)
        poles = np.linalg.norm(normalized[:, :, [0, 2]], axis=2) < 1e-6
        if part.shape == "ellipsoid":
            # A pole's floating-point atan2 is arbitrary. Exclude it from seam
            # detection, unwrap the real neighbors, then interpolate longitude.
            for index in np.flatnonzero(poles.any(axis=1)):
                valid = angle[index, ~poles[index]]
                unwrapped = valid[0]+(valid-valid[0]+.5) % 1-.5
                angle[index, ~poles[index]] = unwrapped
                angle[index, poles[index]] = unwrapped.mean()
        seam = angle.max(axis=1)-angle.min(axis=1) > .5
        angle = np.where(seam[:, None] & (angle < 0), angle+1, angle)
        # An integral repeat count closes the longitudinal seam on curved parts.
        a, b = size[0]/2, size[2]/2
        perimeter = math.pi*(3*(a+b)-math.sqrt((3*a+b)*(a+3*b)))
        u = angle*max(1, round(perimeter/period))
        if part.shape == "cylinder":
            mask = axes != 1  # End caps retain planar mapping.
            result[mask, :, 0] = u[mask]
            result[mask, :, 1] = triangles[mask, :, 1]/period
        else:
            result[:, :, 0] = u
            result[:, :, 1] = np.arccos(np.clip(normalized[:, :, 1], -1, 1))/math.pi * (math.pi/4*(size[1]+(size[0]+size[2])/2))/period
    if not np.isfinite(result).all():
        raise ValueError("Generated material UV coordinates are invalid")
    return result
