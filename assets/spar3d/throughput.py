"""Measure how far SPAR3D reconstruction parallelizes on one Apple GPU.

Two independent levers, which multiply:

  batch    several images in one run_image call, one model in memory
  procs    several worker processes, one model copy each

The question is how much of a generation's wall time the GPU is actually busy
for. This code deliberately routes svd and pca_lowrank to the CPU on MPS (see
run_spar3d.py), so the GPU idles during those stretches and concurrency has
something to fill. Nobody has measured how large that gap is, and the honest
answer is a curve, not a number: throughput climbs while idle units remain and
flattens once the GPU saturates. Run the ramp and read where it flattens.

Inputs are the background-removed input.png files a previous run already wrote,
not the source photographs. That keeps the background remover out of memory and
measures the thing being parallelized rather than the preprocessing.

Ramping matters for more than tidiness. Concurrent Metal contexts contending
for the queue is the shape of the deadlock that previously wedged WindowServer,
so a configuration that hangs should be found at 2 processes, where SIGTERM
recovers it, and not at 13. Never SIGKILL a worker: it leaves Metal work on the
queue and takes the window server with it.

    python assets/spar3d/throughput.py                 # the full ramp
    python assets/spar3d/throughput.py --worker ...    # one process, internal

Writes every artifact under $SPAR3D_LAB/experiments/throughput/, never beside
the real meshes in out/.
"""

import argparse
import json
import os
import resource
import signal
import subprocess
import sys
import time
from pathlib import Path

LAB = Path(os.environ.get("SPAR3D_LAB", Path.home() / "spar3d-lab"))
WORK = LAB / "experiments" / "throughput"

# One fixed workload for every configuration, so throughput is comparable.
# Eight divides by every process count in the ramp, which keeps each worker's
# share equal; an uneven split would make the slowest worker the measurement.
PRODUCTS = 8

# A worker measured 15.3 GB resident, nearly all of it the model on the GPU.
# Unified memory means processes spend the same pool the GPU draws from, so
# overcommitting does not merely swap, it starves the GPU and the window server
# with it. Never plan a configuration above this share of physical memory.
MEMORY_FRACTION = 0.55
FALLBACK_PROCESS_GB = 16.0

# (processes, batch_size). Ordered so contention shows up at the cheap end.
#
# Measured and removed: (1, 4) ran 21% slower per product than serial, and
# (1, 2) matched serial within noise. Handing the model more images at once
# does not help, which says a single generation already saturates the GPU.
# Dropped (8, 1) and (4, 2) for the ceiling rather than the clock: eight
# workers project to ~122 GB against 128 GB installed, and the measurement is
# not worth putting the machine into swap for.
RAMP = [
    (1, 1),  # baseline, and the control for both levers
    (1, 2),
    (2, 1),
    (3, 1),
    (4, 1),
    (2, 2),
]


def physical_memory_gb():
    return int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True,
                              text=True).stdout.strip()) / 2**30


def affordable(procs, measured_gb, total_gb):
    """Whether `procs` workers fit the memory budget, and the projection.

    Refusing is the point of this function. A configuration that overcommits
    unified memory does not produce a slow data point, it produces an
    unresponsive machine, so it must never be launched to find out.
    """
    per_process = measured_gb or FALLBACK_PROCESS_GB
    projected = procs * per_process
    return projected <= MEMORY_FRACTION * total_gb, projected


def workload():
    """Slugs with a prepared input image, newest run first, capped at PRODUCTS."""
    candidates = sorted(
        d for d in (LAB / "out").iterdir() if d.is_dir() and (d / "input.png").exists()
    )
    if len(candidates) < PRODUCTS:
        raise SystemExit(
            f"need {PRODUCTS} prepared inputs, found {len(candidates)}; "
            "run run_spar3d.py first"
        )
    return [d.name for d in candidates[:PRODUCTS]]


def worker(slugs, batch_size, out: Path, tag: str):
    """Reconstruct `slugs` in chunks of `batch_size`, reporting timings as JSON.

    Runs in its own process. Everything heavy is imported here so the
    orchestrator never loads torch.
    """
    sys.path.insert(0, str(LAB / "repo"))
    import torch
    from PIL import Image

    from spar3d.system import SPAR3D

    # Duplicated from run_spar3d.py rather than imported, because that module
    # parses argv at import time. Both patches are load-bearing on MPS: svd
    # deadlocks on the serial Metal queue, and linalg.qr materializes a full
    # m x m Q. See the comments there for the full reasoning.
    _svd = torch.linalg.svd

    def _svd_on_cpu(A, full_matrices=True, **kw):
        if A.device.type != "mps":
            return _svd(A, full_matrices, **kw)
        out = _svd(A.cpu(), full_matrices, **kw)
        return type(out)(*(t.to(A.device) for t in out))

    torch.linalg.svd = _svd_on_cpu
    _pca_lowrank = torch.pca_lowrank

    def _pca_lowrank_on_cpu(A, q=None, center=True, niter=2):
        if A.device.type != "mps":
            return _pca_lowrank(A, q=q, center=center, niter=niter)
        out = _pca_lowrank(A.cpu(), q=q, center=center, niter=niter)
        return tuple(t.to(A.device) for t in out)

    torch.pca_lowrank = _pca_lowrank_on_cpu

    mark = time.time()
    model = SPAR3D.from_pretrained(
        "stabilityai/stable-point-aware-3d",
        config_name="config.yaml",
        weight_name="model.safetensors",
    )
    model.to("mps")
    model.eval()
    load_s = round(time.time() - mark, 2)

    images = [Image.open(LAB / "out" / slug / "input.png").convert("RGBA") for slug in slugs]
    out.mkdir(parents=True, exist_ok=True)

    chunks = []
    started = time.time()
    for index in range(0, len(images), batch_size):
        chunk = images[index : index + batch_size]
        mark = time.time()
        with torch.no_grad():
            meshes, _ = model.run_image(chunk, bake_resolution=1024, remesh="none",
                                        vertex_count=-1, return_points=False)
        infer_s = round(time.time() - mark, 2)

        mark = time.time()
        meshes = meshes if isinstance(meshes, list) else [meshes]
        for slug, mesh in zip(slugs[index : index + batch_size], meshes):
            mesh.export(out / f"{slug}.glb", file_type="glb", include_normals=True)
        export_s = round(time.time() - mark, 2)
        chunks.append({"size": len(chunk), "infer_s": infer_s, "export_s": export_s})

    # ru_maxrss is bytes on macOS, unlike Linux. This is the number that decides
    # how many processes actually fit in unified memory.
    print(json.dumps({
        "tag": tag,
        "slugs": slugs,
        "model_load_s": load_s,
        "busy_s": round(time.time() - started, 2),
        "peak_rss_gb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**30, 2),
        "mps_allocated_gb": round(torch.mps.current_allocated_memory() / 2**30, 2),
        "mps_driver_gb": round(torch.mps.driver_allocated_memory() / 2**30, 2),
        "chunks": chunks,
    }))


def run_configuration(procs, batch_size, slugs):
    """Launch `procs` workers over an equal split and time the whole wave.

    Wall time spans from first launch to last exit, which is what throughput
    means here: model load is inside it on purpose, since a real batch pays it.
    """
    share = len(slugs) // procs
    out = WORK / "meshes" / f"p{procs}-b{batch_size}"
    logs = WORK / "logs"
    logs.mkdir(parents=True, exist_ok=True)

    started = time.time()
    running = []
    for index in range(procs):
        tag = f"p{procs}-b{batch_size}-w{index}"
        mine = slugs[index * share : (index + 1) * share]
        handle = open(logs / f"{tag}.log", "w")
        running.append((
            subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "--worker",
                 "--slugs", ",".join(mine), "--batch", str(batch_size),
                 "--out", str(out / f"w{index}"), "--tag", tag],
                stdout=subprocess.PIPE, stderr=handle, text=True,
            ),
            handle,
        ))

    results, failed = [], []
    try:
        for process, handle in running:
            stdout, _ = process.communicate()
            handle.close()
            line = next((l for l in stdout.splitlines() if l.startswith("{")), "")
            if process.returncode == 0 and line:
                results.append(json.loads(line))
            else:
                failed.append(process.returncode)
    except KeyboardInterrupt:
        # SIGTERM, never SIGKILL: a killed process leaves work on the Metal
        # queue and the window server goes down with it.
        for process, handle in running:
            process.send_signal(signal.SIGTERM)
            handle.close()
        for process, _ in running:
            process.wait()
        raise

    wall_s = round(time.time() - started, 2)
    if failed:
        return {"procs": procs, "batch": batch_size, "ok": False,
                "wall_s": wall_s, "returncodes": failed}

    done = sum(len(r["slugs"]) for r in results)
    return {
        "procs": procs, "batch": batch_size, "ok": True,
        "products": done,
        "wall_s": wall_s,
        "per_product_s": round(wall_s / done, 2),
        "throughput_per_min": round(60 * done / wall_s, 1),
        "model_load_s": max(r["model_load_s"] for r in results),
        "peak_rss_gb": round(sum(r["peak_rss_gb"] for r in results), 2),
        "mps_driver_gb": round(sum(r["mps_driver_gb"] for r in results), 2),
        "workers": results,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--slugs", default="")
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    if args.worker:
        return worker(args.slugs.split(","), args.batch, args.out, args.tag)

    slugs = workload()
    WORK.mkdir(parents=True, exist_ok=True)

    # Earlier configurations are kept, so a stopped ramp resumes instead of
    # paying for measurements it already has.
    results_path = WORK / "results.json"
    rows = json.loads(results_path.read_text()) if results_path.exists() else []
    done = {(r["procs"], r["batch"]) for r in rows if r.get("ok")}
    total_gb = physical_memory_gb()
    measured_gb = next((r["peak_rss_gb"] for r in rows
                        if r.get("ok") and r["procs"] == 1 and r["batch"] == 1), 0)

    print(f"{PRODUCTS} products per configuration, {total_gb:.0f} GB installed, "
          f"budget {MEMORY_FRACTION:.0%} = {MEMORY_FRACTION * total_gb:.0f} GB")
    if done:
        print(f"{len(done)} configuration(s) already measured, skipping")
    print(f"{'config':>10}  {'wall':>8}  {'per item':>9}  {'per min':>8}  "
          f"{'rss GB':>7}  {'gpu GB':>7}")

    for procs, batch_size in RAMP:
        if (procs, batch_size) in done:
            continue
        fits, projected = affordable(procs, measured_gb, total_gb)
        if not fits:
            print(f"{f'p{procs} b{batch_size}':>10}  skipped, projects to "
                  f"{projected:.0f} GB over a {MEMORY_FRACTION * total_gb:.0f} GB budget",
                  flush=True)
            continue
        row = run_configuration(procs, batch_size, slugs)
        if row.get("ok") and procs == 1 and batch_size == 1:
            measured_gb = row["peak_rss_gb"]
        rows.append(row)
        (WORK / "results.json").write_text(json.dumps(rows, indent=2))
        if not row["ok"]:
            print(f"{f'p{procs} b{batch_size}':>10}  FAILED, returncodes "
                  f"{row['returncodes']} -- see {WORK / 'logs'}", flush=True)
            continue
        print(f"{f'p{procs} b{batch_size}':>10}  {row['wall_s']:>7}s  "
              f"{row['per_product_s']:>8}s  {row['throughput_per_min']:>8}  "
              f"{row['peak_rss_gb']:>7}  {row['mps_driver_gb']:>7}", flush=True)

    best = max((r for r in rows if r["ok"]), key=lambda r: r["throughput_per_min"], default=None)
    if best:
        baseline = next((r for r in rows if r["ok"] and r["procs"] == 1 and r["batch"] == 1), None)
        speedup = f"{best['throughput_per_min'] / baseline['throughput_per_min']:.2f}x" if baseline else "n/a"
        print(f"\nbest: {best['procs']} process(es), batch {best['batch']} -- "
              f"{best['throughput_per_min']}/min, {speedup} over serial")
    print(f"results in {WORK / 'results.json'}")


if __name__ == "__main__":
    main()
