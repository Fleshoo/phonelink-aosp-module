#!/usr/bin/env python3
"""
Challenger Empirical Stress Test Suite for Milestone M2:
Empirically stress-tests:
1. Magisk lifecycle & PMS boot synchronization in service.sh
   (sys.boot_completed delay, 120s timeout, PMS wait, corrupt properties).
2. Duplicate package uninstallation logic in customize.sh
   (/data/app vs /system/priv-app, split APKs, path boundaries, arch & API checks).
3. Concurrent AppOps commands and permission grants
   (high-concurrency thread safety, state consistency, privileged vs runtime permissions).
4. Error resilience and absence of unhandled states.
"""

import os
import sys
import time
import shutil
import tempfile
import threading
import subprocess
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.mock_env.pms_service import PackageManagerService, PackageInfo
from tests.mock_env.android_runtime import SecurityException, ApplicationInfo


BASH_PATH = r"C:\Program Files\Git\bin\bash.exe"
SERVICE_SH_PATH = PROJECT_ROOT / "magisk_module" / "service.sh"
CUSTOMIZE_SH_PATH = PROJECT_ROOT / "magisk_module" / "customize.sh"


class MockAndroidEnvironment:
    """
    Creates an isolated sandbox on disk with state files and in-memory shell functions
    for getprop, pm, appops, dumpsys, am, settings, device_config, magiskpolicy, sleep.
    """

    def __init__(self):
        self.temp_dir = tempfile.mkdtemp(prefix="phonelink_m2_stress_")
        self.data_dir = os.path.join(self.temp_dir, "data", "local", "tmp")
        self.state_dir = os.path.join(self.temp_dir, "state")
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.state_dir, exist_ok=True)

        # Default state files
        self.boot_completed_file = os.path.join(self.state_dir, "boot_completed")
        self.pm_list_file = os.path.join(self.state_dir, "pm_packages")
        self.pm_path_file = os.path.join(self.state_dir, "pm_path")
        self.invocations_log = os.path.join(self.state_dir, "commands.log")
        self.sleep_log = os.path.join(self.state_dir, "sleep.log")

        # Set default states
        self.set_boot_completed("1")
        self.set_packages(["com.samsung.android.mdx", "com.microsoft.appmanager"])
        self.set_pm_path("")

    def set_boot_completed(self, val: str):
        with open(self.boot_completed_file, "w", encoding="utf-8") as f:
            f.write(val)

    def set_packages(self, pkgs: List[str]):
        with open(self.pm_list_file, "w", encoding="utf-8") as f:
            for p in pkgs:
                f.write(f"package:{p}\n")

    def set_pm_path(self, path_output: str):
        with open(self.pm_path_file, "w", encoding="utf-8") as f:
            f.write(path_output)

    def get_invocations(self) -> List[str]:
        if not os.path.exists(self.invocations_log):
            return []
        with open(self.invocations_log, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]

    def get_sleeps(self) -> List[str]:
        if not os.path.exists(self.sleep_log):
            return []
        with open(self.sleep_log, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]

    def cleanup(self):
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass


class TestMagiskServiceLifecycleStress(unittest.TestCase):
    """
    Stress-tests service.sh boot synchronization, timeout handling,
    and resilience against delayed or corrupt PMS/property states.
    """

    def setUp(self):
        self.env = MockAndroidEnvironment()

    def tearDown(self):
        self.env.cleanup()

    def run_service_sh(
        self,
        log_path_override: Optional[str] = None,
        custom_getprop_body: Optional[str] = None,
        custom_pm_body: Optional[str] = None,
    ) -> Tuple[int, str, str, str]:
        """
        Executes service.sh in the sandboxed mock environment via bash using in-memory functions.
        Returns (exit_code, stdout, stderr, logfile_content).
        """
        target_log = log_path_override or os.path.join(self.env.data_dir, "phonelink_service.log")
        target_log_posix = target_log.replace(os.sep, "/")
        sleep_log_posix = self.env.sleep_log.replace(os.sep, "/")
        invocations_posix = self.env.invocations_log.replace(os.sep, "/")
        boot_file_posix = self.env.boot_completed_file.replace(os.sep, "/")
        pm_list_posix = self.env.pm_list_file.replace(os.sep, "/")

        getprop_logic = custom_getprop_body or f"""
    if [ "$1" = "sys.boot_completed" ]; then
        if [ -f "{boot_file_posix}" ]; then
            cat "{boot_file_posix}"
        else
            echo "0"
        fi
    else
        echo ""
    fi
"""

        pm_logic = custom_pm_body or f"""
    echo "pm $@" >> "{invocations_posix}"
    if [ "$1" = "list" ] && [ "$2" = "packages" ]; then
        if [ -f "{pm_list_posix}" ]; then
            cat "{pm_list_posix}"
        fi
        return 0
    elif [ "$1" = "grant" ]; then
        return 0
    elif [ "$1" = "uninstall" ]; then
        return 0
    fi
    return 0
"""

        # Read original service.sh and substitute LOGFILE path so it logs into our test sandbox
        with open(SERVICE_SH_PATH, "r", encoding="utf-8") as f:
            service_body = f.read()

        service_body = service_body.replace(
            'LOGFILE="/data/local/tmp/phonelink_service.log"',
            f'LOGFILE="{target_log_posix}"'
        )

        wrapper = f"""#!/bin/sh
# Fast-forward in-memory shell mocks
sleep() {{
    echo "sleep $1" >> "{sleep_log_posix}"
    return 0
}}
getprop() {{
{getprop_logic}
}}
pm() {{
{pm_logic}
}}
appops() {{
    echo "appops $@" >> "{invocations_posix}"
    return 0
}}
dumpsys() {{
    echo "dumpsys $@" >> "{invocations_posix}"
    return 0
}}
am() {{
    echo "am $@" >> "{invocations_posix}"
    return 0
}}
settings() {{
    echo "settings $@" >> "{invocations_posix}"
    return 0
}}
device_config() {{
    echo "device_config $@" >> "{invocations_posix}"
    return 0
}}
magiskpolicy() {{
    echo "magiskpolicy $@" >> "{invocations_posix}"
    return 0
}}

# Execute modified service.sh body inline
{service_body}
"""

        test_script_path = os.path.join(self.env.temp_dir, "run_service.sh")
        with open(test_script_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(wrapper)

        posix_script_path = test_script_path.replace(os.sep, "/")
        cmd = [BASH_PATH, "-c", f'sh "{posix_script_path}"']

        proc = subprocess.run(cmd, capture_output=True, text=True)

        logfile_content = ""
        if os.path.exists(target_log):
            with open(target_log, "r", encoding="utf-8") as f:
                logfile_content = f.read()

        return proc.returncode, proc.stdout, proc.stderr, logfile_content

    def test_boot_completed_immediate(self):
        """When sys.boot_completed is 1 at t=0, service.sh continues immediately and exits 0."""
        self.env.set_boot_completed("1")
        code, stdout, stderr, log = self.run_service_sh()
        self.assertEqual(code, 0, f"Expected 0, got {code}. stderr: {stderr}")
        self.assertIn("Phone Link service.sh starting", log)
        self.assertIn("Android boot completed. Initializing services", log)
        self.assertIn("Phone Link service.sh completed successfully", log)

    def test_boot_completed_delay_below_timeout(self):
        """
        Simulate boot delay: sys.boot_completed remains 0 for 5 polls (10s), then becomes 1.
        Verifies that loop polls correctly and proceeds once completed.
        """
        counter_file = os.path.join(self.env.state_dir, "poll_counter")
        with open(counter_file, "w") as f:
            f.write("0")
        counter_posix = counter_file.replace(os.sep, "/")

        custom_getprop = f"""
    if [ "$1" = "sys.boot_completed" ]; then
        CNT=$(cat "{counter_posix}")
        CNT=$((CNT + 1))
        echo "$CNT" > "{counter_posix}"
        if [ "$CNT" -ge 5 ]; then
            echo "1"
        else
            echo "0"
        fi
    else
        echo ""
    fi
"""
        code, stdout, stderr, log = self.run_service_sh(custom_getprop_body=custom_getprop)
        self.assertEqual(code, 0)
        self.assertIn("Android boot completed. Initializing services", log)
        self.assertIn("Phone Link service.sh completed successfully", log)

        # Verify sleeps occurred
        sleeps = self.env.get_sleeps()
        boot_sleeps = [s for s in sleeps if s == "sleep 2"]
        self.assertGreaterEqual(len(boot_sleeps), 4)

    def test_boot_completed_timeout_120s(self):
        """
        Simulate boot hang: sys.boot_completed is NEVER 1.
        service.sh must time out after exactly 120 seconds (60 iterations),
        log 'Timed out waiting for sys.boot_completed.', and exit with code 1.
        """
        self.env.set_boot_completed("0")
        code, stdout, stderr, log = self.run_service_sh()
        self.assertEqual(code, 1, f"Expected timeout exit code 1, got {code}")
        self.assertIn("Timed out waiting for sys.boot_completed", log)
        self.assertNotIn("Android boot completed", log)
        self.assertNotIn("Phone Link service.sh completed successfully", log)

        # Verify exactly 60 sleep iterations occurred (60 * 2s = 120s)
        sleeps = self.env.get_sleeps()
        boot_sleeps = [s for s in sleeps if s == "sleep 2"]
        self.assertEqual(len(boot_sleeps), 60)

    def test_boot_completed_adversarial_property_outputs(self):
        """
        Adversarial test: getprop returns unexpected, empty, or corrupt values:
        '', 'unknown', 'false', '0\\n', '-1', '2'.
        Ensures quotes prevent shell syntax crash and loops safely until timeout.
        """
        adversarial_values = ["", "unknown", "false", "-1", "2", "running", " \t "]
        for val in adversarial_values:
            with self.subTest(val=val):
                self.env.set_boot_completed(val)
                code, stdout, stderr, log = self.run_service_sh()
                self.assertEqual(code, 1)
                self.assertIn("Timed out waiting for sys.boot_completed", log)
                self.assertEqual(stderr.strip(), "")

    def test_pms_registration_delay(self):
        """
        Simulate PMS package scan delay: com.samsung.android.mdx is absent for
        first 3 polls (6s), then appears in pm list packages.
        """
        counter_file = os.path.join(self.env.state_dir, "pms_counter")
        with open(counter_file, "w") as f:
            f.write("0")
        counter_posix = counter_file.replace(os.sep, "/")

        custom_pm = f"""
    if [ "$1" = "list" ] && [ "$2" = "packages" ]; then
        CNT=$(cat "{counter_posix}")
        CNT=$((CNT + 1))
        echo "$CNT" > "{counter_posix}"
        if [ "$CNT" -ge 4 ]; then
            echo "package:com.samsung.android.mdx"
        else
            echo "package:com.google.android.gms"
        fi
        return 0
    fi
    return 0
"""
        code, stdout, stderr, log = self.run_service_sh(custom_pm_body=custom_pm)
        self.assertEqual(code, 0)
        self.assertIn("Confirmed com.samsung.android.mdx registered in PackageManagerService", log)

    def test_pms_registration_timeout_30s_graceful_continuation(self):
        """
        Simulate PMS never finding com.samsung.android.mdx within 30s.
        service.sh must log warning:
        'Warning: com.samsung.android.mdx not yet found in pm list packages.'
        and continue without crashing, exiting 0.
        """
        self.env.set_packages(["com.android.systemui", "com.google.android.gms"])
        code, stdout, stderr, log = self.run_service_sh()
        self.assertEqual(code, 0)
        self.assertIn("Warning: com.samsung.android.mdx not yet found in pm list packages", log)
        self.assertIn("Phone Link service.sh completed successfully", log)

    def test_complete_privilege_and_appops_execution(self):
        """
        Verify that all commands in service.sh are issued with exact parameters:
        - 9 pm grants for MDX
        - 4 pm grants for MS AppManager
        - 6 appops for MDX
        - 3 appops for MS AppManager
        - deviceidle whitelist
        - standby-bucket active
        - phantom process monitor disabled
        - live sepolicy applied
        """
        self.env.set_boot_completed("1")
        self.env.set_packages(["com.samsung.android.mdx", "com.microsoft.appmanager"])

        code, stdout, stderr, log = self.run_service_sh()
        self.assertEqual(code, 0)

        invocations = self.env.get_invocations()

        # Check MDX permissions
        expected_mdx_perms = [
            "android.permission.RECORD_AUDIO",
            "android.permission.BLUETOOTH_CONNECT",
            "android.permission.BLUETOOTH_SCAN",
            "android.permission.BLUETOOTH_ADVERTISE",
            "android.permission.POST_NOTIFICATIONS",
            "android.permission.READ_PHONE_STATE",
            "android.permission.BATTERY_STATS",
            "android.permission.WRITE_SECURE_SETTINGS",
            "android.permission.INTERACT_ACROSS_USERS",
        ]
        for perm in expected_mdx_perms:
            self.assertTrue(
                any(f"pm grant com.samsung.android.mdx {perm}" in inv for inv in invocations),
                f"Missing pm grant for MDX perm {perm}"
            )

        # Check MS permissions
        expected_ms_perms = [
            "android.permission.POST_NOTIFICATIONS",
            "android.permission.BLUETOOTH_CONNECT",
            "android.permission.BLUETOOTH_SCAN",
            "android.permission.READ_PHONE_STATE",
        ]
        for perm in expected_ms_perms:
            self.assertTrue(
                any(f"pm grant com.microsoft.appmanager {perm}" in inv for inv in invocations),
                f"Missing pm grant for MS perm {perm}"
            )

        # Check MDX AppOps
        expected_mdx_appops = [
            "SYSTEM_ALERT_WINDOW allow",
            "RECORD_AUDIO allow",
            "PROJECT_MEDIA allow",
            "LEGACY_STORAGE allow",
            "RUN_IN_BACKGROUND allow",
            "RUN_ANY_IN_BACKGROUND allow",
        ]
        for op in expected_mdx_appops:
            self.assertTrue(
                any(f"appops set com.samsung.android.mdx {op}" in inv for inv in invocations),
                f"Missing appops for MDX op {op}"
            )

        # Check MS AppOps
        expected_ms_appops = [
            "SYSTEM_ALERT_WINDOW allow",
            "RUN_IN_BACKGROUND allow",
            "RUN_ANY_IN_BACKGROUND allow",
        ]
        for op in expected_ms_appops:
            self.assertTrue(
                any(f"appops set com.microsoft.appmanager {op}" in inv for inv in invocations),
                f"Missing appops for MS op {op}"
            )

        # Check Doze whitelist & standby bucket
        self.assertTrue(any("dumpsys deviceidle whitelist +com.samsung.android.mdx" in inv for inv in invocations))
        self.assertTrue(any("dumpsys deviceidle whitelist +com.microsoft.appmanager" in inv for inv in invocations))
        self.assertTrue(any("am set-standby-bucket com.samsung.android.mdx active" in inv for inv in invocations))
        self.assertTrue(any("am set-standby-bucket com.microsoft.appmanager active" in inv for inv in invocations))

        # Check Phantom process settings
        self.assertTrue(any("settings put global settings_enable_monitor_phantom_procs false" in inv for inv in invocations))
        self.assertTrue(any("device_config put activity_manager max_phantom_processes 2147483647" in inv for inv in invocations))

        # Check live SELinux policies
        self.assertTrue(any("magiskpolicy --live allow priv_app uhid_device" in inv for inv in invocations))
        self.assertTrue(any("magiskpolicy --live allow priv_app input_service" in inv for inv in invocations))


class TestCustomizeDuplicateHandlingStress(unittest.TestCase):
    """
    Stress-tests duplicate package uninstallation and validation logic in customize.sh
    across various /data/app vs /system/priv-app path formats and boundary conditions.
    """

    def setUp(self):
        self.env = MockAndroidEnvironment()
        self.modpath = os.path.join(self.env.temp_dir, "modpath")
        self._setup_mock_modpath()

    def tearDown(self):
        self.env.cleanup()

    def _setup_mock_modpath(self):
        os.makedirs(os.path.join(self.modpath, "system", "priv-app", "LinkToWindowsService"), exist_ok=True)
        os.makedirs(os.path.join(self.modpath, "system", "etc", "permissions"), exist_ok=True)
        os.makedirs(os.path.join(self.modpath, "system", "etc", "sysconfig"), exist_ok=True)

        with open(os.path.join(self.modpath, "system", "priv-app", "LinkToWindowsService", "LinkToWindowsService.apk"), "wb") as f:
            f.write(b"APK_DUMMY")
        with open(os.path.join(self.modpath, "system", "etc", "permissions", "privapp-permissions-phonelink.xml"), "w") as f:
            f.write("<permissions/>")
        with open(os.path.join(self.modpath, "system", "etc", "permissions", "com.samsung.feature.samsung_experience_mobile.xml"), "w") as f:
            f.write("<permissions/>")
        with open(os.path.join(self.modpath, "system", "etc", "sysconfig", "phonelink-whitelist.xml"), "w") as f:
            f.write("<config/>")

        with open(os.path.join(self.modpath, "service.sh"), "w") as f:
            f.write("#!/bin/sh\n")
        with open(os.path.join(self.modpath, "uninstall.sh"), "w") as f:
            f.write("#!/bin/sh\n")
        with open(os.path.join(self.modpath, "post-fs-data.sh"), "w") as f:
            f.write("#!/bin/sh\n")

    def run_customize_sh(self, arch: str = "arm64", api: int = 36) -> Tuple[int, str, str]:
        """Runs customize.sh in bash with Magisk environment variables."""
        test_script_path = os.path.join(self.env.temp_dir, "run_customize.sh")
        invocations_posix = self.env.invocations_log.replace(os.sep, "/")
        pm_path_posix = self.env.pm_path_file.replace(os.sep, "/")

        # Create wrapper that defines Magisk utility functions
        wrapper = f"""#!/bin/sh
ui_print() {{
    echo "$@"
}}
abort() {{
    echo "! ABORT: $@" >&2
    exit 1
}}
set_perm() {{
    echo "set_perm $@"
}}
set_perm_recursive() {{
    echo "set_perm_recursive $@"
}}
pm() {{
    echo "pm $@" >> "{invocations_posix}"
    if [ "$1" = "path" ]; then
        if [ -f "{pm_path_posix}" ]; then
            CONTENT=$(cat "{pm_path_posix}")
            if [ -n "$CONTENT" ]; then
                echo "$CONTENT"
                return 0
            else
                return 1
            fi
        fi
        return 1
    elif [ "$1" = "uninstall" ]; then
        return 0
    fi
    return 0
}}

ARCH="{arch}"
API="{api}"
MODPATH="{self.modpath.replace(os.sep, '/')}"

. "{str(CUSTOMIZE_SH_PATH).replace(os.sep, '/')}"
"""
        with open(test_script_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(wrapper)

        posix_script_path = test_script_path.replace(os.sep, "/")
        cmd = [BASH_PATH, "-c", f'sh "{posix_script_path}"']

        proc = subprocess.run(cmd, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def test_clean_install_no_existing_package(self):
        """When pm path returns empty, pm uninstall is NOT called."""
        self.env.set_pm_path("")
        code, stdout, stderr = self.run_customize_sh()
        self.assertEqual(code, 0, f"Failed with: {stderr}")
        self.assertNotIn("Removing user-space APK", stdout)

        invocations = self.env.get_invocations()
        self.assertFalse(any("pm uninstall" in inv for inv in invocations))

    def test_user_space_data_app_uninstalled(self):
        """When pm path is under /data/app, pm uninstall is triggered."""
        user_path = "package:/data/app/~~u8w7e6r5t4==/com.samsung.android.mdx-abcdefg==/base.apk"
        self.env.set_pm_path(user_path)
        code, stdout, stderr = self.run_customize_sh()
        self.assertEqual(code, 0)
        self.assertIn("Found user-installed com.samsung.android.mdx at: /data/app/", stdout)
        self.assertIn("Removing user-space APK to enable privileged system overlay", stdout)

        invocations = self.env.get_invocations()
        self.assertTrue(any("pm uninstall com.samsung.android.mdx" in inv for inv in invocations))

    def test_user_space_legacy_format_uninstalled(self):
        """Older AOSP format: package:/data/app/com.samsung.android.mdx-1/base.apk."""
        user_path = "package:/data/app/com.samsung.android.mdx-1/base.apk"
        self.env.set_pm_path(user_path)
        code, stdout, stderr = self.run_customize_sh()
        self.assertEqual(code, 0)
        invocations = self.env.get_invocations()
        self.assertTrue(any("pm uninstall com.samsung.android.mdx" in inv for inv in invocations))

    def test_user_space_split_apks_uninstalled(self):
        """Split APKs in /data/app (multiple lines)."""
        user_path = "package:/data/app/~~split/com.samsung.android.mdx-1/base.apk\npackage:/data/app/~~split/com.samsung.android.mdx-1/split_config.arm64_v8a.apk"
        self.env.set_pm_path(user_path)
        code, stdout, stderr = self.run_customize_sh()
        self.assertEqual(code, 0)
        invocations = self.env.get_invocations()
        self.assertTrue(any("pm uninstall com.samsung.android.mdx" in inv for inv in invocations))

    def test_system_privapp_overlay_NOT_uninstalled(self):
        """
        When package is in /system/priv-app (system partition),
        customize.sh MUST NOT uninstall it!
        """
        system_path = "package:/system/priv-app/LinkToWindowsService/LinkToWindowsService.apk"
        self.env.set_pm_path(system_path)
        code, stdout, stderr = self.run_customize_sh()
        self.assertEqual(code, 0)
        self.assertNotIn("Removing user-space APK", stdout)
        invocations = self.env.get_invocations()
        self.assertFalse(any("pm uninstall" in inv for inv in invocations))

    def test_product_privapp_NOT_uninstalled(self):
        """When package is in /product/priv-app, MUST NOT uninstall."""
        prod_path = "package:/product/priv-app/LinkToWindowsService/LinkToWindowsService.apk"
        self.env.set_pm_path(prod_path)
        code, stdout, stderr = self.run_customize_sh()
        self.assertEqual(code, 0)
        invocations = self.env.get_invocations()
        self.assertFalse(any("pm uninstall" in inv for inv in invocations))

    def test_adversarial_path_with_data_inside_system(self):
        """
        Path containing 'data' but not starting with '/data/':
        package:/system/priv-app/data_service/LinkToWindowsService.apk.
        Regex ^/data/ must NOT match!
        """
        tricky_path = "package:/system/priv-app/data_service/LinkToWindowsService.apk"
        self.env.set_pm_path(tricky_path)
        code, stdout, stderr = self.run_customize_sh()
        self.assertEqual(code, 0)
        invocations = self.env.get_invocations()
        self.assertFalse(any("pm uninstall" in inv for inv in invocations))

    def test_architecture_validation(self):
        """ARCH != arm64 must trigger abort."""
        for invalid_arch in ["arm", "x86", "x86_64", "", "mips"]:
            with self.subTest(arch=invalid_arch):
                code, stdout, stderr = self.run_customize_sh(arch=invalid_arch)
                self.assertNotEqual(code, 0)
                self.assertIn("Architecture check failed", stderr)

    def test_api_validation(self):
        """API < 33 must trigger abort."""
        for invalid_api in [32, 31, 30, 28, 0]:
            with self.subTest(api=invalid_api):
                code, stdout, stderr = self.run_customize_sh(api=invalid_api)
                self.assertNotEqual(code, 0)
                self.assertIn("Android API level too low", stderr)

    def test_missing_payload_apk_aborts(self):
        """Missing LinkToWindowsService.apk must abort."""
        apk_path = os.path.join(self.modpath, "system", "priv-app", "LinkToWindowsService", "LinkToWindowsService.apk")
        os.remove(apk_path)
        code, stdout, stderr = self.run_customize_sh()
        self.assertNotEqual(code, 0)
        self.assertIn("Installation payload incomplete", stderr)


class MockAppOpsService:
    """Thread-safe simulation of Android AppOpsService."""

    VALID_OPS = {
        "SYSTEM_ALERT_WINDOW",
        "RECORD_AUDIO",
        "PROJECT_MEDIA",
        "LEGACY_STORAGE",
        "RUN_IN_BACKGROUND",
        "RUN_ANY_IN_BACKGROUND",
    }
    VALID_MODES = {"allow", "ignore", "deny", "default"}

    def __init__(self):
        self._lock = threading.Lock()
        self._op_modes: Dict[str, Dict[str, str]] = {}
        self._op_counts: Dict[str, int] = {}

    def set_mode(self, package: str, op: str, mode: str) -> bool:
        if op not in self.VALID_OPS or mode not in self.VALID_MODES:
            return False
        with self._lock:
            if package not in self._op_modes:
                self._op_modes[package] = {}
            self._op_modes[package][op] = mode
            key = f"{package}:{op}"
            self._op_counts[key] = self._op_counts.get(key, 0) + 1
        return True

    def check_op(self, package: str, op: str) -> str:
        with self._lock:
            return self._op_modes.get(package, {}).get(op, "default")

    def get_count(self, package: str, op: str) -> int:
        with self._lock:
            return self._op_counts.get(f"{package}:{op}", 0)


class TestConcurrentAppOpsAndPermissions(unittest.TestCase):
    """
    Stress-tests concurrent AppOps operations, multithreaded permission grants,
    and permission model boundary invariants.
    """

    def setUp(self):
        self.appops = MockAppOpsService()
        self.pms = PackageManagerService()
        self.pms.load_privapp_permissions_xml("""
        <permissions>
            <privapp-permissions package="com.samsung.android.mdx">
                <permission name="android.permission.WRITE_SECURE_SETTINGS"/>
                <permission name="android.permission.INTERACT_ACROSS_USERS"/>
                <permission name="android.permission.BATTERY_STATS"/>
                <permission name="android.permission.CAPTURE_VIDEO_OUTPUT"/>
            </privapp-permissions>
            <privapp-permissions package="com.microsoft.appmanager">
                <permission name="android.permission.WRITE_SECURE_SETTINGS"/>
                <permission name="android.permission.INTERACT_ACROSS_USERS"/>
                <permission name="android.permission.BATTERY_STATS"/>
            </privapp-permissions>
        </permissions>
        """)

        self.pms.register_package(
            "com.samsung.android.mdx",
            uid=10150,
            source_dir="/system/priv-app/LinkToWindowsService/LinkToWindowsService.apk",
            requested_permissions=[
                "android.permission.RECORD_AUDIO",
                "android.permission.BLUETOOTH_CONNECT",
                "android.permission.WRITE_SECURE_SETTINGS",
                "android.permission.INTERACT_ACROSS_USERS",
                "android.permission.BATTERY_STATS",
            ],
        )

        self.pms.register_package(
            "com.microsoft.appmanager",
            uid=10151,
            source_dir="/data/app/LinkToWindows",
            requested_permissions=[
                "android.permission.POST_NOTIFICATIONS",
                "android.permission.BLUETOOTH_CONNECT",
                "android.permission.WRITE_SECURE_SETTINGS",
            ],
        )

    def test_high_concurrency_appops_50_threads(self):
        """
        50 threads performing 5,000 concurrent AppOps set operations.
        Ensures thread safety, zero deadlocks, and consistent state convergence.
        """
        ops = [
            "SYSTEM_ALERT_WINDOW",
            "RECORD_AUDIO",
            "PROJECT_MEDIA",
            "LEGACY_STORAGE",
            "RUN_IN_BACKGROUND",
            "RUN_ANY_IN_BACKGROUND",
        ]
        pkgs = ["com.samsung.android.mdx", "com.microsoft.appmanager"]

        num_threads = 50
        iterations = 100
        errors: List[Exception] = []

        def worker(thread_id: int):
            try:
                for i in range(iterations):
                    op = ops[(thread_id + i) % len(ops)]
                    pkg = pkgs[i % len(pkgs)]
                    success = self.appops.set_mode(pkg, op, "allow")
                    if not success:
                        raise RuntimeError(f"AppOps set failed for {pkg} {op}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Concurrency errors occurred: {errors}")

        # Verify all ops converged to 'allow'
        for pkg in pkgs:
            for op in ops:
                self.assertEqual(self.appops.check_op(pkg, op), "allow")

    def test_concurrent_permission_checks_and_registrations(self):
        """
        Simultaneous threads querying permissions while new packages are registered
        and evaluated by PMS.
        """
        lock = threading.Lock()
        stop_event = threading.Event()
        errors: List[Exception] = []

        def reader():
            while not stop_event.is_set():
                try:
                    with lock:
                        self.pms.check_permission("com.samsung.android.mdx", "android.permission.WRITE_SECURE_SETTINGS")
                        self.pms.check_permission("com.microsoft.appmanager", "android.permission.WRITE_SECURE_SETTINGS")
                except Exception as e:
                    errors.append(e)

        def writer():
            for i in range(200):
                try:
                    with lock:
                        self.pms.register_package(
                            f"com.test.pkg{i}",
                            10300 + i,
                            f"/system/priv-app/Pkg{i}",
                            requested_permissions=["android.permission.WRITE_SECURE_SETTINGS"],
                        )
                except Exception as e:
                    errors.append(e)

        reader_threads = [threading.Thread(target=reader) for _ in range(10)]
        writer_threads = [threading.Thread(target=writer) for _ in range(5)]

        for t in reader_threads + writer_threads:
            t.start()
        for t in writer_threads:
            t.join()

        stop_event.set()
        for t in reader_threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Concurrent PMS errors: {errors}")

    def test_privileged_vs_runtime_permission_semantics(self):
        """
        Verifies that:
        1. Privileged permissions (WRITE_SECURE_SETTINGS) in /system/priv-app/ are granted
           via the privapp-permissions-phonelink.xml whitelist.
        2. Non-privileged /data/app packages requesting WRITE_SECURE_SETTINGS are strictly denied
           even if declared in XML.
        3. Standard/dangerous runtime permissions (RECORD_AUDIO, BLUETOOTH_CONNECT) are granted.
        """
        # MDX in priv-app has WRITE_SECURE_SETTINGS granted
        self.assertTrue(
            self.pms.check_permission("com.samsung.android.mdx", "android.permission.WRITE_SECURE_SETTINGS")
        )
        self.assertTrue(
            self.pms.check_permission("com.samsung.android.mdx", "android.permission.RECORD_AUDIO")
        )

        # MS in /data/app is NOT privileged -> WRITE_SECURE_SETTINGS is DENIED by PMS
        self.assertFalse(
            self.pms.check_permission("com.microsoft.appmanager", "android.permission.WRITE_SECURE_SETTINGS")
        )
        # But runtime permission POST_NOTIFICATIONS is granted
        self.assertTrue(
            self.pms.check_permission("com.microsoft.appmanager", "android.permission.POST_NOTIFICATIONS")
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
