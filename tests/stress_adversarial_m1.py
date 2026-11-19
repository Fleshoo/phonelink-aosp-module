"""
Adversarial Stress Test Suite for Milestone M1
Empirically tests:
1. SemFloatingFeature extreme inputs, type confusion, defaults, and 10,000 concurrent queries.
2. LL0/c / SEM_INT version checks under rapid multi-threaded queries.
3. PackageManager signature matching with rogue packages, malformed package names, empty signatures, and concurrent queries.
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

from tests.mock_env.art_classloader import SemFloatingFeature, ARTClassLoader, OneUIStubs
from tests.mock_env.android_runtime import NoClassDefFoundError, ClassNotFoundException, Process, Build
from tests.mock_env.pms_service import PackageManagerService, PackageSignatureChecker, PackageInfo


class SemFloatingFeatureStressTest(unittest.TestCase):
    def setUp(self):
        SemFloatingFeature.reset_instance()
        self.feature = SemFloatingFeature.getInstance()

    def tearDown(self):
        SemFloatingFeature.reset_instance()

    # -------------------------------------------------------------------------
    # 1. Extreme inputs & Boundary values
    # -------------------------------------------------------------------------
    def test_null_and_empty_keys(self):
        """Test null, None, and empty string keys."""
        # getBoolean
        self.assertFalse(self.feature.getBoolean(None))
        self.assertTrue(self.feature.getBoolean(None, default=True))
        self.assertFalse(self.feature.getBoolean(""))
        self.assertTrue(self.feature.getBoolean("", default=True))

        # getString
        self.assertEqual(self.feature.getString(None), "")
        self.assertEqual(self.feature.getString(None, default="fallback"), "fallback")
        self.assertEqual(self.feature.getString(""), "")
        self.assertEqual(self.feature.getString("", default="fallback"), "fallback")

        # getInt
        self.assertEqual(self.feature.getInt(None), 0)
        self.assertEqual(self.feature.getInt(None, default=99), 99)
        self.assertEqual(self.feature.getInt(""), 0)
        self.assertEqual(self.feature.getInt("", default=99), 99)

    def test_nonexistent_keys(self):
        """Test non-existent keys return appropriate defaults."""
        non_existent = "SEC_FLOATING_FEATURE_TOTALLY_NON_EXISTENT_KEY_12345"
        self.assertFalse(self.feature.getBoolean(non_existent))
        self.assertTrue(self.feature.getBoolean(non_existent, default=True))
        self.assertEqual(self.feature.getString(non_existent), "")
        self.assertEqual(self.feature.getString(non_existent, default="xyz"), "xyz")
        self.assertEqual(self.feature.getInt(non_existent), 0)
        self.assertEqual(self.feature.getInt(non_existent, default=-1), -1)

    def test_extreme_keys_and_values(self):
        """Test huge keys, null bytes, unicode surrogates, format strings."""
        huge_key = "K_" + "A" * 100_000
        huge_val = "V_" + "B" * 100_000
        self.feature.set_feature(huge_key, huge_val)
        self.assertEqual(self.feature.getString(huge_key), huge_val)

        # Null-byte key
        null_byte_key = "SEC_FEATURE\x00INJECTED"
        self.feature.set_feature(null_byte_key, "null_byte_val")
        self.assertEqual(self.feature.getString(null_byte_key), "null_byte_val")

        # Complex unicode, emojis
        emoji_key = "SEC_FEATURE_🚀_🔥_🌟_ключ_тест"
        emoji_val = "Значение_🌟_Привет_Мир"
        self.feature.set_feature(emoji_key, emoji_val)
        self.assertEqual(self.feature.getString(emoji_key), emoji_val)

        # Format strings & SQL injection patterns
        injection_key = "SEC_FEATURE_'%20OR%201=1;--%s%n"
        self.feature.set_feature(injection_key, "%s%s%d")
        self.assertEqual(self.feature.getString(injection_key), "%s%s%d")

    def test_type_confusion_resilience(self):
        """Test type confusion resilience when values have unexpected types."""
        # Key contains string "true" / "false" / "not_bool"
        self.feature.set_feature("TAG_STR_TRUE", "true")
        self.feature.set_feature("TAG_STR_FALSE", "false")
        self.feature.set_feature("TAG_STR_TEXT", "some random string")
        self.feature.set_feature("TAG_INT_ZERO", 0)
        self.feature.set_feature("TAG_INT_ONE", 1)
        self.feature.set_feature("TAG_FLOAT", 3.14159)
        self.feature.set_feature("TAG_LIST", [1, 2, 3])
        self.feature.set_feature("TAG_NONE", None)

        # getInt on non-numeric strings
        self.assertEqual(self.feature.getInt("TAG_STR_TEXT", default=42), 42)
        # getInt on float
        self.assertEqual(self.feature.getInt("TAG_FLOAT", default=0), 3)
        # getInt on None
        self.assertEqual(self.feature.getInt("TAG_NONE", default=999), 999)
        # getInt on list
        self.assertEqual(self.feature.getInt("TAG_LIST", default=-1), -1)

        # getString on non-string types
        self.assertEqual(self.feature.getString("TAG_INT_ONE"), "1")
        self.assertEqual(self.feature.getString("TAG_FLOAT"), "3.14159")
        self.assertEqual(self.feature.getString("TAG_LIST"), "[1, 2, 3]")
        self.assertEqual(self.feature.getString("TAG_NONE", default="def"), "def")

    # -------------------------------------------------------------------------
    # 2. Concurrency: 10,000 rapid concurrent queries & thread safety
    # -------------------------------------------------------------------------
    def test_10000_rapid_concurrent_queries(self):
        """Stress test: 10,000 rapid concurrent queries across 50 threads."""
        TOTAL_QUERIES = 10_000
        NUM_THREADS = 50
        QUERIES_PER_THREAD = TOTAL_QUERIES // NUM_THREADS

        keys_to_test = [
            ("SEC_FLOATING_FEATURE_LINK_TO_WINDOWS", bool, True),
            ("SEC_FLOATING_FEATURE_COMMON_SUPPORT_KNOX", bool, False),
            ("SEC_FLOATING_FEATURE_SETTINGS_CONFIG_BRAND_NAME", str, "Samsung"),
            ("SEC_FLOATING_FEATURE_SIP_CONFIG_PACKAGE_NAME", str, "com.samsung.android.honeyboard"),
            ("SEC_FLOATING_FEATURE_AUDIO_SUPPORT_SOUND_ALIVE", bool, True),
            ("SEC_NONEXISTENT_KEY", str, ""),
            ("SEC_NONEXISTENT_INT", int, 0),
            (None, bool, False),
            ("", str, ""),
        ]

        errors = []
        completed = 0
        lock = threading.Lock()

        def worker(thread_id: int):
            nonlocal completed
            local_completed = 0
            for i in range(QUERIES_PER_THREAD):
                tag, expected_type, expected_val = random.choice(keys_to_test)
                try:
                    if expected_type is bool:
                        res = self.feature.getBoolean(tag)
                        if tag and tag in self.feature._features:
                            if res != expected_val:
                                errors.append(f"Thread {thread_id} got {res} != {expected_val} for {tag}")
                    elif expected_type is str:
                        res = self.feature.getString(tag)
                        if tag and tag in self.feature._features:
                            if res != expected_val:
                                errors.append(f"Thread {thread_id} got {res} != {expected_val} for {tag}")
                    elif expected_type is int:
                        res = self.feature.getInt(tag)
                        if res != expected_val:
                            errors.append(f"Thread {thread_id} got {res} != {expected_val} for {tag}")
                    local_completed += 1
                except Exception as ex:
                    errors.append(f"Thread {thread_id} crashed with {type(ex).__name__}: {ex}")

            with lock:
                completed += local_completed

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(NUM_THREADS)]
        t0 = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.perf_counter() - t0

        self.assertEqual(len(errors), 0, f"Errors encountered during stress test: {errors[:5]}")
        self.assertEqual(completed, TOTAL_QUERIES)
        print(f"[SemFloatingFeature] 10,000 concurrent queries completed in {elapsed:.4f}s ({TOTAL_QUERIES / elapsed:.1f} qps)")

    def test_concurrent_reader_writer_stress(self):
        """Stress test: 20 reader threads and 5 writer threads running concurrently."""
        stop_event = threading.Event()
        errors = []
        read_count = 0
        write_count = 0
        count_lock = threading.Lock()

        def reader_task(reader_id: int):
            nonlocal read_count
            local_reads = 0
            while not stop_event.is_set():
                tag = f"DYNAMIC_KEY_{random.randint(0, 100)}"
                try:
                    self.feature.getString(tag, "default")
                    self.feature.getInt(tag, 0)
                    self.feature.getBoolean(tag, False)
                    local_reads += 1
                except Exception as ex:
                    errors.append(f"Reader {reader_id} crashed: {ex}")
            with count_lock:
                read_count += local_reads

        def writer_task(writer_id: int):
            nonlocal write_count
            local_writes = 0
            while not stop_event.is_set():
                tag = f"DYNAMIC_KEY_{random.randint(0, 100)}"
                val = f"VAL_{random.randint(0, 10000)}"
                try:
                    self.feature.set_feature(tag, val)
                    local_writes += 1
                except Exception as ex:
                    errors.append(f"Writer {writer_id} crashed: {ex}")
            with count_lock:
                write_count += local_writes

        readers = [threading.Thread(target=reader_task, args=(i,)) for i in range(20)]
        writers = [threading.Thread(target=writer_task, args=(i,)) for i in range(5)]

        for t in readers + writers:
            t.start()

        time.sleep(0.5)  # Run for 500ms
        stop_event.set()

        for t in readers + writers:
            t.join()

        self.assertEqual(len(errors), 0, f"Reader/Writer race conditions: {errors[:5]}")
        print(f"[SemFloatingFeature] Concurrent read/write: {read_count} reads, {write_count} writes with 0 errors")


class LL0cSemIntStressTest(unittest.TestCase):
    def setUp(self):
        self.class_loader = ARTClassLoader(is_aosp_base=True)
        # Register stubs as done by LSPosed MdxServiceHooks
        self.class_loader.register_stub("LL0.c", OneUIStubs)
        self.class_loader.register_stub("L0.c", OneUIStubs)
        self.class_loader.register_stub("com.samsung.android.os.SemVersion", OneUIStubs)

    def test_rapid_multi_threaded_sem_int_queries(self):
        """Stress test: 10,000 rapid multi-threaded queries on LL0/c / SEM_INT."""
        TOTAL_QUERIES = 10_000
        NUM_THREADS = 50
        PER_THREAD = TOTAL_QUERIES // NUM_THREADS

        errors = []
        completed = 0
        lock = threading.Lock()

        def worker(thread_id: int):
            nonlocal completed
            local_completed = 0
            for _ in range(PER_THREAD):
                try:
                    cls = self.class_loader.load_class("LL0.c")
                    sem_int = cls.SEM_INT
                    if sem_int < 3000:
                        errors.append(f"SEM_INT {sem_int} < 3000")
                    is_dex = cls.is_desktop_mode()
                    if is_dex is not False:
                        errors.append("is_desktop_mode is not False")
                    is_smart_clip = cls.is_smart_clip_supported()
                    if is_smart_clip is not False:
                        errors.append("is_smart_clip_supported is not False")
                    local_completed += 1
                except Exception as ex:
                    errors.append(f"Thread {thread_id} crashed: {ex}")

            with lock:
                completed += local_completed

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(NUM_THREADS)]
        t0 = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.perf_counter() - t0

        self.assertEqual(len(errors), 0, f"LL0/c query errors: {errors[:5]}")
        self.assertEqual(completed, TOTAL_QUERIES)
        print(f"[LL0/c SEM_INT] 10,000 multi-threaded queries passed in {elapsed:.4f}s ({TOTAL_QUERIES / elapsed:.1f} qps)")

    def test_concurrent_classloader_queries_with_unregistered_classes(self):
        """Verify classloader handles concurrent mix of valid, stubbed, and invalid class loads."""
        classes_to_load = [
            ("LL0.c", True),
            ("L0.c", True),
            ("com.samsung.android.os.SemVersion", True),
            ("com.samsung.android.nonexistent.ServiceA", False),
            ("com.samsung.android.nonexistent.ServiceB", False),
            ("", False),
        ]

        errors = []

        def worker():
            for _ in range(200):
                target, should_succeed = random.choice(classes_to_load)
                try:
                    cls = self.class_loader.load_class(target)
                    if not should_succeed:
                        errors.append(f"Loaded invalid class {target} successfully!")
                except (ClassNotFoundException, NoClassDefFoundError):
                    if should_succeed:
                        errors.append(f"Failed to load expected class {target}")
                except Exception as ex:
                    errors.append(f"Unexpected exception for {target}: {type(ex).__name__} {ex}")

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Classloader errors: {errors[:5]}")


class PackageManagerSignatureStressTest(unittest.TestCase):
    def setUp(self):
        self.pms = PackageManagerService()
        self.pms.register_package(
            "com.microsoft.appmanager", 10151, "/data/app/LinkToWindows", ["ms_cert_sha256"]
        )
        self.pms.register_package(
            "com.samsung.android.mdx", 10150, "/system/priv-app/LinkToWindowsService", ["samsung_cert_sha256"]
        )
        PackageSignatureChecker.enable_bypass()

    def tearDown(self):
        PackageSignatureChecker.disable_bypass()

    def test_rogue_package_isolation(self):
        """Verify rogue packages can NEVER match authentic MDX or AppManager."""
        rogue_names = [
            "com.samsung.android.mdx.fake",
            "com.samsung.android.mdx_clone",
            "com.samsung.android.mdx ",
            " com.samsung.android.mdx",
            "COM.SAMSUNG.ANDROID.MDX",
            "com.microsoft.appmanager.rogue",
            "com.attacker.spoof",
            "org.malicious.payload",
        ]

        for rogue in rogue_names:
            self.pms.register_package(rogue, random.randint(11000, 19000), "/data/app/rogue", ["attacker_cert"])

            # Rogue -> MDX
            res1 = PackageSignatureChecker.checkSignatures(self.pms, rogue, "com.samsung.android.mdx")
            self.assertEqual(res1, PackageSignatureChecker.SIGNATURE_NO_MATCH, f"Rogue {rogue} matched MDX!")

            # Rogue -> AppManager
            res2 = PackageSignatureChecker.checkSignatures(self.pms, rogue, "com.microsoft.appmanager")
            self.assertEqual(res2, PackageSignatureChecker.SIGNATURE_NO_MATCH, f"Rogue {rogue} matched AppManager!")

    def test_rogue_with_identical_samsung_signature_not_whitelisted(self):
        """Even if an attacker copies the Samsung cert string, can it pair with AppManager?"""
        self.pms.register_package(
            "com.attacker.copiedcert", 10998, "/data/app/fake", ["samsung_cert_sha256"]
        )
        # Should NOT match com.microsoft.appmanager because bypass pair is strictly scoped
        res = PackageSignatureChecker.checkSignatures(self.pms, "com.attacker.copiedcert", "com.microsoft.appmanager")
        self.assertEqual(res, PackageSignatureChecker.SIGNATURE_NO_MATCH)

    def test_malformed_and_extreme_package_names(self):
        """Test malformed package names in checkSignatures."""
        test_cases = [
            (None, "com.samsung.android.mdx", PackageSignatureChecker.SIGNATURE_UNKNOWN_PACKAGE),
            ("com.microsoft.appmanager", None, PackageSignatureChecker.SIGNATURE_UNKNOWN_PACKAGE),
            (None, None, PackageSignatureChecker.SIGNATURE_UNKNOWN_PACKAGE),
            ("", "", PackageSignatureChecker.SIGNATURE_UNKNOWN_PACKAGE),
            ("   ", "com.samsung.android.mdx", PackageSignatureChecker.SIGNATURE_UNKNOWN_PACKAGE),
            ("com.microsoft.appmanager\x00extra", "com.samsung.android.mdx", PackageSignatureChecker.SIGNATURE_UNKNOWN_PACKAGE),
            ("A" * 10_000, "B" * 10_000, PackageSignatureChecker.SIGNATURE_UNKNOWN_PACKAGE),
        ]

        for pkg1, pkg2, expected in test_cases:
            res = PackageSignatureChecker.checkSignatures(self.pms, pkg1, pkg2)
            self.assertEqual(res, expected, f"Failed for ({pkg1}, {pkg2}) -> got {res}, expected {expected}")

    def test_empty_signatures_boundary_behavior(self):
        """
        Adversarial Boundary Test:
        Examine behavior when packages have empty signatures lists.
        In AOSP PackageManager:
        - If neither is signed: returns SIGNATURE_NEITHER_SIGNED (-2).
        - If first is not signed: returns SIGNATURE_FIRST_NOT_SIGNED (-3).
        """
        # Package A with explicitly empty signatures
        pkg_unsigned_a = PackageInfo("com.unsigned.app.a", 10801, "/data/app/a", signatures=["temp"])
        pkg_unsigned_a.signatures = []  # Force empty signatures
        self.pms._packages["com.unsigned.app.a"] = pkg_unsigned_a

        # Package B with explicitly empty signatures
        pkg_unsigned_b = PackageInfo("com.unsigned.app.b", 10802, "/data/app/b", signatures=["temp"])
        pkg_unsigned_b.signatures = []  # Force empty signatures
        self.pms._packages["com.unsigned.app.b"] = pkg_unsigned_b

        # Signed Package C
        pkg_signed_c = PackageInfo("com.signed.app.c", 10803, "/data/app/c", signatures=["valid_cert"])
        self.pms._packages["com.signed.app.c"] = pkg_signed_c

        res_both_empty = PackageSignatureChecker.checkSignatures(self.pms, "com.unsigned.app.a", "com.unsigned.app.b")
        res_first_empty = PackageSignatureChecker.checkSignatures(self.pms, "com.unsigned.app.a", "com.signed.app.c")

        print(f"[PMS Boundary Note] checkSignatures on two unsigned packages returned: {res_both_empty}")
        print(f"[PMS Boundary Note] checkSignatures on (unsigned, signed) returned: {res_first_empty}")

        # Document finding: if mock returns SIGNATURE_MATCH (0) for empty signatures,
        # that is an empirical finding of loose signature checking on unsigned packages!
        # Both packages unsigned should not match in production AOSP.

    def test_rapid_concurrent_signature_queries(self):
        """Stress test: 10,000 rapid multi-threaded signature queries."""
        TOTAL_QUERIES = 10_000
        NUM_THREADS = 50
        PER_THREAD = TOTAL_QUERIES // NUM_THREADS

        query_scenarios = [
            ("com.microsoft.appmanager", "com.samsung.android.mdx", PackageSignatureChecker.SIGNATURE_MATCH),
            ("com.samsung.android.mdx", "com.microsoft.appmanager", PackageSignatureChecker.SIGNATURE_MATCH),
            ("com.microsoft.appmanager", "com.nonexistent.app", PackageSignatureChecker.SIGNATURE_UNKNOWN_PACKAGE),
            ("com.nonexistent.a", "com.nonexistent.b", PackageSignatureChecker.SIGNATURE_UNKNOWN_PACKAGE),
            (None, "com.samsung.android.mdx", PackageSignatureChecker.SIGNATURE_UNKNOWN_PACKAGE),
        ]

        errors = []
        completed = 0
        lock = threading.Lock()

        def worker(thread_id: int):
            nonlocal completed
            local_completed = 0
            for _ in range(PER_THREAD):
                pkg1, pkg2, expected = random.choice(query_scenarios)
                try:
                    res = PackageSignatureChecker.checkSignatures(self.pms, pkg1, pkg2)
                    if res != expected:
                        errors.append(f"Thread {thread_id} ({pkg1}, {pkg2}) -> {res} != {expected}")
                    local_completed += 1
                except Exception as ex:
                    errors.append(f"Thread {thread_id} crashed on ({pkg1}, {pkg2}): {ex}")

            with lock:
                completed += local_completed

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(NUM_THREADS)]
        t0 = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.perf_counter() - t0

        self.assertEqual(len(errors), 0, f"Signature query errors: {errors[:5]}")
        self.assertEqual(completed, TOTAL_QUERIES)
        print(f"[PMS Signatures] 10,000 multi-threaded queries passed in {elapsed:.4f}s ({TOTAL_QUERIES / elapsed:.1f} qps)")


if __name__ == "__main__":
    unittest.main()
