"""Conservative multi-view proposal association in the measured scan frame.

Uses reciprocal depth-visible mask agreement, not bounding-box overlap alone.
Incomplete/ambiguous proposals remain evidence and never become movable objects.
"""
import re

import numpy as np

from .geometry import camera_to_cv_world,depth_frame
from .instances import project,stable_id


def label_family(label):
    label=label.lower().strip()
    families={"armchair":"chair","stool":"chair","sofa":"sofa","ottoman":"ottoman",
        "poster":"wall_art","painting":"wall_art","picture frame":"wall_art",
        "whiteboard":"whiteboard","bulletin board":"bulletin_board","wall clock":"clock",
        "mirror":"mirror","floor lamp":"lamp","table lamp":"lamp","refrigerator":"refrigerator",
        "chair":"chair","table":"table","desk":"desk","bed":"bed","dresser":"storage",
        "bookcase":"storage","cabinet":"storage","plant":"plant","vase":"vase",
        "television":"television","rug":"rug","pillow":"pillow"}
    if label in families:
        return families[label]
    pattern=r"\b(?:"+"|".join(re.escape(t) for t in sorted(families,key=len,reverse=True))+r")\b"
    matches={families[m.group()] for m in re.finditer(pattern,label)}
    # Detector phrase extraction can concatenate unrelated names. Do not silently
    # turn "cabinet refrigerator" into either mobility category.
    return next(iter(matches)) if len(matches)==1 else "unresolved"


def reciprocal_agreement(a,b,inputs):
    """Return the weaker directional agreement of two independent views."""
    if a["frame"].id==b["frame"].id:
        return 0.
    first=camera_to_cv_world(a["frame"].metadata)
    second=camera_to_cv_world(b["frame"].metadata)
    if np.linalg.norm(first[:3,3]-second[:3,3])<.10 and np.dot(first[:3,2],second[:3,2])>np.cos(np.deg2rad(10)):
        return 0.
    scores=[]
    for source,target in ((a,b),(b,a)):
        points=source["points"]
        if len(points)<16:
            return 0.
        points=points[::max(1,len(points)//4096)]
        frame=target["frame"]
        observation=target.get("depth_observation")
        if observation is None:
            observation=depth_frame(frame,inputs)
        if observation is None:
            return 0.
        depth,_=observation
        uv,z=project(points,frame.metadata)
        x=np.floor(uv[:,0]*depth.shape[1]/frame.metadata.width).astype(int)
        y=np.floor(uv[:,1]*depth.shape[0]/frame.metadata.height).astype(int)
        valid=(z>.1)&(x>=0)&(x<depth.shape[1])&(y>=0)&(y<depth.shape[0])
        ids=np.flatnonzero(valid)
        measured=depth[y[ids],x[ids]]
        visible=ids[(measured>0)&(abs(measured-z[ids])<np.maximum(.04,z[ids]*.02))]
        # A tiny accidental overlap must not merge neighboring objects.
        if len(visible)<16 or len(visible)/len(points)<.20:
            return 0.
        mask=target["mask"]
        mx=np.clip(np.floor(uv[visible,0]*mask.shape[1]/frame.metadata.width).astype(int),0,mask.shape[1]-1)
        my=np.clip(np.floor(uv[visible,1]*mask.shape[0]/frame.metadata.height).astype(int),0,mask.shape[0]-1)
        scores.append(float(mask[my,mx].mean()))
    return min(scores)


def associate(proposals,inputs,minimum_agreement=.65):
    if not .5<=minimum_agreement<=1:
        raise ValueError("Invalid association agreement threshold")
    depth_cache={}
    prepared=[]
    for proposal in proposals:
        frame=proposal["frame"]
        if frame.id not in depth_cache:
            depth_cache[frame.id]=depth_frame(frame,inputs)
        prepared.append(dict(proposal,depth_observation=depth_cache[frame.id]))
    proposals=prepared
    parents=list(range(len(proposals)))
    members={i:{i} for i in parents}
    def root(i):
        while parents[i]!=i:
            parents[i]=parents[parents[i]]
            i=parents[i]
        return i
    edges=[]
    for i,a in enumerate(proposals):
        if a["sam_score"]<.7 or label_family(a["label"])=="unresolved":
            continue
        for j in range(i+1,len(proposals)):
            b=proposals[j]
            if b["sam_score"]<.7 or label_family(a["label"])!=label_family(b["label"]):
                continue
            score=reciprocal_agreement(a,b,inputs)
            if score>=minimum_agreement:
                edges.append((score,i,j))
    for score,i,j in sorted(edges,reverse=True):
        left,right=root(i),root(j)
        if left==right:
            continue
        left_frames={proposals[k]["frame"].id for k in members[left]}
        right_frames={proposals[k]["frame"].id for k in members[right]}
        if left_frames & right_frames:
            continue
        # Avoid transitive chaining A~B~C when A and C actually contradict. Only
        # accept a merge if every overlapping, comparable pair also agrees.
        if any(reciprocal_agreement(proposals[a],proposals[b],inputs)<minimum_agreement
               for a in members[left] for b in members[right]):
            continue
        parents[right]=left
        members[left]|=members.pop(right)
    groups=[]
    for indices in members.values():
        observations=[proposals[i] for i in sorted(indices)]
        source_ids=sorted(p["id"] for p in observations)
        points=[p["points"] for p in observations if len(p["points"])]
        combined=np.concatenate(points) if points else np.empty((0,3))
        groups.append({"id":stable_id("instance","|".join(source_ids)),
            "proposal_ids":source_ids,"family":label_family(observations[0]["label"]),
            "independent_views":len(observations),"multi_view_supported":len(observations)>=2,
            "bounds_min":combined.min(axis=0).tolist() if len(combined) else None,
            "bounds_max":combined.max(axis=0).tolist() if len(combined) else None,
            "ready":False})
    return groups
