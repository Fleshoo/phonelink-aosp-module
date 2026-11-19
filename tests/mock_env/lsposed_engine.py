"""
LSPosed Hooking Framework Engine Simulation.
Emulates XposedBridge, hook callbacks, and provides pre-configured hook sets:
AppManagerHooks, MdxServiceHooks, and SystemServerHooks.
"""

from typing import Dict, List, Any, Callable, Optional
from .android_runtime import Build, Process, MotionEvent, KeyEvent
from .art_classloader import ARTClassLoader, SemFloatingFeature, OneUIStubs
from .pms_service import PackageSignatureChecker
from .input_manager import InputManagerService, InputManager


class MethodHookParam:
    def __init__(self, target_obj: Any, method_name: str, args: list):
        self.thisObject = target_obj
        self.methodName = method_name
        self.args = list(args)
        self.result: Any = None
        self.throwable: Optional[Exception] = None
        self.return_early: bool = False

    def setResult(self, res: Any) -> None:
        self.result = res
        self.return_early = True

    def setThrowable(self, t: Exception) -> None:
        self.throwable = t
        self.return_early = True


class MethodHook:
    def beforeHookedMethod(self, param: MethodHookParam) -> None:
        pass

    def afterHookedMethod(self, param: MethodHookParam) -> None:
        pass


class LSPosedEngine:
    def __init__(self):
        self._hooks: Dict[str, List[MethodHook]] = {}
        self.active_modules: List[str] = []

    def hook_method(self, class_name: str, method_name: str, hook: MethodHook) -> None:
        key = f"{class_name}#{method_name}"
        if key not in self._hooks:
            self._hooks[key] = []
        self._hooks[key].append(hook)

    def execute_hooked_call(
        self,
        target_obj: Any,
        class_name: str,
        method_name: str,
        original_fn: Callable,
        *args,
        **kwargs,
    ) -> Any:
        key = f"{class_name}#{method_name}"
        param = MethodHookParam(target_obj, method_name, list(args))

        hooks = self._hooks.get(key, [])
        for h in hooks:
            h.beforeHookedMethod(param)
            if param.return_early:
                if param.throwable:
                    raise param.throwable
                return param.result

        try:
            res = original_fn(*param.args, **kwargs)
            param.result = res
        except Exception as e:
            param.throwable = e

        for h in reversed(hooks):
            h.afterHookedMethod(param)
            if param.throwable:
                raise param.throwable

        return param.result

    def apply_app_manager_hooks(self, class_loader: ARTClassLoader) -> None:
        """AppManagerHooks: device spoofing, SemFloatingFeature stub, signature bypass."""
        # 1. Enable device spoofing for com.microsoft.appmanager
        Build.enable_scoped_spoofing({
            "com.microsoft.appmanager": {
                "MANUFACTURER": "samsung",
                "BRAND": "samsung",
                "MODEL": "SM-G998B",
                "DEVICE": "p3s",
                "PRODUCT": "p3sxx",
            },
            "com.samsung.android.mdx": {
                "MANUFACTURER": "samsung",
                "BRAND": "samsung",
                "MODEL": "SM-G998B",
                "DEVICE": "p3s",
                "PRODUCT": "p3sxx",
            },
        })

        # 2. Register SemFloatingFeature stub in classloader
        class_loader.register_stub("com.samsung.android.feature.SemFloatingFeature", SemFloatingFeature)

        # 3. Enable signature bypass
        PackageSignatureChecker.enable_bypass()
        self.active_modules.append("AppManagerHooks")

    def apply_mdx_service_hooks(self, class_loader: ARTClassLoader) -> None:
        """MdxServiceHooks: One UI stubs (SEM_INT=3001), SemInputInjector redirection."""
        class_loader.register_stub("LL0.c", OneUIStubs)
        class_loader.register_stub("com.samsung.android.os.SemVersion", OneUIStubs)
        class_loader.register_stub("com.samsung.android.desktopmode.DesktopModeManager", OneUIStubs)
        self.active_modules.append("MdxServiceHooks")

    def apply_system_server_hooks(
        self,
        input_manager_service: InputManagerService,
        mdx_uid: int = 10150,
        appmanager_uid: int = 10151,
    ) -> None:
        """SystemServerHooks: bypass INJECT_EVENTS permission check for MDX and AppManager."""
        input_manager_service.enable_inject_bypass_for_uid(mdx_uid)
        input_manager_service.enable_inject_bypass_for_uid(appmanager_uid)
        self.active_modules.append("SystemServerHooks")

    def reset(self) -> None:
        self._hooks.clear()
        self.active_modules.clear()
        Build.disable_scoped_spoofing()
        PackageSignatureChecker.disable_bypass()
