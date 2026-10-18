"""Metric wall-decor surfaces with rectified source pixels, never generated text.

This is a planar asset builder, not a claim that a frame/tray has been recovered.
Nonplanar decor needs its separately reconstructed geometry.
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from .geometry import camera_to_cv_world
from .models import SAFE_NAME


@dataclass
class WallPlane:
    id: str
    local_to_scan: np.ndarray
    width: float
    height: float


def wall_rays(pixels,metadata,wall,offset=0.):
    """Intersect calibrated sensor rays with a measured wall-local Z plane."""
    camera=camera_to_cv_world(metadata)
    wall_to_camera=np.linalg.inv(wall.local_to_scan)@camera
    fx,fy,cx,cy=metadata.intrinsics
    directions=np.c_[(pixels[:,0]-cx)/fx,(pixels[:,1]-cy)/fy,np.ones(len(pixels))]
    directions=directions@wall_to_camera[:3,:3].T
    origin=wall_to_camera[:3,3]
    denominator=directions[:,2]
    distance=np.divide(offset-origin[2],denominator,out=np.full(len(pixels),np.nan),where=abs(denominator)>1e-8)
    points=origin+directions*distance[:,None]
    valid=np.isfinite(points).all(axis=1)&(distance>.1)&(distance<6)
    return points,valid


def rectified_asset(image,mask,metadata,wall,folder: Path,identity,pixels_per_meter=1024):
    if not SAFE_NAME.fullmatch(identity) or ".." in identity:
        raise ValueError("Unsafe decor identity")
    transform=np.asarray(wall.local_to_scan,dtype=float)
    if (transform.shape!=(4,4) or not np.isfinite(transform).all()
        or not np.allclose(transform[3],[0,0,0,1])
        or not np.allclose(transform[:3,:3].T@transform[:3,:3],np.eye(3),atol=.001)
        or np.linalg.det(transform[:3,:3])<.99):
        raise ValueError("Wall transform must be rigid")
    if image.size!=(metadata.width,metadata.height) or mask.shape!=(metadata.height,metadata.width):
        raise ValueError("Decor must use the full-resolution calibrated sensor image and mask")
    if not (0<wall.width<=25 and 0<wall.height<=10 and 64<=pixels_per_meter<=4096):
        raise ValueError("Invalid wall or texture scale")
    y,x=np.nonzero(mask)
    if len(x)<256:
        raise ValueError("Insufficient decor image support")
    # Evaluate an evenly spread sample, preserving the original mask for alpha.
    stride=max(1,len(x)//100000)
    points,valid=wall_rays(np.c_[x[::stride],y[::stride]],metadata,wall)
    if valid.mean()<.99:
        raise ValueError("Decor does not project reliably onto its wall")
    lo,hi=points[valid,:2].min(axis=0),points[valid,:2].max(axis=0)
    if (np.abs(np.r_[lo[0],hi[0]])>wall.width/2+.01).any() or (np.abs(np.r_[lo[1],hi[1]])>wall.height/2+.01).any():
        raise ValueError("Decor mask extends outside its measured wall")
    extent=hi-lo
    if (extent<.03).any() or (extent>5).any():
        raise ValueError("Invalid metric decor extent")
    width,height=np.clip(np.ceil(extent*pixels_per_meter).astype(int),32,2048)
    # Output image X follows wall X; image Y follows negative wall Y. Homography
    # maps output pixels directly into the source photo; no OCR or synthesis.
    pixel_to_local=np.array([[extent[0]/width,0,lo[0]],
                             [0,-extent[1]/height,hi[1]],
                             [0,0,0],[0,0,1]],dtype=float)
    world_to_camera=np.linalg.inv(camera_to_cv_world(metadata))
    fx,fy,cx,cy=metadata.intrinsics
    k=np.array([[fx,0,cx],[0,fy,cy],[0,0,1.]])
    homography=k@(world_to_camera@transform)[:3]@pixel_to_local
    if abs(homography[2,2])<1e-8:
        raise ValueError("Degenerate decor projection")
    h=homography/homography[2,2]
    coefficients=tuple(h.flat[:8])
    rgb=image.convert("RGB").transform((int(width),int(height)),Image.Transform.PERSPECTIVE,
            coefficients,Image.Resampling.BICUBIC)
    alpha=Image.fromarray((mask.astype(bool)*255).astype(np.uint8)).transform(
            rgb.size,Image.Transform.PERSPECTIVE,coefficients,Image.Resampling.NEAREST)
    rgb.putalpha(alpha)
    folder.mkdir(parents=True,exist_ok=True)
    rgb.save(folder/(identity+".png"))
    (folder/(identity+".mtl")).write_text(f"newmtl {identity}\nKd 1 1 1\nmap_Kd {identity}.png\n")
    # Half a centimeter toward the capture side prevents z-fighting. The source
    # texture was rectified at the wall plane, so this is only a render offset.
    camera_local=np.linalg.inv(transform)@camera_to_cv_world(metadata)
    offset=.005 if camera_local[2,3]>=0 else -.005
    center=(lo+hi)/2
    local_to_scan=transform.copy()
    local_to_scan[:3,3]=(transform@np.r_[center,offset,1])[:3]
    w,h=extent/2
    vertices=np.array([[-w,-h,0],[w,-h,0],[w,h,0],[-w,h,0]])
    # The native material must render both sides. Duplicating reverse faces would
    # cause z-fighting in a loader that already enables double-sided materials.
    with (folder/(identity+".obj")).open("w") as stream:
        stream.write(f"mtllib {identity}.mtl\nusemtl {identity}\n")
        np.savetxt(stream,vertices,fmt="v %.8f %.8f %.8f")
        stream.write("vt 0 0\nvt 1 0\nvt 1 1\nvt 0 1\nf 1/1 2/2 3/3\nf 1/1 3/3 4/4\n")
    return {"asset":identity+".obj","texture":identity+".png","support_id":wall.id,
            "local_to_scan_transform":local_to_scan.flatten(order="F").tolist(),
            "bounds_min":[-float(w),-float(h),0.],"bounds_max":[float(w),float(h),0.],
            "source_pixels":True,"double_sided":True,"method":"calibrated_wall_plane_rectification_v1",
            "ready":False,"remaining_checks":["independent_view_consistency","planarity_or_frame_geometry","clean_wall_behind_decor"]}
