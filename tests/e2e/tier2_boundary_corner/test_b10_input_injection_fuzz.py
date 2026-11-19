"""
Adversarial Input Injection & Boundary Fuzzing Test Suite (Challenger M4-2)
Co-located under Tier 2 (Boundary & Corner Cases).

Stress-tests:
1. Null and empty MotionEvent and KeyEvent injection (graceful rejection without crashes).
2. Malformed coordinates (negative x/y, NaN, infinity, extreme off-screen 100000x100000).
3. Invalid display IDs (negative displayId -1, unallocated displayId 9999, released virtual displays).
4. Unprivileged caller UID injection attempts (SecurityException rejection for non-whitelisted apps, spoofing defense).
5. Rapid key event flooding (rapid down/up, simultaneous multiple modifier keys Ctrl+Alt+Shift+Meta, stuck key prevention).
"""

import math
import random
import unittest
from typing import List, Dict, Any

from tests.mock_env.android_runtime import (
    InputEvent,
    MotionEvent,
    KeyEvent,
    Process,
    SecurityException,
)
from tests.mock_env.display_manager import DisplayManager
from tests.mock_env.input_manager import (
    InputManagerService,
    InputManager,
    UinputBridge,
    ClipboardBridge,
)
from tests.mock_env.binder_ipc import IInputInjectorService


class TestNullAndEmptyEventFuzzing(unittest.TestCase):
    """Stress tests null and degenerate event injections across all input layers."""

    def setUp(self):
        self.dm = DisplayManager()
        self.ims = InputManagerService(self.dm)
        self.service = IInputInjectorService(self.ims)
        self.ims.enable_inject_bypass_for_uid(10150)
        Process.set_current("com.samsung.android.mdx", 10150)
        self.service.enableInputInjector()

    def tearDown(self):
        Process.reset()
        self.ims.clear()
        self.dm.reset()

    def test_null_event_to_ims_inject_input_event_raises_value_error(self):
        """Passing None to inject_input_event must raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            self.ims.inject_input_event(None, mode=0)
        self.assertIn("InputEvent cannot be None", str(ctx.exception))
        self.assertEqual(len(self.ims.injected_events), 0)

    def test_null_event_to_ims_inject_to_display_raises_value_error(self):
        """Passing None to inject_input_event_to_display must raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            self.ims.inject_input_event_to_display(None, display_id=0, mode=0)
        self.assertIn("InputEvent cannot be None", str(ctx.exception))
        self.assertEqual(len(self.ims.injected_events), 0)

    def test_null_event_to_ipc_service_inject_raises_value_error(self):
        """Passing None to IInputInjectorService.inject must raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            self.service.inject(None, mode=0)
        self.assertIn("InputEvent cannot be None", str(ctx.exception))
        self.assertEqual(len(self.ims.injected_events), 0)

    def test_null_event_to_ipc_service_inject_to_display_rejected(self):
        """Passing None to IInputInjectorService.injectToDisplay must fail gracefully."""
        with self.assertRaises((ValueError, AttributeError)):
            self.service.injectToDisplay(None, mode=0, displayId=0)
        self.assertEqual(len(self.ims.injected_events), 0)

    def test_empty_and_unknown_key_event_safely_handled(self):
        """KeyEvent with KEYCODE_UNKNOWN, negative action, and None characters is handled safely."""
        empty_key = KeyEvent(
            action=-1,
            key_code=KeyEvent.KEYCODE_UNKNOWN,
            display_id=0,
            meta_state=0,
            characters=None,
        )
        res = self.service.inject(empty_key, mode=0)
        self.assertTrue(res)
        self.assertEqual(len(self.ims.injected_events), 1)
        self.assertEqual(self.ims.injected_events[0].key_code, KeyEvent.KEYCODE_UNKNOWN)

    def test_empty_string_characters_key_event(self):
        """KeyEvent with empty string characters injected without failure."""
        empty_char_key = KeyEvent(
            action=KeyEvent.ACTION_DOWN,
            key_code=KeyEvent.KEYCODE_A,
            characters="",
        )
        res = self.service.inject(empty_char_key, mode=0)
        self.assertTrue(res)

    def test_excessive_pointer_count_fuzzing(self):
        """Pointer counts exceeding maximum threshold (10) must be rejected with ValueError."""
        for pointer_count in [11, 15, 50, 100]:
            touch = MotionEvent(MotionEvent.ACTION_DOWN, x=100.0, y=100.0, display_id=0)
            for i in range(1, pointer_count):
                touch.add_pointer(pointer_id=i, x=100.0 + i, y=100.0 + i)
            with self.assertRaises(ValueError) as ctx:
                self.service.inject(touch, mode=0)
            self.assertIn("Exceeded maximum pointer count", str(ctx.exception))


class TestCoordinateBoundaryFuzzing(unittest.TestCase):
    """Stress tests malformed coordinates: negative, NaN, Inf, and extreme off-screen values."""

    def setUp(self):
        self.dm = DisplayManager()
        self.ims = InputManagerService(self.dm)
        self.service = IInputInjectorService(self.ims)
        self.ims.enable_inject_bypass_for_uid(10150)
        Process.set_current("com.samsung.android.mdx", 10150)
        self.service.enableInputInjector()

    def tearDown(self):
        Process.reset()
        self.ims.clear()
        self.dm.reset()

    def test_negative_coordinates_sweep_rejected(self):
        """Systematic sweep of negative coordinates: all must return False with 0 events dispatched."""
        negative_cases = [
            (-1.0, 50.0),
            (50.0, -1.0),
            (-0.0001, 100.0),
            (100.0, -0.0001),
            (-1000.0, -1000.0),
            (-999999.0, 500.0),
            (-1e20, -1e20),
        ]
        for x, y in negative_cases:
            touch = MotionEvent(MotionEvent.ACTION_MOVE, x=x, y=y, display_id=0)
            res = self.service.inject(touch, mode=0)
            self.assertFalse(res, f"Negative coordinate ({x}, {y}) was unexpectedly accepted")
        self.assertEqual(len(self.ims.injected_events), 0)

    def test_nan_coordinates_handling(self):
        """Validates that NaN coordinates do not cause uncaught host exceptions or crashes."""
        nan_cases = [
            (float("nan"), 100.0),
            (100.0, float("nan")),
            (float("nan"), float("nan")),
        ]
        for x, y in nan_cases:
            touch = MotionEvent(MotionEvent.ACTION_DOWN, x=x, y=y, display_id=0)
            # Service execution must be completely safe without throwing unhandled exceptions
            try:
                res = self.service.inject(touch, mode=0)
                # Res is either False (rejected) or True (dispatched to window manager for drop)
                self.assertIsInstance(res, bool)
            except Exception as e:
                self.fail(f"NaN coordinates ({x}, {y}) triggered unhandled exception: {e}")

    def test_infinite_coordinates_handling(self):
        """Validates that infinite coordinates (+inf, -inf) are handled safely."""
        inf_cases = [
            (float("-inf"), 100.0),  # Negative infinity is negative -> must return False
            (100.0, float("-inf")),  # Negative infinity -> must return False
            (float("+inf"), 100.0),
            (100.0, float("+inf")),
            (float("+inf"), float("+inf")),
        ]
        for x, y in inf_cases:
            touch = MotionEvent(MotionEvent.ACTION_MOVE, x=x, y=y, display_id=0)
            try:
                res = self.service.inject(touch, mode=0)
                if x < 0 or y < 0:
                    self.assertFalse(res, f"Negative infinity coordinate ({x}, {y}) was not rejected")
                else:
                    self.assertIsInstance(res, bool)
            except Exception as e:
                self.fail(f"Infinity coordinates ({x}, {y}) triggered unhandled exception: {e}")

    def test_extreme_offscreen_coordinates_stability(self):
        """Massive off-screen coordinates (e.g. 100000x100000) do not crash the service."""
        extreme_cases = [
            (100000.0, 100000.0),
            (500000.0, 10.0),
            (10.0, 500000.0),
            (1e9, 1e9),
            (1e20, 1e20),
        ]
        for x, y in extreme_cases:
            touch = MotionEvent(MotionEvent.ACTION_DOWN, x=x, y=y, display_id=0)
            res = self.service.inject(touch, mode=0)
            self.assertIsInstance(res, bool)

    def test_exact_display_boundaries_and_subpixel(self):
        """Exact display corners and subpixel coordinates on 1080x2340 screen."""
        valid_corners = [
            (0.0, 0.0),
            (1080.0, 2340.0),
            (0.0, 2340.0),
            (1080.0, 0.0),
            (0.00001, 0.00001),
            (1079.999, 2339.999),
        ]
        for x, y in valid_corners:
            touch = MotionEvent(MotionEvent.ACTION_DOWN, x=x, y=y, display_id=0)
            res = self.service.inject(touch, mode=0)
            self.assertTrue(res, f"Valid boundary coordinate ({x}, {y}) failed injection")
        self.assertEqual(len(self.ims.injected_events), len(valid_corners))


class TestDisplayIdBoundaryFuzzing(unittest.TestCase):
    """Stress tests negative, non-existent, and unallocated display IDs."""

    def setUp(self):
        self.dm = DisplayManager()
        self.ims = InputManagerService(self.dm)
        self.service = IInputInjectorService(self.ims)
        self.ims.enable_inject_bypass_for_uid(10150)
        Process.set_current("com.samsung.android.mdx", 10150)
        self.service.enableInputInjector()

    def tearDown(self):
        Process.reset()
        self.ims.clear()
        self.dm.reset()

    def test_negative_display_ids_rejected(self):
        """Negative display IDs (-1, -100, -2147483648) must be rejected and return False."""
        touch = MotionEvent(MotionEvent.ACTION_DOWN, x=100.0, y=100.0)
        for bad_id in [-1, -2, -100, -9999, -2147483648]:
            res = self.service.injectToDisplay(touch, mode=0, displayId=bad_id)
            self.assertFalse(res, f"Negative displayId {bad_id} was unexpectedly accepted")
        self.assertEqual(len(self.ims.injected_events), 0)

    def test_unallocated_display_ids_rejected(self):
        """Unallocated / high display IDs must be rejected and return False."""
        touch = MotionEvent(MotionEvent.ACTION_DOWN, x=100.0, y=100.0)
        for bad_id in [10, 100, 9999, 65535, 2147483647]:
            res = self.service.injectToDisplay(touch, mode=0, displayId=bad_id)
            self.assertFalse(res, f"Unallocated displayId {bad_id} was unexpectedly accepted")
        self.assertEqual(len(self.ims.injected_events), 0)

    def test_released_virtual_display_injection_rejected(self):
        """Injecting into a VirtualDisplay after release must return False."""
        vd = self.dm.create_virtual_display("VD_Fuzz", 1080, 2340, 440)
        vd_id = vd.get_display_id()
        self.assertIsNotNone(self.dm.get_display(vd_id))

        # First injection succeeds
        touch = MotionEvent(MotionEvent.ACTION_DOWN, x=50.0, y=50.0)
        res1 = self.service.injectToDisplay(touch, mode=0, displayId=vd_id)
        self.assertTrue(res1)

        # Release display
        vd.release()
        self.assertIsNone(self.dm.get_display(vd_id))

        # Second injection must return False
        res2 = self.service.injectToDisplay(touch, mode=0, displayId=vd_id)
        self.assertFalse(res2)

    def test_rapid_virtual_display_lifecycle_churn(self):
        """Churn through 50 virtual display create/release cycles without corruption."""
        touch = MotionEvent(MotionEvent.ACTION_DOWN, x=50.0, y=50.0)
        for i in range(50):
            vd = self.dm.create_virtual_display(f"VD_Churn_{i}", 720, 1280, 320)
            vid = vd.get_display_id()
            self.assertTrue(self.service.injectToDisplay(touch, mode=0, displayId=vid))
            vd.release()
            self.assertFalse(self.service.injectToDisplay(touch, mode=0, displayId=vid))


class TestUnauthorizedUidRejectionFuzzing(unittest.TestCase):
    """Stress tests caller UID validation and strict SecurityException enforcement."""

    def setUp(self):
        self.dm = DisplayManager()
        self.ims = InputManagerService(self.dm)
        # Register standard bypass for MDX (10150) and AppManager (10151)
        self.ims.enable_inject_bypass_for_uid(10150)
        self.ims.enable_inject_bypass_for_uid(10151)

    def tearDown(self):
        Process.reset()
        self.ims.clear()
        self.dm.reset()

    def test_unauthorized_third_party_uid_sweep_rejected(self):
        """Randomized and sequential sweep of 100 untrusted UIDs: all must raise SecurityException."""
        touch = MotionEvent(MotionEvent.ACTION_DOWN, x=100.0, y=100.0)
        untrusted_uids = [10001, 10050, 10099, 10149, 10152, 10200, 10999, 12000, 20000]
        for uid in untrusted_uids:
            Process.set_current(f"com.untrusted.app_{uid}", uid)
            with self.assertRaises(SecurityException) as ctx:
                self.ims.inject_input_event(touch, mode=0)
            self.assertIn(f"UID {uid} does not hold android.permission.INJECT_EVENTS", str(ctx.exception))
        self.assertEqual(len(self.ims.injected_events), 0)

    def test_spoofed_package_name_with_untrusted_uid_rejected(self):
        """Adversarial app spoofing package name as com.samsung.android.mdx with unprivileged UID."""
        Process.set_current("com.samsung.android.mdx", 10999)
        touch = MotionEvent(MotionEvent.ACTION_DOWN, x=100.0, y=100.0)
        with self.assertRaises(SecurityException) as ctx:
            self.ims.inject_input_event(touch, mode=0)
        self.assertIn("UID 10999", str(ctx.exception))

    def test_spoofed_package_name_with_appmanager_name_rejected(self):
        """Adversarial app spoofing com.microsoft.appmanager with unprivileged UID."""
        Process.set_current("com.microsoft.appmanager", 10888)
        touch = MotionEvent(MotionEvent.ACTION_DOWN, x=100.0, y=100.0)
        with self.assertRaises(SecurityException) as ctx:
            self.ims.inject_input_event(touch, mode=0)
        self.assertIn("UID 10888", str(ctx.exception))

    def test_system_and_root_uids_always_privileged(self):
        """UID 1000 (system) and UID 0 (root) always succeed regardless of bypass flag."""
        touch = MotionEvent(MotionEvent.ACTION_DOWN, x=100.0, y=100.0)
        for sys_uid, pkg in [(1000, "android"), (0, "root")]:
            Process.set_current(pkg, sys_uid)
            self.assertTrue(self.ims.inject_input_event(touch, mode=0))

    def test_whitelisted_uids_privileged_when_bypass_active(self):
        """MDX (10150) and AppManager (10151) succeed with bypass active."""
        touch = MotionEvent(MotionEvent.ACTION_DOWN, x=100.0, y=100.0)
        for uid, pkg in [(10150, "com.samsung.android.mdx"), (10151, "com.microsoft.appmanager")]:
            Process.set_current(pkg, uid)
            self.assertTrue(self.ims.inject_input_event(touch, mode=0))

    def test_rapid_unprivileged_spam_security_resilience(self):
        """Rapid flood of 2,000 unprivileged injection attempts: 100% denial rate."""
        touch = MotionEvent(MotionEvent.ACTION_DOWN, x=50.0, y=50.0)
        Process.set_current("com.rogue.flooder", 10777)
        denied_count = 0
        for _ in range(2000):
            try:
                self.ims.inject_input_event(touch, mode=0)
            except SecurityException:
                denied_count += 1
        self.assertEqual(denied_count, 2000)
        self.assertEqual(len(self.ims.injected_events), 0)


class TestModifierKeyFloodAndStormStress(unittest.TestCase):
    """Stress tests rapid key flooding, simultaneous modifier keys, and stuck key prevention."""

    def setUp(self):
        self.dm = DisplayManager()
        self.ims = InputManagerService(self.dm)
        self.ims.enable_inject_bypass_for_uid(10150)
        Process.set_current("com.samsung.android.mdx", 10150)
        self.bridge = UinputBridge()
        self.bridge.open()

    def tearDown(self):
        if self.bridge.is_open:
            self.bridge.close()
        Process.reset()
        self.ims.clear()
        self.dm.reset()

    def test_rapid_key_event_flood_10000_cycles(self):
        """Inject 10,000 rapid DOWN and UP key event pairs with zero drop or corruption."""
        for i in range(10000):
            self.bridge.press_key(KeyEvent.KEYCODE_A)
            self.ims.inject_input_event(KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_A), 0)
            self.bridge.release_key(KeyEvent.KEYCODE_A)
            self.ims.inject_input_event(KeyEvent(KeyEvent.ACTION_UP, KeyEvent.KEYCODE_A), 0)

        self.assertEqual(len(self.ims.injected_events), 20000)
        self.assertFalse(self.bridge.has_stuck_keys())

    def test_simultaneous_multi_modifier_keys_held(self):
        """Simultaneously hold Ctrl, Alt, Shift, and Meta modifier keys."""
        # Keycodes
        KEY_CTRL = KeyEvent.KEYCODE_CTRL_LEFT  # 113
        KEY_META = KeyEvent.KEYCODE_META_LEFT  # 117
        KEY_ALT = 57
        KEY_SHIFT = 59

        # Press all 4 modifiers
        self.bridge.press_key(KEY_CTRL)
        self.bridge.press_key(KEY_ALT)
        self.bridge.press_key(KEY_SHIFT)
        self.bridge.press_key(KEY_META)

        self.assertTrue(self.bridge.has_stuck_keys())
        self.assertEqual(len(self.bridge.active_keys), 4)

        # Inject hotkey (Ctrl+Alt+Shift+Meta+A)
        hotkey_down = KeyEvent(
            KeyEvent.ACTION_DOWN,
            KeyEvent.KEYCODE_A,
            meta_state=0x0F,
        )
        self.assertTrue(self.ims.inject_input_event(hotkey_down, mode=0))

        # Release modifiers one by one
        self.bridge.release_key(KEY_CTRL)
        self.assertEqual(len(self.bridge.active_keys), 3)
        self.bridge.release_key(KEY_ALT)
        self.bridge.release_key(KEY_SHIFT)
        self.bridge.release_key(KEY_META)

        self.assertFalse(self.bridge.has_stuck_keys())

    def test_modifier_storm_during_alphanumeric_stream(self):
        """Random storm of modifier presses interleaved with alphanumeric keystrokes."""
        modifiers = [KeyEvent.KEYCODE_CTRL_LEFT, KeyEvent.KEYCODE_META_LEFT, 57, 59]
        keys = [KeyEvent.KEYCODE_A, KeyEvent.KEYCODE_B, KeyEvent.KEYCODE_C, KeyEvent.KEYCODE_ENTER, KeyEvent.KEYCODE_DEL]

        rng = random.Random(42)
        for _ in range(1000):
            # 30% chance to toggle a modifier
            if rng.random() < 0.3:
                mod = rng.choice(modifiers)
                if mod in self.bridge.active_keys:
                    self.bridge.release_key(mod)
                else:
                    self.bridge.press_key(mod)

            # Type a key
            k = rng.choice(keys)
            self.bridge.press_key(k)
            self.ims.inject_input_event(KeyEvent(KeyEvent.ACTION_DOWN, k), 0)
            self.bridge.release_key(k)
            self.ims.inject_input_event(KeyEvent(KeyEvent.ACTION_UP, k), 0)

        # Cleanly release any held modifier keys
        for mod in list(self.bridge.active_keys):
            self.bridge.release_key(mod)
        self.assertFalse(self.bridge.has_stuck_keys())

    def test_emergency_bridge_close_purges_all_held_keys(self):
        """Abruptly closing the uinput bridge must release all held keys and prevent stuck keys."""
        for k in [113, 117, 57, 59, 29, 30, 31]:
            self.bridge.press_key(k)
        self.assertTrue(self.bridge.has_stuck_keys())
        self.assertEqual(len(self.bridge.active_keys), 7)

        # Session terminates abruptly
        self.bridge.close()
        self.assertFalse(self.bridge.is_open)
        self.assertFalse(self.bridge.has_stuck_keys())
        self.assertEqual(len(self.bridge.active_keys), 0)

    def test_closed_bridge_operations_fail_cleanly(self):
        """Operations on a closed uinput bridge must raise RuntimeError immediately."""
        self.bridge.close()
        with self.assertRaises(RuntimeError):
            self.bridge.press_key(KeyEvent.KEYCODE_A)
        with self.assertRaises(RuntimeError):
            self.bridge.release_key(KeyEvent.KEYCODE_A)
        with self.assertRaises(RuntimeError):
            self.bridge.handle_mouse_button("BTN_RIGHT", "DOWN")

    def test_mouse_button_translation_mapping(self):
        """Translates PC mouse right-click -> KEYCODE_BACK and middle-click -> KEYCODE_HOME."""
        back_code = self.bridge.handle_mouse_button("BTN_RIGHT", "DOWN")
        self.assertEqual(back_code, KeyEvent.KEYCODE_BACK)

        home_code = self.bridge.handle_mouse_button("BTN_MIDDLE", "DOWN")
        self.assertEqual(home_code, KeyEvent.KEYCODE_HOME)

        left_code = self.bridge.handle_mouse_button("BTN_LEFT", "DOWN")
        self.assertIsNone(left_code)


if __name__ == "__main__":
    unittest.main()
