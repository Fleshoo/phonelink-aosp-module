"""
Boundary & Corner Cases: Feature 2 (SemFloatingFeature Stub)
Tests empty/null keys, non-numeric strings in getInt, non-boolean in getBoolean,
large unicode tags, and dynamic feature modification.
"""

import unittest
from tests.mock_env.art_classloader import SemFloatingFeature


class TestFloatingFeatureBounds(unittest.TestCase):
    def setUp(self):
        self.feature = SemFloatingFeature.getInstance()

    def tearDown(self):
        SemFloatingFeature.reset_instance()

    def test_empty_string_tag_returns_default(self):
        self.assertTrue(self.feature.getBoolean("", True))
        self.assertFalse(self.feature.getBoolean("", False))
        self.assertEqual(self.feature.getString("", "fallback"), "fallback")
        self.assertEqual(self.feature.getInt("", 42), 42)

    def test_none_tag_returns_default(self):
        self.assertTrue(self.feature.getBoolean(None, True))
        self.assertEqual(self.feature.getString(None, "fallback"), "fallback")
        self.assertEqual(self.feature.getInt(None, 99), 99)

    def test_non_numeric_string_value_in_get_int_fallback(self):
        self.feature.set_feature("TAG_WITH_TEXT", "not_a_number")
        # Should gracefully return default without throwing ValueError
        self.assertEqual(self.feature.getInt("TAG_WITH_TEXT", default=123), 123)

    def test_large_unicode_tag_and_value(self):
        long_unicode_tag = "TAG_" + "🚀_тест_" * 50
        unicode_val = "значение_флага_🌟_" * 10
        self.feature.set_feature(long_unicode_tag, unicode_val)
        self.assertEqual(self.feature.getString(long_unicode_tag), unicode_val)

    def test_clear_feature_registry_cleans_entries(self):
        self.feature.clear()
        self.assertEqual(self.feature.getString("SEC_FLOATING_FEATURE_SETTINGS_CONFIG_BRAND_NAME", "def"), "def")


if __name__ == "__main__":
    unittest.main()
