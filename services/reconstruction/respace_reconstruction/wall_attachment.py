"""Choose measured support planes using mesh contact and center distance."""
from dataclasses import dataclass

import numpy as np
from shapely import Point


@dataclass
class WallFrame:
    id: str
    a: np.ndarray
    b: np.ndarray
    inward_normal: np.ndarray

    @property
    def length(self):
        return float(np.linalg.norm(self.b-self.a))


def wall_frame(identity, a, b, floor):
    a, b = np.array(a), np.array(b)
    tangent = (b-a)/np.linalg.norm(b-a)
    normal = np.array([-tangent[1], tangent[0]])
    if not floor.buffer(.001).covers(Point((a+b)/2+normal*.05)):
        a, b, normal = b, a, -normal
    return WallFrame(identity, a, b, normal)


def attached_wall(vertices, walls):
    """A panel's edge touching a corner must not beat its own wall plane."""
    center = (vertices.min(axis=0)+vertices.max(axis=0))/2
    candidates = []
    for wall in walls:
        tangent = (np.array(wall.b)-wall.a)/wall.length
        along = (vertices[:, [0, 2]]-wall.a) @ tangent
        signed = (vertices[:, [0, 2]]-wall.a) @ wall.inward_normal
        gap = max(0., float(signed.min()), -float(signed.max()))
        if gap < .2 and along.max() > 0 and along.min() < wall.length:
            distance = abs(float((center[[0, 2]]-wall.a) @ wall.inward_normal))
            candidates.append((distance, gap, wall.id, wall))
    return min(candidates, key=lambda item: item[:3])[-1] if candidates else None
