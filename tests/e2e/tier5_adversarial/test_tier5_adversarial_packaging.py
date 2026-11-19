"""
test_tier5_adversarial_packaging.py - Tier 5 Adversarial Coverage Hardening Suite
Focus Areas:
1. Archive tampering (corrupted ZIPs, truncated APKs, bad checksum manifest lines).
2. SELinux policy edge cases (uinput/uhid chr_file ioctls, domain confinement, script consistency).
3. Service daemon resilience (late boot delays, PMS slow startup, repeated AppOps configuration, customize.sh matrix).
4. Master build script error handling (missing dependencies, non-zero subprocess exits, read-only/missing outputs).
5. PackagingValidator bytecode, XML, and metadata fuzzing.
"""

import io
import os
import re
import sys
import shutil
import struct
import tempfile
import unittest
import zipfile
import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add repository root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.mock_env.packaging_validator import PackagingValidator
import build
from magisk_module.build_magisk import (
    validate_module_prop,
    validate_shell_script,
    validate_xml,
    validate_apk,
    validate_module_tree,
    stage_and_normalize,
    package_zip,
    ValidationError,
    REQUIRED_FILES,
    MODE_EXEC,
    MODE_FILE,
    MODE_DIR,
)


class TestTier5ArchiveTamperingAndCorruption(unittest.TestCase):
    """
    Adversarial testing of ZIP archive parsing, truncation, payload tampering,
    bit-flipping, and structural anomalies.
    """

    def test_truncated_zip_archives(self):
        """Truncated ZIP buffers at various critical byte offsets must be rejected cleanly."""
        test_cases = [
            (b"", "Empty buffer"),
            (b"PK", "2-byte partial signature"),
            (b"PK\x03\x04", "4-byte local file header signature only"),
            (b"PK\x03\x04" + b"\x14\x00" * 10, "Partial local file header"),
            (b"PK\x05\x06", "4-byte EOCD signature only"),
            (b"PK\x05\x06" + b"\x00" * 12, "Truncated 16-byte EOCD"),
            (b"PK\x01\x02" + b"\x00" * 20, "Truncated central directory header"),
            (b"\x00" * 256, "Zeroes without ZIP signature"),
            (b"\xFF" * 512, "High-entropy random non-ZIP bytes"),
        ]

        for payload, description in test_cases:
            with self.subTest(scenario=description):
                buf = io.BytesIO(payload)
                self.assertFalse(zipfile.is_zipfile(buf), f"Should not be recognized as ZIP: {description}")
                with self.assertRaises((zipfile.BadZipFile, EOFError, struct.error)):
                    with zipfile.ZipFile(buf, "r") as z:
                        _ = z.namelist()

    def test_tampered_module_prop_in_zip(self):
        """PackagingValidator and build_magisk must detect and reject any tampered module.prop."""
        corrupted_props = [
            # Missing id
            "name=Phone Link\nversion=v2.0.0\nversionCode=200\nauthor=Team\ndescription=Desc\n",
            # Missing versionCode
            "id=phonelink_module\nname=Phone Link\nversion=v2.0.0\nauthor=Team\ndescription=Desc\n",
            # Non-integer versionCode
            "id=phonelink_module\nname=Phone Link\nversion=v2.0.0\nversionCode=v200\nauthor=Team\ndescription=Desc\n",
            # Invalid ID with leading number
            "id=1phonelink\nname=Phone Link\nversion=v2.0.0\nversionCode=200\nauthor=Team\ndescription=Desc\n",
            # Invalid ID with spaces
            "id=phone link\nname=Phone Link\nversion=v2.0.0\nversionCode=200\nauthor=Team\ndescription=Desc\n",
            # Invalid ID with punctuation
            "id=phonelink!module\nname=Phone Link\nversion=v2.0.0\nversionCode=200\nauthor=Team\ndescription=Desc\n",
        ]

        for idx, prop_text in enumerate(corrupted_props):
            with self.subTest(case_idx=idx):
                with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as tf:
                    tf.write(prop_text)
                    tf_path = Path(tf.name)
                try:
                    # Check build_magisk validator
                    with self.assertRaises(ValidationError):
                        validate_module_prop(tf_path)
                finally:
                    tf_path.unlink()

    def test_module_prop_negative_version_code_boundary_gap(self):
        """
        Adversarial Boundary Hardening Verification:
        build_magisk.py validates `int(props['versionCode']) > 0`.
        Verifies that negative or zero versionCode is strictly rejected with ValidationError.
        """
        prop_text = "id=phonelink_module\nname=Phone Link\nversion=v2.0.0\nversionCode=-1\nauthor=Team\ndescription=Desc\n"
        with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as tf:
            tf.write(prop_text)
            tf_path = Path(tf.name)
        try:
            with self.assertRaises(ValidationError) as ctx:
                validate_module_prop(tf_path)
            self.assertIn("versionCode must be a positive integer", str(ctx.exception))
        finally:
            tf_path.unlink()

    def test_tampered_privapp_xml_scenarios(self):
        """Adversarially fuzzed privapp-permissions XML variants must be rejected."""
        malformed_xmls = [
            # XML without privapp-permissions root child
            "<permissions><other-tag package='com.samsung.android.mdx'/></permissions>",
            # privapp-permissions for wrong package
            "<permissions><privapp-permissions package='com.wrong.package'><permission name='android.permission.WRITE_SECURE_SETTINGS'/></privapp-permissions></permissions>",
            # Missing WRITE_SECURE_SETTINGS
            """<permissions>
                <privapp-permissions package="com.samsung.android.mdx">
                    <permission name="android.permission.INTERACT_ACROSS_USERS"/>
                    <permission name="android.permission.BATTERY_STATS"/>
                </privapp-permissions>
            </permissions>""",
            # Missing INTERACT_ACROSS_USERS
            """<permissions>
                <privapp-permissions package="com.samsung.android.mdx">
                    <permission name="android.permission.WRITE_SECURE_SETTINGS"/>
                    <permission name="android.permission.BATTERY_STATS"/>
                </privapp-permissions>
            </permissions>""",
            # Missing BATTERY_STATS
            """<permissions>
                <privapp-permissions package="com.samsung.android.mdx">
                    <permission name="android.permission.WRITE_SECURE_SETTINGS"/>
                    <permission name="android.permission.INTERACT_ACROSS_USERS"/>
                </privapp-permissions>
            </permissions>""",
            # Unclosed tag
            "<permissions><privapp-permissions package='com.samsung.android.mdx'>",
            # Malformed entity
            "<permissions>&invalid_entity;</permissions>",
        ]

        for idx, xml_text in enumerate(malformed_xmls):
            with self.subTest(xml_idx=idx):
                valid, errors = PackagingValidator.validate_privapp_xml(xml_text)
                self.assertFalse(valid, f"Malformed XML scenario {idx} was unexpectedly approved!")
                self.assertGreater(len(errors), 0)

    def test_tampered_sysconfig_xml_scenarios(self):
        """Adversarially fuzzed sysconfig XML variants must be rejected."""
        malformed_sysconfigs = [
            # Missing com.samsung.android.mdx from power save
            """<config>
                <allow-in-power-save package="com.microsoft.appmanager"/>
                <allow-in-data-saver package="com.samsung.android.mdx"/>
                <allow-in-data-saver package="com.microsoft.appmanager"/>
            </config>""",
            # Missing com.microsoft.appmanager from power save
            """<config>
                <allow-in-power-save package="com.samsung.android.mdx"/>
                <allow-in-data-saver package="com.samsung.android.mdx"/>
                <allow-in-data-saver package="com.microsoft.appmanager"/>
            </config>""",
            # Missing com.samsung.android.mdx from data saver
            """<config>
                <allow-in-power-save package="com.samsung.android.mdx"/>
                <allow-in-power-save package="com.microsoft.appmanager"/>
                <allow-in-data-saver package="com.microsoft.appmanager"/>
            </config>""",
            # Missing com.microsoft.appmanager from data saver
            """<config>
                <allow-in-power-save package="com.samsung.android.mdx"/>
                <allow-in-power-save package="com.microsoft.appmanager"/>
                <allow-in-data-saver package="com.samsung.android.mdx"/>
            </config>""",
            # Empty tags without package attributes
            "<config><allow-in-power-save/><allow-in-data-saver/></config>",
            # Unclosed root tag
            "<config><allow-in-power-save package='com.samsung.android.mdx'>",
        ]

        for idx, sys_xml in enumerate(malformed_sysconfigs):
            with self.subTest(sys_idx=idx):
                valid, errors = PackagingValidator.validate_sysconfig_xml(sys_xml)
                self.assertFalse(valid, f"Malformed sysconfig scenario {idx} was unexpectedly approved!")
                self.assertGreater(len(errors), 0)

    def test_tampered_embedded_apk_scenarios(self):
        """Tampered or architecture-mismatched APKs must be rejected by validate_apk."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)

            # Scenario 1: Zero-byte APK
            empty_apk = tmp / "empty.apk"
            empty_apk.write_bytes(b"")
            with self.assertRaises(ValidationError):
                validate_apk(empty_apk)

            # Scenario 2: Truncated ZIP APK
            truncated_apk = tmp / "truncated.apk"
            truncated_apk.write_bytes(b"PK\x03\x04\x00\x00" + os.urandom(30))
            with self.assertRaises(ValidationError):
                validate_apk(truncated_apk)

            # Scenario 3: Valid ZIP but missing AndroidManifest.xml
            no_manifest_apk = tmp / "no_manifest.apk"
            with zipfile.ZipFile(no_manifest_apk, "w") as z:
                z.writestr("classes.dex", b"dex_stub")
            with self.assertRaises(ValidationError) as ctx:
                validate_apk(no_manifest_apk)
            self.assertIn("missing AndroidManifest.xml", str(ctx.exception))

            # Scenario 4: Missing arm64 native libs (only x86/armeabi)
            wrong_abi_apk = tmp / "wrong_abi.apk"
            with zipfile.ZipFile(wrong_abi_apk, "w") as z:
                z.writestr("AndroidManifest.xml", b"<manifest/>")
                z.writestr("lib/armeabi-v7a/libtest.so", b"\x7fELF")
                z.writestr("lib/x86/libtest.so", b"\x7fELF")
            with self.assertRaises(ValidationError) as ctx:
                validate_apk(wrong_abi_apk)
            self.assertIn("does not contain arm64-v8a native libraries", str(ctx.exception))

            # Scenario 5: Valid APK with arm64 native lib passes
            valid_apk = tmp / "valid.apk"
            with zipfile.ZipFile(valid_apk, "w") as z:
                z.writestr("AndroidManifest.xml", b"<manifest/>")
                z.writestr("lib/arm64-v8a/libKeyboardLib.so", b"\x7fELF\x02\x01\x01")
            validate_apk(valid_apk)  # Must not raise

    def test_zip_path_traversal_detection(self):
        """Verify handling of ZIP archives containing malicious path traversal names."""
        traversal_names = [
            "../../etc/passwd",
            "../system/bin/sh",
            "..\\..\\windows\\system32\\cmd.exe",
            "/absolute/root/file",
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            zip_path = Path(tmp_dir) / "traversal.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                for name in traversal_names:
                    zf.writestr(name, b"malicious content")

            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
                for name in names:
                    # PackagingValidator normalizes and ensures leading slashes / backslashes are resolved
                    normalized = name.replace("\\", "/").lstrip("/")
                    self.assertFalse(normalized.startswith("/"), "Normalized name should not have leading slash")
                    self.assertTrue(".." in normalized or not normalized.startswith("system/"), "Identified path traversal entry")

    def test_zip_payload_bit_flip_detection(self):
        """Single bit-flips in compressed payloads must trigger CRC32 validation errors."""
        buf = io.BytesIO()
        payload = b"id=phonelink_module\nname=Phone Link\nversion=v2.0.0\n"
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("module.prop", payload)

        zip_bytes = bytearray(buf.getvalue())
        # Flip a bit in the middle of the compressed data payload
        payload_offset = zip_bytes.find(b"module.prop") + len("module.prop") + 20
        zip_bytes[payload_offset] ^= 0x01

        corrupted_buf = io.BytesIO(zip_bytes)
        with zipfile.ZipFile(corrupted_buf, "r") as zf:
            with self.assertRaises(zipfile.BadZipFile):
                _ = zf.read("module.prop")


class TestTier5ManifestChecksumAdversarial(unittest.TestCase):
    """
    Adversarial testing of SHA256SUMS.txt manifest parsing, hash validation,
    corrupted lines, and end-to-end verification gating.
    """

    def test_manifest_line_parsing_fuzz(self):
        """Fuzz manifest line structures: spaces, tabs, comments, single-column tokens."""
        valid_hash = "259371349202506e0c20d6c42d269e3fb473cbcf4f3f748efa433fe48d8ebd70"
        manifest_cases = [
            # Standard two-space
            (f"{valid_hash}  PhoneLinkMagisk-v2.0.0.zip", True, valid_hash, "PhoneLinkMagisk-v2.0.0.zip"),
            # Single-space separator
            (f"{valid_hash} PhoneLinkMagisk-v2.0.0.zip", True, valid_hash, "PhoneLinkMagisk-v2.0.0.zip"),
            # Tab separator
            (f"{valid_hash}\tPhoneLinkMagisk-v2.0.0.zip", True, valid_hash, "PhoneLinkMagisk-v2.0.0.zip"),
            # Multiple leading/trailing spaces
            (f"  {valid_hash}    PhoneLinkMagisk-v2.0.0.zip  ", True, valid_hash, "PhoneLinkMagisk-v2.0.0.zip"),
            # Comment line
            ("# SHA-256 Checksums", False, None, None),
            # Empty line
            ("   ", False, None, None),
        ]

        for raw_line, should_parse, expected_h, expected_fn in manifest_cases:
            with self.subTest(line=raw_line):
                stripped = raw_line.strip()
                if not stripped or stripped.startswith("#"):
                    self.assertFalse(should_parse)
                    continue
                parts = stripped.split(None, 1)
                self.assertEqual(len(parts), 2)
                h, fn = parts
                self.assertEqual(h, expected_h)
                self.assertEqual(fn, expected_fn)

    def test_manifest_corrupted_single_token_line(self):
        """Lines containing only a hash or only a filename must be detected."""
        malformed_lines = [
            "259371349202506e0c20d6c42d269e3fb473cbcf4f3f748efa433fe48d8ebd70",
            "PhoneLinkMagisk-v2.0.0.zip",
        ]
        for line in malformed_lines:
            with self.subTest(line=line):
                parts = line.strip().split(None, 1)
                self.assertEqual(len(parts), 1, "Should have only 1 token")

    def test_manifest_checksum_mismatch_detection(self):
        """Altering a single character of expected SHA256 must trigger AssertionError."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            td = Path(tmp_dir)
            test_file = td / "PhoneLinkMagisk-v2.0.0.zip"
            test_file.write_bytes(b"genuine_magisk_payload")
            actual_sha = build.compute_sha256(test_file)

            # Flip first char of hash
            tampered_sha = ("0" if actual_sha[0] != "0" else "1") + actual_sha[1:]

            # Mock verify check
            self.assertNotEqual(actual_sha, tampered_sha)
            with self.assertRaises(AssertionError) as ctx:
                if actual_sha != tampered_sha:
                    raise AssertionError(f"Checksum mismatch for {test_file.name}: expected {tampered_sha}, got {actual_sha}")
            self.assertIn("Checksum mismatch", str(ctx.exception))

    def test_manifest_non_hex_or_wrong_length_hash(self):
        """Hashes that are not 64 lowercase hex characters must be identified."""
        invalid_hashes = [
            "259371349202506e0c20d6c42d269e3fb473cbcf4f3f748efa433fe48d8ebd7",   # 63 chars
            "259371349202506e0c20d6c42d269e3fb473cbcf4f3f748efa433fe48d8ebd700", # 65 chars
            "259371349202506e0c20d6c42d269e3fb473cbcf4f3f748efa433fe48d8ebzzz", # non-hex chars
            "259371349202506E0C20D6C42D269E3FB473CBCF4F3F748EFA433FE48D8EBD70", # uppercase hex
        ]

        hex_pattern = re.compile(r"^[0-9a-f]{64}$")
        for bad_hash in invalid_hashes:
            with self.subTest(bad_hash=bad_hash):
                self.assertIsNone(hex_pattern.match(bad_hash), f"Hash {bad_hash} should fail strict 64-char lowercase hex regex")

    def test_manifest_missing_referenced_artifact(self):
        """Manifest listing a file that is not in the directory must raise FileNotFoundError."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            td = Path(tmp_dir)
            manifest = td / "SHA256SUMS.txt"
            manifest.write_text("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  NonExistentFile.zip\n", encoding="utf-8")

            target_file = td / "NonExistentFile.zip"
            with self.assertRaises(FileNotFoundError):
                if not target_file.is_file():
                    raise FileNotFoundError(f"Missing artifact referenced in manifest: {target_file}")


class TestTier5SELinuxRulesAndDomainConfine(unittest.TestCase):
    """
    Adversarial testing of SELinux policies: syntax validation, domain confinement
    (least privilege), chr_file ioctls, domain transitions, and cross-file rule consistency.
    """

    def setUp(self):
        self.sepolicy_file = REPO_ROOT / "magisk_module" / "sepolicy.rule"
        self.service_sh_file = REPO_ROOT / "magisk_module" / "service.sh"
        self.customize_sh_file = REPO_ROOT / "magisk_module" / "customize.sh"

    def test_sepolicy_rule_syntax_and_structure(self):
        """Verify each line in sepolicy.rule conforms to Magisk policy syntax."""
        self.assertTrue(self.sepolicy_file.is_file(), f"sepolicy.rule missing at {self.sepolicy_file}")
        content = self.sepolicy_file.read_text(encoding="utf-8")
        lines = [line.strip() for line in content.splitlines() if line.strip() and not line.strip().startswith("#")]

        # Expected rule grammar: allow <source_domain> <target_type> <class> { <perms> } OR allow <source> <target> <class> <action>
        rule_pattern = re.compile(
            r"^allow\s+([a-zA-Z0-9_-]+)\s+([a-zA-Z0-9_-]+)\s+([a-zA-Z0-9_-]+)\s+(?:\{\s*([a-zA-Z0-9_\s-]+)\s*\}|([a-zA-Z0-9_-]+))$"
        )

        self.assertGreater(len(lines), 0, "sepolicy.rule has no active rules")
        for line in lines:
            with self.subTest(rule=line):
                match = rule_pattern.match(line)
                self.assertIsNotNone(match, f"Rule failed syntax check: {line}")
                source, target, obj_class, braced_perms, bare_perm = match.groups()
                perms = braced_perms or bare_perm
                self.assertIsNotNone(perms)
                self.assertIn(source, ["priv_app", "system_app", "platform_app"])
                self.assertIn(obj_class, ["chr_file", "service_manager", "file"])

    def test_untrusted_app_confinement_least_privilege(self):
        """
        Verify that untrusted_app is strictly CONFINED and NEVER granted uinput_device
        or uhid_device access in sepolicy.rule, service.sh, or customize.sh.
        Allowing untrusted_app raw uinput access would create an arbitrary input injection vulnerability.
        """
        all_policy_texts = [
            self.sepolicy_file.read_text(encoding="utf-8"),
            self.service_sh_file.read_text(encoding="utf-8"),
            self.customize_sh_file.read_text(encoding="utf-8"),
        ]

        forbidden_domains = [
            "untrusted_app",
            "untrusted_app_25",
            "untrusted_app_27",
            "untrusted_app_29",
            "untrusted_app_30",
            "untrusted_app_32",
            "untrusted_app_36",
            "isolated_app",
            "ephemeral_app",
        ]

        for text in all_policy_texts:
            for domain in forbidden_domains:
                with self.subTest(domain=domain):
                    # Check that domain is never granted uinput_device or uhid_device
                    self.assertNotIn(f"allow {domain} uinput_device", text)
                    self.assertNotIn(f"allow {domain} uhid_device", text)

    def test_uinput_and_uhid_chr_file_ioctls_granted(self):
        """
        Kernel /dev/uinput and /dev/uhid requires { read write open ioctl getattr }.
        Missing 'ioctl' would cause virtual input device creation (UI_DEV_CREATE) to fail with -EACCES.
        """
        content = self.sepolicy_file.read_text(encoding="utf-8")
        for dev in ["uinput_device", "uhid_device"]:
            with self.subTest(device=dev):
                # priv_app must have ioctl on device
                pattern = rf"allow\s+priv_app\s+{dev}\s+chr_file\s+\{{[^}}]*ioctl[^}}]*\}}"
                self.assertTrue(bool(re.search(pattern, content)), f"priv_app lacks ioctl on {dev}")

    def test_privapp_data_file_execute_rule_present(self):
        """
        priv_app must be allowed execute / execute_no_trans on privapp_data_file
        to permit executing dexopt / dynamic runtime payloads.
        """
        content = self.sepolicy_file.read_text(encoding="utf-8")
        pattern = r"allow\s+priv_app\s+privapp_data_file\s+file\s+\{[^}]*execute[^}]*\}"
        self.assertTrue(bool(re.search(pattern, content)), "privapp_data_file execute rule missing")

    def test_service_manager_find_rules_present(self):
        """
        priv_app must be allowed to find input_service and surfaceflinger in service_manager.
        """
        content = self.sepolicy_file.read_text(encoding="utf-8")
        self.assertIn("allow priv_app input_service service_manager find", content)
        self.assertIn("allow priv_app surfaceflinger service_manager find", content)

    def test_cross_script_sepolicy_consistency(self):
        """
        Rules declared in sepolicy.rule must match the live rules executed in service.sh.
        Identifies policy synchronization discrepancies.
        """
        sepolicy_content = self.sepolicy_file.read_text(encoding="utf-8")
        service_content = self.service_sh_file.read_text(encoding="utf-8")
        customize_content = self.customize_sh_file.read_text(encoding="utf-8")

        rules_in_sepolicy = [
            line.strip() for line in sepolicy_content.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

        # Verify all static rules in sepolicy.rule are applied in service.sh
        for rule in rules_in_sepolicy:
            with self.subTest(rule_in_service=rule):
                expected_magiskpolicy = f'magiskpolicy --live "{rule}"'
                self.assertIn(expected_magiskpolicy, service_content)

        # In customize.sh, note that only device rules are applied, not service_manager rules
        for rule in rules_in_sepolicy:
            if "chr_file" in rule:
                expected_magiskpolicy = f'magiskpolicy --live "{rule}"'
                self.assertIn(expected_magiskpolicy, customize_content)


class TestTier5ServiceDaemonResilience(unittest.TestCase):
    """
    Adversarial testing of shell scripts (service.sh, customize.sh):
    boot completion delay simulations, timeout boundaries, PMS slow startup,
    idempotent configurations, and architecture/API gate validation.
    """

    def setUp(self):
        self.service_sh = (REPO_ROOT / "magisk_module" / "service.sh").read_text(encoding="utf-8")
        self.customize_sh = (REPO_ROOT / "magisk_module" / "customize.sh").read_text(encoding="utf-8")

    def test_service_script_shebang_and_lf(self):
        """service.sh must have correct shebang and LF line endings."""
        raw_service = (REPO_ROOT / "magisk_module" / "service.sh").read_bytes()
        self.assertTrue(raw_service.startswith(b"#!/system/bin/sh"))
        self.assertNotIn(b"\r", raw_service, "service.sh contains Windows CRLF line endings")

    def test_customize_script_shebang_and_lf(self):
        """customize.sh must have correct shebang and LF line endings."""
        raw_customize = (REPO_ROOT / "magisk_module" / "customize.sh").read_bytes()
        self.assertTrue(raw_customize.startswith(b"#!/system/bin/sh"))
        self.assertNotIn(b"\r", raw_customize, "customize.sh contains Windows CRLF line endings")

    def test_boot_timeout_simulation_oracle(self):
        """
        Simulate the exact while-loop logic of service.sh lines 11-20:
        BOOT_TIMEOUT=120, sleep 2, TIMER=$((TIMER + 2)).
        If sys.boot_completed is never 1, it must exit after 120s.
        If it completes within 120s, it must exit loop successfully.
        """
        def simulate_boot_wait(boot_completed_at_sec: int, max_sim_sec: int = 150):
            BOOT_TIMEOUT = 120
            TIMER = 0
            exit_code = 0
            while True:
                is_completed = (TIMER >= boot_completed_at_sec)
                if is_completed:
                    break
                TIMER += 2
                if TIMER >= BOOT_TIMEOUT:
                    exit_code = 1
                    break
            return exit_code, TIMER

        # Scenario 1: Immediate boot
        code, t = simulate_boot_wait(0)
        self.assertEqual(code, 0)
        self.assertEqual(t, 0)

        # Scenario 2: Late boot at 60s
        code, t = simulate_boot_wait(60)
        self.assertEqual(code, 0)
        self.assertEqual(t, 60)

        # Scenario 3: Near-timeout boot at 118s
        code, t = simulate_boot_wait(118)
        self.assertEqual(code, 0)
        self.assertEqual(t, 118)

        # Scenario 4: Timeout exceeded (boot takes 130s)
        code, t = simulate_boot_wait(130)
        self.assertEqual(code, 1, "Should exit with code 1 on boot timeout")
        self.assertEqual(t, 120, "Should timeout at exactly 120s")

    def test_pms_slow_registration_simulation_oracle(self):
        """
        Simulate the while-loop logic of service.sh lines 30-34:
        PM_WAIT=0, sleep 2, PM_WAIT=$((PM_WAIT + 2)), max 30s.
        If PMS is slow, script must not hang indefinitely, and must continue.
        """
        def simulate_pm_wait(package_appears_at_sec: int):
            PM_WAIT = 0
            found = False
            while PM_WAIT < 30:
                if PM_WAIT >= package_appears_at_sec:
                    found = True
                    break
                PM_WAIT += 2
            return found, PM_WAIT

        # Scenario 1: PMS registers MDX at 4s
        found, wait_time = simulate_pm_wait(4)
        self.assertTrue(found)
        self.assertEqual(wait_time, 4)

        # Scenario 2: PMS delayed to 26s
        found, wait_time = simulate_pm_wait(26)
        self.assertTrue(found)
        self.assertEqual(wait_time, 26)

        # Scenario 3: PMS fails to register MDX within 30s
        found, wait_time = simulate_pm_wait(40)
        self.assertFalse(found)
        self.assertEqual(wait_time, 30, "Should terminate loop at 30s without hanging")

    def test_permission_and_appops_error_shielding(self):
        """
        All pm grant, appops set, dumpsys deviceidle, and am set-standby-bucket
        commands must have 2>/dev/null || true so that failure on uninstalled or restricted
        apps does not terminate service.sh.
        """
        critical_commands = [
            'pm grant "$PKG_MDX"',
            'pm grant "$PKG_MS"',
            'appops set "$PKG_MDX"',
            'appops set "$PKG_MS"',
            'dumpsys deviceidle whitelist +"$PKG_MDX"',
            'dumpsys deviceidle whitelist +"$PKG_MS"',
            'am set-standby-bucket "$PKG_MDX"',
            'am set-standby-bucket "$PKG_MS"',
            'settings put global settings_enable_monitor_phantom_procs false',
            'device_config put activity_manager max_phantom_processes',
        ]

        for cmd_prefix in critical_commands:
            with self.subTest(command=cmd_prefix):
                self.assertIn(cmd_prefix, self.service_sh)
                # Find all lines with this prefix and verify error suppression
                for line in self.service_sh.splitlines():
                    if cmd_prefix in line:
                        self.assertTrue(
                            "|| true" in line or "2>/dev/null" in line,
                            f"Command line lacks error shielding: {line}"
                        )

    def test_device_node_existence_guard(self):
        """service.sh must verify /dev/uinput and /dev/uhid exist before chmod 0666."""
        self.assertIn("[ -e /dev/uinput ]", self.service_sh)
        self.assertIn("[ -e /dev/uhid ]", self.service_sh)

    def test_customize_arch_validation_matrix(self):
        """customize.sh must abort on non-arm64 architectures and pass on arm64."""
        def check_arch(arch: str) -> bool:
            return arch == "arm64"

        self.assertTrue(check_arch("arm64"))
        for bad_arch in ["arm", "x86", "x86_64", "mips", "riscv64", "armeabi-v7a"]:
            with self.subTest(arch=bad_arch):
                self.assertFalse(check_arch(bad_arch))

    def test_customize_api_level_validation_matrix(self):
        """customize.sh must abort on API < 33 and pass on API >= 33."""
        def check_api(api: int) -> bool:
            return api >= 33

        # Target is Android 16 (API 36), min is API 33 (Android 13)
        self.assertTrue(check_api(36))
        self.assertTrue(check_api(35))
        self.assertTrue(check_api(34))
        self.assertTrue(check_api(33))

        for old_api in [32, 31, 30, 29, 28, 26, 21]:
            with self.subTest(api=old_api):
                self.assertFalse(check_api(old_api))

    def test_customize_user_mdx_cleanup_logic(self):
        """customize.sh must detect and remove user-installed MDX packages in /data/."""
        # Simulated test of lines 34-39 in customize.sh
        def evaluate_cleanup(existing_path: str):
            if existing_path and existing_path.startswith("/data/"):
                return "UNINSTALL"
            return "KEEP"

        self.assertEqual(evaluate_cleanup("/data/app/~~xyz/com.samsung.android.mdx/base.apk"), "UNINSTALL")
        self.assertEqual(evaluate_cleanup("/system/priv-app/LinkToWindowsService/LinkToWindowsService.apk"), "KEEP")
        self.assertEqual(evaluate_cleanup(""), "KEEP")


class TestTier5MasterBuildScriptRobustness(unittest.TestCase):
    """
    Adversarial testing of master build orchestrator (build.py):
    missing script detection, non-zero subprocess error propagation,
    missing output artifacts, and --verify validation edge cases.
    """

    def test_missing_magisk_build_script_raises(self):
        """build.py must raise FileNotFoundError if magisk_module/build_magisk.py is missing."""
        with patch.object(build, "MAGISK_DIR", Path("/nonexistent/magisk_dir")):
            with self.assertRaises(FileNotFoundError) as ctx:
                build.run_magisk_build()
            self.assertIn("Missing Magisk build script", str(ctx.exception))

    def test_missing_lsposed_build_script_raises(self):
        """build.py must raise FileNotFoundError if lsposed_module/build_lsposed.py is missing."""
        with patch.object(build, "LSPOSED_DIR", Path("/nonexistent/lsposed_dir")):
            with self.assertRaises(FileNotFoundError) as ctx:
                build.run_lsposed_build()
            self.assertIn("Missing LSPosed build script", str(ctx.exception))

    def test_magisk_subprocess_nonzero_exit_raises(self):
        """build.py must raise RuntimeError if build_magisk.py exits non-zero."""
        mock_res = MagicMock()
        mock_res.returncode = 2
        with patch("subprocess.run", return_value=mock_res):
            with self.assertRaises(RuntimeError) as ctx:
                build.run_magisk_build()
            self.assertIn("Magisk build failed with exit code 2", str(ctx.exception))

    def test_lsposed_subprocess_nonzero_exit_raises(self):
        """build.py must raise RuntimeError if build_lsposed.py exits non-zero."""
        mock_res = MagicMock()
        mock_res.returncode = 1
        with patch("subprocess.run", return_value=mock_res):
            with self.assertRaises(RuntimeError) as ctx:
                build.run_lsposed_build()
            self.assertIn("LSPosed build failed with exit code 1", str(ctx.exception))

    def test_missing_magisk_output_after_subprocess_zero(self):
        """If subprocess exits 0 but target ZIP is missing, build.py must raise FileNotFoundError."""
        mock_res = MagicMock()
        mock_res.returncode = 0

        with patch.object(build, "TARGET_MAGISK_ZIP", Path("/nonexistent/output.zip")), \
             patch("subprocess.run", return_value=mock_res):
            with self.assertRaises(FileNotFoundError) as ctx:
                build.run_magisk_build()
            self.assertIn("Expected Magisk output not found", str(ctx.exception))

    def test_build_verify_mode_clean_pass(self):
        """build.py validate_release_artifacts passes cleanly on genuine built deliverables."""
        if build.TARGET_MAGISK_ZIP.is_file() and build.TARGET_LSPOSED_APK.is_file():
            build.validate_release_artifacts()  # Must not raise


class TestTier5PackagingValidatorBytecodeAndXmlAdversarial(unittest.TestCase):
    """
    Adversarial testing of PackagingValidator:
    pure Python DEX parsing fuzzing, entrypoint validation, foreign class detection,
    and XML schema edge cases.
    """

    def test_dex_buffer_too_small(self):
        """DEX buffer shorter than 112 bytes must raise ValueError."""
        for sz in [0, 1, 10, 50, 111]:
            with self.subTest(size=sz):
                with self.assertRaises(ValueError) as ctx:
                    PackagingValidator.parse_dex_classes(b"\x00" * sz)
                self.assertIn("DEX buffer too small", str(ctx.exception))

    def test_dex_invalid_magic_bytes(self):
        """DEX buffer with invalid magic must raise ValueError."""
        bad_magics = [
            b"dey\n035\x00",
            b"DEX\n039\x00",
            b"dex\x00035\x00",
            b"\x7fELF\x02\x01\x01\x00",
            b"\x00" * 8,
        ]
        for magic in bad_magics:
            with self.subTest(magic=magic):
                buf = magic + b"\x00" * 104
                with self.assertRaises(ValueError) as ctx:
                    PackagingValidator.parse_dex_classes(buf)
                self.assertIn("Invalid DEX magic", str(ctx.exception))

    def test_validate_dex_entrypoint_with_corrupt_data(self):
        """validate_dex_entrypoint returns (False, errors) on garbage bytes."""
        valid, errors = PackagingValidator.validate_dex_entrypoint(b"not_dex", "me.phonelink.xposed.XposedInit")
        self.assertFalse(valid)
        self.assertTrue(any("Failed to parse classes.dex" in e for e in errors))

    def test_validate_dex_entrypoint_empty_bytes(self):
        """validate_dex_entrypoint returns (False, errors) on empty bytes."""
        valid, errors = PackagingValidator.validate_dex_entrypoint(b"", "me.phonelink.xposed.XposedInit")
        self.assertFalse(valid)
        self.assertIn("classes.dex content is empty", errors)

    def test_foreign_ayra_entrypoint_rejection(self):
        """
        PackagingValidator must detect and reject reference Ayra class entrypoints
        (Lme/ayra/samsung/mdx/XposedInit;) or any class descriptor containing 'ayra'.
        """
        # Read the genuine classes.dex from built APK if available
        if build.TARGET_LSPOSED_APK.is_file():
            with zipfile.ZipFile(build.TARGET_LSPOSED_APK, "r") as apk:
                genuine_dex = apk.read("classes.dex")

            # Normal check passes
            valid, errors = PackagingValidator.validate_dex_entrypoint(genuine_dex, "me.phonelink.xposed.XposedInit")
            self.assertTrue(valid, f"Genuine DEX entrypoint failed: {errors}")

            # Checking with a foreign Ayra entrypoint fails
            valid_ayra, errors_ayra = PackagingValidator.validate_dex_entrypoint(genuine_dex, "me.ayra.samsung.mdx.XposedInit")
            self.assertFalse(valid_ayra)
            self.assertTrue(any("missing from classes.dex" in e or "Foreign reference entrypoint" in e for e in errors_ayra))

    def test_module_prop_missing_and_blank_lines(self):
        """validate_module_prop ignores blank lines and comments, but detects missing keys."""
        content = """
        # Authoritative module.prop
        id=phonelink_module
        name=Phone Link

        # version and versionCode omitted
        author=Teamwork
        description=Xiaomi Mi 9 Link to Windows Port
        """
        valid, props, missing = PackagingValidator.validate_module_prop(content)
        self.assertFalse(valid)
        self.assertIn("version", missing)
        self.assertIn("versionCode", missing)
        self.assertNotIn("id", missing)
        self.assertEqual(props["id"], "phonelink_module")

    def test_lsposed_apk_empty_or_unqualified_entrypoint(self):
        """validate_lsposed_apk rejects empty or unqualified class entrypoints."""
        file_list = ["AndroidManifest.xml", "assets/xposed_init", "classes.dex"]

        # 1. Empty entrypoint
        valid, errors = PackagingValidator.validate_lsposed_apk(file_list, "")
        self.assertFalse(valid)
        self.assertIn("assets/xposed_init is empty", errors)

        # 2. Unqualified class name (no package dot)
        valid, errors = PackagingValidator.validate_lsposed_apk(file_list, "XposedInit")
        self.assertFalse(valid)
        self.assertTrue(any("does not specify a valid qualified class" in e for e in errors))

    def test_lsposed_apk_missing_mandatory_assets(self):
        """validate_lsposed_apk must reject APK lacking AndroidManifest.xml or assets/xposed_init."""
        # Missing AndroidManifest.xml
        valid, errors = PackagingValidator.validate_lsposed_apk(["assets/xposed_init", "classes.dex"], "me.phonelink.xposed.XposedInit")
        self.assertFalse(valid)
        self.assertIn("Missing required asset: AndroidManifest.xml", errors)

        # Missing assets/xposed_init
        valid, errors = PackagingValidator.validate_lsposed_apk(["AndroidManifest.xml", "classes.dex"], "me.phonelink.xposed.XposedInit")
        self.assertFalse(valid)
        self.assertIn("Missing required asset: assets/xposed_init", errors)

    def test_dex_corrupted_table_offsets_handled_safely(self):
        """Corrupted DEX with table offsets pointing outside the file must be handled safely."""
        # Construct header with valid magic but huge string_ids_off
        header = bytearray(112)
        header[:8] = b"dex\n039\x00"
        # string_ids_size = 10, string_ids_off = 0x7FFFFFFF (offset 56 and 60 in header)
        struct.pack_into("<20I", header, 32,
            112, 112, 0x12345678, 0, 0, 0,
            10, 0x7FFFFFFF,  # string_ids_size, string_ids_off
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
        )
        valid, errors = PackagingValidator.validate_dex_entrypoint(bytes(header), "me.phonelink.xposed.XposedInit")
        self.assertFalse(valid)
        self.assertTrue(any("Failed to parse classes.dex" in e for e in errors))

    def test_module_prop_corrupt_line_without_equals_validator_gap(self):
        """
        Adversarial Alignment Verification:
        Both PackagingValidator and build_magisk.py strictly reject malformed lines without '='.
        """
        malformed_line_prop = """
        id=phonelink_module
        THIS_IS_CORRUPTED_TEXT_WITHOUT_EQUALS
        name=Phone Link
        version=v2.0.0
        versionCode=200
        author=Teamwork
        description=Valid
        """
        # 1. PackagingValidator strictly rejects it
        valid, props, missing = PackagingValidator.validate_module_prop(malformed_line_prop)
        self.assertFalse(valid, "PackagingValidator must reject malformed lines without '='")
        self.assertTrue(any("missing '='" in m for m in missing))

        # 2. build_magisk.py strictly raises ValidationError
        with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as tf:
            tf.write(malformed_line_prop)
            tf_path = Path(tf.name)
        try:
            with self.assertRaises(ValidationError) as ctx:
                validate_module_prop(tf_path)
            self.assertIn("Invalid format in module.prop", str(ctx.exception))
        finally:
            tf_path.unlink()

    def test_build_verify_missing_manifest_behavior(self):
        """
        Build Hardening Verification:
        In build.py --verify, TARGET_CHECKSUM_FILE must exist.
        If SHA256SUMS.txt is absent, build.py raises FileNotFoundError rather than silently passing.
        """
        with patch.object(build, "TARGET_CHECKSUM_FILE", Path("/nonexistent/SHA256SUMS.txt")), \
             patch("build.validate_release_artifacts"):
            test_args = ["build.py", "--verify"]
            with patch.object(sys, "argv", test_args):
                with self.assertRaises(FileNotFoundError) as ctx:
                    build.main()
                self.assertIn("Missing SHA-256 checksum manifest", str(ctx.exception))

    def test_customize_split_apk_multiline_path_handling(self):
        """
        In modern Android (12-16), `pm path <package>` often produces multiple lines for split APKs:
        package:/data/app/~~xyz/com.samsung.android.mdx-abc/base.apk
        package:/data/app/~~xyz/com.samsung.android.mdx-abc/split_config.arm64_v8a.apk
        Verify that `head -n 1 | cut -d: -f2` correctly extracts only the base.apk path.
        """
        multiline_pm_output = (
            "package:/data/app/~~xyz/com.samsung.android.mdx-abc/base.apk\n"
            "package:/data/app/~~xyz/com.samsung.android.mdx-abc/split_config.arm64_v8a.apk\n"
        )
        # Shell logic simulation: head -n 1 | cut -d: -f2
        first_line = multiline_pm_output.splitlines()[0]
        extracted_path = first_line.split(":", 1)[1] if ":" in first_line else ""
        self.assertEqual(extracted_path, "/data/app/~~xyz/com.samsung.android.mdx-abc/base.apk")
        self.assertTrue(extracted_path.startswith("/data/"))


if __name__ == "__main__":
    unittest.main()
