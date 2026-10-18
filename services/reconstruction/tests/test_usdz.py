"""Real OpenUSD round trips; no external converter or paid model calls."""
from pathlib import Path
import struct
import zipfile

import numpy as np
from PIL import Image
from pxr import Sdf, Usd, UsdGeom, UsdShade, UsdUtils
import pytest

from respace_reconstruction.obj import read_obj
from respace_reconstruction.usdz import export_usdz


@pytest.fixture
def textured_obj(tmp_path):
    source = tmp_path/"source"
    source.mkdir()
    for name, color in (("color", (180, 60, 20)), ("roughness", (120,)*3), ("normal", (128, 128, 255))):
        Image.new("RGB", (8, 8), color).save(source/(name+".png"))
    (source/"room.mtl").write_text(
        "newmtl wood\nKd 0.8 0.7 0.6\nPr 0.5\nPm 0.2\n"
        "map_Kd color.png\nmap_Pr roughness.png\nnorm normal.png\n"
        "newmtl metal\nKd 0.2 0.3 0.4\nPr 0.1\nPm 1\n")
    obj = source/"model.obj"
    # Two materials share a position but use different UVs/normals at the seam.
    obj.write_text("mtllib room.mtl\nv 4 0 -2\nv 5 0 -2\nv 4 1 -2\nv 4 0 -1\n"
                   "vt 0 0\nvt 1 0\nvt 0 1\nvt 0.5 0.5\nvn 0 0 1\nvn 1 0 0\n"
                   "usemtl wood\nf 1/1/1 2/2/1 3/3/1\nusemtl metal\nf 1/4/2 3/2/2 4/3/2\n")
    return obj


def test_portable_package_preserves_complete_obj_geometry_uvs_normals_and_pbr(textured_obj, tmp_path):
    original = read_obj(textured_obj)
    name = export_usdz(textured_obj)
    package = tmp_path/name
    # Only the USDZ leaves the source directory, exactly as when sharing a scan.
    package.write_bytes((textured_obj.parent/name).read_bytes())
    with zipfile.ZipFile(package) as archive, package.open("rb") as stream:
        assert archive.namelist()[0].endswith(".usdc")
        assert {Path(n).name for n in archive.namelist()} == {"scene.usdc", "color.png", "normal.png", "roughness.png"}
        for item in archive.infolist():
            assert item.compress_type == zipfile.ZIP_STORED
            stream.seek(item.header_offset)
            header = stream.read(30)
            filename_length, extra_length = struct.unpack_from("<HH", header, 26)
            assert (item.header_offset+30+filename_length+extra_length) % 64 == 0
            if item.filename.endswith(".png"):
                assert archive.read(item.filename) == (textured_obj.parent/Path(item.filename).name).read_bytes()
    layers, assets, unresolved = UsdUtils.ComputeAllDependencies(Sdf.AssetPath(str(package)))
    assert layers and len(assets) == 3 and not unresolved
    stage = Usd.Stage.Open(str(package))
    assert stage.GetDefaultPrim().GetPath() == "/Room"
    assert UsdGeom.GetStageMetersPerUnit(stage) == 1
    assert UsdGeom.GetStageUpAxis(stage) == UsdGeom.Tokens.y
    mesh = UsdGeom.Mesh(stage.GetPrimAtPath("/Room/Scan"))
    np.testing.assert_allclose(mesh.GetPointsAttr().Get(), original.vertices)
    np.testing.assert_array_equal(np.array(mesh.GetFaceVertexIndicesAttr().Get()).reshape(-1, 3), original.triangles)
    uv = UsdGeom.PrimvarsAPI(mesh).GetPrimvar("st")
    assert uv.GetInterpolation() == UsdGeom.Tokens.faceVarying
    np.testing.assert_allclose(uv.Get(), [[0, 0], [1, 0], [0, 1], [.5, .5], [1, 0], [0, 1]])
    np.testing.assert_allclose(mesh.GetNormalsAttr().Get(), [[0, 0, 1]]*3+[[1, 0, 0]]*3)
    subsets = UsdShade.MaterialBindingAPI(mesh).GetMaterialBindSubsets()
    assert [list(s.GetIndicesAttr().Get()) for s in subsets] == [[0], [1]]
    for index, name in enumerate(("wood", "metal")):
        material, _ = UsdShade.MaterialBindingAPI(subsets[index]).ComputeBoundMaterial()
        assert material.GetPrim().GetDisplayName() == name
    surface = UsdShade.Shader(stage.GetPrimAtPath("/Room/Materials/Material_1/Surface"))
    assert surface.GetInput("metallic").Get() == 1
    normal = UsdShade.Shader(stage.GetPrimAtPath("/Room/Materials/Material_0/normalTexture"))
    assert tuple(normal.GetInput("scale").Get()) == (2, 2, 2, 1)
    assert tuple(normal.GetInput("bias").Get()) == (-1, -1, -1, 0)
    assert normal.GetInput("sourceColorSpace").Get() == "raw"
    with pytest.warns(DeprecationWarning):
        checker = UsdUtils.ComplianceChecker(arkit=True)
    checker.CheckCompliance(str(package))
    assert not checker.GetErrors()
    assert not checker.GetFailedChecks()


@pytest.mark.parametrize("fault", ["missing_texture", "unsafe_texture", "unknown_material", "missing_library"])
def test_incomplete_sources_do_not_create_a_usdz(textured_obj, fault):
    if fault == "missing_texture":
        (textured_obj.parent/"color.png").unlink()
    elif fault == "unsafe_texture":
        mtl = textured_obj.parent/"room.mtl"
        mtl.write_text(mtl.read_text().replace("color.png", "../color.png"))
    elif fault == "missing_library":
        (textured_obj.parent/"room.mtl").unlink()
    else:
        textured_obj.write_text(textured_obj.read_text().replace("usemtl wood", "usemtl missing"))
    with pytest.raises(ValueError):
        export_usdz(textured_obj)
    assert not textured_obj.with_suffix(".usdz").exists()
    assert not list(textured_obj.parent.glob("usdz-*"))


def test_untextured_obj_exports_without_inventing_uvs(tmp_path):
    source = tmp_path/"model.obj"
    source.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    stage = Usd.Stage.Open(str(tmp_path/export_usdz(source)))
    mesh = UsdGeom.Mesh(stage.GetPrimAtPath("/Room/Scan"))
    assert len(mesh.GetFaceVertexCountsAttr().Get()) == 1
    assert not UsdGeom.PrimvarsAPI(mesh).GetPrimvar("st")
