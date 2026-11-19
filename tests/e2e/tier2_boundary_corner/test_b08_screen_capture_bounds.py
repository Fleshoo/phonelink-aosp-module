"""
Boundary & Corner Cases: Feature 8 (Screen Capture Pipeline)
Tests zero/negative resolution, invalid density DPI, empty name,
released surface injection, and operations on released VirtualDisplays.
"""

import unittest
from tests.mock_env.android_runtime import Surface
from tests.mock_env.display_manager import DisplayManager
from tests.mock_env.binder_ipc import IPhoneScreenMirroringService


class TestScreenCaptureBounds(unittest.TestCase):
    def setUp(self):
        self.dm = DisplayManager()
        self.service = IPhoneScreenMirroringService(self.dm)

    def tearDown(self):
        self.service.releaseVirtualDisplay()
        self.dm.reset()

    def test_zero_dimensions_raise_value_error(self):
        surface = Surface(0, 0)
        with self.assertRaises(ValueError):
            self.service.createVirtualDisplay("BadDisp", 0, 0, 440, 0, surface)

    def test_negative_density_dpi_raises_value_error(self):
        surface = Surface(1080, 2340)
        with self.assertRaises(ValueError):
            self.service.createVirtualDisplay("BadDpi", 1080, 2340, -1, 0, surface)

    def test_empty_display_name_raises_value_error(self):
        surface = Surface(1080, 2340)
        with self.assertRaises(ValueError):
            self.service.createVirtualDisplay("", 1080, 2340, 440, 0, surface)

    def test_invalid_released_surface_raises_value_error(self):
        surface = Surface(1080, 2340)
        surface.release()
        with self.assertRaises(ValueError):
            self.service.createVirtualDisplay("ReleasedSurf", 1080, 2340, 440, 0, surface)

    def test_resize_released_display_raises_runtime_error(self):
        surface = Surface(1080, 2340)
        self.service.createVirtualDisplay("Stream", 1080, 2340, 440, 0, surface)
        self.service.releaseVirtualDisplay()
        with self.assertRaises(RuntimeError):
            self.service.resizeVirtualDisplay(720, 1280, 320)

    def test_push_frame_to_released_surface_raises_runtime_error(self):
        surface = Surface(1080, 2340)
        surface.release()
        with self.assertRaises(RuntimeError):
            surface.push_frame(b"frame_bytes")


if __name__ == "__main__":
    unittest.main()
