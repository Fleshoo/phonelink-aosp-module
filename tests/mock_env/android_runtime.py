"""
Android 16 (SDK 36) Runtime Simulation.
Models system properties, process execution context, InputEvents, and Surfaces.
"""

from typing import Dict, Any, Optional, List


class SecurityException(Exception):
    pass


class ClassNotFoundException(Exception):
    pass


class NoClassDefFoundError(Exception):
    pass


class Process:
    _current_pkg: str = "android"
    _current_uid: int = 1000

    @classmethod
    def set_current(cls, package_name: str, uid: int) -> None:
        cls._current_pkg = package_name
        cls._current_uid = uid

    @classmethod
    def current_package(cls) -> str:
        return cls._current_pkg

    @classmethod
    def current_uid(cls) -> int:
        return cls._current_uid

    @classmethod
    def reset(cls) -> None:
        cls._current_pkg = "android"
        cls._current_uid = 1000


class _BuildMeta(type):
    """Metaclass to support dynamic process-scoped spoofing for Build fields."""
    _default_manufacturer: str = "Xiaomi"
    _default_model: str = "MI 9"
    _default_brand: str = "Xiaomi"
    _default_device: str = "cepheus"
    _default_product: str = "cepheus"
    _sdk_int: int = 36  # Android 16
    _release: str = "16"

    # Scoped overrides map: package_name -> {field: value}
    _scoped_overrides: Dict[str, Dict[str, str]] = {}
    _spoofing_enabled: bool = False

    @property
    def MANUFACTURER(cls) -> str:
        pkg = Process.current_package()
        if cls._spoofing_enabled and pkg in cls._scoped_overrides:
            return cls._scoped_overrides[pkg].get("MANUFACTURER", cls._default_manufacturer)
        return cls._default_manufacturer

    @MANUFACTURER.setter
    def MANUFACTURER(cls, val: str):
        cls._default_manufacturer = val

    @property
    def MODEL(cls) -> str:
        pkg = Process.current_package()
        if cls._spoofing_enabled and pkg in cls._scoped_overrides:
            return cls._scoped_overrides[pkg].get("MODEL", cls._default_model)
        return cls._default_model

    @MODEL.setter
    def MODEL(cls, val: str):
        cls._default_model = val

    @property
    def BRAND(cls) -> str:
        pkg = Process.current_package()
        if cls._spoofing_enabled and pkg in cls._scoped_overrides:
            return cls._scoped_overrides[pkg].get("BRAND", cls._default_brand)
        return cls._default_brand

    @BRAND.setter
    def BRAND(cls, val: str):
        cls._default_brand = val

    @property
    def DEVICE(cls) -> str:
        pkg = Process.current_package()
        if cls._spoofing_enabled and pkg in cls._scoped_overrides:
            return cls._scoped_overrides[pkg].get("DEVICE", cls._default_device)
        return cls._default_device

    @property
    def PRODUCT(cls) -> str:
        pkg = Process.current_package()
        if cls._spoofing_enabled and pkg in cls._scoped_overrides:
            return cls._scoped_overrides[pkg].get("PRODUCT", cls._default_product)
        return cls._default_product

    @property
    def SDK_INT(cls) -> int:
        return cls._sdk_int


class Build(metaclass=_BuildMeta):
    VERSION_SDK_INT = 36
    VERSION_RELEASE = "16"

    @classmethod
    def enable_scoped_spoofing(cls, scoped_map: Dict[str, Dict[str, str]]) -> None:
        cls._scoped_overrides = scoped_map
        cls._spoofing_enabled = True

    @classmethod
    def disable_scoped_spoofing(cls) -> None:
        cls._scoped_overrides = {}
        cls._spoofing_enabled = False

    @classmethod
    def reset_defaults(cls) -> None:
        cls._default_manufacturer = "Xiaomi"
        cls._default_model = "MI 9"
        cls._default_brand = "Xiaomi"
        cls._default_device = "cepheus"
        cls._default_product = "cepheus"
        cls._scoped_overrides = {}
        cls._spoofing_enabled = False


class ApplicationInfo:
    FLAG_SYSTEM = 1 << 0
    FLAG_PRIVILEGED = 1 << 30

    def __init__(self, package_name: str, uid: int, source_dir: str, flags: int = 0):
        self.packageName = package_name
        self.uid = uid
        self.sourceDir = source_dir
        self.flags = flags

    def is_privileged(self) -> bool:
        return bool(self.flags & self.FLAG_PRIVILEGED) or "/priv-app/" in self.sourceDir


class Bundle:
    def __init__(self, initial_data: Optional[Dict[str, Any]] = None):
        self._data: Dict[str, Any] = dict(initial_data) if initial_data else {}

    def put_boolean(self, key: str, value: bool) -> None:
        self._data[key] = bool(value)

    def get_boolean(self, key: str, default: bool = False) -> bool:
        return self._data.get(key, default)

    def put_string(self, key: str, value: str) -> None:
        self._data[key] = str(value)

    def get_string(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self._data.get(key, default)

    def put_int(self, key: str, value: int) -> None:
        self._data[key] = int(value)

    def get_int(self, key: str, default: int = 0) -> int:
        return self._data.get(key, default)

    def contains_key(self, key: str) -> bool:
        return key in self._data

    def as_dict(self) -> Dict[str, Any]:
        return dict(self._data)


class Surface:
    def __init__(self, width: int = 1080, height: int = 2340):
        self.width = width
        self.height = height
        self._valid: bool = True
        self.frames_received: List[bytes] = []

    def is_valid(self) -> bool:
        return self._valid

    def push_frame(self, frame_data: bytes) -> None:
        if not self._valid:
            raise RuntimeError("Cannot push frame to released Surface")
        self.frames_received.append(frame_data)

    def release(self) -> None:
        self._valid = False


class InputEvent:
    def __init__(self, event_time: int = 0, down_time: int = 0, display_id: int = 0):
        self.event_time = event_time
        self.down_time = down_time
        self.display_id = display_id

    def set_display_id(self, display_id: int) -> None:
        self.display_id = display_id


class MotionEvent(InputEvent):
    ACTION_DOWN = 0
    ACTION_UP = 1
    ACTION_MOVE = 2
    ACTION_CANCEL = 3
    ACTION_SCROLL = 8

    def __init__(
        self,
        action: int,
        x: float,
        y: float,
        display_id: int = 0,
        pointer_id: int = 0,
        event_time: int = 0,
        down_time: int = 0,
        pressure: float = 1.0,
    ):
        super().__init__(event_time=event_time, down_time=down_time, display_id=display_id)
        self.action = action
        self.x = x
        self.y = y
        self.pointer_id = pointer_id
        self.pressure = pressure
        self.pointers: List[Dict[str, Any]] = [{"id": pointer_id, "x": x, "y": y}]

    def add_pointer(self, pointer_id: int, x: float, y: float) -> None:
        self.pointers.append({"id": pointer_id, "x": x, "y": y})

    def get_pointer_count(self) -> int:
        return len(self.pointers)


class KeyEvent(InputEvent):
    ACTION_DOWN = 0
    ACTION_UP = 1

    # Key codes
    KEYCODE_UNKNOWN = 0
    KEYCODE_HOME = 3
    KEYCODE_BACK = 4
    KEYCODE_A = 29
    KEYCODE_B = 30
    KEYCODE_C = 31
    KEYCODE_ENTER = 66
    KEYCODE_DEL = 67  # Backspace
    KEYCODE_ESCAPE = 111
    KEYCODE_CTRL_LEFT = 113
    KEYCODE_META_LEFT = 117

    def __init__(
        self,
        action: int,
        key_code: int,
        display_id: int = 0,
        meta_state: int = 0,
        characters: Optional[str] = None,
        event_time: int = 0,
        down_time: int = 0,
    ):
        super().__init__(event_time=event_time, down_time=down_time, display_id=display_id)
        self.action = action
        self.key_code = key_code
        self.meta_state = meta_state
        self.characters = characters


class Context:
    def __init__(self, package_name: str, uid: int, source_dir: str = "/data/app"):
        self.package_name = package_name
        self.uid = uid
        self.application_info = ApplicationInfo(package_name, uid, source_dir)
        self._services: Dict[str, Any] = {}

    def get_package_name(self) -> str:
        return self.package_name

    def get_application_info(self) -> ApplicationInfo:
        return self.application_info

    def register_system_service(self, name: str, service: Any) -> None:
        self._services[name] = service

    def get_system_service(self, name: str) -> Optional[Any]:
        return self._services.get(name)
