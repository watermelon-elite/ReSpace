"""Complete actual captured surfaces; reject candidates contradicting the scan."""
import json
import hashlib
import os
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.spatial import cKDTree

from .geometry import depth_frame
from .instances import ProviderUnavailable, RescanRequired, project
from .store import atomic_json, digest
from .surfaces import close_observed
from .budget import CompletionBudget


def check_free_space(mesh, first_generated_face, transform, frames, inputs):
    vertices, faces = np.asarray(mesh.vertices), np.asarray(mesh.triangles)[first_generated_face:]
    if not len(faces): return
    triangles = vertices[faces] @ transform[:3, :3].T + transform[:3, 3]
    samples = np.concatenate([triangles.mean(axis=1), *(triangles[:, i]*.8+triangles.mean(axis=1)*.2 for i in range(3))])
    contradictions, tested = 0, 0
    for frame in frames:
        observation = depth_frame(frame, inputs)
        if observation is None: continue
        depth, _ = observation
        uv, z = project(samples, frame.metadata)
        x = np.floor(uv[:, 0]*depth.shape[1]/frame.metadata.width).astype(int)
        y = np.floor(uv[:, 1]*depth.shape[0]/frame.metadata.height).astype(int)
        ids = np.flatnonzero((z > .1) & (x >= 0) & (x < depth.shape[1]) & (y >= 0) & (y < depth.shape[0]))
        measured = depth[y[ids], x[ids]]
        ids, measured = ids[measured > 0], measured[measured > 0]
        tested += len(ids)
        contradictions += int(np.count_nonzero(z[ids] < measured-.06))
    if contradictions > max(3, tested*.01):
        raise RescanRequired("Object completion crosses captured empty space; capture more of its sides")


def complete_object(observed, seed, manifest, inputs, working, observations, check_budget=lambda: None):
    import open3d as o3d
    check_budget()
    try:
        completed, original_count = close_observed(observed)
        if (np.ptp(np.asarray(completed.vertices),axis=0)<seed.dimensions*.6).any():
            raise RescanRequired("Capture more of the object's sides and back to recover its measured extent")
        method = "observed_boundary_completion"
    except RescanRequired:
        configured = os.environ.get("RESPACE_OBJECT_COMPLETION_COMMAND")
        if not configured: raise
        command = json.loads(configured)
        if not isinstance(command, list) or not command or not all(isinstance(s, str) and s for s in command):
            raise ProviderUnavailable("Completion command must be a JSON argument array")
        stage = working/seed.id
        stage.mkdir(parents=True, exist_ok=True)
        source = stage/"observed.ply"
        o3d.io.write_triangle_mesh(str(source), observed)
        request = {"schema_version": 1, "capture_id": manifest.capture_id,
            "observed_mesh": str(source.resolve()), "observed_sha256": digest(source),
            "inputs": str(inputs.resolve()), "object_id": seed.id,
            "local_to_scan_transform": seed.transform.flatten(order="F").tolist(),
            "dimensions": seed.dimensions.tolist(), "frames": [f.model_dump() for f in manifest.frames],
            "masks": [{"frame_id": o["frame"].id, "filename": o.get("mask_path")} for o in observations if o["entity_id"] == seed.id],
            "output_coordinate_system": "object_local_meters", "maximum_triangles": 100000}
        fingerprint=hashlib.sha256(json.dumps(dict(request,command=command),sort_keys=True).encode()).hexdigest()
        ledger=CompletionBudget(working/"completion-budget.json")
        reservation=ledger.reserve(fingerprint)
        request.update(request_fingerprint=fingerprint,maximum_cost_usd=reservation)
        atomic_json(stage/"request.json", request)
        candidate = stage/"completed.obj"
        if reservation is not None:
            candidate.unlink(missing_ok=True)
            candidate.with_suffix(".receipt.json").unlink(missing_ok=True)
            with (stage/"completion.log").open("w") as log:
                try:
                    subprocess.run(command+["--request", str(stage/"request.json"), "--output", str(candidate)],
                        stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)
                except (subprocess.SubprocessError, OSError) as exc:
                    raise ProviderUnavailable("Object completion worker failed; review its retained budget reservation and completion.log") from exc
            receipt=candidate.with_suffix(".receipt.json")
            if not receipt.is_file():raise ProviderUnavailable("The completion worker did not return a cost receipt")
            ledger.settle(fingerprint,json.loads(receipt.read_text()))
            atomic_json(stage/"completed-cache.json",{"fingerprint":fingerprint,"sha256":digest(candidate)})
        else:
            marker=stage/"completed-cache.json"
            if not marker.is_file() or not candidate.is_file():raise ProviderUnavailable("Restore the billed completion checkpoint before retrying")
            cached=json.loads(marker.read_text())
            if cached["fingerprint"]!=fingerprint or cached["sha256"]!=digest(candidate):
                raise ProviderUnavailable("The billed completion checkpoint failed integrity verification")
        from .obj import read_obj
        parsed=read_obj(candidate)
        completed=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(parsed.vertices),o3d.utility.Vector3iVector(parsed.triangles))
        if (not len(completed.triangles) or len(completed.triangles) > 100000
            or not np.isfinite(np.asarray(completed.vertices)).all()
            or not completed.is_watertight() or completed.is_self_intersecting()):
            raise RescanRequired("The completion candidate failed geometry checks")
        if abs(completed.get_volume())<1e-8 or (np.ptp(np.asarray(completed.vertices),axis=0)<seed.dimensions*.6).any():
            raise RescanRequired("The completion candidate does not recover a full three-dimensional object")
        scene = o3d.t.geometry.RaycastingScene()
        scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(completed))
        measured_vertices=np.asarray(observed.vertices)
        measured_faces=np.asarray(observed.triangles)
        probes=np.concatenate([measured_vertices,measured_vertices[measured_faces].mean(axis=1)])
        distances = scene.compute_distance(o3d.core.Tensor(probes.astype(np.float32))).numpy()
        if np.max(distances) > .005:
            raise RescanRequired("Completion changed the captured object's visible shape")
        if (np.ptp(np.asarray(completed.vertices), axis=0) > seed.dimensions+.08).any():
            raise RescanRequired("Completion changed the measured object dimensions")
        original_count, method = 0, "configured_object_completion_worker"
    check_free_space(completed, original_count, seed.transform, manifest.frames[::max(1,len(manifest.frames)//32)], inputs)
    check_budget()
    return completed, {"method": method, "observed_faces": original_count,
                       "completed_faces": len(completed.triangles)-original_count,
                       "watertight": True, "self_intersections": False}


def bake_object(mesh, seed, baker, output, observations, minimum_photo_fraction=.35):
    """Keep source-photo UVs per triangle; continue colors only on unseen faces."""
    vertices, faces = np.asarray(mesh.vertices), np.asarray(mesh.triangles)
    world = vertices @ seed.transform[:3, :3].T+seed.transform[:3, 3]
    centers = world[faces].mean(axis=1)
    normals = np.cross(world[faces[:, 1]]-world[faces[:, 0]], world[faces[:, 2]]-world[faces[:, 0]])
    areas = np.linalg.norm(normals, axis=1)/2
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-10)
    best, source_index = np.zeros(len(faces)), np.full(len(faces), -1)
    colors = np.zeros((len(faces), 3), dtype=np.uint8)
    masks = {o["frame"].id: o["mask"] for o in observations if o["entity_id"] == seed.id}
    uv_sets = {}
    from .geometry import camera_to_cv_world
    for index, frame in enumerate(baker.frames):
        uv, valid, rgb = baker.sample(centers, frame)
        if frame.id in masks:
            mask = masks[frame.id]
            ids = np.flatnonzero(valid)
            x = np.clip((uv[ids,0]*mask.shape[1]/frame.metadata.width).astype(int),0,mask.shape[1]-1)
            y = np.clip((uv[ids,1]*mask.shape[0]/frame.metadata.height).astype(int),0,mask.shape[0]-1)
            valid[ids] &= mask[y,x]
        ray = camera_to_cv_world(frame.metadata)[:3,3]-centers
        distance = np.linalg.norm(ray,axis=1)
        score = abs(np.sum(normals*ray,axis=1))/np.maximum(distance,.1)**3
        corners, z = project(world, frame.metadata)
        corner_valid = (z > .1) & (corners[:,0]>=0) & (corners[:,0]<frame.metadata.width) & (corners[:,1]>=0) & (corners[:,1]<frame.metadata.height)
        chosen = valid & corner_valid[faces].all(axis=1) & (score > best)
        if chosen.any():
            source_index[chosen]=index; best[chosen]=score[chosen]; colors[chosen]=rgb[chosen]
            uv_sets[index]=corners/[frame.metadata.width,frame.metadata.height]
    known = source_index>=0
    observed_fraction = float(areas[known].sum()/max(1e-8,areas.sum()))
    if known.sum()<4 or observed_fraction<minimum_photo_fraction:
        raise RescanRequired("Capture clearer overlapping photos of "+seed.label)
    unknown = np.flatnonzero(~known)
    if len(unknown):
        nearest = cKDTree(centers[known]).query(centers[unknown])[1]
        colors[unknown]=colors[known][nearest]
    side=int(np.ceil(np.sqrt(len(faces))))
    palette=np.zeros((side,side,3),dtype=np.uint8)
    palette.reshape(-1,3)[:len(faces)]=colors
    Image.fromarray(palette).save(output/(seed.id+"-fill.png"))
    materials=[seed.id+"-fill"]
    lines=[f"newmtl {materials[0]}\nKd 1 1 1\nmap_Kd {seed.id}-fill.png\n"]
    for index in sorted(set(source_index[known])):
        frame=baker.frames[index]
        filename="capture-"+str(index)+".jpg"
        if not (output/filename).exists():
            image=Image.fromarray(baker.source(frame)[1]);image.thumbnail((2048,2048))
            image.save(output/filename,quality=95)
        name=seed.id+"-photo-"+str(index);materials.append(name)
        lines.append(f"newmtl {name}\nKd 1 1 1\nmap_Kd {filename}\n")
    (output/(seed.id+".mtl")).write_text("".join(lines))
    with (output/(seed.id+".obj")).open("w") as stream:
        stream.write(f"mtllib {seed.id}.mtl\n")
        np.savetxt(stream,vertices,fmt="v %.8f %.8f %.8f")
        for i,face in enumerate(faces):
            index=source_index[i]
            if index>=0:
                uv=uv_sets[index][face].copy();uv[:,1]=1-uv[:,1]
            else:
                uv=np.tile([(i%side+.5)/side,1-(i//side+.5)/side],(3,1))
            np.savetxt(stream,uv,fmt="vt %.8f %.8f")
        current=None
        # Keep UV indices stable but group faces by source material. This avoids
        # thousands of alternating material runs/draw calls in native importers.
        for i in np.argsort(source_index,kind="stable"):
            face=faces[i]
            name=seed.id+("-photo-"+str(source_index[i]) if known[i] else "-fill")
            if name!=current:stream.write("usemtl "+name+"\n");current=name
            stream.write("f "+" ".join(f"{v+1}/{i*3+j+1}" for j,v in enumerate(face))+"\n")
    return materials, observed_fraction
