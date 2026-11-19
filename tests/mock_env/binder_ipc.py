"""
AIDL Binder IPC and ContentProvider Simulation.
Implements IPhoneScreenMirroringService, IInputInjectorService,
CapabilityContentProvider, and CompanionDevicePermissionProvider.
"""

from typing import Dict, Any, Optional, Callable
from .android_runtime import Bundle, Surface, InputEvent, SecurityException
from .display_manager import DisplayManager, VirtualDisplay


class Parcel:
    def __init__(self):
        self._data: list = []
        self._read_pos: int = 0

    def write_string(self, val: str) -> None:
        self._data.append(str(val))

    def read_string(self) -> str:
        if self._read_pos >= len(self._data):
            return ""
        val = str(self._data[self._read_pos])
        self._read_pos += 1
        return val

    def write_int(self, val: int) -> None:
        self._data.append(int(val))

    def read_int(self) -> int:
        if self._read_pos >= len(self._data):
            return 0
        val = int(self._data[self._read_pos])
        self._read_pos += 1
        return val

    def write_bool(self, val: bool) -> None:
        self._data.append(bool(val))

    def read_bool(self) -> bool:
        if self._read_pos >= len(self._data):
            return False
        val = bool(self._data[self._read_pos])
        self._read_pos += 1
        return val


class Binder:
    def __init__(self, descriptor: str):
        self.descriptor = descriptor

    def transact(self, code: int, data: Parcel, reply: Optional[Parcel] = None, flags: int = 0) -> bool:
        return True


class IPhoneScreenMirroringService(Binder):
    """
    AIDL Interface for com.samsung.android.mdx.windowslink.companiondevice.IPhoneScreenMirroringService
    """
    DESCRIPTOR = "com.samsung.android.mdx.windowslink.companiondevice.IPhoneScreenMirroringService"

    def __init__(self, display_manager: DisplayManager):
        super().__init__(self.DESCRIPTOR)
        self.display_manager = display_manager
        self.active_virtual_display: Optional[VirtualDisplay] = None

    def createVirtualDisplay(
        self,
        name: str,
        width: int,
        height: int,
        densityDpi: int,
        flags: int,
        surface: Optional[Surface],
        callback: Optional[Any] = None,
    ) -> int:
        if self.active_virtual_display and self.active_virtual_display.is_valid:
            # Release previous display before creating a new one
            self.active_virtual_display.release()

        vd = self.display_manager.create_virtual_display(
            name=name,
            width=width,
            height=height,
            density_dpi=densityDpi,
            surface=surface,
            flags=flags,
            callback=callback,
        )
        self.active_virtual_display = vd
        return vd.get_display_id()

    def resizeVirtualDisplay(self, width: int, height: int, densityDpi: int) -> None:
        if not self.active_virtual_display or not self.active_virtual_display.is_valid:
            raise RuntimeError("No active VirtualDisplay to resize")
        self.active_virtual_display.resize(width, height, densityDpi)

    def releaseVirtualDisplay(self) -> None:
        if self.active_virtual_display and self.active_virtual_display.is_valid:
            self.active_virtual_display.release()
            self.active_virtual_display = None

    def setSurface(self, surface: Optional[Surface]) -> bool:
        if not self.active_virtual_display or not self.active_virtual_display.is_valid:
            return False
        return self.active_virtual_display.set_surface(surface)


class IInputInjectorService(Binder):
    """
    AIDL Interface for com.samsung.android.mdx.windowslink.interactor.IInputInjectorService
    """
    DESCRIPTOR = "com.samsung.android.mdx.windowslink.interactor.IInputInjectorService"

    def __init__(self, input_manager_service: Any):
        super().__init__(self.DESCRIPTOR)
        self.input_manager_service = input_manager_service
        self._enabled: bool = False

    def enableInputInjector(self) -> None:
        self._enabled = True

    def disableInputInjector(self) -> None:
        self._enabled = False

    def is_enabled(self) -> bool:
        return self._enabled

    def inject(self, event: InputEvent, mode: int) -> bool:
        if not self._enabled:
            return False
        return self.input_manager_service.inject_input_event(event, mode)

    def injectToDisplay(self, event: InputEvent, mode: int, displayId: int) -> bool:
        if not self._enabled:
            return False
        event.set_display_id(displayId)
        return self.input_manager_service.inject_input_event_to_display(event, displayId, mode)


class ContentProviderRegistry:
    """Simulates Android ContentProvider resolution and call methods."""
    def __init__(self):
        self._providers: Dict[str, Callable[[str, Optional[str], Optional[Bundle]], Bundle]] = {}
        self._init_default_providers()

    def register_provider(
        self,
        uri_prefix: str,
        handler: Callable[[str, Optional[str], Optional[Bundle]], Bundle],
    ) -> None:
        self._providers[uri_prefix] = handler

    def _init_default_providers(self) -> None:
        # CapabilityContentProvider
        def capability_handler(method: str, arg: Optional[str], extras: Optional[Bundle]) -> Bundle:
            bundle = Bundle()
            bundle.put_boolean("capability_input_inject", True)
            bundle.put_boolean("capability_companion_device_app_streaming_role", True)
            bundle.put_boolean("capability_pre_granted_permissions", True)
            bundle.put_boolean("capability_screen_mirroring", True)
            bundle.put_boolean("capability_android_apps_on_windows", True)
            bundle.put_boolean("capability_clipboard_redirector", True)
            bundle.put_boolean("capability_device_info", True)
            bundle.put_boolean("capability_audio_streaming", True)
            bundle.put_boolean("capability_black_screen_control", True)
            bundle.put_boolean("capability_virtual_device_manager", True)
            bundle.put_boolean("capability_launch_activity", True)
            bundle.put_boolean("key_is_supported", True)
            bundle.put_string("capability_version", "2.5.0")
            if method and "@" in method:
                sub = method.split("@")[-1]
                bundle.put_boolean(sub, True)
            return bundle

        self.register_provider(
            "content://com.samsung.android.mdx.windowslink.tileservice.CapabilityContentProvider",
            capability_handler,
        )

        # CompanionDevicePermissionProvider
        def permission_handler(method: str, arg: Optional[str], extras: Optional[Bundle]) -> Bundle:
            bundle = Bundle()
            if method in ("checkMediaProjectionPermanentlyGranted", "checkAssociationMade", "requestGrantMediaProjection"):
                bundle.put_boolean("granted", True)
                bundle.put_boolean("keyResult", True)
                bundle.put_string("status", "PERMANENTLY_GRANTED")
            else:
                bundle.put_boolean("granted", False)
                bundle.put_boolean("keyResult", False)
            return bundle

        self.register_provider(
            "content://com.samsung.android.mdx.windowslink.companiondevice.CompanionDevicePermissionProvider",
            permission_handler,
        )

    def call(self, uri: str, method: str, arg: Optional[str] = None, extras: Optional[Bundle] = None) -> Bundle:
        handler = self._providers.get(uri)
        if not handler:
            raise ValueError(f"No ContentProvider registered for URI: {uri}")
        return handler(method, arg, extras)
