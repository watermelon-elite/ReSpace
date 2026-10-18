import io

import numpy as np
import open3d as o3d
from PIL import Image
import pytest

from respace_reconstruction import astra_room
from respace_reconstruction.material_library import PROFILES, export_textures, part_uvs, texture_maps
from respace_reconstruction.obj import read_obj
from respace_reconstruction.scene import SceneBundle
from test_astra_room import box, room_plan


@pytest.mark.parametrize("family", PROFILES)
def test_reusable_maps_are_seamless_nonflat_and_have_valid_normals(family, tmp_path):
    maps = texture_maps(family)
    assert maps == texture_maps(family)
    for data in maps.values():
        pixels = np.array(Image.open(io.BytesIO(data)))
        assert pixels.shape[:2] == (256, 256)
        assert np.array_equal(pixels[0], pixels[-1])
        assert np.array_equal(pixels[:, 0], pixels[:, -1])
    albedo = np.array(Image.open(io.BytesIO(maps["color"])))
    assert albedo.min() < albedo.max()
    normal = np.array(Image.open(io.BytesIO(maps["normal"]))).astype(float)/255*2-1
    assert np.allclose(np.linalg.norm(normal, axis=2), 1, atol=.01)
    assert (normal[:, :, 2] > 0).all()
    assert export_textures(family, tmp_path) == export_textures(family, tmp_path)
    assert len(list(tmp_path.iterdir())) == 3


def part(shape, size=(.8, 1., .6), yaw=.3):
    data = box([.2, .5, -.4], size, shape)
    data["yaw"] = yaw
    return astra_room.Part.model_validate(data)


@pytest.mark.parametrize("shape", ["box", "cylinder", "ellipsoid", "mesh"])
def test_mapping_is_finite_preserves_geometry_and_keeps_curved_seams_local(shape):
    p = part(shape if shape != "mesh" else "box")
    if shape == "mesh":
        source = o3d.geometry.TriangleMesh.create_box(.8, 1., .6)
        p = p.model_copy(update={"shape": "mesh", "size": astra_room.Vector(x=1., y=1., z=1.),
            "vertices": [astra_room.Vector(x=float(x), y=float(y), z=float(z)) for x, y, z in np.asarray(source.vertices)],
            "triangles": [astra_room.Triangle(a=int(a), b=int(b), c=int(c)) for a, b, c in np.asarray(source.triangles)]})
    mesh = astra_room.part_mesh(p, o3d)
    vertices, faces = np.asarray(mesh.vertices).copy(), np.asarray(mesh.triangles).copy()
    uv = part_uvs(p, vertices, faces, .2)
    assert uv.shape == (len(faces), 3, 2) and np.isfinite(uv).all()
    assert np.array_equal(vertices, np.asarray(mesh.vertices))
    assert np.array_equal(faces, np.asarray(mesh.triangles))
    # Continuous local charts prevent a seam triangle spanning an entire wrap.
    if shape == "ellipsoid":
        assert np.max(np.ptp(uv[:, :, 0], axis=1)) < 5.5


def test_box_mapping_uses_real_meters_and_rotates_with_the_part():
    p = part("box", (.8, 1., .6), yaw=0.)
    mesh = astra_room.part_mesh(p, o3d)
    vertices, faces = np.asarray(mesh.vertices), np.asarray(mesh.triangles)
    uv = part_uvs(p, vertices, faces, .2)
    rotated = p.model_copy(update={"yaw": .8})
    rotated_mesh = astra_room.part_mesh(rotated, o3d)
    assert np.allclose(uv, part_uvs(rotated, np.asarray(rotated_mesh.vertices), faces, .2))
    normals = np.cross(vertices[faces][:, 1]-vertices[faces][:, 0], vertices[faces][:, 2]-vertices[faces][:, 0])
    front = np.argmax(np.abs(normals), axis=1) == 2
    assert np.ptp(uv[front, :, 0]) == pytest.approx(.8/.2)
    assert np.ptp(uv[front, :, 1]) == pytest.approx(1./.2)


def test_each_material_slot_has_shared_maps_without_changing_mesh_positions(tmp_path):
    from test_walkthrough import room_capture
    from respace_reconstruction.store import atomic_json
    import json
    manifest, _ = room_capture(tmp_path)
    evidence = {"roomplan": json.loads((tmp_path/"inputs"/manifest.room_export.filename).read_text())}
    shell = astra_room.measured_structure(evidence)
    furnishings = astra_room.FurnishingPlan.model_validate(room_plan())
    plan = astra_room.assemble_room(shell, furnishings)
    output = tmp_path/"export"; output.mkdir()
    entities, bindings, meshes, floor, _ = astra_room.compile_room(plan, {"frame-0"}, output, o3d)
    assert all(m.base_color_texture and m.roughness_texture and m.normal_texture for m in bindings)
    assert len(list(output.glob("material-*.png"))) == 3*len({m.texture_family for m in bindings})
    for entity in entities:
        obj = read_obj(output/entity.asset)
        assert len(obj.uvs) == 3*len(obj.faces)
        assert all(uv is not None for f in obj.faces for _, uv, _ in f)
        pose = np.array(entity.local_to_scan_transform).reshape(4, 4, order="F")
        assert np.allclose(obj.vertices @ pose[:3, :3].T+pose[:3, 3], meshes[entity.id][0], atol=1e-6)
    for filename in ("quality.json", "provenance.json"):
        atomic_json(output/filename, {})
    nav = astra_room.navigation(plan, entities, meshes, floor, manifest.frames)
    bundle = SceneBundle(capture_id=manifest.capture_id, scene_id="scene", reconstruction_revision=1,
        entities=entities, materials=bindings, navigation=nav, ready=True)
    bundle.validate_files(output, {p.name for p in output.iterdir()})
    (output/bindings[0].normal_texture).unlink()
    with pytest.raises(ValueError, match="uncommitted"):
        bundle.validate_files(output, {p.name for p in output.iterdir()})
