"""
Boundary & Corner Cases: Feature 5 (Priv-App Overlay & Whitelist)
Tests malformed XML, empty tags, unprivileged UID checks,
and boundary conditions for system UID permissions.
"""

import unittest
from tests.mock_env.pms_service import PackageManagerService


class TestPrivAppWhitelistBounds(unittest.TestCase):
    def setUp(self):
        self.pms = PackageManagerService()

    def tearDown(self):
        self.pms.clear()

    def test_malformed_xml_raises_value_error(self):
        bad_xml = "<permissions><unclosed_tag></permissions>"
        with self.assertRaises(ValueError):
            self.pms.load_privapp_permissions_xml(bad_xml)

    def test_xml_without_privapp_tags_loads_cleanly(self):
        empty_xml = "<permissions></permissions>"
        self.pms.load_privapp_permissions_xml(empty_xml)
        self.assertEqual(len(self.pms._privapp_whitelist), 0)

    def test_system_uid_1000_inherently_privileged(self):
        self.assertTrue(
            self.pms.check_uid_permission(1000, "android.permission.WRITE_SECURE_SETTINGS")
        )
        self.assertTrue(
            self.pms.check_uid_permission(1000, "android.permission.INJECT_EVENTS")
        )

    def test_unknown_uid_has_no_permissions(self):
        self.assertFalse(
            self.pms.check_uid_permission(99999, "android.permission.WRITE_SECURE_SETTINGS")
        )

    def test_app_in_system_app_but_not_privapp_is_not_privileged(self):
        # /system/app/ is system, but NOT priv-app (requires /system/priv-app/)
        pkg = self.pms.register_package(
            "com.system.normal", 10050, "/system/app/NormalSystemApp",
            requested_permissions=["android.permission.WRITE_SECURE_SETTINGS"]
        )
        self.assertFalse(pkg.is_privileged)
        self.assertFalse(
            self.pms.check_permission("com.system.normal", "android.permission.WRITE_SECURE_SETTINGS")
        )


if __name__ == "__main__":
    unittest.main()
