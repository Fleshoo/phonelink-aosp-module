"""
Boundary & Corner Cases: Feature 7 (MediaProjection Permanent Auto-Grant)
Tests null/empty method arguments, unknown methods, missing ContentProvider URI,
and bundle integrity under repeated queries.
"""

import unittest
from tests.mock_env.binder_ipc import ContentProviderRegistry
from tests.mock_env.android_runtime import Bundle


class TestMediaProjectionBounds(unittest.TestCase):
    def setUp(self):
        self.registry = ContentProviderRegistry()

    def test_null_method_returns_false_granted(self):
        uri = "content://com.samsung.android.mdx.windowslink.companiondevice.CompanionDevicePermissionProvider"
        res = self.registry.call(uri, method="")
        self.assertFalse(res.get_boolean("granted"))

    def test_unknown_method_does_not_throw(self):
        uri = "content://com.samsung.android.mdx.windowslink.companiondevice.CompanionDevicePermissionProvider"
        res = self.registry.call(uri, method="revokePermission")
        self.assertFalse(res.get_boolean("granted"))

    def test_invalid_scheme_uri_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.registry.call("file:///sdcard/malicious.txt", method="read")

    def test_bundle_data_immutability_across_calls(self):
        uri = "content://com.samsung.android.mdx.windowslink.tileservice.CapabilityContentProvider"
        res1 = self.registry.call(uri, method="get")
        res2 = self.registry.call(uri, method="get")
        self.assertEqual(res1.as_dict(), res2.as_dict())
        self.assertIsNot(res1, res2)

    def test_extras_propagation(self):
        uri = "content://com.samsung.android.mdx.windowslink.tileservice.CapabilityContentProvider"
        extras = Bundle({"request_id": "12345"})
        res = self.registry.call(uri, method="get", extras=extras)
        self.assertTrue(res.get_boolean("capability_screen_mirroring"))


if __name__ == "__main__":
    unittest.main()
