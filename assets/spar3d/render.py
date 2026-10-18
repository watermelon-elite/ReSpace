"""Software rasterizer for grading reconstructions. No GPU, no window, no OpenGL.

Renders a GLB from several azimuths, textured and as untextured clay. Clay is
the honest view: a baked photo texture hides bad geometry, matte grey does not.

Orthographic on purpose. A perspective camera makes two products at different
distances hard to compare, and we are judging shape, not photography.
"""

import numpy as np
from PIL import Image

AMBIENT = 0.35
CLAY = np.array([0.72, 0.70, 0.67])
BACKDROP = 250


def _basis(azimuth_deg, elevation_deg):
    """Camera right/up/forward for an orbit position. World up is +Y."""
    a, e = np.radians(azimuth_deg), np.radians(elevation_deg)
    forward = np.array([np.sin(a) * np.cos(e), np.sin(e), np.cos(a) * np.cos(e)])
    right = np.cross([0.0, 1.0, 0.0], forward)
    right /= np.linalg.norm(right)
    return np.stack([right, np.cross(forward, right), forward])


def render(mesh, size=320, azimuth=0.0, elevation=18.0, clay=False):
    """One orthographic view, fit to frame with a small margin."""
    basis = _basis(azimuth, elevation)
    view = mesh.vertices @ basis.T
    normals = mesh.vertex_normals @ basis.T

    low, high = view.min(axis=0), view.max(axis=0)
    centre = (low[:2] + high[:2]) / 2
    span = max(high[0] - low[0], high[1] - low[1])
    if span <= 0:
        span = 1.0
    scale = size * 0.88 / span

    # Screen y grows downward, so the up axis is negated here and nowhere else.
    px = (view[:, 0] - centre[0]) * scale + size / 2
    py = -(view[:, 1] - centre[1]) * scale + size / 2
    screen = np.stack([px, py, view[:, 2]], axis=1)

    # Light sits over the camera's shoulder: front-lit, slightly left and above.
    light = np.array([-0.4, 0.55, -0.73])
    light /= np.linalg.norm(light)
    shade = np.clip(normals @ light, 0, 1) * (1 - AMBIENT) + AMBIENT

    texture = None
    if not clay:
        material = getattr(mesh.visual, "material", None)
        image = getattr(material, "baseColorTexture", None)
        uv = getattr(mesh.visual, "uv", None)
        if image is not None and uv is not None:
            texture = (np.asarray(image.convert("RGB"), dtype=np.float32) / 255, uv)

    colour = np.full((size, size, 3), BACKDROP / 255, dtype=np.float32)
    depth = np.full((size, size), np.inf, dtype=np.float32)

    tri = screen[mesh.faces]
    # Back faces are kept. Single-image reconstructions are not reliably wound,
    # and dropping them would punch holes that look like reconstruction errors.
    for index in np.argsort(-tri[:, :, 2].mean(axis=1)):
        face = mesh.faces[index]
        a, b, c = screen[face]
        x0 = max(int(np.floor(min(a[0], b[0], c[0]))), 0)
        x1 = min(int(np.ceil(max(a[0], b[0], c[0]))) + 1, size)
        y0 = max(int(np.floor(min(a[1], b[1], c[1]))), 0)
        y1 = min(int(np.ceil(max(a[1], b[1], c[1]))) + 1, size)
        if x0 >= x1 or y0 >= y1:
            continue

        area = (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])
        if abs(area) < 1e-12:
            continue

        ys, xs = np.mgrid[y0:y1, x0:x1]
        xs = xs + 0.5
        ys = ys + 0.5
        w0 = ((b[0] - xs) * (c[1] - ys) - (c[0] - xs) * (b[1] - ys)) / area
        w1 = ((c[0] - xs) * (a[1] - ys) - (a[0] - xs) * (c[1] - ys)) / area
        w2 = 1 - w0 - w1
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not inside.any():
            continue

        z = w0 * a[2] + w1 * b[2] + w2 * c[2]
        patch = depth[y0:y1, x0:x1]
        hit = inside & (z < patch)
        if not hit.any():
            continue
        patch[hit] = z[hit]

        lit = w0 * shade[face[0]] + w1 * shade[face[1]] + w2 * shade[face[2]]
        if texture is None:
            base = np.broadcast_to(CLAY, hit.shape + (3,))
        else:
            image, uv = texture
            face_uv = uv[face]
            u = w0 * face_uv[0, 0] + w1 * face_uv[1, 0] + w2 * face_uv[2, 0]
            v = w0 * face_uv[0, 1] + w1 * face_uv[1, 1] + w2 * face_uv[2, 1]
            height, width = image.shape[:2]
            # glTF uv origin is top-left, image row 0 is the top, hence 1 - v.
            col = np.clip((u * width).astype(int), 0, width - 1)
            row = np.clip(((1 - v) * height).astype(int), 0, height - 1)
            base = image[row, col]

        colour[y0:y1, x0:x1][hit] = base[hit] * lit[hit, None]

    return Image.fromarray((np.clip(colour, 0, 1) * 255).astype(np.uint8))
