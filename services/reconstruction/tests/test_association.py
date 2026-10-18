import numpy as np

from respace_reconstruction.association import associate,label_family
from respace_reconstruction.discover_capture import masked_world_points


def test_association_requires_reciprocal_masks_and_separate_views(tmp_path,capture):
    manifest,payloads=capture
    for name,data in payloads.items(): (tmp_path/name).write_bytes(data)
    proposals=[]
    for index,frame in enumerate(manifest.frames[:3]):
        # The left/right objects occupy separate source pixels in each camera.
        for side,center in enumerate((-.5,.5)):
            xcam=frame.metadata.camera_to_scan_transform[12]
            cx=320+480*(center-xcam)/2
            mask=np.zeros((480,640),dtype=bool)
            mask[180:300,max(0,int(cx-35)):min(640,int(cx+35))]=True
            points,_=masked_world_points(frame,mask,tmp_path)
            proposals.append({"id":f"p-{index}-{side}","frame":frame,"label":"chair",
                "mask":mask,"points":points,"sam_score":.95})
    groups=associate(proposals,tmp_path)
    assert len(groups)==2
    assert all(g["independent_views"]==3 for g in groups)
    assert all(g["multi_view_supported"] and not g["ready"] for g in groups)


def test_ambiguous_detector_phrase_cannot_decide_object_mobility():
    assert label_family("cabinet refrigerator")=="unresolved"
    assert label_family("floor lamp table lamp")=="lamp"
