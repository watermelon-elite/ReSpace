import numpy as np

from respace_reconstruction.instances import InstanceSeed, assign_surface_ownership, room_objects,mask_geometric_support


def test_masks_require_depth_visibility_and_cross_view_agreement(tmp_path, capture):
    manifest, payloads = capture
    for name, data in payloads.items():
        (tmp_path / name).write_bytes(data)
    transform = np.eye(4)
    transform[2, 3] = -2
    seed = InstanceSeed("chair-1", "source-1", "chair", "Chair", "furniture", transform, np.array([1., 1., .2]))
    # First face is on the observed plane. Second is behind it, third is in free space.
    front = np.array([[-.1,-.1,-2],[.1,-.1,-2],[0,.1,-2]])
    vertices = np.concatenate([front, front+[0,0,-.4], front+[0,0,.4]])
    faces = np.arange(9).reshape(3,3)
    observations = [{"entity_id": seed.id, "frame": frame,
                     "mask": np.ones((120,160),dtype=bool), "score": .95}
                    for frame in manifest.frames[:2]]
    owner, report = assign_surface_ownership(vertices, faces, [seed], observations, tmp_path)
    assert owner.tolist() == [0,-1,-1]
    assert report["instances"][0]["triangles"] == 1
    owner, _ = assign_surface_ownership(vertices, faces, [seed], observations[:1], tmp_path)
    assert owner.tolist() == [-1,-1,-1]


def test_storage_category_is_not_silently_declared_builtin():
    obj = {"identifier":"cabinet", "category":{"storage":{}}, "dimensions":[1,2,.5],
           "transform":np.eye(4).flatten(order="F").tolist()}
    seeds = room_objects({"objects":[obj], "walls":[]})
    assert seeds[0].kind == "unresolved_storage"
    assert room_objects({"objects":[dict(obj,isBuiltIn=True)]})[0].kind == "fixed"


def test_high_score_mask_on_wall_behind_object_has_no_measured_support(tmp_path,capture):
    manifest,payloads=capture
    for name,data in payloads.items(): (tmp_path/name).write_bytes(data)
    transform=np.eye(4);transform[2,3]=-1.
    seed=InstanceSeed("chair-1","source-1","chair","Chair","furniture",transform,np.array([.5,.5,.5]))
    fraction,count=mask_geometric_support(seed,manifest.frames[2],np.ones((120,160),dtype=bool),tmp_path)
    assert fraction==0 and count==0
