import numpy as np
import pytest

from respace_reconstruction.obj import read_obj, write_submesh


def test_split_preserves_uv_seams_material_and_registered_geometry(tmp_path):
    source = tmp_path / "photo.obj"
    source.write_text("mtllib photo.mtl\nv 1 0 0\nv 2 0 0\nv 1 1 0\nv 2 1 0\n"
                      "vt 0 0\nvt 1 0\nvt 0 1\nvt .2 .3\nvt .7 .8\n"
                      "usemtl fabric\nf 1/1 2/2 3/3\nusemtl wood\nf -3/4 -1/5 -2/3\n")
    mesh = read_obj(source)
    transform = np.eye(4)
    transform[0, 3] = 1
    path = tmp_path / "item.obj"
    points, materials = write_submesh(mesh, [1], path, transform)
    result = read_obj(path)
    assert materials == ["wood"]
    assert result.materials == ["wood"]
    assert result.libraries == ["photo.mtl"]
    assert np.allclose(result.vertices, points)
    for corner, original in zip(result.faces[0], mesh.faces[1]):
        assert np.allclose(result.uvs[corner[1]], mesh.uvs[original[1]])
        assert np.allclose(result.vertices[corner[0]]+[1,0,0], mesh.vertices[original[0]])


def test_reject_external_material_and_broken_indices(tmp_path):
    path = tmp_path / "bad.obj"
    path.write_text("mtllib ../escape.mtl\n")
    with pytest.raises(ValueError, match="Unsafe"):
        read_obj(path)
    path.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 99\n")
    with pytest.raises(ValueError, match="bounds"):
        read_obj(path)
