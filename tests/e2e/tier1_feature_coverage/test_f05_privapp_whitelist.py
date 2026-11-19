"""
Feature 5: Priv-App Overlay & Whitelist Tests (Tier 1)
Verifies privileged permissions enforcement in /system/priv-app/
via privapp-permissions-phonelink.xml parsing.
"""

import unittest
from tests.mock_env.pms_service import PackageManagerService


class TestPrivAppWhitelist(unittest.TestCase):
    PRIVAPP_XML = """
    <permissions>
        <privapp-permissions package="com.samsung.android.mdx">
            <permission name="android.permission.WRITE_SECURE_SETTINGS"/>
            <permission name="android.permission.INTERACT_ACROSS_USERS"/>
            <permission name="android.permission.BATTERY_STATS"/>
            <permission name="android.permission.CAPTURE_VIDEO_OUTPUT"/>
        </privapp-permissions>
    </permissions>
    """

    def setUp(self):
        self.pms = PackageManagerService()
        self.pms.load_privapp_permissions_xml(self.PRIVAPP_XML)
        # Register MDX in priv-app
        self.mdx = self.pms.register_package(
            package_name="com.samsung.android.mdx",
            uid=10150,
            source_dir="/system/priv-app/LinkToWindowsService/LinkToWindowsService.apk",
            requested_permissions=[
                "android.permission.WRITE_SECURE_SETTINGS",
                "android.permission.INTERACT_ACROSS_USERS",
                "android.permission.BATTERY_STATS",
                "android.permission.CAPTURE_VIDEO_OUTPUT",
                "android.permission.INTERNAL_SYSTEM_WINDOW",  # Not in whitelist
                "android.permission.INTERNET",                # Standard permission
            ],
        )

    def tearDown(self):
        self.pms.clear()

    def test_privapp_location_marks_package_privileged(self):
        """Authoritative Source: PROJECT.md § Feature 5"""
        self.assertTrue(self.mdx.is_privileged)

    def test_privapp_permissions_xml_parsed_and_granted(self):
        """Authoritative Source: PROJECT.md § Feature 5"""
        self.assertTrue(self.pms.check_permission("com.samsung.android.mdx", "android.permission.WRITE_SECURE_SETTINGS"))
        self.assertTrue(self.pms.check_permission("com.samsung.android.mdx", "android.permission.INTERACT_ACROSS_USERS"))
        self.assertTrue(self.pms.check_permission("com.samsung.android.mdx", "android.permission.BATTERY_STATS"))
        self.assertTrue(self.pms.check_permission("com.samsung.android.mdx", "android.permission.CAPTURE_VIDEO_OUTPUT"))

    def test_non_privileged_app_denied_privileged_permissions(self):
        """Authoritative Source: Android 16 PMS Security Specification"""
        regular_app = self.pms.register_package(
            package_name="com.thirdparty.app",
            uid=10200,
            source_dir="/data/app/RegularApp",
            requested_permissions=["android.permission.WRITE_SECURE_SETTINGS"],
        )
        self.assertFalse(regular_app.is_privileged)
        self.assertFalse(self.pms.check_permission("com.thirdparty.app", "android.permission.WRITE_SECURE_SETTINGS"))

    def test_unwhitelisted_privileged_permission_is_denied(self):
        """Authoritative Source: Android 16 PMS privapp-permissions enforcement"""
        # INTERNAL_SYSTEM_WINDOW requested by MDX but omitted from XML whitelist
        self.assertFalse(
            self.pms.check_permission("com.samsung.android.mdx", "android.permission.INTERNAL_SYSTEM_WINDOW")
        )

    def test_all_standard_permissions_granted(self):
        """Authoritative Source: Android permission model"""
        self.assertTrue(self.pms.check_permission("com.samsung.android.mdx", "android.permission.INTERNET"))


if __name__ == "__main__":
    unittest.main()
