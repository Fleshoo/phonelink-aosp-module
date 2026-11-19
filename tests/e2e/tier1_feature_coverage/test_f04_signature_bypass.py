"""
Feature 4: Signature Validation Bypass Tests (Tier 1)
Verifies signature match spoofing between Link to Windows and MDX service
and ShipBuild certification bypass.
"""

import unittest
from tests.mock_env.pms_service import PackageManagerService, PackageSignatureChecker
from tests.mock_env.lsposed_engine import LSPosedEngine
from tests.mock_env.art_classloader import ARTClassLoader


class TestSignatureValidationBypass(unittest.TestCase):
    def setUp(self):
        self.pms = PackageManagerService()
        self.class_loader = ARTClassLoader(is_aosp_base=True)
        self.lsposed = LSPosedEngine()

        # Register packages with differing certificates
        self.pms.register_package(
            "com.microsoft.appmanager", 10151, "/data/app/LinkToWindows", ["ms_cert_sha256"]
        )
        self.pms.register_package(
            "com.samsung.android.mdx", 10150, "/system/priv-app/LinkToWindowsService", ["samsung_cert_sha256"]
        )
        self.pms.register_package(
            "com.rogue.app", 10200, "/data/app/RogueApp", ["untrusted_cert"]
        )

        # Apply LSPosed hook
        self.lsposed.apply_app_manager_hooks(self.class_loader)

    def tearDown(self):
        self.lsposed.reset()
        self.pms.clear()

    def test_check_signatures_returns_match_for_target_pair(self):
        """Authoritative Source: PROJECT.md § Feature 4"""
        res = PackageSignatureChecker.checkSignatures(
            self.pms, "com.microsoft.appmanager", "com.samsung.android.mdx"
        )
        self.assertEqual(res, PackageSignatureChecker.SIGNATURE_MATCH)

    def test_check_signatures_returns_match_in_reverse_order(self):
        """Authoritative Source: PROJECT.md § Feature 4"""
        res = PackageSignatureChecker.checkSignatures(
            self.pms, "com.samsung.android.mdx", "com.microsoft.appmanager"
        )
        self.assertEqual(res, PackageSignatureChecker.SIGNATURE_MATCH)

    def test_is_ship_build_returns_true_when_hooked(self):
        """Authoritative Source: PROJECT.md § Feature 4"""
        self.assertTrue(PackageSignatureChecker.isShipBuild())

    def test_third_party_app_check_against_mdx_fails(self):
        """Authoritative Source: PROJECT.md § Feature 4 (unapproved packages must not be bypassed)"""
        res = PackageSignatureChecker.checkSignatures(
            self.pms, "com.rogue.app", "com.samsung.android.mdx"
        )
        self.assertEqual(res, PackageSignatureChecker.SIGNATURE_NO_MATCH)

    def test_identical_native_certs_still_match_naturally(self):
        """Authoritative Source: Standard PMS contract"""
        self.pms.register_package("com.legit.app1", 10301, "/data/app/app1", ["shared_cert"])
        self.pms.register_package("com.legit.app2", 10302, "/data/app/app2", ["shared_cert"])
        res = PackageSignatureChecker.checkSignatures(self.pms, "com.legit.app1", "com.legit.app2")
        self.assertEqual(res, PackageSignatureChecker.SIGNATURE_MATCH)


if __name__ == "__main__":
    unittest.main()
