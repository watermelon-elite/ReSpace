import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from bake import bake_mesh, finish_samples, pixels, project, visibility


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.camera = dict(width=64, height=64, world_to_camera=np.eye(4).tolist(),
                           projection=[[1, 0, 0, 0], [0, 1, 0, 0],
                                       [0, 0, -10.1/9.9, -2/9.9], [0, 0, -1, 0]])

    def mesh(self, z):
        return dict(path="/Room/Test", world=np.array([[-.5, -.5, z], [.5, -.5, z], [0, .5, z]]),
                    faces=np.array([[0, 1, 2]]), color=[.3, .4, .5])

    def test_camera_orientation_and_perspective(self):
        uv, depth = project(np.array([[0, 0, -2], [1, 1, -2], [1, 1, -4]]), self.camera)
        np.testing.assert_allclose(uv, [[32, 32], [48, 16], [40, 24]])
        np.testing.assert_allclose(depth, [2, 2, 4])

    def test_foreground_occludes_background(self):
        depth, owners = visibility([self.mesh(-2), self.mesh(-1)], self.camera)
        self.assertEqual(owners[32, 32], 1)
        self.assertAlmostEqual(depth[32, 32], 1)

    def test_partial_triangle_is_clipped_and_rasterized(self):
        result = pixels(np.array([[-20., 5.], [80., 5.], [32., 60.]]), 64, 64)
        self.assertIsNotNone(result)
        x, y, bary = result
        self.assertGreater(len(x), 500)
        self.assertTrue(((x >= 0) & (x < 64) & (y >= 0) & (y < 64)).all())
        np.testing.assert_allclose(bary.sum(axis=1), 1)

    def test_bake_rejects_hidden_surface(self):
        meshes = [self.mesh(-2), self.mesh(-1)]
        depth, owners = visibility(meshes, self.camera)
        image = np.full((64, 64, 3), [220, 40, 30], dtype=float)
        with tempfile.TemporaryDirectory() as temporary:
            _, _, hidden = bake_mesh(meshes[0], 0, self.camera, image, depth, owners, Path(temporary))
            uv, name, visible = bake_mesh(meshes[1], 1, self.camera, image, depth, owners, Path(temporary))
            self.assertEqual(hidden["projected_fraction"], 0)
            self.assertGreater(visible["projected_fraction"], .5)
            self.assertTrue(((uv >= 0) & (uv <= 1)).all())
            self.assertTrue((np.array(Image.open(Path(temporary)/name)) == [220, 40, 30]).all(axis=-1).any())

    def test_backsplash_fallback_stays_below_upper_wall(self):
        mesh = dict(path="/Room/scan_wall_687159d16597d3f99eb4/Mesh0")
        group = dict(u=np.array([1, 0, 0]), v=np.array([0, 1, 0]))
        image = np.full((100, 100, 3), [80, 70, 60], dtype=float)
        result = finish_samples(mesh, np.array([[0, 1.2, 0], [0, 2.1, 0]]), group, image, [230, 230, 230])
        np.testing.assert_allclose(result, [[80, 70, 60], [230, 230, 230]])


if __name__ == "__main__":
    unittest.main()
