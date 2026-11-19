"""
Tier 4: Real-World Application Scenarios
Simulates realistic end-to-end sessions: initial pairing, screen mirror launch,
high-rate mouse gestures, keyboard typing, clipboard sync, background reconnection,
rotation resize, and graceful teardown.
"""

import unittest
from tests.mock_env.android_runtime import (
    Build, Process, Surface, MotionEvent, KeyEvent, Bundle
)
from tests.mock_env.art_classloader import ARTClassLoader, SemFloatingFeature, OneUIStubs
from tests.mock_env.pms_service import PackageManagerService, PackageSignatureChecker
from tests.mock_env.display_manager import DisplayManager
from tests.mock_env.input_manager import InputManagerService, UinputBridge, ClipboardBridge
from tests.mock_env.binder_ipc import (
    IPhoneScreenMirroringService, IInputInjectorService, ContentProviderRegistry
)
from tests.mock_env.lsposed_engine import LSPosedEngine


class TestRealWorldApplicationScenarios(unittest.TestCase):
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

        # Initialize all module hooks
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

    def test_scenario_01_initial_pairing_and_handshake(self):
        """
        Scenario 1: Complete initial pairing & handshake between Windows Phone Link
        and Link to Windows on Xiaomi Mi 9 (Android 16).
        """
        # 1. AppManager process launches
        Process.set_current("com.microsoft.appmanager", 10151)
        self.assertEqual(Build.MANUFACTURER, "samsung")
        self.assertEqual(Build.BRAND, "samsung")

        # 2. In-memory stubs query
        floating = self.class_loader.load_class("com.samsung.android.feature.SemFloatingFeature").getInstance()
        self.assertTrue(floating.getBoolean("SEC_FLOATING_FEATURE_LINK_TO_WINDOWS"))
        version_stub = self.class_loader.load_class("LL0.c")
        self.assertEqual(version_stub.SEM_INT, 3001)

        # 3. Signature verification with MDX service
        sig_result = PackageSignatureChecker.checkSignatures(
            self.pms, "com.microsoft.appmanager", "com.samsung.android.mdx"
        )
        self.assertEqual(sig_result, PackageSignatureChecker.SIGNATURE_MATCH)
        self.assertTrue(PackageSignatureChecker.isShipBuild())

        # 4. Capability verification
        cap_uri = "content://com.samsung.android.mdx.windowslink.tileservice.CapabilityContentProvider"
        caps = self.content_providers.call(cap_uri, "getCapabilities")
        self.assertTrue(caps.get_boolean("capability_companion_device_app_streaming_role"))
        self.assertTrue(caps.get_boolean("capability_input_inject"))

    def test_scenario_02_phone_screen_mirror_session_launch(self):
        """
        Scenario 2: Launch Phone Screen mirror session with headless auto-grant and surface binding.
        """
        Process.set_current("com.samsung.android.mdx", 10150)

        # 1. Check permanent MediaProjection auto-grant
        perm_uri = "content://com.samsung.android.mdx.windowslink.companiondevice.CompanionDevicePermissionProvider"
        granted_bundle = self.content_providers.call(perm_uri, "checkMediaProjectionPermanentlyGranted")
        self.assertTrue(granted_bundle.get_boolean("granted"))

        # 2. Allocate VirtualDisplay pipeline with hardware surface
        surface = Surface(1080, 2340)
        disp_id = self.screen_service.createVirtualDisplay(
            name="PhoneScreenStream",
            width=1080,
            height=2340,
            densityDpi=440,
            flags=DisplayManager.VIRTUAL_DISPLAY_FLAG_PUBLIC,
            surface=surface,
        )
        self.assertGreater(disp_id, 0)
        self.assertEqual(self.screen_service.active_virtual_display.state, "ACTIVE")

        # 3. Stream hardware encoded H.264 video frames
        nal_sps = b"\x00\x00\x00\x01\x67\x42\x00\x1f"
        nal_pps = b"\x00\x00\x00\x01\x68\xce\x3c\x80"
        nal_idr = b"\x00\x00\x00\x01\x65\x88\x84\x00"

        surface.push_frame(nal_sps)
        surface.push_frame(nal_pps)
        surface.push_frame(nal_idr)

        self.assertEqual(len(surface.frames_received), 3)

    def test_scenario_03_high_rate_mouse_drag_and_gestures(self):
        """
        Scenario 3: Fast mouse drag gestures injected into phone display at 60Hz.
        """
        Process.set_current("com.samsung.android.mdx", 10150)
        self.input_service.enableInputInjector()

        surface = Surface(1080, 2340)
        disp_id = self.screen_service.createVirtualDisplay("Stream_03", 1080, 2340, 440, 0, surface)

        # Simulate smooth swipe gesture: Down, 15 Move steps, Up
        timestamp_start = 1000000000
        down_event = MotionEvent(MotionEvent.ACTION_DOWN, x=540.0, y=1800.0, event_time=timestamp_start, down_time=timestamp_start)
        self.assertTrue(self.input_service.injectToDisplay(down_event, mode=0, displayId=disp_id))

        for i in range(1, 16):
            t = timestamp_start + i * 16666  # ~16.6ms intervals (60 FPS)
            move_event = MotionEvent(MotionEvent.ACTION_MOVE, x=540.0, y=1800.0 - i * 50.0, event_time=t, down_time=timestamp_start)
            self.assertTrue(self.input_service.injectToDisplay(move_event, mode=0, displayId=disp_id))

        up_event = MotionEvent(MotionEvent.ACTION_UP, x=540.0, y=1000.0, event_time=timestamp_start + 260000, down_time=timestamp_start)
        self.assertTrue(self.input_service.injectToDisplay(up_event, mode=0, displayId=disp_id))

        self.assertEqual(len(self.ims.injected_events), 17)
        self.assertEqual(self.ims.injected_events[0].action, MotionEvent.ACTION_DOWN)
        self.assertEqual(self.ims.injected_events[-1].action, MotionEvent.ACTION_UP)

    def test_scenario_04_fast_keyboard_typing_and_special_keys(self):
        """
        Scenario 4: Keystrokes sent from PC keyboard, mapped through bridge, and injected cleanly.
        """
        bridge = UinputBridge()
        bridge.open()
        Process.set_current("com.samsung.android.mdx", 10150)
        self.input_service.enableInputInjector()

        keys_to_type = [
            KeyEvent.KEYCODE_A,
            KeyEvent.KEYCODE_B,
            KeyEvent.KEYCODE_C,
            KeyEvent.KEYCODE_DEL,    # Backspace
            KeyEvent.KEYCODE_ENTER,  # Enter
        ]

        for k in keys_to_type:
            bridge.press_key(k)
            ev_down = KeyEvent(action=KeyEvent.ACTION_DOWN, key_code=k)
            self.assertTrue(self.input_service.inject(ev_down, mode=0))

            bridge.release_key(k)
            ev_up = KeyEvent(action=KeyEvent.ACTION_UP, key_code=k)
            self.assertTrue(self.input_service.inject(ev_up, mode=0))

        # Check right-click BACK
        back_code = bridge.handle_mouse_button("BTN_RIGHT", "DOWN")
        self.assertEqual(back_code, KeyEvent.KEYCODE_BACK)
        self.assertTrue(self.input_service.inject(KeyEvent(KeyEvent.ACTION_DOWN, back_code), mode=0))

        bridge.close()
        self.assertFalse(bridge.has_stuck_keys())
        self.assertEqual(len(self.ims.injected_events), len(keys_to_type) * 2 + 1)

    def test_scenario_05_two_way_clipboard_sync_workflow(self):
        """
        Scenario 5: Two-way clipboard synchronization workflow between PC and Phone.
        """
        clipboard = ClipboardBridge()

        # Step 1: Copy link from PC
        pc_text = "https://github.com/AyraHikari/SamsungPhoneLinkPort"
        self.assertTrue(clipboard.set_text(pc_text))
        self.assertEqual(clipboard.get_text(), pc_text)

        # Step 2: Copy code snippet from Phone
        phone_text = "Magisk /system/priv-app/LinkToWindowsService"
        self.assertTrue(clipboard.set_text(phone_text))
        self.assertEqual(clipboard.get_text(), phone_text)

    def test_scenario_06_doze_mode_entry_and_background_reconnection(self):
        """
        Scenario 6: Battery saver / Doze mode resilience and seamless reconnection.
        """
        # Device enters deep sleep / battery saver
        self.assertTrue(self.pms.is_power_save_exempt("com.samsung.android.mdx"))
        self.assertTrue(self.pms.is_data_saver_exempt("com.samsung.android.mdx"))

        # Service reconnects after network hiccup
        perm_uri = "content://com.samsung.android.mdx.windowslink.companiondevice.CompanionDevicePermissionProvider"
        granted = self.content_providers.call(perm_uri, "checkMediaProjectionPermanentlyGranted")
        self.assertTrue(granted.get_boolean("granted"))

        # Re-establish mirror session without user confirmation
        surface = Surface(1080, 2340)
        disp_id = self.screen_service.createVirtualDisplay("ReconnectedStream", 1080, 2340, 440, 0, surface)
        self.assertGreater(disp_id, 0)
        self.assertEqual(self.screen_service.active_virtual_display.state, "ACTIVE")

    def test_scenario_07_device_rotation_and_dynamic_display_resize(self):
        """
        Scenario 7: Rotation from portrait (1080x2340) to landscape (2340x1080).
        """
        surface = Surface(1080, 2340)
        disp_id = self.screen_service.createVirtualDisplay("Stream_07", 1080, 2340, 440, 0, surface)
        self.input_service.enableInputInjector()

        # User launches game -> landscape orientation
        self.screen_service.resizeVirtualDisplay(2340, 1080, 440)
        vd = self.screen_service.active_virtual_display
        self.assertEqual(vd.get_width(), 2340)
        self.assertEqual(vd.get_height(), 1080)
        self.assertEqual(vd.state, "RESIZED")

        # Landscape touch event
        touch = MotionEvent(MotionEvent.ACTION_DOWN, x=2000.0, y=900.0)
        self.assertTrue(self.input_service.injectToDisplay(touch, mode=0, displayId=disp_id))

    def test_scenario_08_graceful_disconnect_and_resource_cleanup(self):
        """
        Scenario 8: User terminates Phone Screen window, clean resource release.
        """
        surface = Surface(1080, 2340)
        disp_id = self.screen_service.createVirtualDisplay("Stream_08", 1080, 2340, 440, 0, surface)
        self.input_service.enableInputInjector()

        # User closes window on PC
        self.screen_service.releaseVirtualDisplay()
        self.input_service.disableInputInjector()

        self.assertFalse(surface.is_valid())
        self.assertIsNone(self.screen_service.active_virtual_display)
        self.assertIsNone(self.dm.get_display(disp_id))

        # Default phone screen (display 0) remains active and healthy
        default_disp = self.dm.get_display(DisplayManager.DEFAULT_DISPLAY if hasattr(DisplayManager, "DEFAULT_DISPLAY") else 0)
        self.assertIsNotNone(default_disp)
        self.assertTrue(default_disp.is_valid)


if __name__ == "__main__":
    unittest.main()
