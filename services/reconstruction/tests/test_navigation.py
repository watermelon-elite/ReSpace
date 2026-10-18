import numpy as np
import open3d as o3d
from shapely import Polygon,Point

from respace_reconstruction.navigation import build_navigation
from respace_reconstruction.surfaces import Surface


def test_coarse_tall_fixed_mesh_is_solid_even_when_vertices_miss_body_height(capture):
    manifest,_=capture
    pose=np.eye(4);pose[:3,:3]=[[1,0,0],[0,0,-1],[0,1,0]]
    floor=Surface("floor","floor","floor",pose,Polygon([[-2,-2],[2,-2],[2,2],[-2,2]]))
    cabinet=o3d.geometry.TriangleMesh.create_box(.8,2.2,.8);cabinet.translate([-.4,0,-.9])
    nav=build_navigation(floor,[],np.asarray(cabinet.vertices),manifest.frames,fixed_faces=np.asarray(cabinet.triangles))
    assert nav.obstacles
    assert any(Polygon(p).contains(Point(0,-.5)) for p in nav.obstacles)
    assert not any(Polygon(p).buffer(nav.player_radius).contains(Point(nav.spawn_position[0],nav.spawn_position[2])) for p in nav.obstacles)
