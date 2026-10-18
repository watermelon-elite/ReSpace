"""Run detector + full-resolution SAM masks as auditable inventory evidence.

This command never publishes a finished room. Multi-view instance association,
surface ownership and completion must validate these proposals separately.
"""
import argparse
import gc
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from PIL import Image

from .benchmark import inspect_capture
from .detection import GroundingDINO
from .geometry import masked_world_points
from .instances import SAM2Masks, stable_id
from .store import atomic_json, digest


def select_frames(manifest,audit,limit):
    lookup={f.id:f for f in manifest.frames}
    selected=[]
    cosine=np.cos(np.deg2rad(20))
    for candidate in sorted(audit["frames"],key=lambda f:f["sharpness_laplacian_variance"],reverse=True):
        if candidate["valid_depth_fraction"] < .10:
            continue
        if all(np.linalg.norm(np.array(candidate["position"])-p["position"]) > .35
               or np.dot(candidate["forward"],p["forward"]) < cosine for p in selected):
            selected.append(candidate)
        if len(selected)>=limit:
            break
    return sorted([lookup[f["id"]] for f in selected],key=lambda f:f.metadata.timestamp)


def discover_capture(capture,output,limit=12):
    capture,output=Path(capture).resolve(),Path(output).resolve()
    if output==capture or output==capture/"inputs" or capture/"inputs" in output.parents:
        raise ValueError("Discovery cannot modify the immutable source capture")
    manifest,audit=inspect_capture(capture)
    if audit["invalid_artifacts"] or any(a["type"]!="scene_mesh" for a in audit["missing_artifacts"]):
        raise ValueError("Upload complete calibrated RGB-D and RoomPlan before discovery")
    if not 1<=limit<=64:
        raise ValueError("Discovery frame limit must be in [1,64]")
    frames=select_frames(manifest,audit,limit)
    if not frames:
        raise ValueError("No suitable calibrated depth views for discovery")
    output.mkdir(parents=True,exist_ok=True)
    start=time.monotonic()
    detector=GroundingDINO()
    recipe=detector.recipe
    records=[]
    for frame in frames:
        photo=next(a for a in frame.artifacts if a.type=="jpeg")
        signature=hashlib.sha256(json.dumps({"image":photo.sha256,"recipe":recipe},sort_keys=True).encode()).hexdigest()
        cache=output/("detection-"+signature+".json")
        if cache.is_file():
            boxes=json.loads(cache.read_text())
        else:
            with Image.open(capture/"inputs"/photo.filename) as image:
                boxes=[{"box":d.box.tolist(),"label":d.label,"score":d.score}
                       for d in detector.detect(image,frame.metadata)]
            atomic_json(cache,boxes)
        records.append((frame,photo,boxes))
        print(json.dumps({"stage":"inventory_detection","frame":frame.id,"proposals":len(boxes)}),flush=True)
    del detector
    gc.collect()
    masks=SAM2Masks()
    proposals=[]
    for frame,photo,boxes in records:
        image=None
        for index,box in enumerate(boxes):
            identity=stable_id("proposal",json.dumps([photo.sha256,box,masks.recipe],sort_keys=True))
            cache=output/(identity+".npz")
            if cache.is_file():
                with np.load(cache,allow_pickle=False) as stored:
                    mask,score=stored["mask"].astype(bool),float(stored["score"])
            else:
                if image is None:
                    with Image.open(capture/"inputs"/photo.filename) as source:
                        image=np.array(source.convert("RGB"))
                    masks.set_image(image)
                mask,score=masks.mask(box["box"])
                temporary=cache.with_suffix(".tmp")
                with temporary.open("wb") as stream:
                    np.savez_compressed(stream,mask=mask,score=score)
                temporary.replace(cache)
            points,depth_fraction=masked_world_points(frame,mask,capture/"inputs")
            proposals.append(dict(box,id=identity,frame_id=frame.id,image_sha256=photo.sha256,
                mask_cache=cache.name,mask_sha256=digest(cache),sam_score=score,foreground_pixels=int(mask.sum()),
                valid_depth_fraction=depth_fraction,depth_points=len(points),
                observed_bounds_min=points.min(axis=0).tolist() if len(points) else None,
                observed_bounds_max=points.max(axis=0).tolist() if len(points) else None))
        print(json.dumps({"stage":"inventory_masks","frame":frame.id,"masks":len(boxes)}),flush=True)
    report={"schema_version":1,"capture_id":manifest.capture_id,
            "manifest_sha256":audit["manifest_sha256"],"source_capture_complete":audit["complete"],
            "stage":"inventory_proposals","finished_room":False,"seconds":time.monotonic()-start,
            "detector_recipe":recipe,"mask_recipe":masks.recipe,"proposals":proposals,
            "selected_frames":[f.id for f in frames],
            "note":"Proposals may be duplicates or false positives. Scores and bounds are not validated identities, mobility, or full object geometry."}
    atomic_json(output/"inventory-proposals.json",report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--frames",type=int,default=12)
    args=parser.parse_args()
    report=discover_capture(args.capture,args.output,args.frames)
    print(json.dumps({"stage":report["stage"],"proposals":len(report["proposals"]),
                      "seconds":report["seconds"],"finished_room":False}))


if __name__=="__main__": main()
