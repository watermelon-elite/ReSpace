import numpy as np
import pytest

from respace_reconstruction.detection import rotated_box, upright_turns


@pytest.mark.parametrize("turns",range(4))
def test_detection_boxes_return_to_sensor_calibration(turns):
    original=np.array([14.,20.,103.,76.])
    rotated=rotated_box(original,640,480,turns)
    w,h=(480,640) if turns%2 else (640,480)
    assert np.allclose(rotated_box(rotated,w,h,-turns),original)


def test_gravity_drives_detector_orientation(capture):
    manifest,_=capture
    meta=manifest.frames[0].metadata.model_copy(deep=True)
    assert upright_turns(meta)==0
    transform=np.eye(4)
    transform[:3,:3]=[[0,-1,0],[1,0,0],[0,0,1]]
    meta.camera_to_scan_transform=transform.flatten(order="F").tolist()
    assert upright_turns(meta)==1
