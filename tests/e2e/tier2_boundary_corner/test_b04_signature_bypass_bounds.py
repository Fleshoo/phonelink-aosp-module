"""
Boundary & Corner Cases: Feature 4 (Signature Validation Bypass)
Tests empty package names, missing packages, empty signature lists,
bypass disablement, and unwhitelisted app denial.
"""

import unittest
from tests.mock_env.pms_service import PackageManagerService, PackageSignatureChecker


class TestSignatureBypassBounds(unittest.TestCase):
    def setUp(self):
        self.pms = PackageManagerService()
        self.pms.register_package(
            "com.microsoft.appmanager", 10151, "/data/app/LinkToWindows", ["ms_cert_sha256"]
        )
        self.pms.register_package(
            "com.samsung.android.mdx", 10150, "/system/priv-app/LinkToWindowsService", ["samsung_cert_sha256"]
        )
        PackageSignatureChecker.enable_bypass()

    def tearDown(self):
        PackageSignatureChecker.disable_bypass()
        self.pms.clear()

    def test_empty_string_package_name_returns_unknown(self):
        res = PackageSignatureChecker.checkSignatures(self.pms, "", "com.samsung.android.mdx")
        self.assertEqual(res, PackageSignatureChecker.SIGNATURE_UNKNOWN_PACKAGE)

    def test_nonexistent_package_returns_unknown(self):
        res = PackageSignatureChecker.checkSignatures(
            self.pms, "com.nonexistent.app", "com.samsung.android.mdx"
        )
        self.assertEqual(res, PackageSignatureChecker.SIGNATURE_UNKNOWN_PACKAGE)

    def test_disable_bypass_restores_signature_mismatch(self):
        PackageSignatureChecker.disable_bypass()
        res = PackageSignatureChecker.checkSignatures(
            self.pms, "com.microsoft.appmanager", "com.samsung.android.mdx"
        )
        self.assertEqual(res, PackageSignatureChecker.SIGNATURE_NO_MATCH)

    def test_is_ship_build_returns_false_when_disabled(self):
        PackageSignatureChecker.disable_bypass()
        self.assertFalse(PackageSignatureChecker.isShipBuild())

    def test_third_party_app_denied_match_even_with_fake_cert(self):
        self.pms.register_package(
            "com.attacker.fake", 10999, "/data/app/fake", ["fake_samsung_cert"]
        )
        res = PackageSignatureChecker.checkSignatures(
            self.pms, "com.attacker.fake", "com.microsoft.appmanager"
        )
        self.assertEqual(res, PackageSignatureChecker.SIGNATURE_NO_MATCH)


if __name__ == "__main__":
    unittest.main()
