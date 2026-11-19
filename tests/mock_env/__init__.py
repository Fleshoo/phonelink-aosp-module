"""
Mock / Emulated Environment for Android 16 (SDK 36) runtime,
ART classloader, PMS priv-app verification, AIDL binder IPC,
VirtualDisplay lifecycle, and InputManager event injection.
"""

from .android_runtime import (
    Build,
    Process,
    Context,
    ApplicationInfo,
    InputEvent,
    MotionEvent,
    KeyEvent,
    Surface,
    Bundle,
    SecurityException,
    ClassNotFoundException,
    NoClassDefFoundError,
)
from .art_classloader import ARTClassLoader, SemFloatingFeature, OneUIStubs
from .pms_service import PackageManagerService, PackageSignatureChecker
from .binder_ipc import (
    Binder,
    Parcel,
    IPhoneScreenMirroringService,
    IInputInjectorService,
    ContentProviderRegistry,
)
from .display_manager import DisplayManager, Display, VirtualDisplay
from .input_manager import InputManagerService, InputManager, UinputBridge, ClipboardBridge
from .lsposed_engine import LSPosedEngine, MethodHook
from .packaging_validator import PackagingValidator

__all__ = [
    "Build",
    "Process",
    "Context",
    "ApplicationInfo",
    "InputEvent",
    "MotionEvent",
    "KeyEvent",
    "Surface",
    "Bundle",
    "SecurityException",
    "ClassNotFoundException",
    "NoClassDefFoundError",
    "ARTClassLoader",
    "SemFloatingFeature",
    "OneUIStubs",
    "PackageManagerService",
    "PackageSignatureChecker",
    "Binder",
    "Parcel",
    "IPhoneScreenMirroringService",
    "IInputInjectorService",
    "ContentProviderRegistry",
    "DisplayManager",
    "Display",
    "VirtualDisplay",
    "InputManagerService",
    "InputManager",
    "UinputBridge",
    "ClipboardBridge",
    "LSPosedEngine",
    "MethodHook",
    "PackagingValidator",
]
