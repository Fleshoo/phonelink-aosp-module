#!/usr/bin/env python3
"""
build.py - Master Build Orchestrator for Phone Link Port (Xiaomi Mi 9 / Android 16)
Orchestrates:
1. Magisk Module packaging (PhoneLinkMagisk-v2.1.0.zip) via magisk_module/build_magisk.py
2. LSPosed APK compilation & packaging (PhoneLinkXposed.apk) via lsposed_module/build_lsposed.py
3. Unified release delivery to build/ directory
4. PackagingValidator binary & schema integrity assertions
5. SHA-256 checksum generation and SHA256SUMS.txt manifest creation
6. Optional full E2E test suite gating (--test)
"""

import os
import sys
import shutil
import zipfile
import hashlib
import argparse
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
BUILD_DIR = REPO_ROOT / "build"
MAGISK_DIR = REPO_ROOT / "magisk_module"
LSPOSED_DIR = REPO_ROOT / "lsposed_module"
TESTS_DIR = REPO_ROOT / "tests"

# Target deliverables in build/
MAGISK_ZIP_NAME = "PhoneLinkMagisk-v2.1.0.zip"
LSPOSED_APK_NAME = "PhoneLinkXposed.apk"
CHECKSUM_FILE_NAME = "SHA256SUMS.txt"

TARGET_MAGISK_ZIP = BUILD_DIR / MAGISK_ZIP_NAME
TARGET_LSPOSED_APK = BUILD_DIR / LSPOSED_APK_NAME
TARGET_CHECKSUM_FILE = BUILD_DIR / CHECKSUM_FILE_NAME

# Ensure repo root is on sys.path for PackagingValidator
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.mock_env.packaging_validator import PackagingValidator


def compute_sha256(file_path: Path) -> str:
    """Compute hex-encoded SHA-256 digest of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def run_magisk_build(clean: bool = False) -> Path:
    """Invoke magisk_module/build_magisk.py via subprocess."""
    print("\n" + "=" * 80)
    print("  [STEP 1/4] Building Magisk Module Package")
    print("=" * 80)

    build_script = MAGISK_DIR / "build_magisk.py"
    if not build_script.is_file():
        raise FileNotFoundError(f"Missing Magisk build script: {build_script}")

    cmd = [
        sys.executable,
        str(build_script),
        "--src", str(MAGISK_DIR),
        "--output", str(TARGET_MAGISK_ZIP),
    ]
    res = subprocess.run(cmd, cwd=str(REPO_ROOT))
    if res.returncode != 0:
        raise RuntimeError(f"Magisk build failed with exit code {res.returncode}")

    if not TARGET_MAGISK_ZIP.is_file():
        raise FileNotFoundError(f"Expected Magisk output not found: {TARGET_MAGISK_ZIP}")

    print(f"[+] Magisk build complete: {TARGET_MAGISK_ZIP} ({TARGET_MAGISK_ZIP.stat().st_size:,} bytes)")
    return TARGET_MAGISK_ZIP


def run_lsposed_build() -> Path:
    """Invoke lsposed_module/build_lsposed.py via subprocess and copy to build/."""
    print("\n" + "=" * 80)
    print("  [STEP 2/4] Compiling & Building LSPosed Module APK")
    print("=" * 80)

    build_script = LSPOSED_DIR / "build_lsposed.py"
    if not build_script.is_file():
        raise FileNotFoundError(f"Missing LSPosed build script: {build_script}")

    cmd = [sys.executable, str(build_script)]
    res = subprocess.run(cmd, cwd=str(LSPOSED_DIR))
    if res.returncode != 0:
        raise RuntimeError(f"LSPosed build failed with exit code {res.returncode}")

    # Primary output from build_lsposed.py
    src_apk = LSPOSED_DIR / "build" / "outputs" / "apk" / "release" / LSPOSED_APK_NAME
    if not src_apk.is_file():
        src_apk = LSPOSED_DIR / LSPOSED_APK_NAME

    if not src_apk.is_file():
        raise FileNotFoundError(f"Expected LSPosed output not found: {src_apk}")

    # Copy to root build/
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_apk, TARGET_LSPOSED_APK)
    print(f"[+] LSPosed APK placed in release directory: {TARGET_LSPOSED_APK} ({TARGET_LSPOSED_APK.stat().st_size:,} bytes)")
    return TARGET_LSPOSED_APK


def validate_release_artifacts():
    """Execute PackagingValidator assertions on built deliverables."""
    print("\n" + "=" * 80)
    print("  [STEP 3/4] Validating Release Artifacts (PackagingValidator)")
    print("=" * 80)

    # 1. Validate Magisk ZIP
    if not TARGET_MAGISK_ZIP.is_file():
        raise FileNotFoundError(f"Magisk ZIP not found for validation: {TARGET_MAGISK_ZIP}")

    with zipfile.ZipFile(TARGET_MAGISK_ZIP, "r") as z:
        names = z.namelist()
        valid_struct, missing = PackagingValidator.validate_magisk_structure(names)
        if not valid_struct:
            raise RuntimeError(f"Magisk ZIP missing mandatory components: {missing}")

        prop_content = z.read("module.prop").decode("utf-8")
        valid_prop, props, missing_keys = PackagingValidator.validate_module_prop(prop_content)
        if not valid_prop:
            raise RuntimeError(f"Magisk module.prop missing required keys: {missing_keys}")

        privapp_xml = z.read("system/etc/permissions/privapp-permissions-phonelink.xml").decode("utf-8")
        valid_priv, priv_errs = PackagingValidator.validate_privapp_xml(privapp_xml)
        if not valid_priv:
            raise RuntimeError(f"privapp-permissions validation failed: {priv_errs}")

        sysconfig_xml = z.read("system/etc/sysconfig/phonelink-whitelist.xml").decode("utf-8")
        valid_sys, sys_errs = PackagingValidator.validate_sysconfig_xml(sysconfig_xml)
        if not valid_sys:
            raise RuntimeError(f"sysconfig validation failed: {sys_errs}")

    print("[+] Magisk ZIP passed all structural, permission, and XML schema checks.")

    # 2. Validate LSPosed APK
    if not TARGET_LSPOSED_APK.is_file():
        raise FileNotFoundError(f"LSPosed APK not found for validation: {TARGET_LSPOSED_APK}")

    with zipfile.ZipFile(TARGET_LSPOSED_APK, "r") as apk:
        file_list = apk.namelist()
        init_content = apk.read("assets/xposed_init").decode("utf-8").strip()
        packaged_dex = apk.read("classes.dex")

    valid_apk, apk_errs = PackagingValidator.validate_lsposed_apk(
        file_list, init_content, dex_bytes=packaged_dex
    )
    if not valid_apk:
        raise RuntimeError(f"LSPosed APK validation failed: {apk_errs}")

    print("[+] LSPosed APK passed all asset, entrypoint, and DEX bytecode checks.")


def generate_checksums() -> dict:
    """Generate SHA256 checksums and write SHA256SUMS.txt."""
    print("\n" + "=" * 80)
    print("  [STEP 4/4] Computing SHA-256 Checksums & Generating Manifest")
    print("=" * 80)

    hashes = {}
    lines = []
    for file_path in [TARGET_MAGISK_ZIP, TARGET_LSPOSED_APK]:
        sha = compute_sha256(file_path)
        hashes[file_path.name] = sha
        lines.append(f"{sha}  {file_path.name}")
        print(f"  - {file_path.name:<28}: {sha} ({file_path.stat().st_size:,} bytes)")

    TARGET_CHECKSUM_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[+] Wrote SHA-256 manifest to: {TARGET_CHECKSUM_FILE}")
    return hashes


def run_e2e_tests():
    """Optional execution of full 4-tier E2E test runner."""
    print("\n" + "=" * 80)
    print("  [TEST SUITE] Executing Full E2E Test Suite (Tiers 1-4)")
    print("=" * 80)
    test_runner = TESTS_DIR / "test_runner.py"
    res = subprocess.run([sys.executable, str(test_runner)], cwd=str(REPO_ROOT))
    if res.returncode != 0:
        raise RuntimeError(f"E2E test suite failed with exit code {res.returncode}")


def main():
    parser = argparse.ArgumentParser(description="Master Build Script for Phone Link Module")
    parser.add_argument("--clean", action="store_true", help="Clean build/ staging before packaging")
    parser.add_argument("--magisk-only", action="store_true", help="Build only Magisk module")
    parser.add_argument("--lsposed-only", action="store_true", help="Build only LSPosed APK")
    parser.add_argument("--test", action="store_true", help="Run full E2E test suite after build")
    parser.add_argument("--verify", action="store_true", help="Verify existing build artifacts without rebuilding")
    args = parser.parse_args()

    if args.clean and BUILD_DIR.exists():
        print(f"[*] Cleaning build directory: {BUILD_DIR}")
        for item in [TARGET_MAGISK_ZIP, TARGET_LSPOSED_APK, TARGET_CHECKSUM_FILE]:
            if item.is_file():
                item.unlink()

    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    if args.verify:
        validate_release_artifacts()
        if not TARGET_CHECKSUM_FILE.is_file():
            raise FileNotFoundError(f"Missing SHA-256 checksum manifest: {TARGET_CHECKSUM_FILE}")
        print("[*] Verifying existing SHA-256 manifest...")
        for line in TARGET_CHECKSUM_FILE.read_text(encoding="utf-8").splitlines():
            line_str = line.strip()
            if not line_str or line_str.startswith("#"):
                continue
            parts = line_str.split(None, 1)
            if len(parts) != 2:
                raise ValueError(f"Malformed manifest line in {TARGET_CHECKSUM_FILE}: '{line_str}'")
            expected_sha, fname = parts
            target_file = BUILD_DIR / fname
            if not target_file.is_file():
                raise FileNotFoundError(f"Missing artifact referenced in manifest: {target_file}")
            actual_sha = compute_sha256(target_file)
            if expected_sha != actual_sha:
                raise AssertionError(f"Checksum mismatch for {fname}: expected {expected_sha}, got {actual_sha}")
            print(f"  [OK] {fname}: {actual_sha}")
        print("\n[SUCCESS] Verification passed cleanly.")
        return 0

    if not args.lsposed_only:
        run_magisk_build(clean=args.clean)

    if not args.magisk_only:
        run_lsposed_build()

    if not args.magisk_only and not args.lsposed_only:
        validate_release_artifacts()
        generate_checksums()

    if args.test:
        run_e2e_tests()

    print("\n" + "=" * 80)
    print("  [COMPLETE] Master Build Finished Successfully!")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"\n[ERROR] Build aborted: {e}", file=sys.stderr)
        sys.exit(1)
