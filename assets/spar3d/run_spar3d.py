"""Offline SPAR3D image-to-mesh reconstruction for catalog Product assets.

Reads product images plus a manifest, writes one textured GLB and point cloud
per Product. Output feeds assets/prepare.py, which converts GLB to USDZ and
applies verified dimensions. A reconstruction establishes appearance only;
physical size always comes from Product evidence, never from the mesh.

Built to survive interruption: each Product writes through a temp-then-rename,
progress is appended to an fsync'd JSONL log, and a completed Product is skipped
on re-run unless its input image changed. One failure does not stop the batch.

Upstream run.py is unused: it names outputs by batch index (losing the Product
name) and reads an argparse option that exists only when the optional remeshing
libraries are installed.

Usage: python assets/spar3d/run_spar3d.py --device cpu
Requires the lab built by assets/spar3d/setup.sh ($SPAR3D_LAB, ~/spar3d-lab).
"""

import argparse
import json
import os
import socket
import sys
import time
import traceback
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path

LAB = Path(os.environ.get("SPAR3D_LAB", Path.home() / "spar3d-lab"))


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lab", type=Path, default=LAB, help="runtime/weights/output root")
    ap.add_argument("--images", type=Path, help="default: <lab>/images")
    ap.add_argument("--manifest", type=Path, help="default: <lab>/manifest.json")
    ap.add_argument("--out", type=Path, help="default: <lab>/out")
    ap.add_argument("--texture-resolution", type=int, default=1024)
    ap.add_argument(
        "--device",
        default="cpu",
        help="cpu (default), mps or cuda. See README on the MPS deadlock.",
    )
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default="", help="substring filter on slug")
    ap.add_argument("--redo", action="store_true", help="ignore completion markers")
    args = ap.parse_args()
    args.images = args.images or args.lab / "images"
    args.manifest = args.manifest or args.lab / "manifest.json"
    args.out = args.out or args.lab / "out"
    return args


args = parse_args()
sys.path.insert(0, str(args.lab / "repo"))

import torch  # noqa: E402
from PIL import Image  # noqa: E402

from spar3d.system import SPAR3D  # noqa: E402
from spar3d.utils import foreground_crop, remove_background  # noqa: E402
from transparent_background import Remover  # noqa: E402

# Patched only after every import: kornia TorchScript-compiles an SVD caller at
# import time, and TorchScript cannot compile a wrapper taking **kwargs.
#
# torch.linalg.svd deadlocks on MPS. Its internal error check reads one value
# back from the GPU through dispatch_sync on the same serial Metal queue it is
# waiting on, so the queue never drains. uv_unwrapper reaches it via
# torch.pca_lowrank when aligning a mesh to its main axis. The matrices are
# tiny, so route SVD through the CPU. This is necessary but not sufficient for
# MPS; see README.
_svd = torch.linalg.svd


def _svd_on_cpu(A, full_matrices=True, **kw):
    if A.device.type != "mps":
        return _svd(A, full_matrices, **kw)
    out = _svd(A.cpu(), full_matrices, **kw)
    return type(out)(*(t.to(A.device) for t in out))


torch.linalg.svd = _svd_on_cpu

# The actual MPS blocker, and the one that matters. torch 2.14 replaced the
# MPSGraph linalg path with hand-written Metal kernels, and its linalg.qr
# materializes a full m x m Q instead of the reduced m x q (pytorch#187567,
# fixed on main, shipping in 2.15). uv_unwrapper reaches it at unwrap.py:555
# through torch.pca_lowrank(vertices, q=2), so an (Nv, 2) input allocates Nv^2
# floats: measured 23.5 s at Nv=4444 and over 216 s at Nv=17377, against
# instant on CPU. It does not raise at our mesh sizes, it just grinds, which
# presents as a hang. Inputs are at most ~32k x 3, so the CPU cost is nil.
#
# Safe to patch before imports too -- nothing TorchScript-compiles a
# pca_lowrank caller -- but kept here beside the svd patch for symmetry.
#
# Verified: with this applied, --device mps reconstructs end to end in 31.3 s
# against 78.7 s on CPU for the same product, producing an equivalent mesh.
# Once torch 2.15 is released, drop this and raise TORCH_VERSION in setup.sh.
_pca_lowrank = torch.pca_lowrank


def _pca_lowrank_on_cpu(A, q=None, center=True, niter=2):
    if A.device.type != "mps":
        return _pca_lowrank(A, q=q, center=center, niter=niter)
    out = _pca_lowrank(A.cpu(), q=q, center=center, niter=niter)
    return tuple(t.to(A.device) for t in out)


torch.pca_lowrank = _pca_lowrank_on_cpu


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_atomic(path: Path, data: bytes):
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def append_jsonl(path: Path, record: dict):
    with open(path, "a") as handle:
        handle.write(json.dumps(record) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def pending(items, out: Path, redo: bool):
    """Products without a completion marker matching their current input."""
    todo = []
    for item in items:
        marker = out / Path(item["file"]).stem / "done.json"
        if not redo and marker.exists():
            try:
                if json.loads(marker.read_text()).get("sha256") == item.get("sha256"):
                    continue
            except (ValueError, OSError):
                pass
        todo.append(item)
    return todo


def main():
    args.out.mkdir(parents=True, exist_ok=True)
    log = args.out / "events.jsonl"

    items = sorted(
        (m for m in json.loads(args.manifest.read_text()) if args.only in m["file"]),
        key=lambda m: m["file"],
    )
    todo = pending(items, args.out, args.redo)
    if args.limit:
        todo = todo[: args.limit]

    print(
        f"device={args.device} torch={torch.__version__} "
        f"texture={args.texture_resolution} | {len(items) - len(todo)} done, "
        f"{len(todo)} to build"
    )
    if not todo:
        return

    started = time.time()
    model = SPAR3D.from_pretrained(
        "stabilityai/stable-point-aware-3d",
        config_name="config.yaml",
        weight_name="model.safetensors",
    )
    model.to(args.device)
    model.eval()
    load_s = round(time.time() - started, 1)
    print(f"model loaded in {load_s}s")

    write_atomic(
        args.out / "run.json",
        json.dumps(
            {
                "device": args.device,
                "torch": torch.__version__,
                "texture_res": args.texture_resolution,
                "model_load_s": load_s,
                "host": socket.gethostname(),
                "started": now(),
            },
            indent=2,
        ).encode(),
    )

    remover = Remover(device=args.device)

    for n, meta in enumerate(todo, 1):
        slug = Path(meta["file"]).stem
        dest = args.out / slug
        dest.mkdir(parents=True, exist_ok=True)
        print(f"[{n}/{len(todo)}] {slug}", flush=True)
        item_started = time.time()

        try:
            mark = time.time()
            image = remove_background(
                Image.open(args.images / meta["file"]).convert("RGBA"), remover
            )
            image = foreground_crop(image, 1.3)
            image.save(dest / "input.png")
            prep_s = round(time.time() - mark, 2)

            mark = time.time()
            with torch.no_grad():
                with (
                    torch.autocast(device_type=args.device, dtype=torch.bfloat16)
                    if "cuda" in args.device
                    else nullcontext()
                ):
                    mesh, extra = model.run_image(
                        [image],
                        bake_resolution=args.texture_resolution,
                        remesh="none",
                        vertex_count=-1,
                        return_points=True,
                    )
            infer_s = round(time.time() - mark, 2)

            built = mesh[0] if isinstance(mesh, list) else mesh
            # Export beside the target then rename, so an interrupted write never
            # leaves a truncated GLB that looks complete to the next run.
            staged = dest / "mesh.glb.part"
            # file_type is explicit because trimesh picks its exporter from the
            # extension, and the staged name deliberately is not .glb.
            built.export(staged, file_type="glb", include_normals=True)
            os.replace(staged, dest / "mesh.glb")
            extra["point_clouds"][0].export(dest / "points.ply")

            record = {
                **meta,
                "slug": slug,
                "ok": True,
                "device": args.device,
                "prep_s": prep_s,
                "infer_s": infer_s,
                "glb_bytes": (dest / "mesh.glb").stat().st_size,
                "vertices": int(built.vertices.shape[0]),
                "faces": int(built.faces.shape[0]),
                "texture_res": args.texture_resolution,
                "finished": now(),
            }
            write_atomic(dest / "done.json", json.dumps(record, indent=2).encode())
            append_jsonl(log, record)
            print(
                f"    prep {prep_s}s  infer {infer_s}s  "
                f"{record['vertices']}v/{record['faces']}f  "
                f"{record['glb_bytes'] // 1024}KB",
                flush=True,
            )
        except Exception as error:  # one bad Product must not end the batch
            append_jsonl(
                log,
                {
                    "slug": slug,
                    "ok": False,
                    "device": args.device,
                    "error": f"{type(error).__name__}: {error}",
                    "elapsed_s": round(time.time() - item_started, 2),
                    "finished": now(),
                },
            )
            print(f"    FAILED {type(error).__name__}: {error}", flush=True)
            traceback.print_exc()

    # results.json is a convenience view, rebuilt from the durable markers.
    done = [
        json.loads((d / "done.json").read_text())
        for d in sorted(args.out.iterdir())
        if d.is_dir() and (d / "done.json").exists()
    ]
    write_atomic(args.out / "results.json", json.dumps(done, indent=2).encode())
    print(f"\n{len(done)} model(s) complete in {args.out}")


if __name__ == "__main__":
    main()
