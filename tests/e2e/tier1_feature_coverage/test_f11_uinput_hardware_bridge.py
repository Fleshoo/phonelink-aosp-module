"""
Feature 11: Keyboard & Mouse Hardware Bridge Tests (Tier 1)
Verifies /dev/uinput interaction, mouse button translation (Right->BACK, Middle->HOME),
key tracking, and clipboard synchronization.
"""

import unittest
from tests.mock_env.android_runtime import KeyEvent
from tests.mock_env.input_manager import UinputBridge, ClipboardBridge


class TestKeyboardAndMouseBridge(unittest.TestCase):
    def setUp(self):
        self.bridge = UinputBridge(device_node="/dev/uinput", file_mode=0o660, selinux_context="u:object_r:uinput_device:s0")
        self.clipboard = ClipboardBridge()
        self.bridge.open()

    def tearDown(self):
        self.bridge.close()
        self.clipboard.clear()

    def test_uinput_device_open_success_with_valid_perms(self):
        """Authoritative Source: PROJECT.md § Feature 11"""
        self.assertTrue(self.bridge.is_open)

    def test_right_click_translates_to_key_back(self):
        """Authoritative Source: PROJECT.md § Feature 11 (right-click BACK)"""
        key = self.bridge.handle_mouse_button("BTN_RIGHT", "DOWN")
        self.assertEqual(key, KeyEvent.KEYCODE_BACK)

    def test_middle_click_translates_to_key_home(self):
        """Authoritative Source: PROJECT.md § Feature 11 (middle-click HOME)"""
        key = self.bridge.handle_mouse_button("BTN_MIDDLE", "DOWN")
        self.assertEqual(key, KeyEvent.KEYCODE_HOME)

    def test_key_press_and_release_tracking(self):
        """Authoritative Source: PROJECT.md § Feature 11"""
        self.bridge.press_key(KeyEvent.KEYCODE_A)
        self.assertTrue(self.bridge.has_stuck_keys())
        self.bridge.release_key(KeyEvent.KEYCODE_A)
        self.assertFalse(self.bridge.has_stuck_keys())

    def test_clipboard_text_sync_within_limit(self):
        """Authoritative Source: PROJECT.md § Feature 11"""
        text = "Hello from Windows 11 Phone Link! 🚀"
        res = self.clipboard.set_text(text)
        self.assertTrue(res)
        self.assertEqual(self.clipboard.get_text(), text)

    def test_sepolicy_rule_grants_uinput_device_access(self):
        """Authoritative Source: PROJECT.md § Feature 11 & Milestone 4"""
        import os
        sepolicy_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "magisk_module", "sepolicy.rule")
        with open(sepolicy_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("allow priv_app uinput_device chr_file", content)
        self.assertIn("allow system_app uinput_device chr_file", content)
        self.assertIn("allow platform_app uinput_device chr_file", content)
        self.assertIn("allow priv_app uhid_device chr_file", content)

    def test_scripts_configure_uinput_and_uhid_permissions(self):
        """Authoritative Source: PROJECT.md § Feature 11 & Milestone 4"""
        import os
        base_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "magisk_module")
        with open(os.path.join(base_dir, "post-fs-data.sh"), "r", encoding="utf-8") as f:
            post_fs = f.read()
        self.assertIn("/dev/uinput", post_fs)
        self.assertIn("/dev/uhid", post_fs)

        with open(os.path.join(base_dir, "service.sh"), "r", encoding="utf-8") as f:
            service_sh = f.read()
        self.assertIn("/dev/uinput", service_sh)
        self.assertIn("/dev/uhid", service_sh)
        self.assertIn("magiskpolicy --live \"allow priv_app uinput_device", service_sh)


if __name__ == "__main__":
    unittest.main()
