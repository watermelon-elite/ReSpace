"""Runs only inside the isolated TripoSR environment. Never imports API services."""
import argparse
import json
from pathlib import Path
import sys


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--image",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--resolution",type=int,choices=[64,128],required=True)
    args=parser.parse_args()
    sys.path.insert(0,str(args.root/"source"))
    import torch
    from omegaconf import OmegaConf
    from PIL import Image
    from tsr.system import TSR

    torch.set_num_threads(4)
    print(json.dumps({"stage":"loading_cpu_shape_model"}),flush=True)
    config=OmegaConf.load(args.root/"weights/config.yaml")
    OmegaConf.resolve(config)
    model=TSR(config)
    # Official, pinned checkpoint; disallow arbitrary pickle execution and avoid
    # copying its entire state a second time when assigning weights.
    state=torch.load(args.root/"weights/model.ckpt",map_location="cpu",weights_only=True,mmap=True)
    model.load_state_dict(state,assign=True)
    del state
    model=model.eval()
    model.renderer.set_chunk_size(1024)
    with Image.open(args.image) as source:
        image=source.convert("RGB")
    print(json.dumps({"stage":"generating_cpu_shape"}),flush=True)
    with torch.inference_mode():
        codes=model([image],device="cpu")
        mesh=model.extract_mesh(codes,has_vertex_color=False,resolution=args.resolution)[0]
    mesh.export(str(args.output/"candidate-unregistered.obj"))
    print(json.dumps({"stage":"shape_exported","vertices":len(mesh.vertices),"triangles":len(mesh.faces)}),flush=True)


if __name__=="__main__": main()
