"""
DisplayManager and VirtualDisplay Simulation for Android 16.
Models display hierarchy, VirtualDisplay allocation, surface binding,
and display lifecycle transitions.
"""

from typing import Dict, Optional, Callable, List, Any
from .android_runtime import Surface


class Display:
    DEFAULT_DISPLAY = 0

    def __init__(
        self,
        display_id: int,
        name: str,
        width: int,
        height: int,
        density_dpi: int,
        flags: int = 0,
    ):
        self.display_id = display_id
        self.name = name
        self.width = width
        self.height = height
        self.density_dpi = density_dpi
        self.flags = flags
        self.is_valid: bool = True

    def get_display_id(self) -> int:
        return self.display_id

    def get_width(self) -> int:
        return self.width

    def get_height(self) -> int:
        return self.height

    def get_density_dpi(self) -> int:
        return self.density_dpi


class VirtualDisplay(Display):
    def __init__(
        self,
        display_id: int,
        name: str,
        width: int,
        height: int,
        density_dpi: int,
        surface: Optional[Surface] = None,
        flags: int = 0,
        callback: Optional[Any] = None,
    ):
        super().__init__(display_id, name, width, height, density_dpi, flags)
        self.surface = surface
        self.callback = callback
        self.state: str = "ACTIVE"

    def resize(self, width: int, height: int, density_dpi: int) -> None:
        if width <= 0 or height <= 0 or density_dpi <= 0:
            raise ValueError(f"Invalid dimensions for VirtualDisplay: {width}x{height} @ {density_dpi}dpi")
        if not self.is_valid:
            raise RuntimeError("Cannot resize released VirtualDisplay")
        self.width = width
        self.height = height
        self.density_dpi = density_dpi
        self.state = "RESIZED"

    def set_surface(self, surface: Optional[Surface]) -> bool:
        if not self.is_valid:
            return False
        if surface is not None and not surface.is_valid():
            return False
        self.surface = surface
        return True

    def release(self) -> None:
        if not self.is_valid:
            return
        self.is_valid = False
        self.state = "RELEASED"
        if self.surface:
            self.surface.release()
        if self.callback and hasattr(self.callback, "onStopped"):
            self.callback.onStopped()


class DisplayManager:
    VIRTUAL_DISPLAY_FLAG_PUBLIC = 1 << 0
    VIRTUAL_DISPLAY_FLAG_PRESENTATION = 1 << 1
    VIRTUAL_DISPLAY_FLAG_SECURE = 1 << 2
    VIRTUAL_DISPLAY_FLAG_OWN_CONTENT_ONLY = 1 << 3
    VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR = 1 << 4

    def __init__(self):
        self._displays: Dict[int, Display] = {}
        self._next_display_id: int = 1
        # Pre-seed default phone display (Xiaomi Mi 9: 1080x2340 @ 440dpi)
        self._displays[Display.DEFAULT_DISPLAY] = Display(
            display_id=Display.DEFAULT_DISPLAY,
            name="Built-in Screen",
            width=1080,
            height=2340,
            density_dpi=440,
        )

    def get_display(self, display_id: int) -> Optional[Display]:
        disp = self._displays.get(display_id)
        if disp and disp.is_valid:
            return disp
        return None

    def get_displays(self) -> List[Display]:
        return [d for d in self._displays.values() if d.is_valid]

    def create_virtual_display(
        self,
        name: str,
        width: int,
        height: int,
        density_dpi: int,
        surface: Optional[Surface] = None,
        flags: int = 0,
        callback: Optional[Any] = None,
    ) -> VirtualDisplay:
        if not name:
            raise ValueError("VirtualDisplay name cannot be empty")
        if width <= 0 or height <= 0 or density_dpi <= 0:
            raise ValueError(f"Invalid dimensions: {width}x{height} @ {density_dpi}dpi")
        if surface is not None and not surface.is_valid():
            raise ValueError("Surface provided is invalid or already released")

        disp_id = self._next_display_id
        self._next_display_id += 1

        vd = VirtualDisplay(
            display_id=disp_id,
            name=name,
            width=width,
            height=height,
            density_dpi=density_dpi,
            surface=surface,
            flags=flags,
            callback=callback,
        )
        self._displays[disp_id] = vd
        if callback and hasattr(callback, "onResumed"):
            callback.onResumed()
        return vd

    def release_virtual_display(self, display_id: int) -> bool:
        disp = self._displays.get(display_id)
        if disp and isinstance(disp, VirtualDisplay) and disp.is_valid:
            disp.release()
            return True
        return False

    def reset(self) -> None:
        self._displays.clear()
        self._next_display_id = 1
        self._displays[Display.DEFAULT_DISPLAY] = Display(
            display_id=Display.DEFAULT_DISPLAY,
            name="Built-in Screen",
            width=1080,
            height=2340,
            density_dpi=440,
        )
