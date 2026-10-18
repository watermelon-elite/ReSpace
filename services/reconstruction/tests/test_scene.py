import json

import numpy as np
import pytest

from respace_reconstruction.scene import SceneBundle


def scene_data():
    return {"capture_id":"capture", "scene_id":"scene", "reconstruction_revision":1,
            "entities":[{"id":"chair", "label":"Actual chair", "category":"chair", "kind":"furniture",
              "asset":"chair.obj", "local_to_scan_transform":np.eye(4).flatten(order="F").tolist(),
              "bounds_min":[-.3,0,-.3], "bounds_max":[.3,1,.3], "material_ids":["fabric"],
              "move_ready":False, "observed_fraction":.7}],
            "materials":[{"id":"fabric", "owner_id":"chair", "slot":"fabric", "source_material":"photo_fabric"}],
            "navigation":{"floor_polygons":[[[-2,-2],[2,-2],[2,2],[-2,2]]],
                          "floor_height":0, "spawn_position":[1,1.6,1], "spawn_yaw":0}}


def test_incomplete_object_cannot_be_published_as_finished():
    data=scene_data()
    assert not SceneBundle.model_validate(data).ready
    data["ready"]=True
    with pytest.raises(ValueError, match="ready movable"):
        SceneBundle.model_validate(data)
    data["entities"][0]["move_ready"]=True
    assert SceneBundle.model_validate(data).ready


def test_architecture_and_material_ownership_are_explicit():
    data=scene_data()
    data["entities"][0]["kind"]="fixed"
    data["entities"][0]["move_ready"]=True
    with pytest.raises(ValueError, match="built-ins"):
        SceneBundle.model_validate(data)
    data=scene_data()
    data["materials"][0]["owner_id"]="unrelated-wall"
    with pytest.raises(ValueError, match="owner"):
        SceneBundle.model_validate(data)


def test_reject_scene_frame_and_uncommitted_texture(tmp_path):
    data=scene_data()
    data["entities"][0]["local_to_scan_transform"][0]=2
    with pytest.raises(ValueError, match="rigid"):
        SceneBundle.model_validate(data)
    scene=SceneBundle.model_validate(scene_data())
    (tmp_path/"chair.obj").write_text("mtllib chair.mtl\n")
    (tmp_path/"chair.mtl").write_text("newmtl photo_fabric\nmap_Kd ../private.png\n")
    for name in ("quality.json","provenance.json"):
        (tmp_path/name).write_text(json.dumps({}))
    with pytest.raises(ValueError, match="dependency"):
        scene.validate_files(tmp_path, {p.name for p in tmp_path.iterdir()})


def test_camera_spawn_must_be_on_supported_floor():
    data=scene_data()
    data["navigation"]["spawn_position"]=[5,1.6,5]
    with pytest.raises(ValueError, match="floor"):
        SceneBundle.model_validate(data)
