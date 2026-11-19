#!/usr/bin/env python3
"""
Authoritative Build & Packaging Tool for PhoneLink LSPosed Module.
Compiles Java source code in app/src/main/java to classes.dex via javac and D8,
packages PhoneLinkXposed.apk, and performs strict DEX descriptor verification.
"""

import os
import sys
import shutil
import zipfile
import subprocess
import urllib.request
from pathlib import Path

MODULE_ROOT = Path(__file__).parent.resolve()
PROJECT_ROOT = MODULE_ROOT.parent.resolve()
APP_SRC = MODULE_ROOT / "app" / "src" / "main"
BUILD_DIR = MODULE_ROOT / "build"
TOOLS_DIR = MODULE_ROOT / "tools"
STUBS_SRC = BUILD_DIR / "stubs_src"
STUBS_CLASSES = BUILD_DIR / "stubs_classes"
STUBS_JAR = TOOLS_DIR / "android_stubs.jar"
APP_CLASSES = BUILD_DIR / "app_classes"
DEX_DIR = BUILD_DIR / "dex"
SAMSUNG_STUBS_CLASSES = BUILD_DIR / "samsung_stubs_classes"
SAMSUNG_STUBS_DEX_DIR = BUILD_DIR / "samsung_stubs_dex"
GEN_EMBEDDED_JAVA = APP_SRC / "java" / "me" / "phonelink" / "xposed" / "stubs" / "EmbeddedSamsungStubsDex.java"
OUTPUT_APK_DIR = BUILD_DIR / "outputs" / "apk" / "release"
TARGET_APK_NAME = "PhoneLinkXposed.apk"
TARGET_APK = OUTPUT_APK_DIR / TARGET_APK_NAME
ROOT_APK = MODULE_ROOT / TARGET_APK_NAME

API_JAR_URL = "https://api.xposed.info/de/robv/android/xposed/api/82/api-82.jar"
R8_JAR_URL = "https://dl.google.com/android/maven2/com/android/tools/r8/8.5.35/r8-8.5.35.jar"
AAPT2_JAR_URL = "https://dl.google.com/android/maven2/com/android/tools/build/aapt2/8.2.0-10154469/aapt2-8.2.0-10154469-windows.jar"
UBER_SIGNER_URL = "https://github.com/patrickfav/uber-apk-signer/releases/download/v1.3.0/uber-apk-signer-1.3.0.jar"
ANDROID_JAR_URL = "https://raw.githubusercontent.com/Sable/android-platforms/master/android-30/android.jar"

REQUIRED_DESCRIPTORS = [
    "Lme/phonelink/xposed/XposedInit;",
    "Lme/phonelink/xposed/hooks/AppManagerHooks;",
    "Lme/phonelink/xposed/hooks/InputInjectionHooks;",
    "Lme/phonelink/xposed/hooks/MdxServiceHooks;",
    "Lme/phonelink/xposed/hooks/MdxVersionHooks;",
    "Lme/phonelink/xposed/hooks/PackageManagerHooks;",
    "Lme/phonelink/xposed/hooks/SystemServerHooks;",
    "Lme/phonelink/xposed/hooks/VideoCodecHooks;",
    "Lcom/samsung/android/feature/SemFloatingFeature;",
    "Lme/phonelink/xposed/utils/CertConstants;"
]

# Ensure project root is in sys.path
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.mock_env.packaging_validator import PackagingValidator


def find_jdk_binary(binary_name: str) -> str:
    """Locate javac or java executable from PATH or Adoptium JDK installation."""
    cmd = shutil.which(binary_name)
    if cmd:
        return cmd

    default_jdk = Path(r"C:\Program Files\Eclipse Adoptium\jdk-25.0.4.7-hotspot\bin") / f"{binary_name}.exe"
    if default_jdk.exists():
        return str(default_jdk)

    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidate = Path(java_home) / "bin" / f"{binary_name}.exe"
        if candidate.exists():
            return str(candidate)

    raise FileNotFoundError(f"Cannot find {binary_name} in PATH, Adoptium JDK, or JAVA_HOME.")


def ensure_tools():
    """Acquire required compile, dex, packaging, and signing tools."""
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    api_jar = TOOLS_DIR / "api-82.jar"
    r8_jar = TOOLS_DIR / "r8.jar"
    aapt2_exe = TOOLS_DIR / "aapt2.exe"
    signer_jar = TOOLS_DIR / "uber-apk-signer.jar"
    android_jar = TOOLS_DIR / "android.jar"

    local_cache_dirs = [
        Path(r"C:\Users\leona\AppData\Local\Programs\antigravity\.agents\teamwork\explorer_m1_2_it2"),
        Path(r"C:\Users\leona\AppData\Local\Programs\antigravity\.agents\teamwork\explorer_m1_1_it2\tools"),
    ]

    if not api_jar.exists() or api_jar.stat().st_size == 0:
        found_cache = False
        for cache_dir in local_cache_dirs:
            candidate = cache_dir / "api-82.jar"
            if candidate.exists() and candidate.stat().st_size > 0:
                print(f"[*] Copying Xposed API jar from local cache: {candidate}...")
                shutil.copy2(candidate, api_jar)
                found_cache = True
                break
        if not found_cache:
            print(f"[*] Downloading Xposed API from {API_JAR_URL}...")
            urllib.request.urlretrieve(API_JAR_URL, api_jar)

    if not r8_jar.exists() or r8_jar.stat().st_size == 0:
        found_cache = False
        for cache_dir in local_cache_dirs:
            candidate = cache_dir / "r8.jar"
            if candidate.exists() and candidate.stat().st_size > 0:
                print(f"[*] Copying R8/D8 tool jar from local cache: {candidate}...")
                shutil.copy2(candidate, r8_jar)
                found_cache = True
                break
        if not found_cache:
            print(f"[*] Downloading R8/D8 tool from {R8_JAR_URL}...")
            urllib.request.urlretrieve(R8_JAR_URL, r8_jar)

    if not aapt2_exe.exists() or aapt2_exe.stat().st_size == 0:
        print(f"[*] Downloading aapt2 from {AAPT2_JAR_URL}...")
        import io
        jar_data = urllib.request.urlopen(AAPT2_JAR_URL).read()
        with zipfile.ZipFile(io.BytesIO(jar_data)) as zf:
            zf.extract("aapt2.exe", TOOLS_DIR)

    if not signer_jar.exists() or signer_jar.stat().st_size == 0:
        print(f"[*] Downloading uber-apk-signer from {UBER_SIGNER_URL}...")
        urllib.request.urlretrieve(UBER_SIGNER_URL, signer_jar)

    if not android_jar.exists() or android_jar.stat().st_size == 0:
        print(f"[*] Downloading android.jar (API 30) from {ANDROID_JAR_URL}...")
        urllib.request.urlretrieve(ANDROID_JAR_URL, android_jar)

    return api_jar, r8_jar, aapt2_exe, signer_jar, android_jar


def generate_android_stubs(stubs_dir: Path):
    """Generate minimal compile-only Android framework stubs."""
    stubs_dir.mkdir(parents=True, exist_ok=True)

    # 1. Context
    (stubs_dir / "android" / "content").mkdir(parents=True, exist_ok=True)
    (stubs_dir / "android" / "content" / "Context.java").write_text(
        """package android.content;
import android.content.pm.PackageManager;
public abstract class Context {
    public static final String DISPLAY_SERVICE = "display";
    public static final String KEYGUARD_SERVICE = "keyguard";
    public static final String POWER_SERVICE = "power";
    public static final String MEDIA_PROJECTION_SERVICE = "media_projection";
    public static final String INPUT_SERVICE = "input";
    public abstract Object getSystemService(String name);
    public abstract String getPackageName();
    public abstract ClassLoader getClassLoader();
    public abstract PackageManager getPackageManager();
}
""", encoding="utf-8"
    )

    # 2. PM Stubs
    (stubs_dir / "android" / "content" / "pm").mkdir(parents=True, exist_ok=True)
    (stubs_dir / "android" / "content" / "pm" / "Signature.java").write_text(
        """package android.content.pm;
public class Signature {
    public Signature(String text) {}
    public Signature(byte[] signature) {}
    public byte[] toByteArray() { return null; }
    public String toCharsString() { return null; }
}
""", encoding="utf-8"
    )
    (stubs_dir / "android" / "content" / "pm" / "SigningInfo.java").write_text(
        """package android.content.pm;
public final class SigningInfo {
    public SigningInfo() {}
    public SigningInfo(SigningInfo orig) {}
    public boolean hasMultipleSigners() { return false; }
    public Signature[] getSigningCertificateHistory() { return null; }
    public Signature[] getApkContentsSigners() { return null; }
    public boolean hasPastSigningCertificates() { return false; }
}
""", encoding="utf-8"
    )
    (stubs_dir / "android" / "content" / "pm" / "PackageInfo.java").write_text(
        """package android.content.pm;
public class PackageInfo {
    public String packageName;
    public Signature[] signatures;
    public SigningInfo signingInfo;
}
""", encoding="utf-8"
    )
    (stubs_dir / "android" / "content" / "pm" / "PackageManager.java").write_text(
        """package android.content.pm;
public abstract class PackageManager {
    public static final int GET_SIGNATURES = 64;
    public static final int GET_SIGNING_CERTIFICATES = 134217728;
    public static final int SIGNATURE_MATCH = 0;
    public static final int SIGNATURE_NO_MATCH = -1;
    public static final int SIGNATURE_UNKNOWN_PACKAGE = -2;
    public static final int SIGNATURE_NEITHER_SIGNED = -3;
    public abstract String[] getPackagesForUid(int uid);
}
""", encoding="utf-8"
    )

    # 3. OS Stubs
    (stubs_dir / "android" / "os").mkdir(parents=True, exist_ok=True)
    (stubs_dir / "android" / "os" / "Build.java").write_text(
        """package android.os;
public class Build {
    public static String MANUFACTURER;
    public static String BRAND;
    public static String MODEL;
    public static String PRODUCT;
    public static String DEVICE;
    public static class VERSION {
        public static int SDK_INT = 36;
    }
}
""", encoding="utf-8"
    )
    (stubs_dir / "android" / "os" / "Bundle.java").write_text(
        """package android.os;
public final class Bundle {
    public Bundle() {}
    public void putBoolean(String key, boolean value) {}
    public void putInt(String key, int value) {}
    public void putString(String key, String value) {}
    public boolean getBoolean(String key) { return false; }
    public boolean getBoolean(String key, boolean defaultValue) { return defaultValue; }
    public int getInt(String key) { return 0; }
    public int getInt(String key, int defaultValue) { return defaultValue; }
    public String getString(String key) { return null; }
    public boolean containsKey(String key) { return false; }
}
""", encoding="utf-8"
    )
    (stubs_dir / "android" / "os" / "IBinder.java").write_text(
        "package android.os;\npublic interface IBinder {}\n", encoding="utf-8"
    )
    (stubs_dir / "android" / "os" / "Binder.java").write_text(
        """package android.os;
public class Binder implements IBinder {
    public static UserHandle getCallingUserHandle() { return null; }
    public static int getCallingUid() { return 0; }
}
""", encoding="utf-8"
    )
    (stubs_dir / "android" / "os" / "UserHandle.java").write_text(
        "package android.os;\npublic final class UserHandle {}\n", encoding="utf-8"
    )
    (stubs_dir / "android" / "os" / "Process.java").write_text(
        """package android.os;
public class Process {
    public static int myUid() { return 0; }
}
""", encoding="utf-8"
    )
    (stubs_dir / "android" / "os" / "PowerManager.java").write_text(
        """package android.os;
public class PowerManager {
    public static final int WAKE_REASON_APPLICATION = 2;
    public boolean isInteractive() { return true; }
    public void wakeUp(long time, int reason, String details) {}
}
""", encoding="utf-8"
    )
    (stubs_dir / "android" / "os" / "HandlerThread.java").write_text(
        """package android.os;
public class HandlerThread extends Thread {
    public HandlerThread(String name) {}
    public Looper getLooper() { return null; }
}
""", encoding="utf-8"
    )
    (stubs_dir / "android" / "os" / "Handler.java").write_text(
        """package android.os;
public class Handler {
    public Handler() {}
    public Handler(Looper looper) {}
}
""", encoding="utf-8"
    )
    (stubs_dir / "android" / "os" / "Looper.java").write_text(
        "package android.os;\npublic class Looper {}\n", encoding="utf-8"
    )
    (stubs_dir / "android" / "os" / "SystemClock.java").write_text(
        """package android.os;
public final class SystemClock {
    public static long uptimeMillis() { return 0L; }
}
""", encoding="utf-8"
    )

    # 4. App & Keyguard Stubs
    (stubs_dir / "android" / "app").mkdir(parents=True, exist_ok=True)
    (stubs_dir / "android" / "app" / "KeyguardManager.java").write_text(
        """package android.app;
public class KeyguardManager {
    public boolean isKeyguardLocked() { return false; }
}
""", encoding="utf-8"
    )

    # 5. Display & View Stubs
    (stubs_dir / "android" / "view").mkdir(parents=True, exist_ok=True)
    (stubs_dir / "android" / "view" / "Display.java").write_text(
        """package android.view;
public class Display {
    public int getDisplayId() { return 0; }
}
""", encoding="utf-8"
    )
    (stubs_dir / "android" / "view" / "Surface.java").write_text(
        """package android.view;
public class Surface {
    public Surface() {}
}
""", encoding="utf-8"
    )
    (stubs_dir / "android" / "hardware" / "display").mkdir(parents=True, exist_ok=True)
    (stubs_dir / "android" / "hardware" / "display" / "DisplayManager.java").write_text(
        """package android.hardware.display;
import android.os.Handler;
import android.view.Surface;
public class DisplayManager {
    public static final int VIRTUAL_DISPLAY_FLAG_PUBLIC = 1;
    public static final int VIRTUAL_DISPLAY_FLAG_PRESENTATION = 2;
    public static final int VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR = 16;
    public VirtualDisplay createVirtualDisplay(String name, int width, int height, int densityDpi, Surface surface, int flags, VirtualDisplay.Callback callback, Handler handler) { return null; }
}
""", encoding="utf-8"
    )
    (stubs_dir / "android" / "hardware" / "display" / "VirtualDisplay.java").write_text(
        """package android.hardware.display;
import android.view.Display;
import android.view.Surface;
public class VirtualDisplay {
    public static abstract class Callback {
        public void onPaused() {}
        public void onResumed() {}
        public void onStopped() {}
    }
    public Display getDisplay() { return null; }
    public void resize(int width, int height, int densityDpi) {}
    public void setSurface(Surface surface) {}
    public void release() {}
}
""", encoding="utf-8"
    )

    (stubs_dir / "android" / "graphics").mkdir(parents=True, exist_ok=True)
    (stubs_dir / "android" / "graphics" / "PixelFormat.java").write_text(
        """package android.graphics;
public class PixelFormat {
    public static final int TRANSLUCENT = -3;
}
""", encoding="utf-8"
    )

    (stubs_dir / "android" / "view" / "WindowManager.java").write_text(
        """package android.view;
public interface WindowManager {
    public static class LayoutParams {
        public static final int MATCH_PARENT = -1;
        public static final int WRAP_CONTENT = -2;
        public static final int TYPE_APPLICATION_OVERLAY = 2038;
        public static final int FLAG_NOT_FOCUSABLE = 8;
        public static final int FLAG_LAYOUT_IN_SCREEN = 256;
        public static final int FLAG_LAYOUT_NO_LIMITS = 512;
        public LayoutParams() {}
        public LayoutParams(int w, int h, int type, int flags, int format) {}
        public void setTitle(CharSequence title) {}
    }
}
""", encoding="utf-8"
    )

    (stubs_dir / "android" / "view" / "InputEvent.java").write_text(
        """package android.view;
public abstract class InputEvent {
    public int getDisplayId() { return 0; }
    public void setDisplayId(int displayId) {}
}
""", encoding="utf-8"
    )
    (stubs_dir / "android" / "view" / "MotionEvent.java").write_text(
        """package android.view;
public final class MotionEvent extends InputEvent {
    public static final int ACTION_MASK = 0xff;
    public static final int ACTION_DOWN = 0;
    public static final int ACTION_UP = 1;
    public static final int ACTION_MOVE = 2;
    public static final int ACTION_CANCEL = 3;
    public static final int ACTION_SCROLL = 8;
    public static final int ACTION_BUTTON_PRESS = 11;
    public static final int ACTION_BUTTON_RELEASE = 12;
    public static final int BUTTON_PRIMARY = 1;
    public static final int BUTTON_SECONDARY = 2;
    public static final int BUTTON_TERTIARY = 4;
    public int getAction() { return 0; }
    public int getActionMasked() { return 0; }
    public int getActionButton() { return 0; }
    public int getButtonState() { return 0; }
    public long getDownTime() { return 0L; }
    public long getEventTime() { return 0L; }
}
""", encoding="utf-8"
    )
    (stubs_dir / "android" / "view" / "KeyEvent.java").write_text(
        """package android.view;
public class KeyEvent extends InputEvent {
    public static final int ACTION_DOWN = 0;
    public static final int ACTION_UP = 1;
    public static final int KEYCODE_HOME = 3;
    public static final int KEYCODE_BACK = 4;
    public KeyEvent(int action, int code) {}
    public KeyEvent(long downTime, long eventTime, int action, int code, int repeat) {}
    public int getAction() { return 0; }
    public int getKeyCode() { return 0; }
}
""", encoding="utf-8"
    )
    (stubs_dir / "android" / "hardware" / "input").mkdir(parents=True, exist_ok=True)
    (stubs_dir / "android" / "hardware" / "input" / "InputManager.java").write_text(
        """package android.hardware.input;
import android.view.InputEvent;
public class InputManager {
    public static final int INJECT_INPUT_EVENT_MODE_ASYNC = 0;
    public static final int INJECT_INPUT_EVENT_MODE_WAIT_FOR_RESULT = 1;
    public static final int INJECT_INPUT_EVENT_MODE_WAIT_FOR_FINISH = 2;
    public boolean injectInputEvent(InputEvent event, int mode) { return true; }
}
""", encoding="utf-8"
    )

    # 6. Media & Codec Stubs
    (stubs_dir / "android" / "media").mkdir(parents=True, exist_ok=True)
    (stubs_dir / "android" / "media" / "MediaCodec.java").write_text(
        """package android.media;
import android.os.Bundle;
import android.view.Surface;
public class MediaCodec {
    public static final int CONFIGURE_FLAG_ENCODE = 1;
    public static final String PARAMETER_KEY_REQUEST_SYNC_FRAME = "request-sync";
    public static MediaCodec createByCodecName(String name) { return null; }
    public void configure(MediaFormat format, Surface surface, MediaCrypto crypto, int flags) {}
    public void setParameters(Bundle params) {}
}
""", encoding="utf-8"
    )
    (stubs_dir / "android" / "media" / "MediaCodecInfo.java").write_text(
        """package android.media;
public class MediaCodecInfo {
    public static class CodecCapabilities {
        public static final int COLOR_FormatSurface = 0x7F000789;
    }
    public static class EncoderCapabilities {
        public static final int BITRATE_MODE_CBR = 1;
        public static final int BITRATE_MODE_VBR = 2;
    }
}
""", encoding="utf-8"
    )
    (stubs_dir / "android" / "media" / "MediaCrypto.java").write_text(
        "package android.media;\npublic final class MediaCrypto {}\n", encoding="utf-8"
    )
    (stubs_dir / "android" / "media" / "MediaFormat.java").write_text(
        """package android.media;
public class MediaFormat {
    public static final String KEY_COLOR_FORMAT = "color-format";
    public static final String KEY_LOW_LATENCY = "low-latency";
    public static final String KEY_PRIORITY = "priority";
    public static final String KEY_BITRATE_MODE = "bitrate-mode";
    public static final String KEY_I_FRAME_INTERVAL = "i-frame-interval";
    public void setInteger(String name, int value) {}
    public int getInteger(String name) { return 0; }
    public boolean containsKey(String name) { return false; }
}
""", encoding="utf-8"
    )
    (stubs_dir / "android" / "media" / "projection").mkdir(parents=True, exist_ok=True)
    (stubs_dir / "android" / "media" / "projection" / "MediaProjection.java").write_text(
        """package android.media.projection;
import android.hardware.display.VirtualDisplay;
import android.os.Handler;
import android.view.Surface;
public final class MediaProjection {
    public static abstract class Callback {
        public void onStop() {}
    }
    public VirtualDisplay createVirtualDisplay(String name, int width, int height, int densityDpi, int flags, Surface surface, VirtualDisplay.Callback callback, Handler handler) { return null; }
    public void registerCallback(Callback callback, Handler handler) {}
    public void stop() {}
}
""", encoding="utf-8"
    )

    # 7. Util Stubs
    (stubs_dir / "android" / "util").mkdir(parents=True, exist_ok=True)
    (stubs_dir / "android" / "util" / "Log.java").write_text(
        """package android.util;
public final class Log {
    public static int d(String tag, String msg) { return 0; }
    public static int i(String tag, String msg) { return 0; }
    public static int w(String tag, String msg) { return 0; }
    public static int e(String tag, String msg) { return 0; }
    public static int e(String tag, String msg, Throwable tr) { return 0; }
}
""", encoding="utf-8"
    )


def build_embedded_samsung_stubs_dex(javac: str, java: str, api_jar: Path, r8_jar: Path, src_dir: Path) -> Path:
    """Compile pure Samsung framework stubs into a standalone DEX and generate EmbeddedSamsungStubsDex.java."""
    import base64
    for p in [SAMSUNG_STUBS_CLASSES, SAMSUNG_STUBS_DEX_DIR]:
        if p.exists():
            shutil.rmtree(p)
        p.mkdir(parents=True, exist_ok=True)

    stub_java_files = [
        str(f) for f in sorted(src_dir.rglob("*.java"))
        if f.relative_to(src_dir).parts[:2] in (("android", "os"), ("com", "samsung"))
    ]
    if not stub_java_files:
        raise FileNotFoundError(f"No pure Samsung stub sources found in {src_dir}")

    res_compile = subprocess.run(
        [javac, "--release", "17", "-cp", str(STUBS_CLASSES), "-d", str(SAMSUNG_STUBS_CLASSES)] + stub_java_files,
        capture_output=True, text=True
    )
    if res_compile.returncode != 0:
        raise RuntimeError(f"Failed to compile Samsung stub classes:\n{res_compile.stderr}")

    stub_class_files = [str(f) for f in SAMSUNG_STUBS_CLASSES.rglob("*.class")]
    res_d8 = subprocess.run(
        [
            java, "-cp", str(r8_jar),
            "com.android.tools.r8.D8",
            "--min-api", "28",
            "--lib", str(STUBS_JAR),
            "--output", str(SAMSUNG_STUBS_DEX_DIR),
        ] + stub_class_files,
        capture_output=True, text=True
    )
    if res_d8.returncode != 0:
        raise RuntimeError(f"D8 translation failed for samsung_stubs.dex:\n{res_d8.stderr}")

    stubs_dex = SAMSUNG_STUBS_DEX_DIR / "classes.dex"
    stubs_dex_bytes = stubs_dex.read_bytes()
    all_types, defined_classes = PackagingValidator.parse_dex_classes(stubs_dex_bytes)
    for forbidden in ("xposed", "me/phonelink"):
        for desc in all_types:
            if forbidden in desc.lower():
                raise AssertionError(f"samsung_stubs.dex must be standalone pure stubs, found {desc}")
    for required in (
        "Landroid/os/SemSystemProperties;",
        "Lcom/samsung/android/feature/SemFloatingFeature;",
        "Lcom/samsung/android/desktopmode/SemDesktopModeManager;",
        "Lcom/samsung/android/desktopmode/SemDesktopModeState;",
        "Lcom/samsung/android/os/SemTemperatureManager;",
        "Lcom/samsung/android/os/SemTemperatureManager$Thermistor;",
    ):
        if required not in defined_classes:
            raise AssertionError(f"samsung_stubs.dex missing {required}")

    b64 = base64.b64encode(stubs_dex_bytes).decode("ascii")
    chunks = [b64[i:i + 120] for i in range(0, len(b64), 120)]
    chunks_src = ",\n        ".join(f'"{c}"' for c in chunks)
    GEN_EMBEDDED_JAVA.parent.mkdir(parents=True, exist_ok=True)
    GEN_EMBEDDED_JAVA.write_text(
        "package me.phonelink.xposed.stubs;\n\n"
        "import java.util.Base64;\n\n"
        "/**\n"
        " * Auto-generated by build_lsposed.py from pure Samsung framework stubs.\n"
        " * Allows in-memory DEX injection into target PathClassLoader without APK file permissions.\n"
        " */\n"
        "public final class EmbeddedSamsungStubsDex {\n"
        "    private static final String[] B64_CHUNKS = {\n"
        f"        {chunks_src}\n"
        "    };\n\n"
        "    private static volatile byte[] sCached;\n\n"
        "    public static byte[] getDexBytes() {\n"
        "        byte[] cached = sCached;\n"
        "        if (cached == null) {\n"
        "            StringBuilder sb = new StringBuilder();\n"
        "            for (String chunk : B64_CHUNKS) {\n"
        "                sb.append(chunk);\n"
        "            }\n"
        "            cached = Base64.getDecoder().decode(sb.toString());\n"
        "            sCached = cached;\n"
        "        }\n"
        "        return cached;\n"
        "    }\n"
        "}\n",
        encoding="utf-8"
    )
    print(f"[+] Built standalone samsung_stubs.dex ({len(stubs_dex_bytes)} bytes, {len(defined_classes)} classes) and generated {GEN_EMBEDDED_JAVA.name}.")
    return stubs_dex


def compile_dex() -> Path:
    """Compiles all Java sources to class files and translates into classes.dex."""
    javac = find_jdk_binary("javac")
    java = find_jdk_binary("java")
    api_jar, r8_jar, *_ = ensure_tools()

    for p in [STUBS_CLASSES, APP_CLASSES, DEX_DIR]:
        if p.exists():
            shutil.rmtree(p)
        p.mkdir(parents=True, exist_ok=True)

    # 1. Compile stubs
    generate_android_stubs(STUBS_SRC)
    stub_files = [str(f) for f in STUBS_SRC.rglob("*.java")]
    cmd_stubs = [javac, "--release", "17", "-d", str(STUBS_CLASSES)] + stub_files
    res_stubs = subprocess.run(cmd_stubs, capture_output=True, text=True)
    if res_stubs.returncode != 0:
        raise RuntimeError(f"Failed to compile Android stubs: {res_stubs.stderr}")

    # Package stubs into jar using Python zipfile
    with zipfile.ZipFile(STUBS_JAR, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in STUBS_CLASSES.rglob("*.class"):
            arcname = f.relative_to(STUBS_CLASSES).as_posix()
            zf.write(f, arcname)

    # 1b. Compile standalone samsung_stubs.dex and generate EmbeddedSamsungStubsDex.java
    src_dir = APP_SRC / "java"
    build_embedded_samsung_stubs_dex(javac, java, api_jar, r8_jar, src_dir)

    # 2. Compile app sources
    app_files = [str(f) for f in src_dir.rglob("*.java")]
    if not app_files:
        raise FileNotFoundError(f"No Java sources found in {src_dir}")

    classpath = f"{STUBS_CLASSES}{os.pathsep}{api_jar}"
    cmd_app = [javac, "--release", "17", "-cp", classpath, "-d", str(APP_CLASSES)] + app_files
    res_app = subprocess.run(cmd_app, capture_output=True, text=True)
    if res_app.returncode != 0:
        raise RuntimeError(f"Failed to compile application sources:\n{res_app.stderr}")

    class_files = [str(f) for f in APP_CLASSES.rglob("*.class")]
    print(f"[+] Compiled {len(class_files)} application .class files with javac (--release 17).")

    # 3. Translate to classes.dex using D8
    cmd_d8 = [
        java, "-cp", str(r8_jar),
        "com.android.tools.r8.D8",
        "--min-api", "28",
        "--classpath", str(api_jar),
        "--lib", str(STUBS_JAR),
        "--output", str(DEX_DIR)
    ] + class_files
    res_d8 = subprocess.run(cmd_d8, capture_output=True, text=True)
    if res_d8.returncode != 0:
        raise RuntimeError(f"D8 translation failed:\n{res_d8.stderr}")

    dex_path = DEX_DIR / "classes.dex"
    if not dex_path.exists():
        raise FileNotFoundError(f"D8 succeeded but {dex_path} not found.")

    print(f"[+] Generated classes.dex ({dex_path.stat().st_size} bytes).")
    verify_dex(dex_path)
    return dex_path


def verify_dex(dex_path: Path):
    """Verify that classes.dex contains the authentic classes and zero foreign classes."""
    data = dex_path.read_bytes()
    all_types, defined_classes = PackagingValidator.parse_dex_classes(data)

    for req in REQUIRED_DESCRIPTORS:
        if req not in defined_classes:
            raise AssertionError(f"Integrity check failed: missing required class descriptor {req}")

    if "Lme/ayra/samsung/mdx/XposedInit;" in all_types or "Lme/ayra/samsung/mdx/XposedInit;" in defined_classes:
        raise AssertionError("Integrity check failed: foreign Ayra class descriptor found in classes.dex!")

    for cls_desc in defined_classes:
        if "ayra" in cls_desc.lower():
            raise AssertionError(f"Integrity check failed: foreign class {cls_desc} found in classes.dex!")

    print(f"[+] DEX verification PASSED: {len(defined_classes)} classes present. All required descriptors verified.")


def build_apk():
    print(f"[*] Building LSPosed APK in {MODULE_ROOT}...")
    OUTPUT_APK_DIR.mkdir(parents=True, exist_ok=True)

    manifest_src = APP_SRC / "AndroidManifest.xml"
    init_src = APP_SRC / "assets" / "xposed_init"
    res_dir = APP_SRC / "res"

    if not manifest_src.exists():
        raise FileNotFoundError(f"Missing AndroidManifest.xml at {manifest_src}")
    if not init_src.exists():
        raise FileNotFoundError(f"Missing assets/xposed_init at {init_src}")

    expected_entrypoint = init_src.read_text(encoding="utf-8").strip()

    # Compile source directly to classes.dex
    dex_path = compile_dex()
    dex_bytes = dex_path.read_bytes()

    # Pre-packaging DEX verification via PackagingValidator
    dex_valid, dex_errors = PackagingValidator.validate_dex_entrypoint(dex_bytes, expected_entrypoint)
    if not dex_valid:
        raise RuntimeError(f"Pre-packaging DEX validation failed: {dex_errors}")

    # Acquire tools
    api_jar, r8_jar, aapt2_exe, signer_jar, android_jar = ensure_tools()
    java = find_jdk_binary("java")

    # 1. Compile resources using aapt2
    compiled_res = BUILD_DIR / "compiled_res.zip"
    cmd_compile = [
        str(aapt2_exe), "compile",
        "--dir", str(res_dir),
        "-o", str(compiled_res)
    ]
    res_compile = subprocess.run(cmd_compile, capture_output=True, text=True)
    if res_compile.returncode != 0:
        raise RuntimeError(f"aapt2 compile failed:\n{res_compile.stderr}")

    # 2. Link manifest and resources to skeleton APK
    skeleton_apk = BUILD_DIR / "skeleton.apk"
    cmd_link = [
        str(aapt2_exe), "link",
        "-I", str(android_jar),
        "--manifest", str(manifest_src),
        "--min-sdk-version", "28",
        "--target-sdk-version", "33",
        "--version-code", "1",
        "--version-name", "1.0.0",
        "-o", str(skeleton_apk),
        str(compiled_res),
        "--auto-add-overlay"
    ]
    res_link = subprocess.run(cmd_link, capture_output=True, text=True)
    if res_link.returncode != 0:
        raise RuntimeError(f"aapt2 link failed:\n{res_link.stderr}")

    # 3. Add classes.dex and assets/xposed_init
    shutil.copy2(skeleton_apk, TARGET_APK)
    with zipfile.ZipFile(TARGET_APK, "a") as apk:
        apk.write(dex_path, "classes.dex")
        apk.write(init_src, "assets/xposed_init")

    # 4. Sign and zipalign with uber-apk-signer (applies v1, v2, v3 schemes and 4-byte alignment)
    cmd_sign = [
        java, "-jar", str(signer_jar),
        "-a", str(TARGET_APK),
        "--overwrite"
    ]
    res_sign = subprocess.run(cmd_sign, capture_output=True, text=True)
    if res_sign.returncode != 0:
        raise RuntimeError(f"uber-apk-signer failed:\n{res_sign.stdout}\n{res_sign.stderr}")

    # Maintain copy in module root and aliases
    shutil.copy2(TARGET_APK, ROOT_APK)
    shutil.copy2(TARGET_APK, OUTPUT_APK_DIR / "phonelink_lsposed.apk")

    # Validate packaged APK with PackagingValidator
    with zipfile.ZipFile(TARGET_APK, "r") as apk:
        file_list = apk.namelist()
        init_content = apk.read("assets/xposed_init").decode("utf-8").strip()
        packaged_dex = apk.read("classes.dex")
        manifest_bytes = apk.read("AndroidManifest.xml")

    # Assert binary manifest magic (0x00080003)
    if manifest_bytes[:4] != b"\x03\x00\x08\x00":
        raise RuntimeError(f"AndroidManifest.xml is not compiled binary XML! Magic: {manifest_bytes[:4].hex()}")

    valid, errors = PackagingValidator.validate_lsposed_apk(file_list, init_content, dex_bytes=packaged_dex)
    if not valid:
        raise RuntimeError(f"PackagingValidator failed: {errors}")

    print(f"[+] Successfully built, binary-compiled, signed and validated APK: {TARGET_APK} ({TARGET_APK.stat().st_size} bytes)")
    print(f"[+] Files packaged: {file_list}")
    print(f"[+] Xposed entrypoint verified in DEX: {init_content}")
    print(f"[+] Binary AXML header: {manifest_bytes[:4].hex()} (VALID)")
    print(f"[+] PackagingValidator assertion: PASSED")
    return TARGET_APK


if __name__ == "__main__":
    build_apk()
