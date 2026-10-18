import numpy as np

from respace_reconstruction.geometry import camera_to_cv_world, repair_small_holes
from respace_reconstruction.pipeline import semantic_openings, complete_semantic_planes


def ring(size):
    # Plane with a square central opening; outer boundary must not be sealed.
    vertices = np.array([[-1,-1,0], [1,-1,0], [1,1,0], [-1,1,0],
        [-size,-size,0], [size,-size,0], [size,size,0], [-size,size,0]], dtype=float)
    faces = np.array([[0,1,5], [0,5,4], [1,2,6], [1,6,5], [2,3,7], [2,7,6], [3,0,4], [3,4,7]])
    return vertices, faces


def test_only_small_hole_is_repaired_with_exact_face_provenance():
    vertices, faces = ring(.04)
    repaired, patches = repair_small_holes(vertices, faces)
    assert np.array_equal(repaired[:len(faces)], faces)
    assert len(patches) == 1
    assert patches[0]["face_indices"] == [8, 9]
    assert len(repaired) == 10
    vertices, faces = ring(.5)
    repaired, patches = repair_small_holes(vertices, faces)
    assert len(repaired) == len(faces)
    assert patches == []


def test_arkit_camera_axes_are_converted_once(capture):
    manifest, _ = capture
    c2w = camera_to_cv_world(manifest.frames[0].metadata)
    assert np.allclose(c2w @ [0,0,2,1], [-.4,0,-2,1])
    assert np.linalg.det(c2w[:3,:3]) == 1


def test_semantic_opening_transform_uses_column_major_encoding():
    transform = np.eye(4)
    transform[:3,3] = [1,2,3]
    boxes = semantic_openings({"doors": [{"transform": transform.T.tolist(), "dimensions": [1,2,.1]}]})
    inverse, half = boxes[0]
    assert np.allclose(inverse @ [1,2,3,1], [0,0,0,1])
    assert np.all(half > 0)


def test_semantic_wall_completion_protects_door_and_tracks_added_faces():
    import open3d as o3d
    # Existing patch is well below this wall. All eligible wall cells are missing.
    mesh = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector([[-1,-4,0],[1,-4,0],[0,-3,0]]),
        o3d.utility.Vector3iVector([[0,1,2]]))
    transform = np.eye(4).T.tolist()
    wall = {"identifier": "wall-1", "transform": transform, "dimensions": [3,3,0]}
    door = {"transform": transform, "dimensions": [1,2,0]}
    room = {"walls": [wall], "doors": [door]}
    completed, patches = complete_semantic_planes(mesh, room, semantic_openings(room), o3d)
    assert patches and patches[0]["source_identifier"] == "wall-1"
    triangles = np.asarray(completed.triangles)[patches[0]["face_indices"]]
    points = np.asarray(completed.vertices)[triangles]
    centers = points.mean(axis=1)
    assert not ((abs(centers[:,0]) < .5) & (abs(centers[:,1]) < 1)).any()
    assert (points[:,:,2] == 0).all()


def test_floor_completion_respects_concave_polygon():
    import open3d as o3d
    mesh = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector([[-1,-4,-2],[1,-4,-2],[0,-3,-2]]),
        o3d.utility.Vector3iVector([[0,1,2]]))
    floor = {"identifier": "floor", "transform": np.eye(4).T.tolist(),
        "polygonCorners": [[0,0,0],[2,0,0],[2,1,0],[1,1,0],[1,2,0],[0,2,0]]}
    completed, patches = complete_semantic_planes(mesh, {"floors": [floor]}, [], o3d)
    assert patches
    points = np.asarray(completed.vertices)[np.asarray(completed.triangles)[patches[0]["face_indices"]]]
    assert not ((points[:,:,0] > 1.0001) & (points[:,:,1] > 1.0001)).any()


def test_floor_completion_does_not_bridge_a_narrow_notch():
    import open3d as o3d
    mesh = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector([[-1,-4,-2],[1,-4,-2],[0,-3,-2]]),
        o3d.utility.Vector3iVector([[0,1,2]]))
    polygon = [[0,0,0],[2,0,0],[2,2,0],[1.02,2,0],[1.02,.2,0],[1,.2,0],[1,2,0],[0,2,0]]
    completed, patches = complete_semantic_planes(mesh, {"floors": [{"transform": np.eye(4).T.tolist(), "polygonCorners": polygon}]}, [], o3d)
    faces = np.asarray(completed.triangles)[patches[0]["face_indices"]]
    points = np.asarray(completed.vertices)[faces]
    low, high = points.min(axis=1), points.max(axis=1)
    assert not ((low[:,0] < 1.02) & (high[:,0] > 1) & (high[:,1] > .2001)).any()
