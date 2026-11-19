"""
ART ClassLoader and Samsung One UI Framework Stubs Simulation.
Models class loading, NoClassDefFoundError reproduction on AOSP,
and dynamic injection of SemFloatingFeature and One UI stubs.
"""

from typing import Dict, Any, Type, Optional
from .android_runtime import NoClassDefFoundError, ClassNotFoundException


class SemFloatingFeature:
    """In-memory stub for com.samsung.android.feature.SemFloatingFeature."""
    _instance: Optional["SemFloatingFeature"] = None

    def __init__(self):
        self._features: Dict[str, Any] = {
            "SEC_FLOATING_FEATURE_LINK_TO_WINDOWS": True,
            "SEC_FLOATING_FEATURE_COMMON_SUPPORT_KNOX": False,
            "SEC_FLOATING_FEATURE_SETTINGS_CONFIG_BRAND_NAME": "Samsung",
            "SEC_FLOATING_FEATURE_SIP_CONFIG_PACKAGE_NAME": "com.samsung.android.honeyboard",
            "SEC_FLOATING_FEATURE_AUDIO_SUPPORT_SOUND_ALIVE": True,
        }

    @classmethod
    def getInstance(cls) -> "SemFloatingFeature":
        if cls._instance is None:
            cls._instance = SemFloatingFeature()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    def getBoolean(self, tag: str, default: bool = False) -> bool:
        if not tag:
            return default
        val = self._features.get(tag, default)
        return bool(val)

    def getString(self, tag: str, default: str = "") -> str:
        if not tag:
            return default
        val = self._features.get(tag, default)
        return str(val) if val is not None else default

    def getInt(self, tag: str, default: int = 0) -> int:
        if not tag:
            return default
        val = self._features.get(tag, default)
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    def set_feature(self, tag: str, value: Any) -> None:
        self._features[tag] = value

    def clear(self) -> None:
        self._features.clear()


class OneUIStubs:
    """Stubs for One UI version (SEM_INT) and DeX/SmartClip managers."""
    SEM_INT: int = 3001  # One UI 3.1+ compatibility constant
    ONEUI_VERSION_NAME: str = "6.1"

    @classmethod
    def is_desktop_mode(cls) -> bool:
        # Safe fallback for DeX DesktopModeManager
        return False

    @classmethod
    def is_smart_clip_supported(cls) -> bool:
        # Safe fallback for Samsung SmartClip S-Pen
        return False


class ARTClassLoader:
    """Emulates ART ClassLoader with synthetic stub injection support."""

    def __init__(self, is_aosp_base: bool = True):
        self._is_aosp_base = is_aosp_base
        self._loaded_classes: Dict[str, Type] = {}
        self._stubbed_classes: Dict[str, Type] = {}

    def register_stub(self, class_name: str, class_type: Type) -> None:
        self._stubbed_classes[class_name] = class_type

    def unregister_stub(self, class_name: str) -> None:
        self._stubbed_classes.pop(class_name, None)

    def clear_stubs(self) -> None:
        self._stubbed_classes.clear()

    def load_class(self, class_name: str) -> Type:
        # 1. Check stubbed synthetic classes
        if class_name in self._stubbed_classes:
            return self._stubbed_classes[class_name]

        # 2. Check standard runtime classes
        if class_name == "com.samsung.android.feature.SemFloatingFeature":
            if not self._is_aosp_base:
                return SemFloatingFeature
            raise NoClassDefFoundError(f"NoClassDefFoundError: {class_name}")

        if class_name in ("LL0.c", "com.samsung.android.os.SemVersion"):
            if not self._is_aosp_base:
                return OneUIStubs
            raise NoClassDefFoundError(f"NoClassDefFoundError: {class_name}")

        if class_name == "com.samsung.android.desktopmode.DesktopModeManager":
            if not self._is_aosp_base:
                return OneUIStubs
            raise ClassNotFoundException(f"ClassNotFoundException: {class_name}")

        if class_name in self._loaded_classes:
            return self._loaded_classes[class_name]

        raise ClassNotFoundException(f"ClassNotFoundException: {class_name}")
