"""
Feature 2: Dynamic SemFloatingFeature Stub Tests (Tier 1)
Verifies in-memory synthetic stub for com.samsung.android.feature.SemFloatingFeature
eliminates ART NoClassDefFoundError and answers required feature inquiries.
"""

import unittest
from tests.mock_env.art_classloader import ARTClassLoader, SemFloatingFeature
from tests.mock_env.lsposed_engine import LSPosedEngine


class TestSemFloatingFeatureStub(unittest.TestCase):
    def setUp(self):
        self.class_loader = ARTClassLoader(is_aosp_base=True)
        self.lsposed = LSPosedEngine()
        self.lsposed.apply_app_manager_hooks(self.class_loader)

    def tearDown(self):
        SemFloatingFeature.reset_instance()
        self.lsposed.reset()

    def test_class_loads_without_noclassdeffounderror(self):
        """Authoritative Source: PROJECT.md § Feature 2"""
        cls = self.class_loader.load_class("com.samsung.android.feature.SemFloatingFeature")
        self.assertIsNotNone(cls)
        self.assertIs(cls, SemFloatingFeature)

    def test_get_instance_returns_singleton(self):
        """Authoritative Source: PROJECT.md § Feature 2"""
        inst1 = SemFloatingFeature.getInstance()
        inst2 = SemFloatingFeature.getInstance()
        self.assertIsNotNone(inst1)
        self.assertIs(inst1, inst2)

    def test_link_to_windows_feature_tag_is_true(self):
        """Authoritative Source: PROJECT.md § Feature 2"""
        feature = SemFloatingFeature.getInstance()
        self.assertTrue(feature.getBoolean("SEC_FLOATING_FEATURE_LINK_TO_WINDOWS"))

    def test_brand_name_feature_tag_returns_samsung(self):
        """Authoritative Source: PROJECT.md § Feature 2"""
        feature = SemFloatingFeature.getInstance()
        self.assertEqual(feature.getString("SEC_FLOATING_FEATURE_SETTINGS_CONFIG_BRAND_NAME"), "Samsung")

    def test_default_value_fallback_on_unconfigured_tag(self):
        """Authoritative Source: PROJECT.md § Feature 2"""
        feature = SemFloatingFeature.getInstance()
        self.assertTrue(feature.getBoolean("SEC_FLOATING_FEATURE_NON_EXISTENT", True))
        self.assertFalse(feature.getBoolean("SEC_FLOATING_FEATURE_NON_EXISTENT", False))
        self.assertEqual(feature.getString("NON_EXISTENT_TAG", "default_val"), "default_val")


if __name__ == "__main__":
    unittest.main()
