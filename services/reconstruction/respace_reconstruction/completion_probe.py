"""Bounded local shape-candidate experiment; candidates are not finished objects."""
import argparse
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time

import numpy as np
from PIL import Image

from .obj import read_obj
from .store import atomic_json, digest


def candidate_checks(path):
    """Structural checks only; camera alignment and fidelity remain untested."""
    import open3d as o3d
    source=read_obj(path)
    if len(source.faces)>128000:
        raise ValueError("Completion candidate exceeds the experiment mesh budget")
    mesh=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(source.vertices),
                                  o3d.utility.Vector3iVector(source.triangles))
    return {"watertight":bool(mesh.is_watertight()),
            "edge_manifold":bool(mesh.is_edge_manifold(allow_boundary_edges=False)),
            "vertex_manifold":bool(mesh.is_vertex_manifold()),
            "no_self_intersections":not bool(mesh.is_self_intersecting())}


def masked_input(image, mask, intrinsics, size=512):
    """Preserve observed pixels, composite neutral gray, record exact crop camera."""
    if mask.shape != (image.height, image.width):
        mask = np.asarray(Image.fromarray(mask.astype(bool)).resize(image.size, Image.Resampling.NEAREST))
    y, x = np.nonzero(mask)
    if len(x) < 16:
        raise ValueError("Object mask has insufficient observed content")
    left, top, right, bottom = int(x.min()), int(y.min()), int(x.max())+1, int(y.max())+1
    width, height = right-left, bottom-top
    side = int(math.ceil(max(width, height)/.85))
    pad_x, pad_y = (side-width)//2, (side-height)//2
    observed = image.convert("RGBA").crop((left, top, right, bottom))
    observed.putalpha(Image.fromarray((mask[top:bottom, left:right]*255).astype(np.uint8)))
    canvas = Image.new("RGBA", (side, side), (128,128,128,255))
    canvas.alpha_composite(observed, (pad_x,pad_y))
    result = canvas.convert("RGB").resize((size,size), Image.Resampling.LANCZOS)
    fx, fy, cx, cy = intrinsics
    scale = size/side
    return result, {"crop_xyxy":[left,top,right,bottom], "square_size":side,
                    "padding_xy":[pad_x,pad_y], "output_size":size,
                    "intrinsics":[fx*scale,fy*scale,(cx-left+pad_x)*scale,(cy-top+pad_y)*scale]}


def probe(image: Path, output: Path, timeout=600, max_rss_gib=4.5, resolution=64):
    if timeout <= 0 or max_rss_gib <= 0 or resolution not in (64, 128):
        raise ValueError("Invalid local completion resource limits")
    # Verify monitoring access before starting a model. A restricted process
    # inspector must not leave an unmonitored inference process behind.
    subprocess.run(["ps", "-o", "rss=", "-p", str(os.getpid())],
                   capture_output=True, text=True, check=True)
    root = Path(__file__).resolve().parents[1] / ".tools/triposr"
    python = root / "env/bin/python"
    if not python.is_file() or not (root / "recipe.json").is_file():
        raise RuntimeError("Run setup-completion.sh to install the isolated CPU candidate stage")
    recipe=json.loads((root/"recipe.json").read_text())
    expected_commit="107cefdc244c39106fa830359024f6a2f1c78871"
    actual_commit=subprocess.run(["git","-C",str(root/"source"),"rev-parse","HEAD"],
                                 capture_output=True,text=True,check=True).stdout.strip()
    clean=subprocess.run(["git","-C",str(root/"source"),"diff","--quiet","HEAD"],check=False)
    if (actual_commit!=expected_commit or clean.returncode!=0
        or digest(root/"weights/model.ckpt")!="429e2c6b22a0923967459de24d67f05962b235f79cde6b032aa7ed2ffcd970ee"):
        raise RuntimeError("Completion model or source differs from the pinned recipe")
    output.mkdir(parents=True,exist_ok=True)
    environment = os.environ.copy()
    environment.update({"HF_HOME":str(root/"cache"), "HF_HUB_OFFLINE":"1", "TRANSFORMERS_OFFLINE":"1",
                        "NUMBA_CACHE_DIR":str(root/"cache/numba"), "OMP_NUM_THREADS":"4",
                        "TOKENIZERS_PARALLELISM":"false"})
    command = [str(python),str(Path(__file__).with_name("completion_child.py")),
               "--root",str(root),"--image",str(image.resolve()),"--output",str(output.resolve()),
               "--resolution",str(resolution)]
    start, peak = time.monotonic(), 0
    with (output/"inference.log").open("w") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,env=environment,start_new_session=True)
        reason = None
        try:
            while process.poll() is None:
                resident = subprocess.run(["ps","-o","rss=","-p",str(process.pid)],capture_output=True,text=True,check=False)
                peak=max(peak,int(resident.stdout.strip() or 0)*1024)
                if time.monotonic()-start > timeout:
                    reason="completion_probe_time_limit"
                elif peak > max_rss_gib*1024**3:
                    reason="completion_probe_memory_limit"
                if reason:
                    break
                time.sleep(.5)
        finally:
            if process.poll() is None:
                try:
                    os.killpg(process.pid,signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL)
                    process.wait()
    result={"stage":"shape_candidate", "model":"TripoSR", "recipe":recipe,
            "seconds":time.monotonic()-start,"sampled_peak_rss_bytes":peak,
            "resolution":resolution,"registered":False,"finished_room":False,
            "source_image_sha256":digest(image),"error":reason}
    if process.returncode != 0 and reason is None:
        result["error"]="model_inference_failed; see local inference.log"
    candidate=output/"candidate-unregistered.obj"
    if not result["error"]:
        mesh=read_obj(candidate)
        checks=candidate_checks(candidate)
        result.update({"vertices":len(mesh.vertices),"triangles":len(mesh.faces),
                       "asset":candidate.name,"sha256":digest(candidate),
                       "geometry_checks":checks,"geometry_checks_passed":all(checks.values())})
    atomic_json(output/"completion-probe.json",result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--resolution",type=int,choices=[64,128],default=64)
    parser.add_argument("--timeout",type=int,default=600)
    args=parser.parse_args()
    result=probe(args.image,args.output,args.timeout,resolution=args.resolution)
    print(json.dumps(result))
    if result["error"]: raise SystemExit(1)
    if not result["geometry_checks_passed"]: raise SystemExit(2)


if __name__=="__main__": main()
