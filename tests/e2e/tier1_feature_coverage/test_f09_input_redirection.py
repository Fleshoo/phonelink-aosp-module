"""
Feature 9: Input Redirection in SemInputInjector Tests (Tier 1)
Verifies IInputInjectorService AIDL contract and redirection of touch/key
events to AOSP InputManagerService.
"""

import unittest
from tests.mock_env.android_runtime import MotionEvent, KeyEvent, Process
from tests.mock_env.display_manager import DisplayManager
from tests.mock_env.input_manager import InputManagerService
from tests.mock_env.binder_ipc import IInputInjectorService


class TestInputRedirection(unittest.TestCase):
    def setUp(self):
        self.display_manager = DisplayManager()
        self.ims = InputManagerService(self.display_manager)
        self.service = IInputInjectorService(self.ims)
        # Grant bypass for testing
        self.ims.enable_inject_bypass_for_uid(10150)
        Process.set_current("com.samsung.android.mdx", 10150)

    def tearDown(self):
        Process.reset()
        self.ims.clear()
        self.display_manager.reset()

    def test_enable_disable_input_injector(self):
        """Authoritative Source: PROJECT.md § Interface Contracts (IInputInjectorService)"""
        self.assertFalse(self.service.is_enabled())
        self.service.enableInputInjector()
        self.assertTrue(self.service.is_enabled())
        self.service.disableInputInjector()
        self.assertFalse(self.service.is_enabled())

    def test_inject_motion_event_dispatched(self):
        """Authoritative Source: PROJECT.md § Feature 9 & Interface Contracts"""
        self.service.enableInputInjector()
        touch_down = MotionEvent(action=MotionEvent.ACTION_DOWN, x=540.0, y=1170.0, display_id=0)
        res = self.service.inject(touch_down, mode=InputManagerService.INJECT_INPUT_EVENT_MODE_ASYNC)
        self.assertTrue(res)
        self.assertEqual(len(self.ims.injected_events), 1)
        self.assertIs(self.ims.injected_events[0], touch_down)

    def test_inject_to_virtual_display(self):
        """Authoritative Source: PROJECT.md § Feature 9"""
        vd = self.display_manager.create_virtual_display("TestVD", 1080, 2340, 440)
        self.service.enableInputInjector()
        touch = MotionEvent(action=MotionEvent.ACTION_MOVE, x=300.0, y=600.0)
        res = self.service.injectToDisplay(touch, mode=0, displayId=vd.get_display_id())
        self.assertTrue(res)
        self.assertEqual(touch.display_id, vd.get_display_id())

    def test_inject_when_disabled_returns_false(self):
        """Authoritative Source: IInputInjectorService contract"""
        self.service.disableInputInjector()
        touch = MotionEvent(action=MotionEvent.ACTION_DOWN, x=100.0, y=100.0)
        res = self.service.inject(touch, mode=0)
        self.assertFalse(res)
        self.assertEqual(len(self.ims.injected_events), 0)

    def test_inject_key_event_back_dispatched(self):
        """Authoritative Source: PROJECT.md § Feature 9"""
        self.service.enableInputInjector()
        back_down = KeyEvent(action=KeyEvent.ACTION_DOWN, key_code=KeyEvent.KEYCODE_BACK)
        res = self.service.inject(back_down, mode=0)
        self.assertTrue(res)
        self.assertEqual(len(self.ims.injected_events), 1)
        self.assertEqual(self.ims.injected_events[0].key_code, KeyEvent.KEYCODE_BACK)

    def test_dex_contains_input_injection_hooks_descriptor(self):
        """Authoritative Source: Milestone M4 Task Specification & Feature 9"""
        import os, zipfile
        from tests.mock_env.packaging_validator import PackagingValidator
        apk_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "lsposed_module", "PhoneLinkXposed.apk")
        self.assertTrue(os.path.exists(apk_path), f"PhoneLinkXposed.apk not found at {apk_path}")
        with zipfile.ZipFile(apk_path, "r") as z:
            dex_data = z.read("classes.dex")
        types, defined_classes = PackagingValidator.parse_dex_classes(dex_data)
        self.assertIn("Lme/phonelink/xposed/hooks/InputInjectionHooks;", defined_classes)


if __name__ == "__main__":
    unittest.main()
