"""Associate actual inventory proposals; never mark them as completed objects."""
import argparse
import json
from pathlib import Path

import numpy as np

from .association import associate
from .benchmark import inspect_capture
from .discover_capture import masked_world_points
from .models import SAFE_NAME
from .store import atomic_json,digest


def associate_capture(capture,evidence):
    capture,evidence=Path(capture).resolve(),Path(evidence).resolve()
    if evidence==capture or evidence==capture/"inputs" or capture/"inputs" in evidence.parents:
        raise ValueError("Association must remain outside the source capture")
    manifest,audit=inspect_capture(capture)
    if audit["invalid_artifacts"] or any(a["type"]!="scene_mesh" for a in audit["missing_artifacts"]):
        raise ValueError("Complete calibrated RGB-D is required")
    report_path=evidence/"inventory-proposals.json"
    report=json.loads(report_path.read_text())
    if report["capture_id"]!=manifest.capture_id or report["manifest_sha256"]!=audit["manifest_sha256"]:
        raise ValueError("Inventory belongs to another immutable capture")
    frames={f.id:f for f in manifest.frames}
    proposals=[]
    hashes={}
    for record in report["proposals"]:
        name=record["mask_cache"]
        if not SAFE_NAME.fullmatch(name) or ".." in name:
            raise ValueError("Unsafe mask-cache reference")
        hashes[name]=digest(evidence/name)
        if record.get("mask_sha256",hashes[name])!=hashes[name]:
            raise ValueError("Inventory mask integrity failed")
        frame=frames[record["frame_id"]]
        photo=next(a for a in frame.artifacts if a.type=="jpeg")
        if record["image_sha256"]!=photo.sha256:
            raise ValueError("Inventory image integrity failed")
        with np.load(evidence/name,allow_pickle=False) as stored:
            mask=stored["mask"].astype(bool)
            if mask.shape!=(frame.metadata.height,frame.metadata.width):
                raise ValueError("Inventory mask is not in calibrated sensor pixels")
            if abs(float(stored["score"])-record["sam_score"])>1e-6:
                raise ValueError("Inventory mask score disagrees with its evidence")
        points,_=masked_world_points(frame,mask,capture/"inputs")
        proposals.append(dict(record,frame=frame,mask=mask,points=points))
    groups=associate(proposals,capture/"inputs")
    result={"schema_version":1,"capture_id":manifest.capture_id,
            "manifest_sha256":audit["manifest_sha256"],"source_capture_complete":audit["complete"],
            "inventory_sha256":digest(report_path),"mask_sha256":hashes,
            "method":"reciprocal_depth_visible_masks_v1","minimum_agreement":.65,
            "instances":groups,"finished_room":False,
            "remaining_stages":["RoomPlan_identity_reconciliation","wall_decor_support_and_planarity",
                "fixed_vs_freestanding_classification","full_surface_ownership","object_and_background_completion",
                "source_texture_baking","walkthrough_and_mobile_validation"]}
    atomic_json(evidence/"associated-instances.json",result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture",type=Path,required=True)
    parser.add_argument("--evidence",type=Path,required=True)
    args=parser.parse_args()
    report=associate_capture(args.capture,args.evidence)
    print(json.dumps({"groups":len(report["instances"]),"multi_view_groups":
        sum(g["multi_view_supported"] for g in report["instances"]),"finished_room":False}))


if __name__=="__main__": main()
