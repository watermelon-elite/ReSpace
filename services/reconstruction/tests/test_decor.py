import numpy as np
from PIL import Image
import pytest

from respace_reconstruction.decor import WallPlane,rectified_asset,wall_rays
from respace_reconstruction.obj import read_obj


def test_decor_preserves_metric_scale_source_pixels_and_independent_asset(tmp_path,capture):
    manifest,payloads=capture
    frame=manifest.frames[2]
    # Smooth coordinate-coded source pixels give an exact orientation/UV oracle
    # without checkerboard-edge interpolation obscuring a half-pixel difference.
    u,v=np.meshgrid(np.arange(640),np.arange(480))
    image=Image.fromarray(np.stack([u/3,v/2,np.full_like(u,71)],axis=2).astype(np.uint8))
    wall=np.eye(4);wall[2,3]=-2
    plane=WallPlane("wall-1",wall,4,3)
    mask=np.zeros((480,640),dtype=bool);mask[180:300,200:440]=True
    result=rectified_asset(image,mask,frame.metadata,plane,tmp_path,"poster-1",512)
    extent=np.array(result["bounds_max"])-result["bounds_min"]
    assert np.allclose(extent[:2],[239*2/480,119*2/480],atol=1e-6)
    transform=np.array(result["local_to_scan_transform"]).reshape(4,4,order="F")
    assert abs(transform[2,3]+1.995)<1e-8
    mesh=read_obj(tmp_path/result["asset"])
    assert len(mesh.faces)==2 and len(mesh.uvs)==4 and result["double_sided"]
    with Image.open(tmp_path/result["texture"]) as texture:
        # At output center the homography samples the original captured image.
        expected=np.array(image)[240,320]
        actual=np.array(texture)[texture.height//2,texture.width//2,:3]
        assert np.max(abs(actual.astype(int)-expected))<=2
    assert result["source_pixels"] and not result["ready"]


def test_decor_cannot_attach_to_wrong_wall(tmp_path,capture):
    manifest,_=capture
    meta=manifest.frames[2].metadata
    wall=np.eye(4);wall[2,3]=2 # Behind the camera.
    image=Image.new("RGB",(640,480))
    with pytest.raises(ValueError,match="project reliably"):
        rectified_asset(image,np.ones((480,640),dtype=bool),meta,WallPlane("wall-1",wall,4,3),tmp_path,"poster-1")
