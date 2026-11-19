"""
InputManagerService, UinputBridge, and ClipboardBridge Simulation.
Models AOSP event injection, INJECT_EVENTS permission check,
LSPosed system_server hook bypass, and /dev/uinput hardware emulation.
"""

from typing import List, Dict, Optional, Set, Any
from .android_runtime import (
    InputEvent,
    MotionEvent,
    KeyEvent,
    Process,
    SecurityException,
)
from .display_manager import DisplayManager


class InputManagerService:
    INJECT_INPUT_EVENT_MODE_ASYNC = 0
    INJECT_INPUT_EVENT_MODE_WAIT_FOR_RESULT = 1
    INJECT_INPUT_EVENT_MODE_WAIT_FOR_FINISH = 2

    def __init__(self, display_manager: DisplayManager):
        self.display_manager = display_manager
        self.injected_events: List[InputEvent] = []
        # UIDs granted bypass by LSPosed hook in system_server
        self._bypass_uids: Set[int] = set()
        self._bypass_active: bool = False

    def enable_inject_bypass_for_uid(self, uid: int) -> None:
        self._bypass_active = True
        self._bypass_uids.add(uid)

    def disable_inject_bypass(self) -> None:
        self._bypass_active = False
        self._bypass_uids.clear()

    def _check_permission(self) -> None:
        caller_uid = Process.current_uid()
        # System UID 1000 and Root UID 0 always have permission (matching SystemServerHooks.java)
        if caller_uid == 1000 or caller_uid == 0:
            return

        # Check LSPosed system_server hook bypass
        if self._bypass_active and caller_uid in self._bypass_uids:
            return

        raise SecurityException(
            f"UID {caller_uid} does not hold android.permission.INJECT_EVENTS"
        )

    def inject_input_event(self, event: InputEvent, mode: int) -> bool:
        if event is None:
            raise ValueError("InputEvent cannot be None")
        self._check_permission()

        display = self.display_manager.get_display(event.display_id)
        if not display or not display.is_valid:
            return False

        if isinstance(event, MotionEvent):
            if event.get_pointer_count() > 10:
                raise ValueError("Exceeded maximum pointer count of 10")
            # Verify coordinates are non-negative
            if event.x < 0 or event.y < 0:
                return False

        self.injected_events.append(event)
        return True

    def inject_input_event_to_display(self, event: InputEvent, display_id: int, mode: int) -> bool:
        if event is None:
            raise ValueError("InputEvent cannot be None")
        event.set_display_id(display_id)
        return self.inject_input_event(event, mode)

    def clear(self) -> None:
        self.injected_events.clear()


class InputManager:
    _instance: Optional["InputManager"] = None

    def __init__(self, service: InputManagerService):
        self._service = service

    @classmethod
    def getInstance(cls, service: Optional[InputManagerService] = None) -> "InputManager":
        if cls._instance is None:
            if service is None:
                raise RuntimeError("InputManager not initialized with service")
            cls._instance = InputManager(service)
        return cls._instance

    @classmethod
    def set_instance(cls, instance: Optional["InputManager"]) -> None:
        cls._instance = instance

    def injectInputEvent(self, event: InputEvent, mode: int) -> bool:
        return self._service.inject_input_event(event, mode)


class UinputBridge:
    """Simulates Linux /dev/uinput character device and translation layer."""
    MAX_PAYLOAD_SIZE = 1048576  # 1 MB

    def __init__(
        self,
        device_node: str = "/dev/uinput",
        file_mode: int = 0o660,
        selinux_context: str = "u:object_r:uinput_device:s0",
    ):
        self.device_node = device_node
        self.file_mode = file_mode
        self.selinux_context = selinux_context
        self.is_open: bool = False
        self.active_keys: Set[int] = set()
        self.dispatched_mouse_events: List[Dict[str, Any]] = []

    def open(self) -> None:
        # Validate permissions
        if (self.file_mode & 0o660) != 0o660:
            raise PermissionError(f"Permission denied on {self.device_node} (mode: {oct(self.file_mode)})")
        if self.selinux_context != "u:object_r:uinput_device:s0":
            raise PermissionError(f"SELinux policy denied access to {self.device_node}")
        self.is_open = True

    def close(self) -> None:
        # Release all active keys on close to prevent stuck keys
        self.active_keys.clear()
        self.is_open = False

    def handle_mouse_button(self, button_code: str, action: str) -> Optional[int]:
        """
        Translates PC mouse buttons:
        - BTN_LEFT: standard click
        - BTN_RIGHT: Android BACK (KEYCODE_BACK = 4)
        - BTN_MIDDLE: Android HOME (KEYCODE_HOME = 3)
        """
        if not self.is_open:
            raise RuntimeError("uinput device not open")

        self.dispatched_mouse_events.append({"button": button_code, "action": action})

        if button_code == "BTN_RIGHT" and action == "DOWN":
            return KeyEvent.KEYCODE_BACK
        if button_code == "BTN_MIDDLE" and action == "DOWN":
            return KeyEvent.KEYCODE_HOME
        return None

    def press_key(self, key_code: int) -> None:
        if not self.is_open:
            raise RuntimeError("uinput device not open")
        self.active_keys.add(key_code)

    def release_key(self, key_code: int) -> None:
        if not self.is_open:
            raise RuntimeError("uinput device not open")
        self.active_keys.discard(key_code)

    def has_stuck_keys(self) -> bool:
        return len(self.active_keys) > 0


class ClipboardBridge:
    """Simulates two-way clipboard synchronization bridge."""
    MAX_CLIPBOARD_BYTES = 1048576  # 1 MB

    def __init__(self):
        self._clipboard_content: str = ""

    def set_text(self, text: str) -> bool:
        if text is None:
            raise ValueError("Clipboard payload cannot be None")
        payload_bytes = text.encode("utf-8")
        if len(payload_bytes) > self.MAX_CLIPBOARD_BYTES:
            raise ValueError(f"Clipboard payload exceeds limit: {len(payload_bytes)} > {self.MAX_CLIPBOARD_BYTES}")
        self._clipboard_content = text
        return True

    def get_text(self) -> str:
        return self._clipboard_content

    def clear(self) -> None:
        self._clipboard_content = ""
