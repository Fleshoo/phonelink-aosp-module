"""
Feature 3: One UI Version & Framework Stubs Tests (Tier 1)
Verifies SEM_INT (3001) compatibility stub and safe fallbacks for DeX/SmartClip.
"""

import unittest
from tests.mock_env.art_classloader import ARTClassLoader, OneUIStubs
from tests.mock_env.lsposed_engine import LSPosedEngine


class TestOneUIVersionStubs(unittest.TestCase):
    def setUp(self):
        self.class_loader = ARTClassLoader(is_aosp_base=True)
        self.lsposed = LSPosedEngine()
        self.lsposed.apply_mdx_service_hooks(self.class_loader)

    def tearDown(self):
        self.lsposed.reset()

    def test_sem_int_constant_returns_3001(self):
        """Authoritative Source: PROJECT.md § Feature 3 (SEM_INT = 3001)"""
        self.assertEqual(OneUIStubs.SEM_INT, 3001)

    def test_ll0_c_loads_stub(self):
        """Authoritative Source: PROJECT.md § Feature 3"""
        cls = self.class_loader.load_class("LL0.c")
        self.assertIs(cls, OneUIStubs)
        self.assertEqual(cls.SEM_INT, 3001)

    def test_semversion_loads_stub(self):
        """Authoritative Source: PROJECT.md § Feature 3"""
        cls = self.class_loader.load_class("com.samsung.android.os.SemVersion")
        self.assertIs(cls, OneUIStubs)
        self.assertEqual(cls.SEM_INT, 3001)

    def test_desktop_mode_manager_returns_false(self):
        """Authoritative Source: PROJECT.md § Feature 3"""
        cls = self.class_loader.load_class("com.samsung.android.desktopmode.DesktopModeManager")
        self.assertIs(cls, OneUIStubs)
        self.assertFalse(cls.is_desktop_mode())

    def test_smart_clip_returns_false(self):
        """Authoritative Source: PROJECT.md § Feature 3"""
        self.assertFalse(OneUIStubs.is_smart_clip_supported())

    def test_mdx_service_hooks_system_repository_keyguard_hook(self):
        """Authoritative Source: Milestone M4 Task Specification & Polish Finding 1"""
        import os
        src_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "lsposed_module", "app", "src", "main", "java",
            "me", "phonelink", "xposed", "hooks", "MdxServiceHooks.java"
        )
        with open(src_path, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn('findAndHookMethod(sysRepoClass, "isKeyguardLocked", new XC_MethodReplacement()', src)
        self.assertIn('XposedHelpers.getObjectField(param.thisObject, "mAppContext")', src)


if __name__ == "__main__":
    unittest.main()
