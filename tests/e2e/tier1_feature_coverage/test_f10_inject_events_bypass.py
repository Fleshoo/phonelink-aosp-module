"""
Feature 10: system_server INJECT_EVENTS Bypass Tests (Tier 1)
Verifies LSPosed hook in system_server permits non-platform-signed
MDX service and AppManager to inject input events while denying untrusted callers.
"""

import unittest
from tests.mock_env.android_runtime import MotionEvent, Process, SecurityException
from tests.mock_env.display_manager import DisplayManager
from tests.mock_env.input_manager import InputManagerService
from tests.mock_env.lsposed_engine import LSPosedEngine


class TestInjectEventsBypass(unittest.TestCase):
    def setUp(self):
        self.display_manager = DisplayManager()
        self.ims = InputManagerService(self.display_manager)
        self.lsposed = LSPosedEngine()

    def tearDown(self):
        Process.reset()
        self.lsposed.reset()
        self.ims.clear()
        self.display_manager.reset()

    def test_stock_aosp_denies_injection_without_permission(self):
        """Authoritative Source: PROJECT.md § Feature 10 (AOSP baseline)"""
        Process.set_current("com.samsung.android.mdx", 10150)
        touch = MotionEvent(MotionEvent.ACTION_DOWN, x=100.0, y=100.0)
        with self.assertRaises(SecurityException) as ctx:
            self.ims.inject_input_event(touch, mode=0)
        self.assertIn("INJECT_EVENTS", str(ctx.exception))

    def test_lsposed_hook_allows_mdx_uid(self):
        """Authoritative Source: PROJECT.md § Feature 10"""
        self.lsposed.apply_system_server_hooks(self.ims, mdx_uid=10150, appmanager_uid=10151)
        Process.set_current("com.samsung.android.mdx", 10150)
        touch = MotionEvent(MotionEvent.ACTION_DOWN, x=200.0, y=300.0)
        res = self.ims.inject_input_event(touch, mode=0)
        self.assertTrue(res)

    def test_lsposed_hook_allows_appmanager_uid(self):
        """Authoritative Source: PROJECT.md § Feature 10"""
        self.lsposed.apply_system_server_hooks(self.ims, mdx_uid=10150, appmanager_uid=10151)
        Process.set_current("com.microsoft.appmanager", 10151)
        touch = MotionEvent(MotionEvent.ACTION_DOWN, x=200.0, y=300.0)
        res = self.ims.inject_input_event(touch, mode=0)
        self.assertTrue(res)

    def test_system_uid_1000_always_allowed(self):
        """Authoritative Source: Android Security Framework Architecture"""
        Process.set_current("android", 1000)
        touch = MotionEvent(MotionEvent.ACTION_DOWN, x=50.0, y=50.0)
        res = self.ims.inject_input_event(touch, mode=0)
        self.assertTrue(res)

    def test_unwhitelisted_third_party_uid_still_denied(self):
        """Authoritative Source: PROJECT.md § Feature 10 (Strict Security Isolation)"""
        self.lsposed.apply_system_server_hooks(self.ims, mdx_uid=10150, appmanager_uid=10151)
        Process.set_current("com.rogue.malware", 10200)
        touch = MotionEvent(MotionEvent.ACTION_DOWN, x=200.0, y=300.0)
        with self.assertRaises(SecurityException):
            self.ims.inject_input_event(touch, mode=0)

    def test_system_server_hooks_java_source_contains_uid_cache(self):
        """Authoritative Source: Milestone M4 Task Specification & Feature 10"""
        import os
        src_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "lsposed_module", "app", "src", "main", "java",
            "me", "phonelink", "xposed", "hooks", "SystemServerHooks.java"
        )
        with open(src_path, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("sPrivilegedUidCache", src)
        self.assertIn("hookInputManagerService", src)
        self.assertIn("checkCallingPermission", src)


if __name__ == "__main__":
    unittest.main()
