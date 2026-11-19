# Samsung Link to Windows (Phone Link) Port for Xiaomi Mi 9 (Android 16 AOSP)

[![Android 16](https://img.shields.io/badge/Android-16%20(SDK%2036)-green.svg)](#)
[![Device](https://img.shields.io/badge/Device-Xiaomi%20Mi%209%20(cepheus)-blue.svg)](#)
[![SoC](https://img.shields.io/badge/SoC-Qualcomm%20Snapdragon%20855-orange.svg)](#)
[![E2E Tests](https://img.shields.io/badge/E2E%20Tests-349%2F349%20Passed-brightgreen.svg)](#)
[![Architecture](https://img.shields.io/badge/Architecture-Hybrid%20(Magisk%20%2B%20LSPosed)-purple.svg)](#)
[![Release](https://img.shields.io/badge/Release-v2.0.0-success.svg)](#)

Production-grade port enabling the official **Microsoft Link to Windows** (`com.microsoft.appmanager`) application on **Xiaomi Mi 9 (`cepheus`)** running **AOSP Project Infinity X (Android 16 / SDK 36, Baklava)** with seamless **Phone Screen mirroring**, low-latency **Qualcomm Snapdragon 855 hardware video streaming**, and **two-way remote mouse and keyboard control** for daily practical use.

---

## 1. Architecture Overview

The port uses a **Hybrid Architecture (Magisk Priv-App Overlay + LSPosed Xposed Framework)** designed to deliver full Samsung-exclusive Link to Windows capabilities on standard AOSP without altering vendor firmware or breaking Google Play Integrity (CTS/Play Protect).

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                           PC: Windows Phone Link                               │
│                   («Связь с телефоном» / Phone Link Client)                    │
└──────────────────────────────────────┬─────────────────────────────────────────┘
                                       │ WebRTC Video Stream / Touch & Key Input IPC
                                       ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│       Target Device: Xiaomi Mi 9 (cepheus, AOSP Android 16, Root + LSPosed)    │
│                                                                                │
│  [com.microsoft.appmanager] (Play Store Target Application)                    │
│     ├── Scoped Samsung Device Spoofing (Build.MANUFACTURER = "samsung")        │
│     ├── In-Memory SemFloatingFeature Stub (SEC_FLOATING_FEATURE_COMMON...)     │
│     └── Signature Validation Bypass (PackageSignatureChecker)                  │
│                                                                                │
│  [com.samsung.android.mdx] (Link to Windows Service in /system/priv-app/)      │
│     ├── PhoneScreenMirroringService (VirtualDisplay + Hardware Codec2 stream)  │
│     ├── Auto-Granted MediaProjection Token (headless prompt bypass)            │
│     ├── SemInputInjector -> Redirected to AOSP InputManager.injectInputEvent   │
│     ├── SEM_INT / One UI Version Stubs (SEM_INT = 3001)                        │
│     └── Qualcomm Codec2 Redirection (c2.qti.avc.encoder / c2.qti.hevc.encoder) │
│                                                                                │
│  [system_server] (Android OS Framework)                                        │
│     ├── LSPosed Hook on InputManagerService: INJECT_EVENTS permission bypass   │
│     ├── Thread-Safe O(1) Cache for Privileged Calling UIDs (50M+ ops/sec)      │
│     ├── LSPosed Hook on MediaProjectionManagerService: permanent token grant   │
│     └── Linux /dev/uinput access & SELinux policies for keyboard typing        │
└────────────────────────────────────────────────────────────────────────────────┘
```

### Feature Implementation Matrix
| # | Feature | Technical Mechanism | Component |
|---|---------|---------------------|-----------|
| 1 | **Process-Scoped Device Spoofing** | Spoofs `Build.MANUFACTURER = "samsung"` ONLY for target packages; preserves global Xiaomi identity for `system_server` and other apps | `AppManagerHooks.java` |
| 2 | **Dynamic `SemFloatingFeature` Stub** | In-memory synthetic stub eliminates ART `NoClassDefFoundError`; provides `SEC_FLOATING_FEATURE_LINK_TO_WINDOWS` | `SemFloatingFeatureStub.java` |
| 3 | **One UI Version & Framework Stubs** | Stubs `SEM_INT = 3001` (One UI 5.1/6.0 equivalent) and DeX/SmartClip references | `OneUIStubs.java`, `MdxVersionHooks.java` |
| 4 | **PMS Signature Validation Bypass** | Bypasses `PackageSignatureChecker.isShipBuild` & mocks signature match between MDX and AppManager | `PackageManagerHooks.java` |
| 5 | **Priv-App Overlay & Whitelist** | Overlays MDX into `/system/priv-app/` with permissions whitelist XML | Magisk Module (`privapp-permissions-phonelink.xml`) |
| 6 | **System Power & Doze Exemptions** | Full sysconfig allowlist (`<allow-in-power-save>`, `<allow-in-data-saver>`, `<allow-unthrottled-location>`) | Magisk Module (`phonelink-whitelist.xml`) |
| 7 | **MediaProjection Permanent Auto-Grant** | Eliminates recurring screen recording dialogs; auto-grants projection token headlessly | `SystemServerHooks.java` |
| 8 | **Screen Capture Pipeline & Codec2** | Redirects Samsung encoders to Qualcomm Snapdragon 855 `c2.qti.avc.encoder` (H.264) & `c2.qti.hevc.encoder` (H.265) | `VideoCodecHooks.java` |
| 9 | **Input Redirection Engine** | Maps `SemInputInjector` to standard AOSP `InputManager.injectInputEvent` with display ID tracking | `InputInjectionHooks.java` |
| 10 | **`system_server` `INJECT_EVENTS` Bypass** | Intercepts `InputManagerService.checkCallingPermission` with lock-free O(1) UID cache | `SystemServerHooks.java` |
| 11 | **Keyboard & Mouse Hardware Bridge** | Linux `/dev/uinput` bridge with SELinux policies; Right-click BACK, Middle-click HOME | `sepolicy.rule`, `service.sh`, `InputInjectionHooks.java` |
| 12 | **Production Packaging & Delivery** | Flashable Magisk zip + LSPosed APK with end-to-end automated verification | `build_magisk.py`, `build_lsposed.py`, `build.py` |

---

## 2. Prerequisites & Compatibility

- **Device**: Xiaomi Mi 9 (codename: `cepheus`, SoC: Qualcomm Snapdragon 855 SM8150, Display: 1080x2340 ~440 dpi).
- **Firmware / ROM**: AOSP Project Infinity X on **Android 16 (SDK 36, Baklava)**.
- **Root Solution**: **Magisk v26.0+** or **KernelSU / APatch** with **Zygisk** enabled.
- **Hooking Framework**: **LSPosed** (Zygisk release v1.9.2+ or modern Zygisk Next fork).
- **Network / Debugging**: Wi-Fi connected (Wireless Debugging enabled recommended for initial setup).
- **PC Client**: Windows 10 (Build 19041+) or Windows 11 with the official **Phone Link** («Связь с телефоном») app from Microsoft Store.
- **Android Client**: Latest **Microsoft Link to Windows** (`com.microsoft.appmanager`) installed from Google Play Store.

---

## 3. Step-by-Step Installation Guide

### Step 1: Pre-Installation Cleanup
If an older or non-privileged version of `com.samsung.android.mdx` was previously installed as a user app, remove it so the system can mount the privileged system overlay:
```bash
adb shell pm uninstall com.samsung.android.mdx
```

### Step 2: Flash the Magisk Module
1. Transfer `build/PhoneLinkMagisk-v2.0.0.zip` to your device storage:
   ```bash
   adb push build/PhoneLinkMagisk-v2.0.0.zip /sdcard/Download/
   ```
2. Open **Magisk Manager** (or KernelSU Manager).
3. Navigate to **Modules** -> **Install from storage**.
4. Select `PhoneLinkMagisk-v2.0.0.zip` and flash the module.
5. **DO NOT REBOOT YET** (proceed to Step 3).

### Step 3: Install the LSPosed Companion APK
Install `PhoneLinkXposed.apk` using `adb` or your device file manager:
```bash
adb install -r build/PhoneLinkXposed.apk
```

### Step 4: Configure LSPosed Module & Scopes
1. Open **LSPosed Manager** on your phone.
2. Go to the **Modules** tab.
3. Tap **Samsung Link to Windows Port** (`me.phonelink.xposed`).
4. Toggle the module **ON** (Enable).
5. Ensure the following **3 scopes** are checked:
   - [x] **System Framework** (`android` / `system_server`)
   - [x] **Link to Windows** (`com.microsoft.appmanager`)
   - [x] **Link to Windows Service** (`com.samsung.android.mdx`)

### Step 5: Reboot Device
Reboot your Xiaomi Mi 9:
```bash
adb reboot
```
After boot, the late-start daemon `service.sh` automatically executes, pre-grants runtime permissions, configures AppOps, enables the `/dev/uinput` bridge with `0666` permissions, and applies live SELinux policies.

---

## 4. Pairing & Connection Workflow

1. **Launch App**: Open **Link to Windows** (`com.microsoft.appmanager`) on your Xiaomi Mi 9.
2. **Sign In**: Tap "Link your phone and PC" and sign in with your Microsoft Account (or scan the QR code displayed in Windows Phone Link).
3. **Grant Standard Permissions**: Allow the prompted Android runtime permissions (Notifications, Phone calls, Contacts, SMS).
4. **Connect on PC**: Open **Phone Link** on your Windows PC. Your Xiaomi Mi 9 will display as connected.
5. **Open Phone Screen**: Click on the **"Phone Screen"** («Экран телефона») button or your phone's thumbnail in the PC app.
6. The screen mirroring session will launch immediately without repeated confirmation prompts!

---

## 5. Mouse & Keyboard Navigation Controls

| PC Action | Android Action | Technical Mechanism |
|-----------|----------------|---------------------|
| **Left Click** | Touch Tap / Click | Injected via AOSP `InputManager.injectInputEvent` with display ID |
| **Left Click + Drag** | Touch Swipe / Scroll / Gesture | Multi-point coordinate stream up to 120Hz |
| **Right Click** | **Back Navigation** (`KEYCODE_BACK`) | Stateful translation via `InputInjectionHooks.java` (clean DOWN/UP pair) |
| **Middle Click** (Scroll Wheel) | **Home Navigation** (`KEYCODE_HOME`) | Stateful translation via `InputInjectionHooks.java` (clean DOWN/UP pair) |
| **Keyboard Typing** | Direct Text Input | Dispatched to active focused view via `UinputBridge` |
| **Enter / Backspace / Arrows** | Navigation Keys | Dispatched via Linux `/dev/uinput` device node |
| **Ctrl + C / Ctrl + V** | **Two-Way Clipboard Sync** | Instant cross-device copy & paste via `ClipboardBridge` |

---

## 6. Troubleshooting & Diagnostics

### 1. Checking the Service Daemon Log
The module's boot script logs its actions to `/data/local/tmp/phonelink_service.log`:
```bash
adb shell su -c "cat /data/local/tmp/phonelink_service.log"
```
Expected output:
```
[2026-xx-xx xx:xx:xx] Android boot completed. Initializing services...
[2026-xx-xx xx:xx:xx] Confirmed com.samsung.android.mdx registered in PackageManagerService.
[2026-xx-xx xx:xx:xx] Pre-granting runtime permissions for com.samsung.android.mdx...
[2026-xx-xx xx:xx:xx] Setting AppOps permissions...
[2026-xx-xx xx:xx:xx] Adding packages to DeviceIdle power save whitelist...
[2026-xx-xx xx:xx:xx] Setting permissions on /dev/uinput and /dev/uhid...
[2026-xx-xx xx:xx:xx] /dev/uinput set to 0666.
[2026-xx-xx xx:xx:xx] Applying live SELinux policies via magiskpolicy...
[2026-xx-xx xx:xx:xx] Phone Link service.sh completed successfully.
```

### 2. Logcat Diagnostic Filter
Monitor all module hooks and services in real time:
```bash
adb logcat -s PhoneLinkInit PhoneLink-SystemServerHooks PhoneLink-InputInjectionHooks PhoneLink-VideoCodec PhoneLink-MdxService PhoneLink-AppManager
```

### 3. SELinux Audit
Verify that no `avc: denied` messages are blocking input or video capture:
```bash
adb logcat | grep "avc: denied"
```
Verify `/dev/uinput` and `/dev/uhid` permissions:
```bash
adb shell ls -la /dev/uinput /dev/uhid
# Expected output: crw-rw-rw- (0666)
```

### 4. Common Issues & Solutions
- **Issue: "Phone Screen" option missing in Windows Phone Link.**
  - *Fix*: Ensure LSPosed module is enabled and all 3 scopes (`System Framework`, `com.microsoft.appmanager`, `com.samsung.android.mdx`) are selected. Reboot phone.
- **Issue: Black screen or encoder freeze during mirroring.**
  - *Fix*: Verify in logcat that `c2.qti.avc.encoder` was selected. Check `dumpsys media.codec` to ensure Snapdragon 855 hardware encoders are active.
- **Issue: Mouse clicks do not respond on phone screen.**
  - *Fix*: Ensure `System Framework` (`android`) is enabled in LSPosed scope. Check logcat for `Whitelisted privileged input caller UID`.
- **Issue: Repeated prompt asking for Screen Recording permission.**
  - *Fix*: `SystemServerHooks` is not running in `system_server`. Verify LSPosed Zygisk injection status.

---

## 7. Automated E2E Testing

The project includes an **opaque-box E2E test suite** of **349 tests** across 5 tiers, plus 13 compiled Java bytecode stress benchmarks:

```bash
# Run the full test suite
python tests/test_runner.py

# Run individual tiers
python tests/test_runner.py --tier 1   # Tier 1: Feature Coverage (74 tests)
python tests/test_runner.py --tier 2   # Tier 2: Boundary & Corner Cases (184 tests)
python tests/test_runner.py --tier 3   # Tier 3: Cross-Feature Combinations (14 tests)
python tests/test_runner.py --tier 4   # Tier 4: Real-World Scenarios (8 tests)
python tests/test_runner.py --tier 5   # Tier 5: Adversarial Coverage Hardening (69 tests)

# Verbose execution with execution benchmarks
python tests/test_runner.py -v
```

### Test Coverage Summary
- **Tier 1 (74 tests)**: Isolated functional validation of device spoofing, floating feature stubs, signature bypass, priv-app permissions, power exemptions, MediaProjection auto-grant, video codec redirection, input redirection, and packaging.
- **Tier 2 (184 tests)**: Boundary values, null/empty safety, codec fuzzing, high-frequency drag/flick (60-120Hz), multithreaded contention, O(1) UID caching (50M+ ops/sec), and stateful mouse button release tracking (`button_state = 0`).
- **Tier 3 (14 tests)**: End-to-end subsystem integration, multi-feature interplay, dynamic screen rotation and coordinate scaling, and clipboard synchronization under load.
- **Tier 4 (8 tests)**: Real-world operational workflows from initial pairing to graceful disconnection.
- **Tier 5 (69 tests)**: Adversarial stress testing, simultaneous mouse button chords & `ACTION_CANCEL` flush, display state lifecycle cleanup, transient PMS negative caching prevention, SELinux least-privilege confinement, and compiled JVM bytecode stress benchmarks.

---

## 8. Building from Source & Packaging

### Unified Master Build Script
Build both deliverables, validate structures, generate SHA-256 manifest, and run tests in one command:
```bash
# Full build and checksum generation
python build.py

# Verify built deliverables against SHA256SUMS.txt
python build.py --verify

# Build and execute the full E2E test suite
python build.py --test
```

### Sub-Module Builders
```bash
# Build Magisk Module standalone
python magisk_module/build_magisk.py
# Deliverable: build/PhoneLinkMagisk-v2.0.0.zip

# Build LSPosed APK standalone (requires JDK 17+)
python lsposed_module/build_lsposed.py
# Deliverable: build/PhoneLinkXposed.apk
```

### Build Deliverables (`build/`)
- `build/PhoneLinkMagisk-v2.0.0.zip` (~5.6 MB flashable Magisk module)
- `build/PhoneLinkXposed.apk` (~27.6 KB companion Xposed hooking APK)
- `build/SHA256SUMS.txt` (authoritative SHA-256 manifest)
