# Project: Microsoft Link to Windows for Xiaomi Mi 9 (Android 16)

## Architecture
The module employs a **Hybrid Architecture (Magisk Module + LSPosed Hooking Module)** to achieve production-grade stability, zero Google Play Integrity / CTS disruption, and seamless screen mirroring with two-way remote control on AOSP Android 16 (Project Infinity X, Xiaomi Mi 9 `cepheus`).

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                           PC: Windows Phone Link                               │
└──────────────────────────────────────┬─────────────────────────────────────────┘
                                       │ WebRTC Video / Touch & Key Input IPC
                                       ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│       Target Device: Xiaomi Mi 9 (cepheus, AOSP Android 16, Root + LSPosed)    │
│                                                                                │
│  [com.microsoft.appmanager] (Play Store target app)                            │
│     ├── Scoped Samsung Device Spoofing (Build.MANUFACTURER = "samsung")        │
│     ├── In-Memory SemFloatingFeature Stub (SEC_FLOATING_FEATURE_COMMON...)     │
│     └── Signature Validation Bypass (PackageSignatureChecker)                  │
│                                                                                │
│  [com.samsung.android.mdx] (Link to Windows Service in /system/priv-app/)      │
│     ├── PhoneScreenMirroringService (VirtualDisplay + MediaCodec H.264 stream) │
│     ├── Auto-Granted MediaProjection Token (headless prompt bypass)            │
│     ├── SemInputInjector -> Redirected to AOSP InputManager.injectInputEvent   │
│     └── SEM_INT / One UI Version Stubs (SEM_INT = 3001)                        │
│                                                                                │
│  [system_server] (Android OS Framework)                                        │
│     ├── LSPosed Hook on InputManagerService: INJECT_EVENTS permission bypass   │
│     ├── LSPosed Hook on MediaProjectionManagerService: permanent token grant   │
│     └── Linux /dev/uinput access & SELinux policies for keyboard typing        │
└────────────────────────────────────────────────────────────────────────────────┘
```

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Process-Scoped Device Spoofing | Spoof `Build.MANUFACTURER = "samsung"` scoped to MS/Samsung apps; preserve global Xiaomi identity | M1 | Survey |
| 2 | Dynamic `SemFloatingFeature` Stub | Supply in-memory synthetic stub for `SemFloatingFeature` to eliminate ART `NoClassDefFoundError` | M1 | Survey |
| 3 | One UI Version & Framework Stubs | Stub `SEM_INT` (`LL0/c`) and DeX/SmartClip references to eliminate fatal binder aborts | M1 | Survey |
| 4 | Signature Validation Bypass | Mock `PackageSignatureChecker.isShipBuild` and PMS signatures for `com.samsung.android.mdx` | M1 | Survey |
| 5 | Priv-App Overlay & Whitelist | Place MDX service in `/system/priv-app/` with `privapp-permissions-phonelink.xml` | M2 | Survey |
| 6 | System Power & Doze Exemptions | Add `sysconfig` allowlists for `<allow-in-power-save>` and `<allow-in-data-saver>` | M2 | Survey |
| 7 | MediaProjection Permanent Auto-Grant | Intercept `initMediaProjection` / PMS to eliminate repeated screen recording prompts | M3 | Survey |
| 8 | Screen Capture & Virtual Display Pipeline | Feed hardware `VirtualDisplay` surface into hardware encoder for PC Phone Screen session | M3 | Survey |
| 9 | Input Redirection in `SemInputInjector` | Redirect `semInjectInputEvent` / `semSetDisplayId` to standard AOSP `InputManager.injectInputEvent` | M4 | Survey |
| 10 | `system_server` `INJECT_EVENTS` Bypass | Allow non-platform-signed MDX service to inject touch and mouse events into display 0 | M4 | Survey |
| 11 | Keyboard & Mouse Hardware Bridge | Configure `/dev/uinput` permissions, SELinux policy, right-click BACK, middle HOME, clipboard | M4 | Survey |
| 12 | Unified Packaging & Delivery | Assemble flashable Magisk zip + LSPosed APK, verification suite, and deployment instructions | M5 | Survey |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | M1: Core Runtime Compatibility & Crash Elimination | LSPosed hooks for device spoofing, `SemFloatingFeature` stub, `SEM_INT` stub, signature bypass | none | **DONE** (DEX 039 32KB compiled via javac/D8, 47 classes, Gate 2 PASSED) |
| 2 | M2: Priv-App Whitelist & System Power Configuration | Magisk overlay (`/system/priv-app/`), `privapp-permissions-*.xml`, `sysconfig` allowlists, `service.sh` | M1 | **DONE** (PhoneLinkMagisk-v2.0.0.zip built, 10 deliverables, Gate PASSED) |
| 3 | M3: Screen Mirroring & Virtual Display Pipeline | Headless `MediaProjection` token acquisition, `VirtualDisplay` lifecycle, video streaming | M1, M2 | **DONE** (DEX 039 54KB compiled via javac/D8, 75 classes, Gate PASSED, 233/233 tests passed) |
| 4 | M4: Remote Input Injection Engine | `system_server` `INJECT_EVENTS` bypass, `SemInputInjector` hook, `/dev/uinput` bridge, mouse/key mapping | M1, M2, M3 | **DONE** (DEX 039 61KB compiled via javac/D8, 82 classes, Gate PASSED, 238/238 tests passed, Magisk zip rebuilt with uinput_device SELinux rules) |
| 5 | M5: Packaging, E2E Test Suite Pass & Adversarial Hardening | Flashable Magisk zip + LSPosed APK build, 100% E2E test pass (Tiers 1-4), Tier 5 hardening, audit | M1..M4 | **DONE** (build.py verified, 349/349 E2E tests pass, DEX 039 87 classes, Clean victory audit) |

## Interface Contracts

### 1. `com.microsoft.appmanager` ↔ `com.samsung.android.mdx` (AIDL & IPC)
- **AIDL Interface `IPhoneScreenMirroringService` (`com.samsung.android.mdx.windowslink.companiondevice.IPhoneScreenMirroringService`)**:
  - `int createVirtualDisplay(String name, int width, int height, int densityDpi, int flags, Surface surface, ICallback callback)`
  - `void resizeVirtualDisplay(int width, int height, int densityDpi)`
  - `void releaseVirtualDisplay()`
  - `boolean setSurface(Surface surface)`
- **AIDL Interface `IInputInjectorService` (`com.samsung.android.mdx.windowslink.interactor.IInputInjectorService`)**:
  - `void enableInputInjector()`
  - `void disableInputInjector()`
  - `boolean inject(InputEvent event, int mode)`
  - `boolean injectToDisplay(InputEvent event, int mode, int displayId)`
- **Content Providers**:
  - `content://com.samsung.android.mdx.windowslink.tileservice.CapabilityContentProvider`
    - Returns `Bundle` with flags: `capability_input_inject=true`, `capability_companion_device_app_streaming_role=true`, `capability_pre_granted_permissions=true`.
  - `content://com.samsung.android.mdx.windowslink.companiondevice.CompanionDevicePermissionProvider`
    - Handles `checkMediaProjectionPermanentlyGranted` -> returns `true`.

### 2. `LSPosed Hook Engine` ↔ `Android System Framework`
- **`InputManagerService.injectInputEventInternal(InputEvent event, int displayId, int mode)`**:
  - Hook intercepts permission check: if caller UID belongs to `com.samsung.android.mdx` or `com.microsoft.appmanager`, bypass `INJECT_EVENTS` permission check and allow event dispatch.
- **`SemInputInjector` (inside `com.samsung.android.mdx`)**:
  - Intercept `injectMotionEvent(MotionEvent event, int mode, int displayId)`: call `event.setDisplayId(displayId)` and `InputManager.getInstance().injectInputEvent(event, mode)`.
  - Intercept `injectKeyEvent(KeyEvent event, int mode, int displayId)`: call `event.setDisplayId(displayId)` and `InputManager.getInstance().injectInputEvent(event, mode)`.
- **`W0/p.initMediaProjection(Context)` (inside `com.samsung.android.mdx`)**:
  - Intercept call: replace missing `semGetMediaProjection()` with valid `MediaProjection` token obtained via standard Android API or synthetic binder token.

## Code Layout
```
phonelink_module/
├── magisk_module/
│   ├── META-INF/com/google/android/
│   │   ├── update-binary
│   │   └── updater-script
│   ├── system/
│   │   ├── priv-app/
│   │   │   └── LinkToWindowsService/
│   │   │       └── LinkToWindowsService.apk
│   │   └── etc/
│   │       ├── permissions/
│   │       │   └── privapp-permissions-phonelink.xml
│   │       └── sysconfig/
│   │           └── phonelink-whitelist.xml
│   ├── customize.sh
│   ├── service.sh
│   ├── post-fs-data.sh
│   └── module.prop
├── lsposed_module/
│   ├── app/
│   │   ├── src/main/
│   │   │   ├── AndroidManifest.xml
│   │   │   ├── assets/xposed_init
│   │   │   └── java/me/phonelink/xposed/
│   │   │       ├── XposedInit.java
│   │   │       ├── hooks/
│   │   │       │   ├── AppManagerHooks.java
│   │   │       │   ├── MdxServiceHooks.java
│   │   │       │   └── SystemServerHooks.java
│   │   │       └── stubs/
│   │   │           └── SemFloatingFeatureStub.java
│   │   └── build.gradle
│   └── build.gradle
├── tests/
│   ├── e2e/
│   │   ├── tier1_feature_coverage/
│   │   ├── tier2_boundary_corner/
│   │   ├── tier3_cross_feature/
│   │   └── tier4_real_world/
│   ├── test_runner.py
│   └── mock_environment.py
├── build.py
├── README.md
└── PROJECT.md
```
