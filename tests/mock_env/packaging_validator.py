"""
Packaging and Delivery Validator for Magisk Module and LSPosed APK.
Validates structural integrity, required files, permissions manifests,
and module properties.
"""

import struct
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple, Set


class PackagingValidator:
    REQUIRED_MAGISK_FILES: Set[str] = {
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
    }

    REQUIRED_MODULE_PROP_KEYS: Set[str] = {
        "id", "name", "version", "versionCode", "author", "description"
    }

    REQUIRED_LSPOSED_ASSETS: Set[str] = {
        "AndroidManifest.xml",
        "assets/xposed_init",
    }

    @classmethod
    def validate_magisk_structure(cls, file_list: List[str]) -> Tuple[bool, List[str]]:
        normalized_files = {f.replace("\\", "/").lstrip("/") for f in file_list}
        missing = [f for f in cls.REQUIRED_MAGISK_FILES if f not in normalized_files]
        return len(missing) == 0, missing

    @classmethod
    def validate_module_prop(cls, content: str) -> Tuple[bool, Dict[str, str], List[str]]:
        props: Dict[str, str] = {}
        for line_num, line in enumerate(content.strip().splitlines(), start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                props[k.strip()] = v.strip()
            else:
                return False, {}, [f"Invalid format in module.prop line {line_num}: missing '=' in '{line}'"]

        missing_keys = [k for k in cls.REQUIRED_MODULE_PROP_KEYS if k not in props]
        return len(missing_keys) == 0, props, missing_keys

    @classmethod
    def validate_privapp_xml(cls, xml_content: str) -> Tuple[bool, List[str]]:
        errors = []
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            return False, [f"XML parse error: {e}"]

        privapps = root.findall("privapp-permissions")
        if not privapps:
            return False, ["No <privapp-permissions> tags found"]

        mdx_found = False
        for pa in privapps:
            if pa.get("package") == "com.samsung.android.mdx":
                mdx_found = True
                perms = {p.get("name") for p in pa.findall("permission")}
                required_perms = {
                    "android.permission.WRITE_SECURE_SETTINGS",
                    "android.permission.INTERACT_ACROSS_USERS",
                    "android.permission.BATTERY_STATS",
                }
                missing_perms = required_perms - perms
                if missing_perms:
                    errors.append(f"Missing required permissions: {missing_perms}")

        if not mdx_found:
            errors.append("Missing <privapp-permissions package='com.samsung.android.mdx'>")

        return len(errors) == 0, errors

    @classmethod
    def validate_sysconfig_xml(cls, xml_content: str) -> Tuple[bool, List[str]]:
        errors = []
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            return False, [f"XML parse error: {e}"]

        power_save_pkgs = {e.get("package") for e in root.findall("allow-in-power-save")}
        data_saver_pkgs = {e.get("package") for e in root.findall("allow-in-data-saver")}

        required_pkgs = {"com.samsung.android.mdx", "com.microsoft.appmanager"}
        missing_power = required_pkgs - power_save_pkgs
        missing_data = required_pkgs - data_saver_pkgs

        if missing_power:
            errors.append(f"Missing <allow-in-power-save> for: {missing_power}")
        if missing_data:
            errors.append(f"Missing <allow-in-data-saver> for: {missing_data}")

        return len(errors) == 0, errors

    @classmethod
    def parse_dex_classes(cls, dex_bytes: bytes) -> Tuple[Set[str], Set[str]]:
        """
        Parses DEX header, string_ids, type_ids, and class_defs in pure Python.
        Returns a tuple of (all_types_set, defined_classes_set).
        Descriptors are formatted as 'Lpkg/Cls;'.
        """
        if len(dex_bytes) < 112:
            raise ValueError(f"DEX buffer too small ({len(dex_bytes)} bytes, minimum is 112)")

        magic = dex_bytes[:8]
        if not (magic.startswith(b"dex\n") and len(magic) == 8):
            raise ValueError(f"Invalid DEX magic: {magic!r}")

        fields = struct.unpack_from("<20I", dex_bytes, 32)
        (
            file_size, header_size, endian_tag, link_size, link_off, map_off,
            string_ids_size, string_ids_off,
            type_ids_size, type_ids_off,
            proto_ids_size, proto_ids_off,
            field_ids_size, field_ids_off,
            method_ids_size, method_ids_off,
            class_defs_size, class_defs_off,
            data_size, data_off
        ) = fields

        # 1. Unpack string offsets
        string_offsets = [
            struct.unpack_from("<I", dex_bytes, string_ids_off + i * 4)[0]
            for i in range(string_ids_size)
        ]

        def read_mutf8_string(offset: int) -> str:
            pos = offset
            # Skip uleb128 length prefix
            while pos < len(dex_bytes) and (dex_bytes[pos] & 0x80):
                pos += 1
            pos += 1  # Last byte of uleb128
            end = dex_bytes.find(b"\x00", pos)
            if end == -1:
                end = len(dex_bytes)
            return dex_bytes[pos:end].decode("utf-8", errors="replace")

        strings = [read_mutf8_string(off) for off in string_offsets]

        # 2. Unpack type descriptors
        type_ids = [
            struct.unpack_from("<I", dex_bytes, type_ids_off + i * 4)[0]
            for i in range(type_ids_size)
        ]
        types = [strings[idx] for idx in type_ids]

        # 3. Unpack defined class descriptors
        defined_classes = []
        for i in range(class_defs_size):
            class_idx = struct.unpack_from("<I", dex_bytes, class_defs_off + i * 32)[0]
            if class_idx < len(types):
                defined_classes.append(types[class_idx])

        return set(types), set(defined_classes)

    @classmethod
    def validate_dex_entrypoint(cls, dex_bytes: bytes, xposed_init_class: str) -> Tuple[bool, List[str]]:
        """
        Validates that dex_bytes is a structurally valid DEX file and contains
        the class declared in xposed_init in its class definitions table, while
        rejecting foreign reference entrypoints.
        """
        errors = []
        if not dex_bytes:
            return False, ["classes.dex content is empty"]

        try:
            all_types, defined_classes = cls.parse_dex_classes(dex_bytes)
        except Exception as e:
            return False, [f"Failed to parse classes.dex binary: {e}"]

        expected_descriptor = "L" + xposed_init_class.strip().replace(".", "/") + ";"
        if expected_descriptor not in defined_classes:
            if expected_descriptor in all_types:
                errors.append(
                    f"Class '{xposed_init_class}' ({expected_descriptor}) is referenced in DEX type table "
                    f"but is not defined in class_defs (not compiled into bytecode)"
                )
            else:
                errors.append(
                    f"Class '{xposed_init_class}' ({expected_descriptor}) is missing from classes.dex "
                    f"(found {len(defined_classes)} defined classes, {len(all_types)} types)"
                )

        # Reject foreign reference entrypoints (e.g. from reference port)
        if "Lme/ayra/samsung/mdx/XposedInit;" in all_types or "Lme/ayra/samsung/mdx/XposedInit;" in defined_classes:
            errors.append("Foreign reference entrypoint 'Lme/ayra/samsung/mdx/XposedInit;' detected in classes.dex")

        for cls_desc in defined_classes:
            if "ayra" in cls_desc.lower():
                errors.append(f"Foreign reference class '{cls_desc}' detected in classes.dex")
                break

        return len(errors) == 0, errors

    @classmethod
    def validate_dex_classes(cls, dex_bytes: bytes, expected_entrypoint: str) -> Tuple[bool, List[str]]:
        """Alias for validate_dex_entrypoint."""
        return cls.validate_dex_entrypoint(dex_bytes, expected_entrypoint)

    @classmethod
    def validate_lsposed_apk(
        cls,
        file_list: List[str],
        xposed_init_content: str,
        dex_bytes: Optional[bytes] = None
    ) -> Tuple[bool, List[str]]:
        """
        Validates LSPosed APK contents.
        If dex_bytes is provided, executes deep binary validation to confirm that
        the class declared in xposed_init is physically compiled into classes.dex
        and that foreign reference entrypoints are rejected.
        """
        normalized = {f.replace("\\", "/").lstrip("/") for f in file_list}
        errors = []
        for req in cls.REQUIRED_LSPOSED_ASSETS:
            if req not in normalized:
                errors.append(f"Missing required asset: {req}")

        if not xposed_init_content or not xposed_init_content.strip():
            errors.append("assets/xposed_init is empty")
        elif "." not in xposed_init_content.strip():
            errors.append(f"assets/xposed_init does not specify a valid qualified class: '{xposed_init_content}'")

        if "classes.dex" in normalized and dex_bytes is not None:
            entrypoint = xposed_init_content.strip() if xposed_init_content else ""
            dex_valid, dex_errors = cls.validate_dex_entrypoint(dex_bytes, entrypoint)
            if not dex_valid:
                errors.extend(dex_errors)

        return len(errors) == 0, errors
