# Test Infrastructure: Microsoft Link to Windows for Xiaomi Mi 9 (Android 16)

## 1. Overview
This document describes the testing infrastructure, mock environment architecture, test methodology, and test execution framework for the **Phone Link Module** targeting Xiaomi Mi 9 (`cepheus`) running AOSP Project Infinity X on Android 16 (SDK 36).

The test suite is built on an **opaque-box methodology** using:
- **Category-Partitioning**: Isolates each feature into input categories and choices.
- **Boundary Value Analysis (BVA)**: Tests minimum, maximum, empty, null, and out-of-range boundaries.
- **Pairwise Combinatorial Testing**: Verifies multi-component interactions across device spoofing, class stubs, priv-app permissions, video streaming, and input injection.
- **Real-World Workload Testing**: Simulates complete end-to-end user sessions from pairing to screen streaming, high-frequency touch drag, keyboard typing, and reconnection.

---

## 2. Test Architecture & Emulation Engine (`tests/mock_env/`)
Because development and automated verification run on host environments (Windows / Linux) without requiring a physical rooted phone attached for every CI run, high-fidelity mock and emulated environments were constructed to simulate Android 16 framework internals:

| Component | File | Responsibilities |
|-----------|------|------------------|
| **Android Runtime** | `android_runtime.py` | Models `Build` properties with scoped spoofing, `Process` context (PID/UID), `Context`, `ApplicationInfo`, `Surface` buffer sink, `MotionEvent`, `KeyEvent`, and `Bundle`. |
| **ART ClassLoader** | `art_classloader.py` | Simulates Android Runtime class loading. Faithfully throws `NoClassDefFoundError` for missing Samsung classes on AOSP and manages synthetic stub injection for `SemFloatingFeature` and `OneUIStubs` (`SEM_INT = 3001`). |
| **Package Manager Service** | `pms_service.py` | Simulates Android 16 PMS priv-app verification (`/system/priv-app/`), parses `privapp-permissions-*.xml` and `sysconfig/*.xml`, and simulates `PackageSignatureChecker`. |
| **Binder IPC & AIDL** | `binder_ipc.py` | Simulates AIDL interfaces `IPhoneScreenMirroringService` and `IInputInjectorService`, and provides ContentProvider routing for `CapabilityContentProvider` and `CompanionDevicePermissionProvider`. |
| **Display Manager** | `display_manager.py` | Models Display hierarchy (Display 0 default built-in screen) and `VirtualDisplay` lifecycle (create, resize, setSurface, release, callbacks). |
| **Input Manager** | `input_manager.py` | Simulates `InputManagerService` event dispatch, `INJECT_EVENTS` permission checks, coordinate validation, `/dev/uinput` Linux hardware bridge with SELinux checks, and `ClipboardBridge`. |
| **LSPosed Engine** | `lsposed_engine.py` | Simulates Xposed hooking engine, pre-configuring `AppManagerHooks`, `MdxServiceHooks`, and `SystemServerHooks`. |
| **Packaging Validator** | `packaging_validator.py` | Validates structural integrity and manifest requirements of Magisk flashable zips and LSPosed APKs. |

---

## 3. Test Tiers & Inventory

### Tier 1: Feature Coverage (74 Tests)
Covers isolated happy paths across all 12 inventoried features in `PROJECT.md`:
- `test_f01_device_spoofing.py`: Scoped `Build.MANUFACTURER = "samsung"`, global Xiaomi identity preservation, SDK 36 integrity.
- `test_f02_sem_floating_feature.py`: In-memory `SemFloatingFeature` stub, singleton access, `SEC_FLOATING_FEATURE_LINK_TO_WINDOWS`, brand queries.
- `test_f03_oneui_version_stubs.py`: `SEM_INT = 3001` stub in `LL0.c` and `SemVersion`, DeX / SmartClip safe fallbacks.
- `test_f04_signature_bypass.py`: `PackageSignatureChecker` bypass for target pair, `isShipBuild = true`.
- `test_f05_privapp_whitelist.py`: Priv-app placement, `privapp-permissions-phonelink.xml` parsing and granting.
- `test_f06_power_exemptions.py`: Sysconfig parsing for `<allow-in-power-save>` and `<allow-in-data-saver>`.
- `test_f07_mediaprojection_autogrant.py`: Headless permission query via `CompanionDevicePermissionProvider`.
- `test_f08_screen_capture_pipeline.py`: `IPhoneScreenMirroringService` `VirtualDisplay` creation, surface binding, frame push.
- `test_f08_video_codec_and_capability_provider.py`: Qualcomm Snapdragon 855 hardware Codec2 redirection (`c2.qti.avc.encoder`), format sanitization, sync frame parameters.
- `test_f09_input_redirection.py`: `IInputInjectorService` touch and key event redirection to AOSP `InputManager`.
- `test_f10_inject_events_bypass.py`: `system_server` hook bypass with O(1) cache for MDX / AppManager UIDs.
- `test_f11_uinput_hardware_bridge.py`: `/dev/uinput` bridge, right-click to `KEYCODE_BACK`, middle-click to `KEYCODE_HOME`.
- `test_f12_packaging_delivery.py`: Magisk module structure, `module.prop`, `privapp-permissions.xml`, `xposed_init`.

### Tier 2: Boundary & Corner Cases (184 Tests)
Covers limits, empty/null values, malformed inputs, fuzzing, and security denials:
- `test_b01_device_spoofing_bounds.py`: Empty package lookup, non-existent packages, rapid context switching, explicit disablement.
- `test_b02_floating_feature_bounds.py`: Empty/null keys, non-numeric strings in `getInt`, unicode strings, clear registry.
- `test_b03_oneui_stubs_bounds.py`: Unstubbed classes throwing `NoClassDefFoundError`, unregister restoration, version limits.
- `test_b04_signature_bypass_bounds.py`: Empty strings, non-existent packages, bypass disablement, untrusted package denial.
- `test_b05_privapp_whitelist_bounds.py`: Malformed XML, empty tags, system UID 1000 inherent privileges, non-privapp rejection.
- `test_b06_power_exemptions_bounds.py`: Malformed XML, deduplication, empty package attributes, non-exempt package rejection.
- `test_b07_mediaprojection_bounds.py`: Null methods, unknown methods, invalid URI scheme, bundle immutability.
- `test_b08_screen_capture_bounds.py`: Zero dimensions, negative DPI, empty name, released surface rejection, runtime errors on released display.
- `test_b09_input_redirection_bounds.py`: None events, negative coordinates, non-existent display IDs, excessive pointer counts (>10).
- `test_b10_inject_events_bounds.py`: Untrusted UIDs throwing `SecurityException`, bypass disablement, rogue UID tampering prevention.
- `test_b11_uinput_bridge_bounds.py`: Invalid file permissions (0600), SELinux context denial, closed bridge operations, stuck key cleanup, >1MB clipboard limits.
- `test_b12_packaging_bounds.py`: Missing Magisk files, missing module.prop keys, missing MDX in privapp, missing xposed_init.

### Tier 3: Cross-Feature Combinations (14 Tests)
Covers pairwise and multi-feature interactions in `test_cross_feature_combinations.py`:
- Device spoofing + SemFloatingFeature stub on app startup.
- One UI version stub + signature bypass handshake.
- Priv-app whitelist + power-save exemption in low battery state.
- MediaProjection auto-grant + VirtualDisplay allocation pipeline.
- VirtualDisplay pipeline + SemInputInjector coordinate redirection.
- System_server inject bypass + rapid pointer stream.
- Keyboard uinput bridge + InputManager key event injection.
- VirtualDisplay dynamic resize + input scaling synchronization.
- Stream teardown + input injector disable cycle.
- Device spoofing isolation during high-load video streaming.
- Uinput mouse gestures and right-click interleaving without stuck keys.
- Two-way clipboard synchronization during active screen mirroring.
- Privapp cross-user permission validation.
- Packaging specification matching runtime stubs.

### Tier 4: Real-World Application Scenarios (8 Tests)
Simulates end-to-end sessions in `test_real_world_scenarios.py`:
1. Initial pairing & handshake between Windows Phone Link and phone.
2. Phone Screen mirror session launch with headless auto-grant and video streaming.
3. High-rate mouse drag gestures at 60Hz.
4. Fast keyboard typing and navigation keys (Enter, Backspace, Home).
5. Two-way clipboard copy/paste workflow.
6. Battery saver / Doze mode resilience and seamless reconnection.
7. Screen rotation (portrait 1080x2340 to landscape 2340x1080) and coordinate adaptation.
8. Graceful disconnect and complete resource cleanup.

---

## 4. Execution Instructions

### Running the Full Test Suite
From the `tests/` directory:
```bash
python test_runner.py
```
Or from the project root:
```bash
python tests/test_runner.py
```

### Running Individual Tiers
```bash
python tests/test_runner.py --tier 1   # Tier 1: Feature Coverage (74 tests)
python tests/test_runner.py --tier 2   # Tier 2: Boundary Cases (184 tests)
python tests/test_runner.py --tier 3   # Tier 3: Combinations (14 tests)
python tests/test_runner.py --tier 4   # Tier 4: Real-World Scenarios (8 tests)
```

### Verbose Mode
```bash
python tests/test_runner.py -v
```

---

## 5. Authoritative Sources of Expected Output
All test cases derive expected outputs directly from:
1. `PROJECT.md`: Feature inventory, AIDL interface contracts (`IPhoneScreenMirroringService`, `IInputInjectorService`), ContentProvider URIs, and code layout.
2. `ORIGINAL_REQUEST.md`: Target device specification (Xiaomi Mi 9 `cepheus`, AOSP Android 16), acceptance criteria (R1–R4).
3. Android Open Source Project (AOSP) Android 16 / SDK 36 Platform Specifications: `InputManagerService` permission contracts (`INJECT_EVENTS`), `PackageManagerService` privapp whitelist enforcement rules, `DisplayManager` `VirtualDisplay` lifecycle.
