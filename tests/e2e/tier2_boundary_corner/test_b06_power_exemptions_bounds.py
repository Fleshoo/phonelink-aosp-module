"""
Boundary & Corner Cases: Feature 6 (System Power & Doze Exemptions)
Tests malformed sysconfig XML, duplicate entries, empty package attributes,
and non-whitelisted app denials.
"""

import unittest
from tests.mock_env.pms_service import PackageManagerService


class TestPowerExemptionsBounds(unittest.TestCase):
    def setUp(self):
        self.pms = PackageManagerService()

    def tearDown(self):
        self.pms.clear()

    def test_malformed_sysconfig_xml_raises_value_error(self):
        bad_xml = "<config><allow-in-power-save></config>"
        with self.assertRaises(ValueError):
            self.pms.load_sysconfig_xml(bad_xml)

    def test_duplicate_entries_deduplicated_cleanly(self):
        dup_xml = """
        <config>
            <allow-in-power-save package="com.samsung.android.mdx" />
            <allow-in-power-save package="com.samsung.android.mdx" />
            <allow-in-data-saver package="com.samsung.android.mdx" />
        </config>
        """
        self.pms.load_sysconfig_xml(dup_xml)
        self.assertTrue(self.pms.is_power_save_exempt("com.samsung.android.mdx"))
        self.assertEqual(len(self.pms._power_save_whitelist), 1)

    def test_empty_package_attribute_ignored(self):
        xml = """
        <config>
            <allow-in-power-save package="" />
            <allow-in-power-save package="com.samsung.android.mdx" />
        </config>
        """
        self.pms.load_sysconfig_xml(xml)
        self.assertFalse(self.pms.is_power_save_exempt(""))
        self.assertTrue(self.pms.is_power_save_exempt("com.samsung.android.mdx"))

    def test_nonexistent_package_not_exempt(self):
        self.assertFalse(self.pms.is_power_save_exempt("com.never.exempt"))
        self.assertFalse(self.pms.is_data_saver_exempt("com.never.exempt"))

    def test_package_only_in_power_save_is_not_data_saver_exempt(self):
        xml = '<config><allow-in-power-save package="com.only.power" /></config>'
        self.pms.load_sysconfig_xml(xml)
        self.assertTrue(self.pms.is_power_save_exempt("com.only.power"))
        self.assertFalse(self.pms.is_data_saver_exempt("com.only.power"))


if __name__ == "__main__":
    unittest.main()
