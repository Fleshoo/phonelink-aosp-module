"""
Feature 6: System Power & Doze Exemptions Tests (Tier 1)
Verifies sysconfig allowlists for allow-in-power-save and allow-in-data-saver
for com.samsung.android.mdx and com.microsoft.appmanager.
"""

import unittest
from tests.mock_env.pms_service import PackageManagerService


class TestPowerAndDozeExemptions(unittest.TestCase):
    SYSCONFIG_XML = """
    <config>
        <allow-in-power-save package="com.samsung.android.mdx" />
        <allow-in-power-save package="com.microsoft.appmanager" />
        <allow-in-data-saver package="com.samsung.android.mdx" />
        <allow-in-data-saver package="com.microsoft.appmanager" />
    </config>
    """

    def setUp(self):
        self.pms = PackageManagerService()
        self.pms.load_sysconfig_xml(self.SYSCONFIG_XML)

    def tearDown(self):
        self.pms.clear()

    def test_sysconfig_xml_grants_power_save_to_mdx(self):
        """Authoritative Source: PROJECT.md § Feature 6"""
        self.assertTrue(self.pms.is_power_save_exempt("com.samsung.android.mdx"))

    def test_sysconfig_xml_grants_power_save_to_appmanager(self):
        """Authoritative Source: PROJECT.md § Feature 6"""
        self.assertTrue(self.pms.is_power_save_exempt("com.microsoft.appmanager"))

    def test_sysconfig_xml_grants_data_saver_to_mdx(self):
        """Authoritative Source: PROJECT.md § Feature 6"""
        self.assertTrue(self.pms.is_data_saver_exempt("com.samsung.android.mdx"))

    def test_sysconfig_xml_grants_data_saver_to_appmanager(self):
        """Authoritative Source: PROJECT.md § Feature 6"""
        self.assertTrue(self.pms.is_data_saver_exempt("com.microsoft.appmanager"))

    def test_unwhitelisted_app_not_power_exempt(self):
        """Authoritative Source: PROJECT.md § Feature 6"""
        self.assertFalse(self.pms.is_power_save_exempt("com.random.app"))
        self.assertFalse(self.pms.is_data_saver_exempt("com.random.app"))


if __name__ == "__main__":
    unittest.main()
