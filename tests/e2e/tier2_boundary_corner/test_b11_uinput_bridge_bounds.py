"""
Boundary & Corner Cases: Feature 11 (Keyboard & Mouse Hardware Bridge)
Tests permission failures, SELinux policy violations, operations on closed bridge,
stuck key release handling, and clipboard payload limits.
"""

import unittest
from tests.mock_env.android_runtime import KeyEvent
from tests.mock_env.input_manager import UinputBridge, ClipboardBridge


class TestUinputBridgeBounds(unittest.TestCase):
    def setUp(self):
        self.clipboard = ClipboardBridge()

    def tearDown(self):
        self.clipboard.clear()

    def test_invalid_file_mode_raises_permission_error(self):
        # 0o600 lacks group permissions (requires at least 0o660)
        bad_bridge = UinputBridge(device_node="/dev/uinput", file_mode=0o600)
        with self.assertRaises(PermissionError) as ctx:
            bad_bridge.open()
        self.assertIn("Permission denied", str(ctx.exception))

    def test_invalid_selinux_context_raises_permission_error(self):
        bad_bridge = UinputBridge(device_node="/dev/uinput", selinux_context="u:object_r:untrusted_app:s0")
        with self.assertRaises(PermissionError) as ctx:
            bad_bridge.open()
        self.assertIn("SELinux policy denied", str(ctx.exception))

    def test_operations_on_closed_bridge_raise_runtime_error(self):
        bridge = UinputBridge()
        with self.assertRaises(RuntimeError):
            bridge.handle_mouse_button("BTN_RIGHT", "DOWN")
        with self.assertRaises(RuntimeError):
            bridge.press_key(KeyEvent.KEYCODE_A)

    def test_close_clears_stuck_keys_automatically(self):
        bridge = UinputBridge()
        bridge.open()
        bridge.press_key(KeyEvent.KEYCODE_CTRL_LEFT)
        bridge.press_key(KeyEvent.KEYCODE_A)
        self.assertTrue(bridge.has_stuck_keys())

        # Closing session must purge all held keys
        bridge.close()
        self.assertFalse(bridge.has_stuck_keys())

    def test_clipboard_payload_exceeding_1mb_rejected(self):
        oversized_text = "A" * (1024 * 1024 + 10)  # > 1MB
        with self.assertRaises(ValueError) as ctx:
            self.clipboard.set_text(oversized_text)
        self.assertIn("exceeds limit", str(ctx.exception))

    def test_clipboard_none_payload_rejected(self):
        with self.assertRaises(ValueError):
            self.clipboard.set_text(None)


if __name__ == "__main__":
    unittest.main()
