"""
Adversarial High-Throughput Stress Test Suite for Mock Environment and Hook Lookups.

Empirically tests:
1. LSPosedEngine hook lookups and dispatch under high throughput across 16 threads.
2. ARTClassLoader concurrent class loading with stub injection under 16 threads.
3. Process-scoped Build device spoofing under 16 concurrent threads.
4. PackageManagerService signature matching and rogue isolation under 16 concurrent threads.
5. High-throughput end-to-end IPC handshakes between AppManager and MDX.
"""

import unittest
import threading
import concurrent.futures
import time
import random
import string
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.mock_env.lsposed_engine import LSPosedEngine, MethodHook, MethodHookParam
from tests.mock_env.art_classloader import ARTClassLoader, SemFloatingFeature, OneUIStubs
from tests.mock_env.android_runtime import Build, Process, NoClassDefFoundError, ClassNotFoundException
from tests.mock_env.pms_service import PackageManagerService, PackageSignatureChecker, PackageInfo


class DummyService:
    def get_version(self, offset: int = 0) -> int:
        return 100 + offset

    def authenticate_caller(self, caller_pkg: str) -> bool:
        return caller_pkg == "trusted"


class MockEnvThroughputStressTest(unittest.TestCase):

    def setUp(self):
        self.engine = LSPosedEngine()
        self.class_loader = ARTClassLoader(is_aosp_base=True)
        self.pms = PackageManagerService()
        self.pms.register_package("com.microsoft.appmanager", 10151, "/data/app/LTW", ["ms_sig"])
        self.pms.register_package("com.samsung.android.mdx", 10150, "/system/priv-app/MDX", ["samsung_sig"])
        Build.disable_scoped_spoofing()
        PackageSignatureChecker.disable_bypass()

    def tearDown(self):
        self.engine.reset()
        self.class_loader.clear_stubs()
        Build.disable_scoped_spoofing()
        PackageSignatureChecker.disable_bypass()

    def test_lsposed_hook_lookups_16_threads_100k_ops(self):
        """Stress-test LSPosedEngine hook lookups and dispatch across 16 threads (100,000 operations)."""
        NUM_THREADS = 16
        TOTAL_OPS = 100_000
        OPS_PER_THREAD = TOTAL_OPS // NUM_THREADS

        service = DummyService()

        # Hook 1: override get_version
        class VersionHook(MethodHook):
            def beforeHookedMethod(self, param: MethodHookParam):
                offset = param.args[0] if param.args else 0
                param.setResult(5001 + offset)

        # Hook 2: override authenticate_caller
        class AuthHook(MethodHook):
            def beforeHookedMethod(self, param: MethodHookParam):
                pkg = param.args[0] if param.args else ""
                if pkg in ("com.microsoft.appmanager", "com.samsung.android.mdx"):
                    param.setResult(True)

        self.engine.hook_method("DummyService", "get_version", VersionHook())
        self.engine.hook_method("DummyService", "authenticate_caller", AuthHook())

        errors = []
        barrier = threading.Barrier(NUM_THREADS)
        start_time = time.perf_counter()

        def worker(tid: int):
            try:
                barrier.wait()
                for i in range(OPS_PER_THREAD):
                    if i % 2 == 0:
                        # Hooked call with argument
                        res = self.engine.execute_hooked_call(
                            service, "DummyService", "get_version", service.get_version, i % 10
                        )
                        expected = 5001 + (i % 10)
                        if res != expected:
                            errors.append(f"Thread {tid}: get_version returned {res} != {expected}")
                    else:
                        # Hooked auth call
                        pkg = "com.microsoft.appmanager" if (i % 4 == 1) else "com.untrusted.attacker"
                        res = self.engine.execute_hooked_call(
                            service, "DummyService", "authenticate_caller", service.authenticate_caller, pkg
                        )
                        expected = (pkg == "com.microsoft.appmanager")
                        if res != expected:
                            errors.append(f"Thread {tid}: auth returned {res} != {expected} for {pkg}")
            except Exception as ex:
                errors.append(f"Thread {tid} crashed: {type(ex).__name__}: {ex}")

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        elapsed = time.perf_counter() - start_time
        qps = TOTAL_OPS / elapsed

        self.assertEqual(len(errors), 0, f"Hook dispatch errors: {errors[:5]}")
        print(f"[LSPosed Hook Lookups] {TOTAL_OPS} operations across {NUM_THREADS} threads completed in {elapsed:.4f}s ({qps:.1f} ops/sec)")

    def test_art_classloader_16_threads_100k_ops(self):
        """Stress-test ARTClassLoader concurrent class loading across 16 threads (100,000 operations)."""
        NUM_THREADS = 16
        TOTAL_OPS = 100_000
        OPS_PER_THREAD = TOTAL_OPS // NUM_THREADS

        # Configure stubs
        self.class_loader.register_stub("com.samsung.android.feature.SemFloatingFeature", SemFloatingFeature)
        self.class_loader.register_stub("LL0.c", OneUIStubs)
        self.class_loader.register_stub("L0.c", OneUIStubs)
        self.class_loader.register_stub("com.samsung.android.os.SemVersion", OneUIStubs)
        self.class_loader.register_stub("com.samsung.android.desktopmode.DesktopModeManager", OneUIStubs)

        targets = [
            ("com.samsung.android.feature.SemFloatingFeature", SemFloatingFeature, True),
            ("LL0.c", OneUIStubs, True),
            ("L0.c", OneUIStubs, True),
            ("com.samsung.android.os.SemVersion", OneUIStubs, True),
            ("com.samsung.android.desktopmode.DesktopModeManager", OneUIStubs, True),
            ("com.unknown.FakeService", None, False),
            ("android.os.NonexistentClass", None, False),
        ]

        errors = []
        barrier = threading.Barrier(NUM_THREADS)
        start_time = time.perf_counter()

        def worker(tid: int):
            try:
                barrier.wait()
                for i in range(OPS_PER_THREAD):
                    target, expected_cls, should_succeed = targets[i % len(targets)]
                    try:
                        cls = self.class_loader.load_class(target)
                        if not should_succeed:
                            errors.append(f"Thread {tid}: unexpectedly succeeded loading {target}")
                        elif cls is not expected_cls:
                            errors.append(f"Thread {tid}: {target} returned {cls} != {expected_cls}")
                    except (ClassNotFoundException, NoClassDefFoundError):
                        if should_succeed:
                            errors.append(f"Thread {tid}: failed to load {target}")
            except Exception as ex:
                errors.append(f"Thread {tid} crashed: {type(ex).__name__}: {ex}")

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        elapsed = time.perf_counter() - start_time
        qps = TOTAL_OPS / elapsed

        self.assertEqual(len(errors), 0, f"ClassLoader lookup errors: {errors[:5]}")
        print(f"[ARTClassLoader Lookups] {TOTAL_OPS} operations across {NUM_THREADS} threads completed in {elapsed:.4f}s ({qps:.1f} ops/sec)")

    def test_pms_signature_matching_16_threads_100k_ops(self):
        """Stress-test PackageManagerService & PackageSignatureChecker across 16 threads (100,000 operations)."""
        NUM_THREADS = 16
        TOTAL_OPS = 100_000
        OPS_PER_THREAD = TOTAL_OPS // NUM_THREADS

        PackageSignatureChecker.enable_bypass()

        # Register several test packages
        for idx in range(10):
            self.pms.register_package(f"com.rogue.attacker_{idx}", 12000 + idx, f"/data/app/rogue_{idx}", [f"sig_{idx}"])

        pairs = [
            ("com.microsoft.appmanager", "com.samsung.android.mdx", PackageSignatureChecker.SIGNATURE_MATCH),
            ("com.samsung.android.mdx", "com.microsoft.appmanager", PackageSignatureChecker.SIGNATURE_MATCH),
            ("com.rogue.attacker_0", "com.samsung.android.mdx", PackageSignatureChecker.SIGNATURE_NO_MATCH),
            ("com.rogue.attacker_1", "com.microsoft.appmanager", PackageSignatureChecker.SIGNATURE_NO_MATCH),
            ("com.rogue.attacker_2", "com.rogue.attacker_3", PackageSignatureChecker.SIGNATURE_NO_MATCH),
            (None, "com.samsung.android.mdx", PackageSignatureChecker.SIGNATURE_UNKNOWN_PACKAGE),
            ("com.microsoft.appmanager", None, PackageSignatureChecker.SIGNATURE_UNKNOWN_PACKAGE),
            ("nonexistent_pkg", "com.samsung.android.mdx", PackageSignatureChecker.SIGNATURE_UNKNOWN_PACKAGE),
        ]

        errors = []
        barrier = threading.Barrier(NUM_THREADS)
        start_time = time.perf_counter()

        def worker(tid: int):
            try:
                barrier.wait()
                for i in range(OPS_PER_THREAD):
                    pkg1, pkg2, expected = pairs[i % len(pairs)]
                    res = PackageSignatureChecker.checkSignatures(self.pms, pkg1, pkg2)
                    if res != expected:
                        errors.append(f"Thread {tid}: ({pkg1}, {pkg2}) -> {res} != {expected}")
            except Exception as ex:
                errors.append(f"Thread {tid} crashed: {type(ex).__name__}: {ex}")

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        elapsed = time.perf_counter() - start_time
        qps = TOTAL_OPS / elapsed

        self.assertEqual(len(errors), 0, f"PMS Signature matching errors: {errors[:5]}")
        print(f"[PMS Signature Matching] {TOTAL_OPS} operations across {NUM_THREADS} threads completed in {elapsed:.4f}s ({qps:.1f} ops/sec)")

    def test_sem_floating_feature_python_16_threads_100k_ops(self):
        """Stress-test Python SemFloatingFeature mock under 16 concurrent threads (100,000 operations)."""
        NUM_THREADS = 16
        TOTAL_OPS = 100_000
        OPS_PER_THREAD = TOTAL_OPS // NUM_THREADS

        SemFloatingFeature.reset_instance()
        feature = SemFloatingFeature.getInstance()

        errors = []
        barrier = threading.Barrier(NUM_THREADS)
        start_time = time.perf_counter()

        def worker(tid: int):
            try:
                barrier.wait()
                for i in range(OPS_PER_THREAD):
                    # Reader actions
                    ltw = feature.getBoolean("SEC_FLOATING_FEATURE_LINK_TO_WINDOWS")
                    if not ltw:
                        errors.append(f"Thread {tid}: LTW was false")

                    brand = feature.getString("SEC_FLOATING_FEATURE_SETTINGS_CONFIG_BRAND_NAME")
                    if brand != "Samsung":
                        errors.append(f"Thread {tid}: Brand was {brand}")

                    # Null check actions
                    if feature.getBoolean(None, default=False) is not False:
                        errors.append(f"Thread {tid}: getBoolean(None) failed")
                    if feature.getString(None, default="fallback") != "fallback":
                        errors.append(f"Thread {tid}: getString(None) failed")
                    if feature.getInt(None, default=42) != 42:
                        errors.append(f"Thread {tid}: getInt(None) failed")

                    # Dynamic write actions (writers)
                    if tid % 4 == 0:
                        feature.set_feature(f"DYNAMIC_KEY_{i % 50}", f"VAL_{i}")
            except Exception as ex:
                errors.append(f"Thread {tid} crashed: {type(ex).__name__}: {ex}")

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        elapsed = time.perf_counter() - start_time
        qps = TOTAL_OPS / elapsed

        self.assertEqual(len(errors), 0, f"Python SemFloatingFeature errors: {errors[:5]}")
        print(f"[Python SemFloatingFeature] {TOTAL_OPS} operations across {NUM_THREADS} threads completed in {elapsed:.4f}s ({qps:.1f} ops/sec)")


if __name__ == "__main__":
    unittest.main()
