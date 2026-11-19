"""
Feature 12: Unified Packaging & Delivery Tests (Tier 1)
Verifies structure and metadata of Magisk module and LSPosed APK components.
"""

import unittest
from tests.mock_env.packaging_validator import PackagingValidator


class TestPackagingAndDelivery(unittest.TestCase):
    SAMPLE_MAGISK_FILES = [
        "META-INF/com/google/android/update-binary",
        "META-INF/com/google/android/updater-script",
        "module.prop",
        "customize.sh",
        "service.sh",
        "uninstall.sh",
        "system/priv-app/LinkToWindowsService/LinkToWindowsService.apk",
        "system/etc/permissions/privapp-permissions-phonelink.xml",
        "system/etc/permissions/com.samsung.feature.samsung_experience_mobile.xml",
        "system/etc/sysconfig/phonelink-whitelist.xml",
    ]

    SAMPLE_MODULE_PROP = """
    id=phonelink_mi9_a16
    name=Link to Windows for Xiaomi Mi 9
    version=v1.0.0
    versionCode=100
    author=Antigravity Engineering
    description=Enables full Microsoft Link to Windows phone screen & input on Android 16
    """

    SAMPLE_PRIVAPP_XML = """
    <permissions>
        <privapp-permissions package="com.samsung.android.mdx">
            <permission name="android.permission.WRITE_SECURE_SETTINGS"/>
            <permission name="android.permission.INTERACT_ACROSS_USERS"/>
            <permission name="android.permission.BATTERY_STATS"/>
            <permission name="android.permission.CAPTURE_VIDEO_OUTPUT"/>
        </privapp-permissions>
    </permissions>
    """

    SAMPLE_SYSCONFIG_XML = """
    <config>
        <allow-in-power-save package="com.samsung.android.mdx" />
        <allow-in-power-save package="com.microsoft.appmanager" />
        <allow-in-data-saver package="com.samsung.android.mdx" />
        <allow-in-data-saver package="com.microsoft.appmanager" />
    </config>
    """

    def test_magisk_module_structure_has_all_required_files(self):
        """Authoritative Source: PROJECT.md § Code Layout & Feature 12"""
        valid, missing = PackagingValidator.validate_magisk_structure(self.SAMPLE_MAGISK_FILES)
        self.assertTrue(valid, f"Missing files: {missing}")
        self.assertEqual(len(missing), 0)

    def test_module_prop_contains_all_metadata_keys(self):
        """Authoritative Source: PROJECT.md § Feature 12"""
        valid, props, missing = PackagingValidator.validate_module_prop(self.SAMPLE_MODULE_PROP)
        self.assertTrue(valid, f"Missing keys: {missing}")
        self.assertEqual(props["id"], "phonelink_mi9_a16")
        self.assertEqual(props["versionCode"], "100")

    def test_privapp_xml_manifest_has_mdx_and_permissions(self):
        """Authoritative Source: PROJECT.md § Feature 5 & 12"""
        valid, errors = PackagingValidator.validate_privapp_xml(self.SAMPLE_PRIVAPP_XML)
        self.assertTrue(valid, f"Validation errors: {errors}")

    def test_sysconfig_xml_has_power_and_data_saver(self):
        """Authoritative Source: PROJECT.md § Feature 6 & 12"""
        valid, errors = PackagingValidator.validate_sysconfig_xml(self.SAMPLE_SYSCONFIG_XML)
        self.assertTrue(valid, f"Validation errors: {errors}")

    def test_lsposed_apk_has_manifest_and_valid_xposed_init(self):
        """Authoritative Source: PROJECT.md § Feature 12"""
        files = ["AndroidManifest.xml", "assets/xposed_init", "classes.dex"]
        valid, errors = PackagingValidator.validate_lsposed_apk(files, "me.phonelink.xposed.XposedInit")
        self.assertTrue(valid, f"Validation errors: {errors}")


if __name__ == "__main__":
    unittest.main()
