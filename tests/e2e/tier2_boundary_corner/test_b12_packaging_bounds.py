"""
Boundary & Corner Cases: Feature 12 (Unified Packaging & Delivery)
Tests missing archive files, missing module.prop properties, malformed manifests,
and invalid xposed_init configurations.
"""

import unittest
from tests.mock_env.packaging_validator import PackagingValidator


class TestPackagingBounds(unittest.TestCase):
    def test_missing_magisk_file_detected(self):
        incomplete_files = [
            "module.prop",
            "customize.sh",
            # missing update-binary, updater-script, priv-app apk, etc.
        ]
        valid, missing = PackagingValidator.validate_magisk_structure(incomplete_files)
        self.assertFalse(valid)
        self.assertIn("META-INF/com/google/android/update-binary", missing)
        self.assertIn("system/priv-app/LinkToWindowsService/LinkToWindowsService.apk", missing)

    def test_missing_module_prop_field_detected(self):
        incomplete_prop = """
        id=phonelink_mi9
        name=LinkToWindows
        # missing version, versionCode, author, description
        """
        valid, props, missing = PackagingValidator.validate_module_prop(incomplete_prop)
        self.assertFalse(valid)
        self.assertIn("version", missing)
        self.assertIn("versionCode", missing)
        self.assertIn("author", missing)

    def test_privapp_xml_missing_package_tag_fails(self):
        bad_privapp = "<permissions><privapp-permissions package='com.other.app'></privapp-permissions></permissions>"
        valid, errors = PackagingValidator.validate_privapp_xml(bad_privapp)
        self.assertFalse(valid)
        self.assertTrue(any("Missing <privapp-permissions package='com.samsung.android.mdx'>" in e for e in errors))

    def test_sysconfig_xml_missing_required_app_fails(self):
        incomplete_sysconfig = """
        <config>
            <allow-in-power-save package="com.samsung.android.mdx" />
            <!-- missing allow-in-power-save for com.microsoft.appmanager -->
            <allow-in-data-saver package="com.samsung.android.mdx" />
            <allow-in-data-saver package="com.microsoft.appmanager" />
        </config>
        """
        valid, errors = PackagingValidator.validate_sysconfig_xml(incomplete_sysconfig)
        self.assertFalse(valid)
        self.assertTrue(any("Missing <allow-in-power-save>" in e for e in errors))

    def test_lsposed_apk_missing_xposed_init_asset_fails(self):
        files = ["AndroidManifest.xml", "classes.dex"]  # missing assets/xposed_init
        valid, errors = PackagingValidator.validate_lsposed_apk(files, "me.phonelink.xposed.XposedInit")
        self.assertFalse(valid)
        self.assertTrue(any("Missing required asset: assets/xposed_init" in e for e in errors))

    def test_lsposed_apk_empty_xposed_init_fails(self):
        files = ["AndroidManifest.xml", "assets/xposed_init"]
        valid, errors = PackagingValidator.validate_lsposed_apk(files, "")
        self.assertFalse(valid)
        self.assertTrue(any("assets/xposed_init is empty" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
