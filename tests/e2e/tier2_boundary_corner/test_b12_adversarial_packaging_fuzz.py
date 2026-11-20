"""
Adversarial Packaging & Boundary Fuzzing Test Suite
Targets: PhoneLinkMagisk-v2.0.0.zip, build_magisk.py, and PackagingValidator.

Verification checks:
1. Corrupted ZIP files, missing mandatory files from module root.
2. Malformed XML in privapp-permissions and sysconfig allowlists (unclosed tags, missing package attributes).
3. Injected CRLF line endings in shell scripts.
4. Truncated or dummy APK files lacking arm64-v8a native libraries.
5. Accurate rejection of all bad inputs and approval of genuine builds.
"""

import io
import os
import sys
import shutil
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.mock_env.packaging_validator import PackagingValidator
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


class TestGenuineMagiskZipPackaging(unittest.TestCase):
    """Verifies that genuine PhoneLinkMagisk-v2.1.0.zip satisfies all production criteria."""

    @classmethod
    def setUpClass(cls):
        cls.zip_path = PROJECT_ROOT / "build" / "PhoneLinkMagisk-v2.1.0.zip"
        if not cls.zip_path.is_file():
            # Check fallback in magisk_module
            fallback = PROJECT_ROOT / "magisk_module" / "PhoneLinkMagisk-v2.1.0.zip"
            if fallback.is_file():
                cls.zip_path = fallback

    def test_genuine_zip_exists_and_is_valid_archive(self):
        self.assertTrue(self.zip_path.is_file(), f"PhoneLinkMagisk-v2.1.0.zip not found at {self.zip_path}")
        self.assertTrue(zipfile.is_zipfile(self.zip_path), "File is not a valid ZIP archive")

    def test_genuine_zip_packaging_validator_approval(self):
        with zipfile.ZipFile(self.zip_path, "r") as z:
            names = z.namelist()
            valid_struct, missing = PackagingValidator.validate_magisk_structure(names)
            self.assertTrue(valid_struct, f"Genuine ZIP failed structure check. Missing: {missing}")
            self.assertEqual(len(missing), 0)

            # Validate module.prop
            prop_content = z.read("module.prop").decode("utf-8")
            valid_prop, props, missing_keys = PackagingValidator.validate_module_prop(prop_content)
            self.assertTrue(valid_prop, f"Genuine module.prop failed check. Missing keys: {missing_keys}")
            self.assertEqual(props["id"], "phonelink_module")
            self.assertEqual(props["version"], "v2.1.0")
            self.assertEqual(props["versionCode"], "210")

            # Validate privapp XML
            privapp_xml = z.read("system/etc/permissions/privapp-permissions-phonelink.xml").decode("utf-8")
            valid_priv, priv_errors = PackagingValidator.validate_privapp_xml(privapp_xml)
            self.assertTrue(valid_priv, f"Genuine privapp XML failed check: {priv_errors}")

            # Validate sysconfig XML
            sysconfig_xml = z.read("system/etc/sysconfig/phonelink-whitelist.xml").decode("utf-8")
            valid_sys, sys_errors = PackagingValidator.validate_sysconfig_xml(sysconfig_xml)
            self.assertTrue(valid_sys, f"Genuine sysconfig XML failed check: {sys_errors}")

    def test_genuine_zip_zero_crlf_contamination(self):
        with zipfile.ZipFile(self.zip_path, "r") as z:
            crlf_files = []
            for name in z.namelist():
                if name.endswith("/") or name.endswith(".apk") or name.endswith(".so"):
                    continue
                content = z.read(name)
                if b"\r" in content:
                    crlf_files.append(name)
            self.assertEqual(crlf_files, [], f"CRLF line endings detected in genuine build files: {crlf_files}")

    def test_genuine_zip_unix_file_permissions(self):
        with zipfile.ZipFile(self.zip_path, "r") as z:
            for info in z.infolist():
                mode = info.external_attr >> 16
                if info.filename.endswith("/"):
                    self.assertEqual(mode, 0o040755, f"Directory {info.filename} does not have 0755 mode (got {oct(mode)})")
                elif info.filename.endswith(".sh") or info.filename.endswith("update-binary"):
                    self.assertEqual(mode, 0o100755, f"Script {info.filename} does not have 0755 executable mode (got {oct(mode)})")
                else:
                    self.assertEqual(mode, 0o100644, f"File {info.filename} does not have 0644 mode (got {oct(mode)})")

    def test_genuine_zip_embedded_apk_has_arm64_libraries(self):
        with zipfile.ZipFile(self.zip_path, "r") as z:
            apk_bytes = z.read("system/priv-app/LinkToWindowsService/LinkToWindowsService.apk")
            with zipfile.ZipFile(io.BytesIO(apk_bytes), "r") as apk_zip:
                names = set(apk_zip.namelist())
                self.assertIn("AndroidManifest.xml", names)
                arm64_libs = [n for n in names if n.startswith("lib/arm64-v8a/") and n.endswith(".so")]
                self.assertGreaterEqual(len(arm64_libs), 2)
                self.assertIn("lib/arm64-v8a/libKeyboardLib.so", arm64_libs)
                self.assertIn("lib/arm64-v8a/libDiagMonKey.so", arm64_libs)


class TestAdversarialZipCorruption(unittest.TestCase):
    """Stress tests PackagingValidator and build_magisk against corrupted ZIP archives."""

    def test_truncated_and_garbage_zip_rejection(self):
        garbage_payloads = [
            b"",
            b"PK\x03\x04",  # Truncated local file header
            b"PK\x05\x06" + b"\x00" * 10,  # Truncated EOCD
            b"\x00" * 512,  # Zero-filled buffer
            os.urandom(1024),  # High-entropy random noise
            b"NOT_A_ZIP_HEADER" + os.urandom(256),
        ]
        for idx, payload in enumerate(garbage_payloads):
            with self.subTest(payload_idx=idx):
                buf = io.BytesIO(payload)
                self.assertFalse(zipfile.is_zipfile(buf))
                with self.assertRaises((zipfile.BadZipFile, EOFError)):
                    with zipfile.ZipFile(buf, "r") as z:
                        _ = z.namelist()

    def test_empty_zip_structure_rejected(self):
        valid, missing = PackagingValidator.validate_magisk_structure([])
        self.assertFalse(valid)
        self.assertEqual(set(missing), PackagingValidator.REQUIRED_MAGISK_FILES)


class TestAdversarialMissingMandatoryFilesFuzz(unittest.TestCase):
    """Fuzzes structure validation by omitting mandatory root and nested module files."""

    COMPLETE_FILE_LIST = [
        "META-INF/com/google/android/update-binary",
        "META-INF/com/google/android/updater-script",
        "module.prop",
        "customize.sh",
        "service.sh",
        "uninstall.sh",
        "system/priv-app/LinkToWindowsService/LinkToWindowsService.apk",
        "system/etc/permissions/privapp-permissions-phonelink.xml",
        "system/etc/permissions/com.samsung.feature.samsung_experience_mobile.xml",
        "system/etc/sysconfig/phonelink-whitelist.xml",
    ]

    def test_single_missing_mandatory_file_permutations(self):
        for req_file in PackagingValidator.REQUIRED_MAGISK_FILES:
            with self.subTest(omitted_file=req_file):
                incomplete = [f for f in self.COMPLETE_FILE_LIST if f != req_file]
                valid, missing = PackagingValidator.validate_magisk_structure(incomplete)
                self.assertFalse(valid)
                self.assertEqual(missing, [req_file])

    def test_pairwise_missing_mandatory_files(self):
        req_list = sorted(list(PackagingValidator.REQUIRED_MAGISK_FILES))
        for i in range(len(req_list) - 1):
            file_a = req_list[i]
            file_b = req_list[i + 1]
            with self.subTest(pair=(file_a, file_b)):
                incomplete = [f for f in self.COMPLETE_FILE_LIST if f not in (file_a, file_b)]
                valid, missing = PackagingValidator.validate_magisk_structure(incomplete)
                self.assertFalse(valid)
                self.assertEqual(set(missing), {file_a, file_b})

    def test_path_separator_and_leading_slash_normalization(self):
        # Even with Windows backslashes and leading slashes, validator normalizes correctly
        windows_style = [f.replace("/", "\\") for f in self.COMPLETE_FILE_LIST]
        valid, missing = PackagingValidator.validate_magisk_structure(windows_style)
        self.assertTrue(valid)
        self.assertEqual(missing, [])

        leading_slash = ["/" + f for f in self.COMPLETE_FILE_LIST]
        valid, missing = PackagingValidator.validate_magisk_structure(leading_slash)
        self.assertTrue(valid)
        self.assertEqual(missing, [])


class TestAdversarialMalformedPrivappXml(unittest.TestCase):
    """Adversarially fuzzes privapp-permissions XML parsing and validation."""

    def test_unclosed_xml_tags_rejected(self):
        malformed_inputs = [
            "<permissions><privapp-permissions package='com.samsung.android.mdx'>",
            "<permissions><privapp-permissions package='com.samsung.android.mdx'><permission name='android.permission.WRITE_SECURE_SETTINGS'>",
            "<permissions><privapp-permissions",
            "<?xml version='1.0'?><permissions>",
            "<permissions><unclosed",
        ]
        for bad_xml in malformed_inputs:
            with self.subTest(bad_xml=bad_xml):
                valid, errors = PackagingValidator.validate_privapp_xml(bad_xml)
                self.assertFalse(valid)
                self.assertTrue(any("XML parse error" in e for e in errors))

    def test_missing_package_attribute_rejected(self):
        bad_xml = """
        <permissions>
            <privapp-permissions>
                <permission name="android.permission.WRITE_SECURE_SETTINGS"/>
                <permission name="android.permission.INTERACT_ACROSS_USERS"/>
                <permission name="android.permission.BATTERY_STATS"/>
            </privapp-permissions>
        </permissions>
        """
        valid, errors = PackagingValidator.validate_privapp_xml(bad_xml)
        self.assertFalse(valid)
        self.assertTrue(any("Missing <privapp-permissions package='com.samsung.android.mdx'>" in e for e in errors))

    def test_wrong_package_attribute_rejected(self):
        bad_xml = """
        <permissions>
            <privapp-permissions package="com.google.android.gms">
                <permission name="android.permission.WRITE_SECURE_SETTINGS"/>
                <permission name="android.permission.INTERACT_ACROSS_USERS"/>
                <permission name="android.permission.BATTERY_STATS"/>
            </privapp-permissions>
        </permissions>
        """
        valid, errors = PackagingValidator.validate_privapp_xml(bad_xml)
        self.assertFalse(valid)
        self.assertTrue(any("Missing <privapp-permissions package='com.samsung.android.mdx'>" in e for e in errors))

    def test_missing_required_permissions_rejected(self):
        required = [
            "android.permission.WRITE_SECURE_SETTINGS",
            "android.permission.INTERACT_ACROSS_USERS",
            "android.permission.BATTERY_STATS",
        ]
        for omitted in required:
            with self.subTest(omitted_perm=omitted):
                remaining = [p for p in required if p != omitted]
                perm_tags = "".join(f'<permission name="{p}"/>' for p in remaining)
                xml = f'<permissions><privapp-permissions package="com.samsung.android.mdx">{perm_tags}</privapp-permissions></permissions>'
                valid, errors = PackagingValidator.validate_privapp_xml(xml)
                self.assertFalse(valid)
                self.assertTrue(any("Missing required permissions" in e for e in errors))

    def test_empty_or_whitespace_or_null_bytes_rejected(self):
        for bad_input in ["", "   \n\t   ", "\x00\x00\x00"]:
            with self.subTest(bad_input=bad_input):
                valid, errors = PackagingValidator.validate_privapp_xml(bad_input)
                self.assertFalse(valid)
                self.assertGreater(len(errors), 0)


class TestAdversarialMalformedSysconfigXml(unittest.TestCase):
    """Adversarially fuzzes sysconfig allowlist XML parsing and validation."""

    def test_unclosed_xml_tags_rejected(self):
        malformed_inputs = [
            "<config><allow-in-power-save package='com.samsung.android.mdx'>",
            "<config><allow-in-data-saver",
            "<?xml version='1.0'?><config>",
        ]
        for bad_xml in malformed_inputs:
            with self.subTest(bad_xml=bad_xml):
                valid, errors = PackagingValidator.validate_sysconfig_xml(bad_xml)
                self.assertFalse(valid)
                self.assertTrue(any("XML parse error" in e for e in errors))

    def test_missing_package_attribute_rejected(self):
        bad_xml = """
        <config>
            <allow-in-power-save />
            <allow-in-data-saver />
        </config>
        """
        valid, errors = PackagingValidator.validate_sysconfig_xml(bad_xml)
        self.assertFalse(valid)
        self.assertTrue(any("Missing <allow-in-power-save>" in e for e in errors))
        self.assertTrue(any("Missing <allow-in-data-saver>" in e for e in errors))

    def test_missing_individual_package_allowlists(self):
        scenarios = [
            # (power_pkgs, data_pkgs, expected_missing_substr)
            (["com.microsoft.appmanager"], ["com.samsung.android.mdx", "com.microsoft.appmanager"], "Missing <allow-in-power-save>"),
            (["com.samsung.android.mdx"], ["com.samsung.android.mdx", "com.microsoft.appmanager"], "Missing <allow-in-power-save>"),
            (["com.samsung.android.mdx", "com.microsoft.appmanager"], ["com.microsoft.appmanager"], "Missing <allow-in-data-saver>"),
            (["com.samsung.android.mdx", "com.microsoft.appmanager"], ["com.samsung.android.mdx"], "Missing <allow-in-data-saver>"),
        ]
        for power_pkgs, data_pkgs, expected_substr in scenarios:
            with self.subTest(power=power_pkgs, data=data_pkgs):
                power_tags = "".join(f'<allow-in-power-save package="{p}"/>' for p in power_pkgs)
                data_tags = "".join(f'<allow-in-data-saver package="{p}"/>' for p in data_pkgs)
                xml = f"<config>{power_tags}{data_tags}</config>"
                valid, errors = PackagingValidator.validate_sysconfig_xml(xml)
                self.assertFalse(valid)
                self.assertTrue(any(expected_substr in e for e in errors))

    def test_empty_or_whitespace_or_null_bytes_rejected(self):
        for bad_input in ["", "  \n  ", "\x00\x00"]:
            with self.subTest(bad_input=bad_input):
                valid, errors = PackagingValidator.validate_sysconfig_xml(bad_input)
                self.assertFalse(valid)
                self.assertGreater(len(errors), 0)


class TestAdversarialCrlfLineEndingsInPipeline(unittest.TestCase):
    """Tests CRLF detection, rejection, and sanitization within build_magisk pipeline."""

    def test_validate_shell_script_shebang_and_empty(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # 1. Non-existent file
            with self.assertRaises(ValidationError) as ctx:
                validate_shell_script(tmp_path / "nonexistent.sh")
            self.assertIn("Missing script", str(ctx.exception))

            # 2. Empty file
            empty_sh = tmp_path / "empty.sh"
            empty_sh.write_bytes(b"")
            with self.assertRaises(ValidationError) as ctx:
                validate_shell_script(empty_sh)
            self.assertIn("Empty shell script", str(ctx.exception))

            # 3. Invalid shebangs
            invalid_shebangs = [
                b"echo hello\n",
                b"#!/usr/bin/python3\n",
                b"#!/bin/bash\n",
                b"# Missing bang\n",
            ]
            for idx, bad_sh_content in enumerate(invalid_shebangs):
                bad_file = tmp_path / f"bad_{idx}.sh"
                bad_file.write_bytes(bad_sh_content)
                with self.assertRaises(ValidationError) as ctx:
                    validate_shell_script(bad_file)
                self.assertIn("Invalid shebang", str(ctx.exception))

            # 4. Valid shebangs pass
            valid_shebangs = [
                b"#!/system/bin/sh\necho ok\n",
                b"#!/bin/sh\necho ok\n",
                b"#!/sbin/sh\necho ok\n",
            ]
            for idx, good_sh in enumerate(valid_shebangs):
                good_file = tmp_path / f"good_{idx}.sh"
                good_file.write_bytes(good_sh)
                validate_shell_script(good_file)  # Should not raise

    def test_stage_and_normalize_purges_injected_crlf(self):
        with tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as dst_tmp:
            src_dir = Path(src_tmp)
            dst_dir = Path(dst_tmp)

            # Infiltrate CRLF into shell script, module.prop, and XML
            (src_dir / "service.sh").write_bytes(b"#!/system/bin/sh\r\n# CRLF injected\r\nexit 0\r\n")
            (src_dir / "module.prop").write_bytes(b"id=test\r\nname=Test\r\nversion=1\r\nversionCode=1\r\nauthor=A\r\ndescription=D\r\n")
            (src_dir / "test.xml").write_bytes(b"<root>\r\n  <child />\r\n</root>\r\n")
            (src_dir / "standalone_cr.sh").write_bytes(b"#!/bin/sh\recho 'old mac cr'\rexit 0\r")

            stage_and_normalize(src_dir, dst_dir)

            for normalized_file in dst_dir.glob("**/*"):
                if normalized_file.is_file():
                    content = normalized_file.read_bytes()
                    self.assertNotIn(b"\r", content, f"File {normalized_file.name} still contains \\r after normalization!")
                    self.assertIn(b"\n", content, f"File {normalized_file.name} lacks Unix \\n")


class TestAdversarialApkValidation(unittest.TestCase):
    """Stress tests validate_apk against truncated archives and missing native libraries."""

    def test_truncated_apk_rejected(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            apk_path = Path(tmp_dir) / "corrupt.apk"
            apk_path.write_bytes(b"PK\x03\x04" + os.urandom(32))
            with self.assertRaises(ValidationError) as ctx:
                validate_apk(apk_path)
            self.assertIn("Corrupt APK file", str(ctx.exception))

    def test_missing_manifest_in_apk_rejected(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            apk_path = Path(tmp_dir) / "no_manifest.apk"
            with zipfile.ZipFile(apk_path, "w") as z:
                z.writestr("classes.dex", b"dummy")
            with self.assertRaises(ValidationError) as ctx:
                validate_apk(apk_path)
            self.assertIn("missing AndroidManifest.xml", str(ctx.exception))

    def test_apk_without_arm64_libraries_rejected(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # 1. Zero libraries
            no_libs_apk = Path(tmp_dir) / "no_libs.apk"
            with zipfile.ZipFile(no_libs_apk, "w") as z:
                z.writestr("AndroidManifest.xml", b"<manifest/>")
                z.writestr("classes.dex", b"dummy")
            with self.assertRaises(ValidationError) as ctx:
                validate_apk(no_libs_apk)
            self.assertIn("does not contain arm64-v8a native libraries", str(ctx.exception))

            # 2. Only x86 or armeabi-v7a libraries
            wrong_arch_apk = Path(tmp_dir) / "wrong_arch.apk"
            with zipfile.ZipFile(wrong_arch_apk, "w") as z:
                z.writestr("AndroidManifest.xml", b"<manifest/>")
                z.writestr("lib/armeabi-v7a/libtest.so", b"\x7fELF")
                z.writestr("lib/x86_64/libtest.so", b"\x7fELF")
            with self.assertRaises(ValidationError) as ctx:
                validate_apk(wrong_arch_apk)
            self.assertIn("does not contain arm64-v8a native libraries", str(ctx.exception))

    def test_apk_with_arm64_libraries_approved(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            good_apk = Path(tmp_dir) / "good.apk"
            with zipfile.ZipFile(good_apk, "w") as z:
                z.writestr("AndroidManifest.xml", b"<manifest/>")
                z.writestr("lib/arm64-v8a/libKeyboardLib.so", b"\x7fELF\x02\x01\x01")
            validate_apk(good_apk)  # Must not raise


class TestAdversarialModulePropValidation(unittest.TestCase):
    """Stress tests validate_module_prop in build_magisk and PackagingValidator."""

    def test_missing_keys_in_packaging_validator(self):
        incomplete_prop = "id=test\nname=Test\nversion=1.0\n"
        valid, props, missing = PackagingValidator.validate_module_prop(incomplete_prop)
        self.assertFalse(valid)
        self.assertIn("versionCode", missing)
        self.assertIn("author", missing)
        self.assertIn("description", missing)

    def test_build_magisk_module_prop_rejections(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prop_file = Path(tmp_dir) / "module.prop"

            # 1. Missing file
            with self.assertRaises(ValidationError) as ctx:
                validate_module_prop(Path(tmp_dir) / "nonexistent.prop")
            self.assertIn("Missing required file", str(ctx.exception))

            # 2. Non key-value format line
            prop_file.write_text("id=test\nINVALID_LINE_WITHOUT_EQUALS\nname=Test", encoding="utf-8")
            with self.assertRaises(ValidationError) as ctx:
                validate_module_prop(prop_file)
            self.assertIn("Invalid format in module.prop", str(ctx.exception))

            # 3. Invalid module ID pattern
            invalid_ids = ["123_starts_with_num", "has space", "has$invalid!chars", ""]
            for bad_id in invalid_ids:
                content = f"id={bad_id}\nname=Test\nversion=1\nversionCode=1\nauthor=A\ndescription=D\n"
                prop_file.write_text(content, encoding="utf-8")
                with self.assertRaises(ValidationError) as ctx:
                    validate_module_prop(prop_file)
                self.assertIn("Invalid module id", str(ctx.exception))

            # 4. Non-integer versionCode
            invalid_vcs = ["v100", "1.0.0", "one", ""]
            for bad_vc in invalid_vcs:
                content = f"id=valid_id\nname=Test\nversion=1\nversionCode={bad_vc}\nauthor=A\ndescription=D\n"
                prop_file.write_text(content, encoding="utf-8")
                with self.assertRaises(ValidationError) as ctx:
                    validate_module_prop(prop_file)
                self.assertIn("versionCode must be an integer", str(ctx.exception))

            # 5. Valid module.prop passes
            good_content = "id=phonelink_module\nname=Phone Link\nversion=v2.0.0\nversionCode=200\nauthor=Teamwork\ndescription=Valid\n"
            prop_file.write_text(good_content, encoding="utf-8")
            parsed = validate_module_prop(prop_file)
            self.assertEqual(parsed["id"], "phonelink_module")
            self.assertEqual(parsed["versionCode"], "200")


class TestAdversarialBuildMagiskTreeValidation(unittest.TestCase):
    """Stress tests build_magisk.validate_module_tree with structural corruptions."""

    def _setup_mock_tree(self, tree_dir: Path):
        # Create all required directories
        (tree_dir / "META-INF/com/google/android").mkdir(parents=True, exist_ok=True)
        (tree_dir / "system/priv-app/LinkToWindowsService").mkdir(parents=True, exist_ok=True)
        (tree_dir / "system/etc/permissions").mkdir(parents=True, exist_ok=True)
        (tree_dir / "system/etc/sysconfig").mkdir(parents=True, exist_ok=True)

        # module.prop
        (tree_dir / "module.prop").write_text(
            "id=phonelink_module\nname=Phone Link\nversion=v2.0.0\nversionCode=200\nauthor=Team\ndescription=Desc\n",
            encoding="utf-8",
        )
        # Scripts
        for s in ["customize.sh", "service.sh", "uninstall.sh", "META-INF/com/google/android/update-binary"]:
            (tree_dir / s).write_bytes(b"#!/system/bin/sh\nexit 0\n")

        # updater-script
        (tree_dir / "META-INF/com/google/android/updater-script").write_bytes(b"#MAGISK\n")

        # XML files
        (tree_dir / "system/etc/permissions/privapp-permissions-phonelink.xml").write_text(
            '<permissions><privapp-permissions package="com.samsung.android.mdx"/></permissions>',
            encoding="utf-8",
        )
        (tree_dir / "system/etc/permissions/com.samsung.feature.samsung_experience_mobile.xml").write_text(
            '<permissions><feature name="com.samsung.feature.samsung_experience_mobile"/></permissions>',
            encoding="utf-8",
        )
        (tree_dir / "system/etc/sysconfig/phonelink-whitelist.xml").write_text(
            '<config><allow-in-power-save package="com.samsung.android.mdx"/></config>',
            encoding="utf-8",
        )

        # Mock APK with arm64 native lib
        apk_path = tree_dir / "system/priv-app/LinkToWindowsService/LinkToWindowsService.apk"
        with zipfile.ZipFile(apk_path, "w") as z:
            z.writestr("AndroidManifest.xml", b"<manifest/>")
            z.writestr("lib/arm64-v8a/libKeyboardLib.so", b"\x7fELF")

    def test_mock_tree_validates_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tree_path = Path(tmp_dir)
            self._setup_mock_tree(tree_path)
            validate_module_tree(tree_path)  # Must pass

    def test_missing_each_required_file_raises_validation_error(self):
        for req_file in REQUIRED_FILES:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tree_path = Path(tmp_dir)
                self._setup_mock_tree(tree_path)
                target = tree_path / req_file
                if target.is_file():
                    target.unlink()
                with self.assertRaises(ValidationError) as ctx:
                    validate_module_tree(tree_path)
                self.assertTrue("Missing required file" in str(ctx.exception) or "Missing" in str(ctx.exception))

    def test_updater_script_missing_magisk_marker_rejected(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tree_path = Path(tmp_dir)
            self._setup_mock_tree(tree_path)
            (tree_path / "META-INF/com/google/android/updater-script").write_bytes(b"NOT_MAGISK\n")
            with self.assertRaises(ValidationError) as ctx:
                validate_module_tree(tree_path)
            self.assertIn("updater-script must contain #MAGISK marker", str(ctx.exception))

    def test_empty_optional_sepolicy_rule_rejected(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tree_path = Path(tmp_dir)
            self._setup_mock_tree(tree_path)
            (tree_path / "sepolicy.rule").write_text("   \n   ", encoding="utf-8")
            with self.assertRaises(ValidationError) as ctx:
                validate_module_tree(tree_path)
            self.assertIn("sepolicy.rule is empty", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
