import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import numpy as np
from PIL import Image
from pxr import Usd, UsdGeom, UsdShade

from assets.assemble_scan import assemble, read_obj


class AssembleScanTests(unittest.TestCase):
    def test_rotated_asymmetric_part_keeps_scale_uvs_and_separate_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"; source.mkdir()
            Image.new("RGB", (2, 2), "red").save(source / "photo.jpg")
            (source / "part.mtl").write_text("newmtl photo\nKd 1 1 1\nPr 0.4\nPm 0.2\nmap_Kd photo.jpg\n")
            (source / "part.obj").write_text("mtllib part.mtl\nv 0 0 0\nv 1 0 0\nv 0 2 0\nvt 0 0\nvt 1 0\nvt 0 1\nusemtl photo\nf -3/-3 -2/-2 -1/-1\nf 1/1 2/2 1/1\n")
            matrix = np.array([[0, 0, 1, 2], [0, 1, 0, 0.5], [-1, 0, 0, 3], [0, 0, 0, 1]])
            scene = {"schema_version": 2, "coordinate_system": "arkit_scan_meters_y_up", "capture_id": "scan",
                     "navigation": {"floor_polygons": [[[-2, -3], [4, -3], [4, 5], [-2, 5]]], "floor_height": -1},
                     "entities": [{"id": "asymmetric-part", "label": "Asymmetric part", "kind": "furniture", "category": "appliance", "move_ready": True,
                                   "asset": "part.obj", "local_to_scan_transform": matrix.flatten(order="F").tolist()}]}
            (source / "scene.json").write_text(json.dumps(scene))
            (source / "provenance.json").write_text(json.dumps({"geometry": "Measured shell and reconstructed Objects", "assumptions": []}))
            (source / "quality.json").write_text(json.dumps({"objects": [{"detail": "coarse"}]}))
            result = assemble(source, root / "output")
            self.assertEqual(result["triangle_count"], 1)
            self.assertEqual(result["dropped_zero_area_triangles"], 1)
            self.assertEqual(result["texture_count"], 1)
            self.assertEqual(result["translation_from_scan"], [2, 1, 3])
            self.assertTrue(np.allclose(result["bounds_min"], [4, 1.5, 5]))
            self.assertTrue(np.allclose(result["bounds_max"], [4, 3.5, 6]))
            stage = Usd.Stage.Open(str(root / "output/kitchenette.usdz"))
            mesh = UsdGeom.Mesh(stage.GetPrimAtPath("/Room/scan_asymmetric_part/Mesh0"))
            self.assertEqual(list(mesh.GetFaceVertexIndicesAttr().Get()), [0, 1, 2])
            uv = UsdGeom.PrimvarsAPI(mesh).GetPrimvar("st")
            self.assertEqual(uv.GetInterpolation(), "faceVarying")
            self.assertEqual([tuple(pair) for pair in uv.Get()], [(0, 0), (1, 0), (0, 1)])
            self.assertTrue(UsdShade.MaterialBindingAPI(mesh).ComputeBoundMaterial()[0])
            with zipfile.ZipFile(root / "output/kitchenette.usdz") as archive:
                self.assertTrue(any(name.endswith("photo.jpg") for name in archive.namelist()))
            scene["entities"][0]["asset"] = "../outside.obj"
            (source / "scene.json").write_text(json.dumps(scene))
            with self.assertRaisesRegex(ValueError, "out-of-folder"):
                assemble(source, root / "invalid")

    def test_obj_rejects_bad_indices_instead_of_silently_corrupting_geometry(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.obj"
            path.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 0 2 3\n")
            with self.assertRaisesRegex(ValueError, "Invalid OBJ index"):
                read_obj(path)


if __name__ == "__main__":
    unittest.main()
