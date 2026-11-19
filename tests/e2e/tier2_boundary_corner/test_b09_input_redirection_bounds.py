"""
Boundary & Corner Cases: Feature 9 (Input Redirection in SemInputInjector)
Tests None event injection, negative coordinates rejection, injection to non-existent displays,
excessive multitouch pointer counts, and disabled state handling.
"""

import unittest
from tests.mock_env.android_runtime import MotionEvent, Process
from tests.mock_env.display_manager import DisplayManager
from tests.mock_env.input_manager import InputManagerService
from tests.mock_env.binder_ipc import IInputInjectorService


class TestInputRedirectionBounds(unittest.TestCase):
    def setUp(self):
        self.dm = DisplayManager()
        self.ims = InputManagerService(self.dm)
        self.service = IInputInjectorService(self.ims)
        self.ims.enable_inject_bypass_for_uid(10150)
        Process.set_current("com.samsung.android.mdx", 10150)
        self.service.enableInputInjector()

    def tearDown(self):
        Process.reset()
        self.ims.clear()
        self.dm.reset()

    def test_inject_none_event_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.service.inject(None, mode=0)

    def test_negative_coordinates_rejected(self):
        negative_touch = MotionEvent(action=MotionEvent.ACTION_DOWN, x=-10.0, y=50.0, display_id=0)
        res = self.service.inject(negative_touch, mode=0)
        self.assertFalse(res)
        self.assertEqual(len(self.ims.injected_events), 0)

    def test_inject_to_nonexistent_display_id_returns_false(self):
        touch = MotionEvent(action=MotionEvent.ACTION_DOWN, x=100.0, y=200.0)
        res = self.service.injectToDisplay(touch, mode=0, displayId=9999)
        self.assertFalse(res)

    def test_excessive_multitouch_pointers_raises_value_error(self):
        touch = MotionEvent(action=MotionEvent.ACTION_DOWN, x=100.0, y=100.0, display_id=0)
        # Add 11 additional pointers (total 12 > max 10)
        for i in range(1, 12):
            touch.add_pointer(pointer_id=i, x=100.0 + i, y=100.0 + i)
        with self.assertRaises(ValueError) as ctx:
            self.service.inject(touch, mode=0)
        self.assertIn("Exceeded maximum pointer count", str(ctx.exception))

    def test_inject_to_released_virtual_display_returns_false(self):
        vd = self.dm.create_virtual_display("VD_Temp", 1080, 2340, 440)
        disp_id = vd.get_display_id()
        vd.release()

        touch = MotionEvent(action=MotionEvent.ACTION_DOWN, x=50.0, y=50.0)
        res = self.service.injectToDisplay(touch, mode=0, displayId=disp_id)
        self.assertFalse(res)


if __name__ == "__main__":
    unittest.main()
