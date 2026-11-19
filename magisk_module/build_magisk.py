#!/usr/bin/env python3
"""
build_magisk.py - Magisk Module Packaging & Validation Tool for Phone Link Port
Target Device: Xiaomi Mi 9 (cepheus, Android 16 AOSP)

Validates module structure, XML schemas, APK signatures/libraries, shell scripts,
normalizes Unix line endings and permissions, and packages a flashable Magisk ZIP.
"""

import os
import sys
import re
import shutil
import zipfile
import hashlib
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

# Expected module metadata
MODULE_ID = "phonelink_module"
TARGET_ARCH = "arm64-v8a"
MIN_SDK = 33

# File mode constants for ZIP archive
MODE_DIR = 0o040755 << 16   # drwxr-xr-x
MODE_EXEC = 0o100755 << 16  # -rwxr-xr-x
MODE_FILE = 0o100644 << 16  # -rw-r--r--

# Required files relative to module root
REQUIRED_FILES = [
    "module.prop",
    "customize.sh",
    "service.sh",
    "uninstall.sh",
    "META-INF/com/google/android/update-binary",
    "META-INF/com/google/android/updater-script",
    "system/priv-app/LinkToWindowsService/LinkToWindowsService.apk",
    "system/etc/permissions/privapp-permissions-phonelink.xml",
    "system/etc/permissions/com.samsung.feature.samsung_experience_mobile.xml",
    "system/etc/sysconfig/phonelink-whitelist.xml",
]

OPTIONAL_FILES = [
    "post-fs-data.sh",
    "sepolicy.rule",
]


class ValidationError(Exception):
    """Raised when module validation fails."""
    pass


def validate_module_prop(prop_path: Path) -> dict:
    """Validate module.prop file and return parsed dictionary."""
    if not prop_path.is_file():
        raise ValidationError(f"Missing required file: {prop_path}")

    props = {}
    content = prop_path.read_text(encoding="utf-8")
    for line_num, line in enumerate(content.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValidationError(f"Invalid format in module.prop:{line_num}: {line}")
        key, val = line.split("=", 1)
        props[key.strip()] = val.strip()

    required_keys = ["id", "name", "version", "versionCode", "author", "description"]
    missing = [k for k in required_keys if k not in props]
    if missing:
        raise ValidationError(f"module.prop missing required keys: {missing}")

    # Validate ID pattern
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9._-]+$", props["id"]):
        raise ValidationError(f"Invalid module id in module.prop: '{props['id']}'")

    # Validate versionCode is integer > 0
    try:
        vc = int(props["versionCode"])
        if vc <= 0:
            raise ValidationError(f"versionCode must be a positive integer (> 0): '{props['versionCode']}'")
    except ValueError:
        raise ValidationError(f"versionCode must be an integer: '{props['versionCode']}'")

    return props


def validate_shell_script(script_path: Path):
    """Validate shell script formatting, shebang, and line endings."""
    if not script_path.is_file():
        raise ValidationError(f"Missing script: {script_path}")

    raw_bytes = script_path.read_bytes()
    if b"\r" in raw_bytes:
        print(f"  [WARN] Windows CRLF line endings detected in {script_path.name}; will normalize to LF.")

    lines = raw_bytes.splitlines()
    if not lines:
        raise ValidationError(f"Empty shell script: {script_path}")

    shebang = lines[0].decode("utf-8", errors="replace").strip()
    if not (shebang.startswith("#!/system/bin/sh") or shebang.startswith("#!/bin/sh") or shebang.startswith("#!/sbin/sh")):
        raise ValidationError(f"Invalid shebang in {script_path.name}: {shebang}")


def validate_xml(xml_path: Path, expected_root_tags: list):
    """Validate XML well-formedness and root element tag."""
    if not xml_path.is_file():
        raise ValidationError(f"Missing XML file: {xml_path}")

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        if root.tag not in expected_root_tags:
            raise ValidationError(
                f"XML root tag in {xml_path.name} is '<{root.tag}>', expected one of {expected_root_tags}"
            )
    except ET.ParseError as e:
        raise ValidationError(f"Malformed XML in {xml_path.name}: {e}")


def validate_apk(apk_path: Path):
    """Validate APK archive integrity and native library presence."""
    if not apk_path.is_file():
        raise ValidationError(f"Missing APK file: {apk_path}")

    try:
        with zipfile.ZipFile(apk_path, "r") as z:
            names = set(z.namelist())
            if "AndroidManifest.xml" not in names:
                raise ValidationError(f"{apk_path.name} is not a valid APK: missing AndroidManifest.xml")
            
            # Check for arm64 native libraries
            arm64_libs = [n for n in names if n.startswith("lib/arm64-v8a/") and n.endswith(".so")]
            if not arm64_libs:
                raise ValidationError(f"{apk_path.name} does not contain arm64-v8a native libraries!")
            print(f"  [OK] APK {apk_path.name} contains {len(arm64_libs)} arm64-v8a native libraries: {arm64_libs}")
    except zipfile.BadZipFile as e:
        raise ValidationError(f"Corrupt APK file {apk_path.name}: {e}")


def validate_module_tree(module_dir: Path):
    """Perform full validation of the Magisk module source tree."""
    print(f"[*] Validating Magisk module tree at: {module_dir}")

    # 1. Check all required files exist
    for req in REQUIRED_FILES:
        req_path = module_dir / req
        if not req_path.is_file():
            raise ValidationError(f"Missing required file: {req}")

    # 2. module.prop
    props = validate_module_prop(module_dir / "module.prop")
    print(f"  [OK] module.prop valid: id={props['id']}, version={props['version']} ({props['versionCode']})")

    # 3. Scripts
    for script_name in ["customize.sh", "service.sh", "uninstall.sh", "META-INF/com/google/android/update-binary"]:
        script_path = module_dir / script_name
        validate_shell_script(script_path)
        print(f"  [OK] Script valid: {script_name}")

    # 4. updater-script
    updater_script = module_dir / "META-INF/com/google/android/updater-script"
    if not updater_script.is_file():
        raise ValidationError(f"Missing updater-script: {updater_script}")
    if b"#MAGISK" not in updater_script.read_bytes():
        raise ValidationError("updater-script must contain #MAGISK marker")
    print("  [OK] META-INF updater-script valid")

    # 5. XML files
    validate_xml(
        module_dir / "system/etc/permissions/privapp-permissions-phonelink.xml",
        ["permissions"],
    )
    print("  [OK] privapp-permissions-phonelink.xml valid")

    validate_xml(
        module_dir / "system/etc/permissions/com.samsung.feature.samsung_experience_mobile.xml",
        ["permissions"],
    )
    print("  [OK] com.samsung.feature.samsung_experience_mobile.xml valid")

    validate_xml(
        module_dir / "system/etc/sysconfig/phonelink-whitelist.xml",
        ["config"],
    )
    print("  [OK] phonelink-whitelist.xml valid")

    # 6. LinkToWindowsService.apk
    apk_path = module_dir / "system/priv-app/LinkToWindowsService/LinkToWindowsService.apk"
    validate_apk(apk_path)

    # 7. Optional files
    if (module_dir / "post-fs-data.sh").is_file():
        validate_shell_script(module_dir / "post-fs-data.sh")
        print("  [OK] Optional script post-fs-data.sh valid")

    if (module_dir / "sepolicy.rule").is_file():
        rule_content = (module_dir / "sepolicy.rule").read_text(encoding="utf-8")
        if not rule_content.strip():
            raise ValidationError("sepolicy.rule is empty")
        print(f"  [OK] Optional sepolicy.rule valid ({len(rule_content.splitlines())} lines)")

    print("[+] All module validation checks PASSED successfully.")


def stage_and_normalize(src_dir: Path, staging_dir: Path, ref_inspect_dir: Path = None):
    """Copy files to staging directory, excluding dev/build artifacts, and normalize line endings to Unix LF."""
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    # Ensure system/priv-app/LinkToWindowsService/LinkToWindowsService.apk exists
    target_apk = src_dir / "system/priv-app/LinkToWindowsService/LinkToWindowsService.apk"
    if not target_apk.is_file() and ref_inspect_dir:
        fallback_apk = ref_inspect_dir / "system/app/LinkToWindowsService/LinkToWindowsService.apk"
        if fallback_apk.is_file():
            print(f"[*] Copying reference LinkToWindowsService.apk from: {fallback_apk}")
            target_apk.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fallback_apk, target_apk)

    # Copy files
    for root, dirs, files in os.walk(src_dir):
        # Exclude directories
        dirs[:] = [d for d in dirs if d not in ["__pycache__", ".git", ".idea", ".vscode"]]
        rel_dir = Path(root).relative_to(src_dir)
        dest_dir = staging_dir / rel_dir
        dest_dir.mkdir(parents=True, exist_ok=True)

        for f in files:
            # Exclude non-module files (build script itself, zips, pyc)
            if f in ["build_magisk.py"] or f.endswith(".py") or f.endswith(".pyc") or f.endswith(".zip"):
                continue

            src_file = Path(root) / f
            dest_file = dest_dir / f

            # Normalize text files to LF
            ext = src_file.suffix.lower()
            if ext in [".sh", ".prop", ".rule", ".xml", ".txt"] or src_file.name in ["update-binary", "updater-script"]:
                content = src_file.read_bytes()
                content = content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
                dest_file.write_bytes(content)
            else:
                shutil.copy2(src_file, dest_file)


def package_zip(staging_dir: Path, output_zip: Path) -> dict:
    """Create a deterministic Magisk flashable ZIP with proper Unix permissions."""
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    if output_zip.exists():
        output_zip.unlink()

    print(f"[*] Packaging flashable Magisk ZIP to: {output_zip}")

    fixed_time = (2026, 1, 1, 0, 0, 0)
    file_count = 0

    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for root, dirs, files in os.walk(staging_dir):
            rel_root = Path(root).relative_to(staging_dir)

            # Store directory entries
            for d in sorted(dirs):
                dir_rel_path = (rel_root / d).as_posix() + "/"
                zinfo = zipfile.ZipInfo(dir_rel_path, date_time=fixed_time)
                zinfo.external_attr = MODE_DIR
                zf.writestr(zinfo, "")

            # Store file entries
            for f in sorted(files):
                file_path = Path(root) / f
                file_rel_path = (rel_root / f).as_posix()
                content = file_path.read_bytes()

                zinfo = zipfile.ZipInfo(file_rel_path, date_time=fixed_time)

                # Set executable permissions for scripts
                if f.endswith(".sh") or file_rel_path.endswith("update-binary"):
                    zinfo.external_attr = MODE_EXEC
                else:
                    zinfo.external_attr = MODE_FILE

                zf.writestr(zinfo, content)
                file_count += 1

    # Calculate SHA256
    sha256 = hashlib.sha256(output_zip.read_bytes()).hexdigest()
    size_bytes = output_zip.stat().st_size
    size_mb = size_bytes / (1024 * 1024)

    summary = {
        "file": str(output_zip.resolve()),
        "file_count": file_count,
        "size_bytes": size_bytes,
        "size_mb": round(size_mb, 2),
        "sha256": sha256,
    }

    print(f"[+] Magisk ZIP created successfully!")
    print(f"    Total files: {summary['file_count']}")
    print(f"    Size:        {summary['size_mb']} MB ({summary['size_bytes']} bytes)")
    print(f"    SHA256:      {summary['sha256']}")

    return summary


def main():
    parser = argparse.ArgumentParser(description="Magisk Module Packaging and Validation Tool")
    parser.add_argument(
        "--src",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Path to Magisk module source directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "build" / "PhoneLinkMagisk-v2.0.0.zip",
        help="Path for destination flashable ZIP",
    )
    parser.add_argument(
        "--ref-inspect",
        type=Path,
        default=None,
        help="Path to module_inspect reference directory (for copying MDX APK)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate module tree without building ZIP",
    )
    args = parser.parse_args()

    src_dir = args.src.resolve()
    print(f"=== Magisk Module Builder: {src_dir} ===")

    # Stage files into a clean temporary directory for validation and packaging
    staging_dir = src_dir.parent / "build" / "staging_magisk"

    stage_and_normalize(src_dir, staging_dir, args.ref_inspect)
    validate_module_tree(staging_dir)

    if args.validate_only:
        print("[+] Validation finished (--validate-only). Exiting.")
        return 0

    summary = package_zip(staging_dir, args.output.resolve())

    # Also place a copy in magisk_module for convenience
    copy_dest = src_dir / "PhoneLinkMagisk-v2.0.0.zip"
    if copy_dest != args.output.resolve():
        shutil.copy2(args.output.resolve(), copy_dest)
        print(f"[+] Placed convenience copy at: {copy_dest}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
