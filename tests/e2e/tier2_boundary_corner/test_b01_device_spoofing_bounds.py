"""
Boundary & Corner Cases: Feature 1 (Device Spoofing)
Tests empty package lookup, non-existent packages, rapid process context switching,
explicit disablement, and null override handling.
"""

import unittest
from tests.mock_env.android_runtime import Build, Process
from tests.mock_env.art_classloader import ARTClassLoader
from tests.mock_env.lsposed_engine import LSPosedEngine


class TestDeviceSpoofingBounds(unittest.TestCase):
    def setUp(self):
        self.class_loader = ARTClassLoader(is_aosp_base=True)
        self.lsposed = LSPosedEngine()
        self.lsposed.apply_app_manager_hooks(self.class_loader)

    def tearDown(self):
        Process.reset()
        self.lsposed.reset()
        Build.reset_defaults()

    def test_empty_package_name_preserves_default(self):
        Process.set_current("", 0)
        self.assertEqual(Build.MANUFACTURER, "Xiaomi")
        self.assertEqual(Build.MODEL, "MI 9")

    def test_nonexistent_package_preserves_default(self):
        Process.set_current("com.unknown.nonexistent.app", 99999)
        self.assertEqual(Build.MANUFACTURER, "Xiaomi")
        self.assertEqual(Build.MODEL, "MI 9")

    def test_process_context_switching_isolation(self):
        # Target package -> Samsung
        Process.set_current("com.microsoft.appmanager", 10151)
        self.assertEqual(Build.MANUFACTURER, "samsung")

        # Switch to non-target package -> Xiaomi
        Process.set_current("com.miui.camera", 10020)
        self.assertEqual(Build.MANUFACTURER, "Xiaomi")

        # Switch back -> Samsung
        Process.set_current("com.microsoft.appmanager", 10151)
        self.assertEqual(Build.MANUFACTURER, "samsung")

    def test_disable_spoofing_restores_defaults_immediately(self):
        Process.set_current("com.microsoft.appmanager", 10151)
        self.assertEqual(Build.MANUFACTURER, "samsung")

        Build.disable_scoped_spoofing()
        self.assertEqual(Build.MANUFACTURER, "Xiaomi")

    def test_partial_override_preserves_unspecified_fields(self):
        Build.enable_scoped_spoofing({
            "com.partial.app": {
                "MANUFACTURER": "samsung"
                # MODEL and BRAND not specified
            }
        })
        Process.set_current("com.partial.app", 10190)
        self.assertEqual(Build.MANUFACTURER, "samsung")
        self.assertEqual(Build.MODEL, "MI 9")
        self.assertEqual(Build.BRAND, "Xiaomi")


if __name__ == "__main__":
    unittest.main()
