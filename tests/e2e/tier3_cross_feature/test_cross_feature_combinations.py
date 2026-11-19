"""
Tier 3: Cross-Feature Combinations Tests
Verifies complex pairwise and multi-feature interactions across device spoofing,
class stubs, priv-app permissions, video streaming, input injection, and hardware bridges.
"""

import unittest
from tests.mock_env.android_runtime import (
    Build, Process, Surface, MotionEvent, KeyEvent, Bundle
)
from tests.mock_env.art_classloader import ARTClassLoader, SemFloatingFeature, OneUIStubs
from tests.mock_env.pms_service import PackageManagerService, PackageSignatureChecker
from tests.mock_env.display_manager import DisplayManager
from tests.mock_env.input_manager import InputManagerService, InputManager, UinputBridge, ClipboardBridge
from tests.mock_env.binder_ipc import (
    IPhoneScreenMirroringService, IInputInjectorService, ContentProviderRegistry
)
from tests.mock_env.lsposed_engine import LSPosedEngine
from tests.mock_env.packaging_validator import PackagingValidator


class TestCrossFeatureCombinations(unittest.TestCase):
    PRIVAPP_XML = """
    <permissions>
        <privapp-permissions package="com.samsung.android.mdx">
            <permission name="android.permission.WRITE_SECURE_SETTINGS"/>
            <permission name="android.permission.INTERACT_ACROSS_USERS"/>
            <permission name="android.permission.BATTERY_STATS"/>
            <permission name="android.permission.CAPTURE_VIDEO_OUTPUT"/>
        </privapp-permissions>
    </permissions>
    """

    SYSCONFIG_XML = """
    <config>
        <allow-in-power-save package="com.samsung.android.mdx" />
        <allow-in-power-save package="com.microsoft.appmanager" />
        <allow-in-data-saver package="com.samsung.android.mdx" />
        <allow-in-data-saver package="com.microsoft.appmanager" />
    </config>
    """

    def setUp(self):
        self.class_loader = ARTClassLoader(is_aosp_base=True)
        self.pms = PackageManagerService()
        self.pms.load_privapp_permissions_xml(self.PRIVAPP_XML)
        self.pms.load_sysconfig_xml(self.SYSCONFIG_XML)

        self.pms.register_package(
            "com.samsung.android.mdx", 10150,
            "/system/priv-app/LinkToWindowsService/LinkToWindowsService.apk",
            signatures=["samsung_sig"],
            requested_permissions=[
                "android.permission.WRITE_SECURE_SETTINGS",
                "android.permission.INTERACT_ACROSS_USERS",
                "android.permission.BATTERY_STATS",
                "android.permission.CAPTURE_VIDEO_OUTPUT",
            ]
        )
        self.pms.register_package(
            "com.microsoft.appmanager", 10151,
            "/data/app/LinkToWindows",
            signatures=["ms_sig"],
            requested_permissions=["android.permission.INTERNET"]
        )

        self.dm = DisplayManager()
        self.ims = InputManagerService(self.dm)
        self.screen_service = IPhoneScreenMirroringService(self.dm)
        self.input_service = IInputInjectorService(self.ims)
        self.content_providers = ContentProviderRegistry()
        self.lsposed = LSPosedEngine()

        # Apply all module hooks
        self.lsposed.apply_app_manager_hooks(self.class_loader)
        self.lsposed.apply_mdx_service_hooks(self.class_loader)
        self.lsposed.apply_system_server_hooks(self.ims, mdx_uid=10150, appmanager_uid=10151)

    def tearDown(self):
        Process.reset()
        self.screen_service.releaseVirtualDisplay()
        self.lsposed.reset()
        self.ims.clear()
        self.pms.clear()
        self.dm.reset()
        Build.reset_defaults()
        SemFloatingFeature.reset_instance()

    def test_comb_01_device_spoofing_and_floating_feature_on_app_startup(self):
        """Combination 1: Device spoofing + SemFloatingFeature stub on app startup"""
        Process.set_current("com.microsoft.appmanager", 10151)
        self.assertEqual(Build.MANUFACTURER, "samsung")
        feature_cls = self.class_loader.load_class("com.samsung.android.feature.SemFloatingFeature")
        inst = feature_cls.getInstance()
        self.assertTrue(inst.getBoolean("SEC_FLOATING_FEATURE_LINK_TO_WINDOWS"))
        self.assertEqual(inst.getString("SEC_FLOATING_FEATURE_SETTINGS_CONFIG_BRAND_NAME"), "Samsung")

    def test_comb_02_oneui_version_stub_and_signature_bypass_handshake(self):
        """Combination 2: One UI version stub + Signature bypass during service binding"""
        Process.set_current("com.microsoft.appmanager", 10151)
        ver_cls = self.class_loader.load_class("LL0.c")
        self.assertEqual(ver_cls.SEM_INT, 3001)

        sig_res = PackageSignatureChecker.checkSignatures(
            self.pms, "com.microsoft.appmanager", "com.samsung.android.mdx"
        )
        self.assertEqual(sig_res, PackageSignatureChecker.SIGNATURE_MATCH)
        self.assertTrue(PackageSignatureChecker.isShipBuild())

    def test_comb_03_privapp_permissions_and_power_exemptions_in_battery_saver(self):
        """Combination 3: Priv-App XML whitelist + System Power exemption in battery saver mode"""
        self.assertTrue(self.pms.check_permission("com.samsung.android.mdx", "android.permission.WRITE_SECURE_SETTINGS"))
        self.assertTrue(self.pms.check_permission("com.samsung.android.mdx", "android.permission.CAPTURE_VIDEO_OUTPUT"))
        self.assertTrue(self.pms.is_power_save_exempt("com.samsung.android.mdx"))
        self.assertTrue(self.pms.is_power_save_exempt("com.microsoft.appmanager"))

    def test_comb_04_mediaprojection_autogrant_and_virtualdisplay_pipeline(self):
        """Combination 4: MediaProjection auto-grant + VirtualDisplay pipeline initialization"""
        perm_uri = "content://com.samsung.android.mdx.windowslink.companiondevice.CompanionDevicePermissionProvider"
        perm_bundle = self.content_providers.call(perm_uri, "checkMediaProjectionPermanentlyGranted")
        self.assertTrue(perm_bundle.get_boolean("granted"))

        surface = Surface(1080, 2340)
        disp_id = self.screen_service.createVirtualDisplay("Stream_04", 1080, 2340, 440, 0, surface)
        self.assertGreater(disp_id, 0)
        self.assertTrue(surface.is_valid())

    def test_comb_05_virtualdisplay_and_touch_input_coordinate_redirection(self):
        """Combination 5: VirtualDisplay pipeline + SemInputInjector touch coordinate mapping"""
        surface = Surface(1080, 2340)
        disp_id = self.screen_service.createVirtualDisplay("Stream_05", 1080, 2340, 440, 0, surface)

        self.input_service.enableInputInjector()
        touch = MotionEvent(action=MotionEvent.ACTION_DOWN, x=540.0, y=1170.0)
        success = self.input_service.injectToDisplay(touch, mode=0, displayId=disp_id)
        self.assertTrue(success)
        self.assertEqual(len(self.ims.injected_events), 1)
        self.assertEqual(self.ims.injected_events[0].display_id, disp_id)

    def test_comb_06_system_server_inject_bypass_and_rapid_pointer_stream(self):
        """Combination 6: system_server INJECT_EVENTS bypass + SemInputInjector pointer event stream"""
        Process.set_current("com.samsung.android.mdx", 10150)
        self.input_service.enableInputInjector()

        # Send 10 consecutive motion events (drag gesture)
        events = []
        events.append(MotionEvent(MotionEvent.ACTION_DOWN, x=100.0, y=100.0, display_id=0))
        for step in range(1, 9):
            events.append(MotionEvent(MotionEvent.ACTION_MOVE, x=100.0 + step * 20, y=100.0 + step * 20, display_id=0))
        events.append(MotionEvent(MotionEvent.ACTION_UP, x=260.0, y=260.0, display_id=0))

        for ev in events:
            res = self.input_service.inject(ev, mode=0)
            self.assertTrue(res)

        self.assertEqual(len(self.ims.injected_events), 10)
        self.assertEqual(self.ims.injected_events[0].action, MotionEvent.ACTION_DOWN)
        self.assertEqual(self.ims.injected_events[-1].action, MotionEvent.ACTION_UP)

    def test_comb_07_keyboard_uinput_bridge_and_keyevent_dispatch_fallback(self):
        """Combination 7: Keyboard /dev/uinput bridge + InputManager KeyEvent injection"""
        bridge = UinputBridge()
        bridge.open()

        Process.set_current("com.samsung.android.mdx", 10150)
        self.input_service.enableInputInjector()

        key_a_down = KeyEvent(action=KeyEvent.ACTION_DOWN, key_code=KeyEvent.KEYCODE_A)
        bridge.press_key(KeyEvent.KEYCODE_A)
        self.assertTrue(self.input_service.inject(key_a_down, mode=0))

        key_a_up = KeyEvent(action=KeyEvent.ACTION_UP, key_code=KeyEvent.KEYCODE_A)
        bridge.release_key(KeyEvent.KEYCODE_A)
        self.assertTrue(self.input_service.inject(key_a_up, mode=0))

        bridge.close()
        self.assertFalse(bridge.has_stuck_keys())
        self.assertEqual(len(self.ims.injected_events), 2)

    def test_comb_08_virtualdisplay_dynamic_resize_and_input_scaling(self):
        """Combination 8: VirtualDisplay dynamic resize + input coordinate scaling"""
        surface = Surface(1080, 2340)
        disp_id = self.screen_service.createVirtualDisplay("Stream_08", 1080, 2340, 440, 0, surface)
        self.input_service.enableInputInjector()

        # Dynamic resize to 720p
        self.screen_service.resizeVirtualDisplay(720, 1560, 320)
        touch_in_bounds = MotionEvent(MotionEvent.ACTION_DOWN, x=700.0, y=1500.0)
        self.assertTrue(self.input_service.injectToDisplay(touch_in_bounds, mode=0, displayId=disp_id))

    def test_comb_09_stream_teardown_and_input_injector_disable_cycle(self):
        """Combination 9: MediaProjection tear-down + Input injector disable cycle"""
        surface = Surface(1080, 2340)
        self.screen_service.createVirtualDisplay("Stream_09", 1080, 2340, 440, 0, surface)
        self.input_service.enableInputInjector()

        # Session terminates
        self.screen_service.releaseVirtualDisplay()
        self.input_service.disableInputInjector()

        self.assertFalse(surface.is_valid())
        touch = MotionEvent(MotionEvent.ACTION_DOWN, x=100.0, y=100.0)
        self.assertFalse(self.input_service.inject(touch, mode=0))

    def test_comb_10_device_spoofing_isolation_during_active_streaming_load(self):
        """Combination 10: Device spoofing integrity during high-load touch injection and video streaming"""
        surface = Surface(1080, 2340)
        self.screen_service.createVirtualDisplay("Stream_10", 1080, 2340, 440, 0, surface)
        surface.push_frame(b"FRAME_DATA_CHUNK")

        # Simultaneously query identity from a non-target package
        Process.set_current("com.google.android.gms", 10050)
        self.assertEqual(Build.MANUFACTURER, "Xiaomi")
        self.assertEqual(Build.MODEL, "MI 9")

        # Query identity from Link to Windows
        Process.set_current("com.microsoft.appmanager", 10151)
        self.assertEqual(Build.MANUFACTURER, "samsung")

    def test_comb_11_uinput_right_click_and_touch_gesture_interleaving(self):
        """Combination 11: Interleaving mouse gestures with right-click BACK and middle-click HOME"""
        bridge = UinputBridge()
        bridge.open()
        Process.set_current("com.samsung.android.mdx", 10150)
        self.input_service.enableInputInjector()

        # Mouse click down and up
        t_down = MotionEvent(MotionEvent.ACTION_DOWN, x=200.0, y=200.0)
        t_up = MotionEvent(MotionEvent.ACTION_UP, x=200.0, y=200.0)
        self.assertTrue(self.input_service.inject(t_down, mode=0))
        self.assertTrue(self.input_service.inject(t_up, mode=0))

        # Mouse right click -> translates to BACK
        key_back = bridge.handle_mouse_button("BTN_RIGHT", "DOWN")
        self.assertEqual(key_back, KeyEvent.KEYCODE_BACK)
        back_ev = KeyEvent(KeyEvent.ACTION_DOWN, key_back)
        self.assertTrue(self.input_service.inject(back_ev, mode=0))

        bridge.close()

    def test_comb_12_two_way_clipboard_sync_with_active_mirroring_session(self):
        """Combination 12: Two-way clipboard synchronization with active mirroring session"""
        surface = Surface(1080, 2340)
        self.screen_service.createVirtualDisplay("Stream_12", 1080, 2340, 440, 0, surface)
        clipboard = ClipboardBridge()

        # Send text from PC to Phone
        clipboard.set_text("Copied from Windows 11")
        self.assertEqual(clipboard.get_text(), "Copied from Windows 11")

        # Update from Phone to PC
        clipboard.set_text("Copied from Android Phone")
        self.assertEqual(clipboard.get_text(), "Copied from Android Phone")

    def test_comb_13_multi_user_interaction_with_privapp_interact_across_users(self):
        """Combination 13: Privapp permission interact-across-users verification"""
        self.assertTrue(
            self.pms.check_permission("com.samsung.android.mdx", "android.permission.INTERACT_ACROSS_USERS")
        )

    def test_comb_14_end_to_end_packaging_spec_matches_runtime_classes(self):
        """Combination 14: Module packaging file tree matches expected runtime stubs"""
        files = [
            "META-INF/com/google/android/update-binary",
            "META-INF/com/google/android/updater-script",
            "module.prop", "customize.sh", "service.sh", "uninstall.sh",
            "system/priv-app/LinkToWindowsService/LinkToWindowsService.apk",
            "system/etc/permissions/privapp-permissions-phonelink.xml",
            "system/etc/permissions/com.samsung.feature.samsung_experience_mobile.xml",
            "system/etc/sysconfig/phonelink-whitelist.xml",
        ]
        valid_magisk, _ = PackagingValidator.validate_magisk_structure(files)
        self.assertTrue(valid_magisk)

        lsposed_files = ["AndroidManifest.xml", "assets/xposed_init", "classes.dex"]
        valid_lsposed, _ = PackagingValidator.validate_lsposed_apk(lsposed_files, "me.phonelink.xposed.XposedInit")
        self.assertTrue(valid_lsposed)


if __name__ == "__main__":
    unittest.main()
