import numpy as np
from PIL import Image

from respace_reconstruction.completion_probe import masked_input,candidate_checks


def test_crop_calibration_tracks_observed_pixels_and_alpha():
    image=Image.new("RGB",(640,480),(255,0,0))
    mask=np.zeros((480,640),dtype=bool)
    mask[100:300,200:350]=True
    result,metadata=masked_input(image,mask,[500,500,320,240])
    assert result.mode=="RGB" and result.size==(512,512)
    left,top,_,_=metadata["crop_xyxy"]
    px,py=metadata["padding_xy"]
    scale=512/metadata["square_size"]
    old_u,old_v=345.,215.
    fx,fy,cx,cy=metadata["intrinsics"]
    assert abs(((old_u-left+px)*scale-cx)/fx-(old_u-320)/500)<1e-8
    assert abs(((old_v-top+py)*scale-cy)/fy-(old_v-240)/500)<1e-8
    assert np.all(np.asarray(result)[0,0]==128)


def test_open_generated_candidate_is_not_accepted_as_complete(tmp_path):
    candidate=tmp_path/"candidate.obj"
    candidate.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    checks=candidate_checks(candidate)
    assert not checks["watertight"] and not checks["edge_manifold"]
