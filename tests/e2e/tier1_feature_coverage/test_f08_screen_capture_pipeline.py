"""
Feature 8: Screen Capture & Virtual Display Pipeline Tests (Tier 1)
Verifies IPhoneScreenMirroringService AIDL contract, VirtualDisplay lifecycle,
and hardware surface buffer pipeline.
"""

import unittest
from tests.mock_env.android_runtime import Surface
from tests.mock_env.display_manager import DisplayManager
from tests.mock_env.binder_ipc import IPhoneScreenMirroringService


class MockDisplayCallback:
    def __init__(self):
        self.stopped = False
        self.resumed = False

    def onStopped(self):
        self.stopped = True

    def onResumed(self):
        self.resumed = True


class TestScreenCapturePipeline(unittest.TestCase):
    def setUp(self):
        self.display_manager = DisplayManager()
        self.service = IPhoneScreenMirroringService(self.display_manager)

    def tearDown(self):
        self.service.releaseVirtualDisplay()
        self.display_manager.reset()

    def test_create_virtual_display_returns_valid_id(self):
        """Authoritative Source: PROJECT.md § Interface Contracts (IPhoneScreenMirroringService)"""
        surface = Surface(1080, 2340)
        callback = MockDisplayCallback()
        disp_id = self.service.createVirtualDisplay(
            name="PhoneScreenStream",
            width=1080,
            height=2340,
            densityDpi=440,
            flags=DisplayManager.VIRTUAL_DISPLAY_FLAG_PUBLIC,
            surface=surface,
            callback=callback,
        )
        self.assertGreater(disp_id, 0)
        self.assertTrue(callback.resumed)
        self.assertIsNotNone(self.service.active_virtual_display)

    def test_virtual_display_receives_surface_and_frames(self):
        """Authoritative Source: PROJECT.md § Feature 8"""
        surface = Surface(1080, 2340)
        self.service.createVirtualDisplay(
            name="PhoneScreenStream",
            width=1080,
            height=2340,
            densityDpi=440,
            flags=DisplayManager.VIRTUAL_DISPLAY_FLAG_PUBLIC,
            surface=surface,
        )
        test_frame = b"\x00\x00\x00\x01\x67\x42\x00\x1f"  # H.264 SPS NAL unit
        surface.push_frame(test_frame)
        self.assertEqual(len(surface.frames_received), 1)
        self.assertEqual(surface.frames_received[0], test_frame)

    def test_resize_virtual_display(self):
        """Authoritative Source: PROJECT.md § Interface Contracts"""
        surface = Surface(1080, 2340)
        self.service.createVirtualDisplay(
            name="PhoneScreenStream",
            width=1080,
            height=2340,
            densityDpi=440,
            flags=DisplayManager.VIRTUAL_DISPLAY_FLAG_PUBLIC,
            surface=surface,
        )
        self.service.resizeVirtualDisplay(720, 1560, 320)
        vd = self.service.active_virtual_display
        self.assertEqual(vd.get_width(), 720)
        self.assertEqual(vd.get_height(), 1560)
        self.assertEqual(vd.get_density_dpi(), 320)
        self.assertEqual(vd.state, "RESIZED")

    def test_set_surface_updates_buffer_target(self):
        """Authoritative Source: PROJECT.md § Interface Contracts"""
        surface1 = Surface(1080, 2340)
        surface2 = Surface(1080, 2340)
        self.service.createVirtualDisplay(
            name="PhoneScreenStream",
            width=1080,
            height=2340,
            densityDpi=440,
            flags=DisplayManager.VIRTUAL_DISPLAY_FLAG_PUBLIC,
            surface=surface1,
        )
        success = self.service.setSurface(surface2)
        self.assertTrue(success)
        self.assertIs(self.service.active_virtual_display.surface, surface2)

    def test_release_virtual_display_cleans_up_resources(self):
        """Authoritative Source: PROJECT.md § Interface Contracts"""
        surface = Surface(1080, 2340)
        callback = MockDisplayCallback()
        disp_id = self.service.createVirtualDisplay(
            name="PhoneScreenStream",
            width=1080,
            height=2340,
            densityDpi=440,
            flags=DisplayManager.VIRTUAL_DISPLAY_FLAG_PUBLIC,
            surface=surface,
            callback=callback,
        )
        self.service.releaseVirtualDisplay()
        self.assertIsNone(self.service.active_virtual_display)
        self.assertFalse(surface.is_valid())
        self.assertTrue(callback.stopped)
        self.assertIsNone(self.display_manager.get_display(disp_id))


if __name__ == "__main__":
    unittest.main()
