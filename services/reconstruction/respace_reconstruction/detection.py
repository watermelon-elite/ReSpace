"""Open-vocabulary inventory proposals, in original calibrated image pixels.

Detections and model scores are proposals, never completed scene objects.
"""
from dataclasses import dataclass
import json
import os
from pathlib import Path

import numpy as np
from PIL import Image

from .geometry import camera_to_cv_world
from .instances import ProviderUnavailable
from .store import digest

REVISION = "a2bb814dd30d776dcf7e30523b00659f4f141c71"
CHECKSUM = "1a2412ef99bd74bcd3c2a246fa1e48581f8889a1300c9051974741314fc042f3"
PROMPTS = (
    "chair. sofa. armchair. table. desk. bed. dresser. bookcase. stool. ottoman.",
    "poster. painting. picture frame. whiteboard. wall clock. mirror. bulletin board.",
    "floor lamp. table lamp. plant. vase. television. rug. pillow. cabinet. refrigerator.",
)
DECOR = {"poster", "painting", "picture frame", "whiteboard", "wall clock", "mirror", "bulletin board"}


@dataclass
class Detection:
    box: np.ndarray
    label: str
    score: float


def upright_turns(metadata):
    """Nearest right-angle image roll from measured world gravity, not EXIF.

    Returns np.rot90's counterclockwise turn count. Near vertical camera views
    have no stable image-up direction and retain their sensor orientation.
    """
    up = camera_to_cv_world(metadata)[:3, :3].T @ np.array([0., 1., 0.])
    if np.linalg.norm(up[:2]) < .25:
        return 0
    x, y = up[:2]
    candidates = [(x, y), (y, -x), (-x, -y), (-y, x)]
    return int(np.argmin([v[1] for v in candidates]))


def rotated_box(box, width, height, turns):
    """Rotate continuous pixel-edge XYXY coordinates, preserving calibration."""
    x1, y1, x2, y2 = box
    points = np.array([[x1,y1],[x1,y2],[x2,y1],[x2,y2]],dtype=float)
    for _ in range(turns % 4):
        points = np.c_[points[:,1], width-points[:,0]]
        width,height = height,width
    return np.r_[points.min(axis=0),points.max(axis=0)]


def box_iou(a,b):
    overlap=np.maximum(0,np.minimum(a[2:],b[2:])-np.maximum(a[:2],b[:2]))
    intersection=float(np.prod(overlap))
    union=float(np.prod(a[2:]-a[:2])+np.prod(b[2:]-b[:2])-intersection)
    return intersection/max(union,1e-12)


class GroundingDINO:
    def __init__(self, folder=None):
        folder=Path(folder or Path(__file__).resolve().parents[1]/".tools/grounding-dino")
        if not (folder/"recipe.json").is_file():
            raise ProviderUnavailable("Install the public detector with setup-detection.sh")
        self.recipe=json.loads((folder/"recipe.json").read_text())
        if self.recipe.get("revision") != REVISION or digest(folder/"model.safetensors") != CHECKSUM:
            raise ProviderUnavailable("Grounding DINO differs from the pinned checkpoint")
        for name,checksum in self.recipe["file_sha256"].items():
            if Path(name).name != name or digest(folder/name) != checksum:
                raise ProviderUnavailable("Grounding DINO model/config integrity failed")
        os.environ.setdefault("HF_HOME",str(folder/"cache"))
        os.environ.setdefault("HF_HUB_OFFLINE","1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE","1")
        import torch
        import transformers
        from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
        if transformers.__version__ != "4.46.3":
            raise ProviderUnavailable("This detector adapter requires Transformers 4.46.3")
        torch.set_num_threads(4)
        self.torch=torch
        self.processor=AutoProcessor.from_pretrained(folder,local_files_only=True)
        self.model=AutoModelForZeroShotObjectDetection.from_pretrained(
            folder,local_files_only=True,use_safetensors=True,disable_custom_kernels=True).to("cpu").eval()
        self.recipe=dict(self.recipe,device="cpu",torch=torch.__version__,
                         box_threshold=.30,text_threshold=.25,prompts=list(PROMPTS),
                         adapter="gravity_corrected_sensor_boxes_v1")

    def detect(self,image: Image.Image,metadata,prompts=PROMPTS):
        turns=upright_turns(metadata)
        upright=Image.fromarray(np.rot90(np.array(image.convert("RGB")),turns).copy())
        proposals=[]
        for prompt in prompts:
            inputs=self.processor(images=upright,text=prompt,return_tensors="pt")
            if inputs.input_ids.shape[-1] > 256:
                raise ValueError("Detector prompt exceeds the model token limit")
            with self.torch.inference_mode():
                outputs=self.model(**inputs)
            result=self.processor.post_process_grounded_object_detection(
                outputs,inputs.input_ids,box_threshold=.30,text_threshold=.25,
                target_sizes=[(upright.height,upright.width)])[0]
            for box,label,score in zip(result["boxes"],result["labels"],result["scores"]):
                original=rotated_box(box.cpu().numpy(),upright.width,upright.height,-turns)
                original=np.maximum(original,0)
                original[[0,2]]=np.minimum(original[[0,2]],image.width)
                original[[1,3]]=np.minimum(original[[1,3]],image.height)
                if np.min(original[2:]-original[:2]) < 12:
                    continue
                proposals.append(Detection(original,label.strip(),float(score)))
        kept=[]
        for candidate in sorted(proposals,key=lambda d:d.score,reverse=True):
            if not any(candidate.label==p.label and box_iou(candidate.box,p.box)>.5 for p in kept):
                kept.append(candidate)
        return kept
