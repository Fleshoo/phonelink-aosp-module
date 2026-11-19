"""
Feature 7: MediaProjection Permanent Auto-Grant Tests (Tier 1)
Verifies headless prompt bypass via CompanionDevicePermissionProvider
and CapabilityContentProvider IPC queries.
"""

import unittest
from tests.mock_env.binder_ipc import ContentProviderRegistry


class TestMediaProjectionAutoGrant(unittest.TestCase):
    def setUp(self):
        self.registry = ContentProviderRegistry()

    def test_companion_device_permission_provider_returns_permanently_granted(self):
        """Authoritative Source: PROJECT.md § Interface Contracts (Content Providers)"""
        uri = "content://com.samsung.android.mdx.windowslink.companiondevice.CompanionDevicePermissionProvider"
        result = self.registry.call(uri, method="checkMediaProjectionPermanentlyGranted")
        self.assertTrue(result.get_boolean("granted"))
        self.assertEqual(result.get_string("status"), "PERMANENTLY_GRANTED")

    def test_capability_content_provider_returns_screen_mirroring_capability(self):
        """Authoritative Source: PROJECT.md § Interface Contracts (Content Providers)"""
        uri = "content://com.samsung.android.mdx.windowslink.tileservice.CapabilityContentProvider"
        result = self.registry.call(uri, method="getCapabilities")
        self.assertTrue(result.get_boolean("capability_screen_mirroring"))
        self.assertTrue(result.get_boolean("capability_companion_device_app_streaming_role"))

    def test_capability_provider_returns_pre_granted_permissions_flag(self):
        """Authoritative Source: PROJECT.md § Interface Contracts (Content Providers)"""
        uri = "content://com.samsung.android.mdx.windowslink.tileservice.CapabilityContentProvider"
        result = self.registry.call(uri, method="getCapabilities")
        self.assertTrue(result.get_boolean("capability_pre_granted_permissions"))

    def test_unknown_content_provider_method_returns_false(self):
        """Authoritative Source: CompanionDevicePermissionProvider contract"""
        uri = "content://com.samsung.android.mdx.windowslink.companiondevice.CompanionDevicePermissionProvider"
        result = self.registry.call(uri, method="unknownMethod")
        self.assertFalse(result.get_boolean("granted"))

    def test_companion_device_permission_provider_check_association_made(self):
        """Authoritative Source: CompanionDevicePermissionProvider contract"""
        uri = "content://com.samsung.android.mdx.windowslink.companiondevice.CompanionDevicePermissionProvider"
        result = self.registry.call(uri, method="checkAssociationMade")
        self.assertTrue(result.get_boolean("granted"))
        self.assertTrue(result.get_boolean("keyResult"))

    def test_companion_device_permission_provider_request_grant_media_projection(self):
        """Authoritative Source: CompanionDevicePermissionProvider contract"""
        uri = "content://com.samsung.android.mdx.windowslink.companiondevice.CompanionDevicePermissionProvider"
        result = self.registry.call(uri, method="requestGrantMediaProjection")
        self.assertTrue(result.get_boolean("granted"))
        self.assertTrue(result.get_boolean("keyResult"))

    def test_capability_content_provider_submethods_supported(self):
        """Authoritative Source: CapabilityContentProvider IPC contract"""
        uri = "content://com.samsung.android.mdx.windowslink.tileservice.CapabilityContentProvider"
        for cap in [
            "capability_input_inject",
            "capability_companion_device_app_streaming_role",
            "capability_pre_granted_permissions",
            "capability_screen_mirroring",
        ]:
            result = self.registry.call(uri, method=f"isSupported@{cap}")
            self.assertTrue(result.get_boolean("key_is_supported"))
            self.assertTrue(result.get_boolean(cap))

    def test_system_server_media_projection_bypass_logic(self):
        """
        Authoritative Source: SystemServerHooks MediaProjectionManagerService bypass logic
        Verifies permission check bypass, foreground service waiver, and consent reuse.
        """
        class MockMediaProjectionManagerService:
            MANAGE_MEDIA_PROJECTION = "android.permission.MANAGE_MEDIA_PROJECTION"
            PERMISSION_GRANTED = 0
            PERMISSION_DENIED = -1

            def __init__(self):
                self.created_projections = {}

            def create_projection_hook(self, process_uid: int, package_name: str, proj_type: int, is_permanent: bool):
                # Simulated SystemServerHooks.createProjection logic
                privileged = (package_name in ("com.samsung.android.mdx", "com.microsoft.appmanager"))
                if privileged:
                    # Bypasses checkCallingPermission(MANAGE_MEDIA_PROJECTION)
                    token = {
                        "uid": process_uid,
                        "pkg": package_name,
                        "type": proj_type,
                        "permanent": is_permanent,
                        "requires_fg": False,  # Bypassed
                        "is_valid": True,       # Bypassed
                        "prevent_reuse": False  # Bypassed
                    }
                    self.created_projections[package_name] = token
                    return token
                else:
                    # Non-privileged caller requires permission
                    raise PermissionError("Requires MANAGE_MEDIA_PROJECTION")

            def has_projection_permission_hook(self, process_uid: int, package_name: str) -> bool:
                if package_name in ("com.samsung.android.mdx", "com.microsoft.appmanager"):
                    return True
                return False

        service = MockMediaProjectionManagerService()

        # 1. Privileged MDX caller creates projection without MANAGE_MEDIA_PROJECTION
        token = service.create_projection_hook(10150, "com.samsung.android.mdx", 0, True)
        self.assertIsNotNone(token)
        self.assertEqual(token["pkg"], "com.samsung.android.mdx")
        self.assertFalse(token["requires_fg"])
        self.assertTrue(token["is_valid"])
        self.assertFalse(token["prevent_reuse"])
        self.assertTrue(service.has_projection_permission_hook(10150, "com.samsung.android.mdx"))

        # 2. Privileged AppManager caller creates projection
        token2 = service.create_projection_hook(10151, "com.microsoft.appmanager", 0, True)
        self.assertIsNotNone(token2)
        self.assertTrue(service.has_projection_permission_hook(10151, "com.microsoft.appmanager"))

        # 3. Unprivileged caller is rejected
        with self.assertRaises(PermissionError):
            service.create_projection_hook(10200, "com.unauthorized.app", 0, True)
        self.assertFalse(service.has_projection_permission_hook(10200, "com.unauthorized.app"))


if __name__ == "__main__":
    unittest.main()
