"""
Feature 1: Process-Scoped Device Spoofing Tests (Tier 1)
Verifies that Samsung device identity is selectively presented to Link to Windows
and MDX service while preserving standard Xiaomi Mi 9 identity for all other packages.
"""

import unittest
from tests.mock_env.android_runtime import Build, Process
from tests.mock_env.art_classloader import ARTClassLoader
from tests.mock_env.lsposed_engine import LSPosedEngine


class TestProcessScopedDeviceSpoofing(unittest.TestCase):
    def setUp(self):
        self.class_loader = ARTClassLoader(is_aosp_base=True)
        self.lsposed = LSPosedEngine()
        self.lsposed.apply_app_manager_hooks(self.class_loader)

    def tearDown(self):
        Process.reset()
        self.lsposed.reset()
        Build.reset_defaults()

    def test_target_appmanager_sees_samsung_manufacturer(self):
        """Authoritative Source: PROJECT.md § Feature 1 & Architecture"""
        Process.set_current("com.microsoft.appmanager", 10151)
        self.assertEqual(Build.MANUFACTURER, "samsung")

    def test_target_mdx_sees_samsung_brand_and_model(self):
        """Authoritative Source: PROJECT.md § Feature 1"""
        Process.set_current("com.samsung.android.mdx", 10150)
        self.assertEqual(Build.BRAND, "samsung")
        self.assertEqual(Build.MODEL, "SM-G998B")

    def test_nontarget_package_preserves_xiaomi_manufacturer(self):
        """Authoritative Source: PROJECT.md § Feature 1 (preserve global Xiaomi identity)"""
        Process.set_current("com.google.android.gms", 10050)
        self.assertEqual(Build.MANUFACTURER, "Xiaomi")

    def test_system_server_preserves_xiaomi_identity(self):
        """Authoritative Source: PROJECT.md § Feature 1"""
        Process.set_current("android", 1000)
        self.assertEqual(Build.MANUFACTURER, "Xiaomi")
        self.assertEqual(Build.MODEL, "MI 9")
        self.assertEqual(Build.DEVICE, "cepheus")

    def test_sdk_int_remains_android16_36(self):
        """Authoritative Source: ORIGINAL_REQUEST.md R1 & PROJECT.md § Architecture"""
        Process.set_current("com.microsoft.appmanager", 10151)
        self.assertEqual(Build.VERSION_SDK_INT, 36)
        Process.set_current("com.google.android.gms", 10050)
        self.assertEqual(Build.VERSION_SDK_INT, 36)


if __name__ == "__main__":
    unittest.main()
