"""
Boundary & Corner Cases: Feature 10 (system_server INJECT_EVENTS Bypass)
Tests security denials for untrusted UIDs, rapid bypass toggle,
null event handling, and process identity spoofing prevention.
"""

import unittest
from tests.mock_env.android_runtime import MotionEvent, Process, SecurityException
from tests.mock_env.display_manager import DisplayManager
from tests.mock_env.input_manager import InputManagerService


class TestInjectEventsBounds(unittest.TestCase):
    def setUp(self):
        self.dm = DisplayManager()
        self.ims = InputManagerService(self.dm)

    def tearDown(self):
        Process.reset()
        self.ims.clear()
        self.dm.reset()

    def test_untrusted_uid_rejected_with_security_exception(self):
        Process.set_current("com.untrusted.daemon", 10999)
        touch = MotionEvent(MotionEvent.ACTION_DOWN, x=50.0, y=50.0)
        with self.assertRaises(SecurityException) as ctx:
            self.ims.inject_input_event(touch, mode=0)
        self.assertIn("UID 10999 does not hold android.permission.INJECT_EVENTS", str(ctx.exception))

    def test_disable_inject_bypass_causes_immediate_denial(self):
        self.ims.enable_inject_bypass_for_uid(10150)
        Process.set_current("com.samsung.android.mdx", 10150)
        touch = MotionEvent(MotionEvent.ACTION_DOWN, x=50.0, y=50.0)
        self.assertTrue(self.ims.inject_input_event(touch, mode=0))

        # Disable bypass and verify denial
        self.ims.disable_inject_bypass()
        with self.assertRaises(SecurityException):
            self.ims.inject_input_event(touch, mode=0)

    def test_null_event_raises_value_error_before_permission(self):
        # Even with bypass enabled, null event must raise ValueError
        self.ims.enable_inject_bypass_for_uid(10150)
        Process.set_current("com.samsung.android.mdx", 10150)
        with self.assertRaises(ValueError):
            self.ims.inject_input_event(None, mode=0)

    def test_rogue_process_tamper_attempt_denied(self):
        self.ims.enable_inject_bypass_for_uid(10150)
        # Rogue app tries to claim MDX package name but has untrusted UID
        Process.set_current("com.samsung.android.mdx", 10888)
        touch = MotionEvent(MotionEvent.ACTION_DOWN, x=50.0, y=50.0)
        with self.assertRaises(SecurityException):
            self.ims.inject_input_event(touch, mode=0)

    def test_system_uid_1000_unaffected_by_bypass_disable(self):
        self.ims.disable_inject_bypass()
        Process.set_current("android", 1000)
        touch = MotionEvent(MotionEvent.ACTION_DOWN, x=10.0, y=10.0)
        self.assertTrue(self.ims.inject_input_event(touch, mode=0))


if __name__ == "__main__":
    unittest.main()
