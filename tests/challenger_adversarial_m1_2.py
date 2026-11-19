"""
Adversarial Challenge Test Suite for Milestone M1 (Challenger m1_2_it2)
Tests:
1. Binary DEX verification: Fuzzing & challenging PackagingValidator with corrupted headers,
   truncated string tables, truncated type lists, out-of-bounds indices, and foreign reference entrypoints.
2. Boundary conditions: SemFloatingFeature with null tags, missing tags, empty strings, unusual types, and edge cases.
3. APK structure: PhoneLinkXposed.apk integrity as a valid ZIP, valid XML resources, and genuine DEX 039 format.
"""

import io
import os
import struct
import sys
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.mock_env.packaging_validator import PackagingValidator
from tests.mock_env.art_classloader import SemFloatingFeature, ARTClassLoader
from tests.mock_env.android_runtime import NoClassDefFoundError, ClassNotFoundException


def create_mini_dex(
    strings=None,
    types=None,
    class_defs=None,
    magic=b"dex\n039\x00",
    header_overrides=None
):
    """
    Synthesizes a minimal structurally valid binary DEX buffer.
    strings: list of str
    types: list of int (indices into strings)
    class_defs: list of int (indices into types)
    """
    if strings is None:
        strings = ["Lme/phonelink/xposed/XposedInit;", "V"]
    if types is None:
        types = [0, 1]
    if class_defs is None:
        class_defs = [0]

    # Encode strings into MUTF-8 with ULEB128 prefix
    encoded_strings = []
    for s in strings:
        utf_bytes = s.encode("utf-8")
        # uleb128 length prefix (single byte for len < 128)
        length_byte = bytes([len(utf_bytes)])
        encoded_strings.append(length_byte + utf_bytes + b"\x00")

    # Layout:
    # 0x00..0x70: Header (112 bytes)
    # String ID table: len(strings) * 4 bytes
    # Type ID table: len(types) * 4 bytes
    # Class Defs table: len(class_defs) * 32 bytes
    # String data buffer: concatenated encoded_strings

    string_ids_off = 112
    string_ids_size = len(strings)

    type_ids_off = string_ids_off + string_ids_size * 4
    type_ids_size = len(types)

    class_defs_off = type_ids_off + type_ids_size * 4
    class_defs_size = len(class_defs)

    string_data_off = class_defs_off + class_defs_size * 32

    # Compute string offsets
    string_offsets = []
    cur_off = string_data_off
    for item in encoded_strings:
        string_offsets.append(cur_off)
        cur_off += len(item)

    total_file_size = cur_off

    # Pack Header (112 bytes)
    header = bytearray(112)
    header[0:8] = magic
    # Checksum at 8..12
    struct.pack_into("<I", header, 8, 0x12345678)
    # SHA-1 signature at 12..32
    header[12:32] = b"\xaa" * 20

    # Fields unpacked with <20I at offset 32:
    header_fields = {
        "file_size": total_file_size,
        "header_size": 112,
        "endian_tag": 0x12345678,
        "link_size": 0,
        "link_off": 0,
        "map_off": 0,
        "string_ids_size": string_ids_size,
        "string_ids_off": string_ids_off,
        "type_ids_size": type_ids_size,
        "type_ids_off": type_ids_off,
        "proto_ids_size": 0,
        "proto_ids_off": 0,
        "field_ids_size": 0,
        "field_ids_off": 0,
        "method_ids_size": 0,
        "method_ids_off": 0,
        "class_defs_size": class_defs_size,
        "class_defs_off": class_defs_off,
        "data_size": cur_off - string_data_off,
        "data_off": string_data_off,
    }

    if header_overrides:
        header_fields.update(header_overrides)

    packed_fields = struct.pack(
        "<20I",
        header_fields["file_size"],
        header_fields["header_size"],
        header_fields["endian_tag"],
        header_fields["link_size"],
        header_fields["link_off"],
        header_fields["map_off"],
        header_fields["string_ids_size"],
        header_fields["string_ids_off"],
        header_fields["type_ids_size"],
        header_fields["type_ids_off"],
        header_fields["proto_ids_size"],
        header_fields["proto_ids_off"],
        header_fields["field_ids_size"],
        header_fields["field_ids_off"],
        header_fields["method_ids_size"],
        header_fields["method_ids_off"],
        header_fields["class_defs_size"],
        header_fields["class_defs_off"],
        header_fields["data_size"],
        header_fields["data_off"],
    )
    header[32:112] = packed_fields

    # Build full buffer
    buf = bytearray(header)

    # String IDs
    for off in string_offsets:
        buf.extend(struct.pack("<I", off))

    # Type IDs
    for s_idx in types:
        buf.extend(struct.pack("<I", s_idx))

    # Class Defs (32 bytes per item: class_idx (4), access_flags (4), superclass_idx (4),
    # interfaces_off (4), source_file_idx (4), annotations_off (4), class_data_off (4), static_values_off (4))
    for t_idx in class_defs:
        cdef = struct.pack("<8I", t_idx, 1, 0, 0, 0, 0, 0, 0)
        buf.extend(cdef)

    # String Data
    for item in encoded_strings:
        buf.extend(item)

    return bytes(buf)


class TestBinaryDexVerificationFuzzing(unittest.TestCase):
    """Scope 1: Adversarial challenge of PackagingValidator DEX verification."""

    def test_empty_buffer(self):
        """Empty buffer handling."""
        valid, errors = PackagingValidator.validate_dex_entrypoint(b"", "me.phonelink.xposed.XposedInit")
        self.assertFalse(valid)
        self.assertIn("classes.dex content is empty", errors[0])

        with self.assertRaises(ValueError):
            PackagingValidator.parse_dex_classes(b"")

    def test_truncated_buffer_under_112_bytes(self):
        """Buffers smaller than minimum DEX header (112 bytes)."""
        for size in [1, 7, 8, 16, 31, 32, 64, 111]:
            corrupted = (b"dex\n039\x00" + b"\x00" * 112)[:size]
            with self.assertRaises(ValueError) as ctx:
                PackagingValidator.parse_dex_classes(corrupted)
            self.assertIn("DEX buffer too small", str(ctx.exception))

            valid, errors = PackagingValidator.validate_dex_entrypoint(corrupted, "me.phonelink.xposed.XposedInit")
            self.assertFalse(valid)
            self.assertIn("Failed to parse classes.dex binary", errors[0])

    def test_corrupted_magic_numbers(self):
        """Invalid non-DEX magic signatures are properly rejected."""
        invalid_magics = [
            b"dey\n035\x00",             # ODEX magic
            b"dex\x00039\x00",             # Null byte in magic
            b"PK\x03\x04\x14\x00\x00\x00", # ZIP magic
            b"\x7fELF\x02\x01\x01\x00",     # ELF magic
            b"\xca\xfe\xba\xbe\x00\x00\x00\x00", # Java class magic
            b"\x00\x00\x00\x00\x00\x00\x00\x00", # Zeroes
        ]
        for mag in invalid_magics:
            buf = mag + b"\x00" * 110
            with self.assertRaises(ValueError) as ctx:
                PackagingValidator.parse_dex_classes(buf)
            self.assertIn("Invalid DEX magic", str(ctx.exception))

            valid, errors = PackagingValidator.validate_dex_entrypoint(buf, "me.phonelink.xposed.XposedInit")
            self.assertFalse(valid)

    def test_vulnerability_loose_magic_validation(self):
        """
        Adversarial Boundary Finding: PackagingValidator only checks magic.startswith(b'dex\\n')
        and len == 8. This permits arbitrary junk versions such as b'dex\\nJUNK' and
        non-null-terminated strings like b'dex\\n999\\xff'.
        """
        pseudo_magics = [b"dex\nJUNK", b"dex\n03\x00\x00", b"dex\n999\xff"]
        for p_mag in pseudo_magics:
            buf = p_mag + b"\x00" * 110
            # Does NOT raise ValueError despite invalid DEX specification version format
            types, defs = PackagingValidator.parse_dex_classes(buf)
            self.assertEqual(len(types), 0)
            self.assertEqual(len(defs), 0)

    def test_corrupted_header_offsets(self):
        """Adversarial header offsets (pointing past EOF, overlapping, negative)."""
        scenarios = [
            # string_ids_off beyond file size
            {"string_ids_off": 999_999, "string_ids_size": 10},
            # string_ids_size massive
            {"string_ids_size": 0x7FFFFFFF, "string_ids_off": 112},
            # type_ids_off beyond file size
            {"type_ids_off": 999_999, "type_ids_size": 5},
            # class_defs_off beyond file size
            {"class_defs_off": 999_999, "class_defs_size": 5},
        ]
        for scen in scenarios:
            dex = create_mini_dex(header_overrides=scen)
            valid, errors = PackagingValidator.validate_dex_entrypoint(dex, "me.phonelink.xposed.XposedInit")
            self.assertFalse(valid)
            self.assertTrue(len(errors) > 0)
            self.assertIn("Failed to parse classes.dex binary", errors[0])

    def test_truncated_string_data_and_mutf8_fuzzing(self):
        """String offset points beyond end of file or without null terminator."""
        # 1. String offset pointing past EOF
        dex = bytearray(create_mini_dex())
        # Overwrite first string offset in table (at offset 112) to point beyond file
        struct.pack_into("<I", dex, 112, len(dex) + 500)
        valid, errors = PackagingValidator.validate_dex_entrypoint(bytes(dex), "me.phonelink.xposed.XposedInit")
        self.assertFalse(valid)

        # 2. String data truncated before null terminator
        dex2 = bytearray(create_mini_dex())
        string_ids_off = 112
        type_ids_off = 112 + 2 * 4
        class_defs_off = type_ids_off + 2 * 4
        string_data_off = class_defs_off + 1 * 32
        for i in range(string_data_off, len(dex2)):
            dex2[i] = ord("A")
        # read_mutf8_string handles missing null byte by slicing up to len(dex)
        types, defs = PackagingValidator.parse_dex_classes(bytes(dex2))
        self.assertIsInstance(types, set)
        self.assertIsInstance(defs, set)

    def test_type_table_index_out_of_bounds(self):
        """Type IDs table contains string index >= len(strings)."""
        dex = bytearray(create_mini_dex(strings=["LValid;"], types=[0, 999], class_defs=[0]))
        # Parsing should catch IndexError in validate_dex_entrypoint
        valid, errors = PackagingValidator.validate_dex_entrypoint(bytes(dex), "Valid")
        self.assertFalse(valid)
        self.assertIn("Failed to parse classes.dex binary", errors[0])

    def test_class_def_index_out_of_bounds(self):
        """Class defs table contains type index >= len(types)."""
        dex = bytearray(create_mini_dex(strings=["LValid;"], types=[0], class_defs=[999]))
        types, defs = PackagingValidator.parse_dex_classes(bytes(dex))
        self.assertEqual(len(defs), 0)
        self.assertIn("LValid;", types)

    def test_uncompiled_facade_rejection(self):
        """
        Critical regression test: Class is in type_ids (string table/types),
        BUT NOT in class_defs (uncompiled facade).
        """
        dex = create_mini_dex(
            strings=["Lme/phonelink/xposed/XposedInit;", "V"],
            types=[0, 1],
            class_defs=[]  # NOT compiled into class_defs!
        )
        valid, errors = PackagingValidator.validate_dex_entrypoint(dex, "me.phonelink.xposed.XposedInit")
        self.assertFalse(valid)
        self.assertEqual(len(errors), 1)
        self.assertIn("referenced in DEX type table but is not defined in class_defs", errors[0])
        self.assertIn("(not compiled into bytecode)", errors[0])

    def test_foreign_reference_entrypoint_rejection(self):
        """Foreign reference entrypoint and ayra classes must be strictly rejected."""
        # Case 1: Lme/ayra/samsung/mdx/XposedInit; in types
        dex1 = create_mini_dex(
            strings=["Lme/phonelink/xposed/XposedInit;", "Lme/ayra/samsung/mdx/XposedInit;"],
            types=[0, 1],
            class_defs=[0]
        )
        valid1, errors1 = PackagingValidator.validate_dex_entrypoint(dex1, "me.phonelink.xposed.XposedInit")
        self.assertFalse(valid1)
        self.assertTrue(any("Foreign reference entrypoint 'Lme/ayra/samsung/mdx/XposedInit;'" in e for e in errors1))

        # Case 2: Ayra class in class_defs
        dex2 = create_mini_dex(
            strings=["Lme/phonelink/xposed/XposedInit;", "Lcom/ayra/module/Helper;"],
            types=[0, 1],
            class_defs=[0, 1]
        )
        valid2, errors2 = PackagingValidator.validate_dex_entrypoint(dex2, "me.phonelink.xposed.XposedInit")
        self.assertFalse(valid2)
        self.assertTrue(any("Foreign reference class 'Lcom/ayra/module/Helper;'" in e for e in errors2))

        # Case 3: Case-insensitive 'AYRA'
        dex3 = create_mini_dex(
            strings=["Lme/phonelink/xposed/XposedInit;", "Lorg/AYRA/Test;"],
            types=[0, 1],
            class_defs=[0, 1]
        )
        valid3, errors3 = PackagingValidator.validate_dex_entrypoint(dex3, "me.phonelink.xposed.XposedInit")
        self.assertFalse(valid3)
        self.assertTrue(any("Foreign reference class 'Lorg/AYRA/Test;'" in e for e in errors3))

    def test_vulnerability_none_entrypoint_crashes(self):
        """
        Adversarial Boundary Finding: validate_dex_entrypoint(dex, None) crashes with
        AttributeError: 'NoneType' object has no attribute 'strip'.
        """
        dex = create_mini_dex()
        with self.assertRaises(AttributeError):
            PackagingValidator.validate_dex_entrypoint(dex, None)

    def test_completely_missing_entrypoint(self):
        """Entrypoint missing from both types and class_defs."""
        dex = create_mini_dex(
            strings=["Lcom/other/Class;", "V"],
            types=[0, 1],
            class_defs=[0]
        )
        valid, errors = PackagingValidator.validate_dex_entrypoint(dex, "me.phonelink.xposed.XposedInit")
        self.assertFalse(valid)
        self.assertTrue(any("missing from classes.dex" in e for e in errors))

    def test_valid_synthesized_dex_passes(self):
        """A valid synthesized DEX with entrypoint compiled passes cleanly."""
        dex = create_mini_dex(
            strings=["Lme/phonelink/xposed/XposedInit;", "V"],
            types=[0, 1],
            class_defs=[0]
        )
        valid, errors = PackagingValidator.validate_dex_entrypoint(dex, "me.phonelink.xposed.XposedInit")
        self.assertTrue(valid)
        self.assertEqual(len(errors), 0)


class TestSemFloatingFeatureBoundaries(unittest.TestCase):
    """Scope 2: Adversarial challenge of SemFloatingFeature boundary conditions."""

    def setUp(self):
        SemFloatingFeature.reset_instance()
        self.feature = SemFloatingFeature.getInstance()

    def tearDown(self):
        SemFloatingFeature.reset_instance()

    def test_null_and_empty_tags(self):
        """Null, empty string, whitespace tags."""
        for null_tag in [None, "", "   ", "\t\n"]:
            # getBoolean
            self.assertFalse(self.feature.getBoolean(null_tag))
            self.assertTrue(self.feature.getBoolean(null_tag, default=True))

            # getString
            self.assertEqual(self.feature.getString(null_tag), "")
            self.assertEqual(self.feature.getString(null_tag, default="FALLBACK"), "FALLBACK")

            # getInt
            self.assertEqual(self.feature.getInt(null_tag), 0)
            self.assertEqual(self.feature.getInt(null_tag, default=-999), -999)

            # set_feature should not crash
            self.feature.set_feature(null_tag, "some_value")

    def test_missing_tags(self):
        """Non-existent tags return defaults."""
        missing = "TOTALLY_NON_EXISTENT_TAG_987654321"
        self.assertFalse(self.feature.getBoolean(missing))
        self.assertTrue(self.feature.getBoolean(missing, default=True))
        self.assertEqual(self.feature.getString(missing), "")
        self.assertEqual(self.feature.getString(missing, default="def_str"), "def_str")
        self.assertEqual(self.feature.getInt(missing), 0)
        self.assertEqual(self.feature.getInt(missing, default=777), 777)

    def test_unusual_types_in_storage(self):
        """Values stored as None, floats, complex types, tuples, dicts."""
        self.feature.set_feature("TAG_NONE", None)
        self.feature.set_feature("TAG_FLOAT_POS", 42.99)
        self.feature.set_feature("TAG_FLOAT_NEG", -3.14)
        self.feature.set_feature("TAG_FLOAT_NAN", float("nan"))
        self.feature.set_feature("TAG_COMPLEX", {"nested": [1, 2, 3]})
        self.feature.set_feature("TAG_OBJ", object())

        # getInt on None
        self.assertEqual(self.feature.getInt("TAG_NONE", default=10), 10)
        # getInt on floats
        self.assertEqual(self.feature.getInt("TAG_FLOAT_POS", default=0), 42)
        self.assertEqual(self.feature.getInt("TAG_FLOAT_NEG", default=0), -3)
        # getInt on NaN (raises ValueError in python int(nan) which is caught)
        self.assertEqual(self.feature.getInt("TAG_FLOAT_NAN", default=-1), -1)

        # getInt on complex object
        self.assertEqual(self.feature.getInt("TAG_COMPLEX", default=55), 55)

        # getString on None
        self.assertEqual(self.feature.getString("TAG_NONE", default="fallback"), "fallback")

    def test_vulnerability_float_infinity_in_python_mock(self):
        """
        Adversarial Boundary Finding: In tests.mock_env.art_classloader.SemFloatingFeature.getInt,
        int(float('inf')) raises OverflowError which is not caught by except (ValueError, TypeError).
        In Java implementation, Double.POSITIVE_INFINITY.intValue() evaluates to Integer.MAX_VALUE safely.
        """
        self.feature.set_feature("TAG_FLOAT_INF", float("inf"))
        with self.assertRaises(OverflowError):
            self.feature.getInt("TAG_FLOAT_INF", default=-1)

    def test_extreme_key_lengths_and_special_chars(self):
        """Very large keys, special chars, binary data."""
        huge_tag = "TAG_" + "X" * 50_000
        self.feature.set_feature(huge_tag, "HUGE_VAL")
        self.assertEqual(self.feature.getString(huge_tag), "HUGE_VAL")

        null_byte_tag = "TAG\x00WITH\x00NULL"
        self.feature.set_feature(null_byte_tag, "NULL_BYTE_VAL")
        self.assertEqual(self.feature.getString(null_byte_tag), "NULL_BYTE_VAL")

        unicode_tag = "тег_🌟_🚀_中文_日本語_عربي"
        self.feature.set_feature(unicode_tag, "UNICODE_VAL")
        self.assertEqual(self.feature.getString(unicode_tag), "UNICODE_VAL")


class TestApkStructureAndIntegrity(unittest.TestCase):
    """Scope 3: Verification of PhoneLinkXposed.apk integrity and DEX format."""

    APK_PATH = PROJECT_ROOT / "lsposed_module" / "build" / "outputs" / "apk" / "release" / "PhoneLinkXposed.apk"

    def test_apk_exists_and_is_valid_zip(self):
        """PhoneLinkXposed.apk must exist and pass ZIP CRC checks."""
        self.assertTrue(self.APK_PATH.exists(), f"APK does not exist at {self.APK_PATH}")
        self.assertTrue(zipfile.is_zipfile(str(self.APK_PATH)), "APK is not a valid zip archive")

        with zipfile.ZipFile(str(self.APK_PATH), "r") as z:
            bad_file = z.testzip()
            self.assertIsNone(bad_file, f"ZIP archive corrupted at entry: {bad_file}")

    def test_apk_contains_required_assets(self):
        """APK must contain manifest, xposed_init, classes.dex, and resource xmls."""
        required = {
            "AndroidManifest.xml",
            "assets/xposed_init",
            "classes.dex",
            "res/values/strings.xml",
            "res/values/arrays.xml",
        }
        with zipfile.ZipFile(str(self.APK_PATH), "r") as z:
            names = set(z.namelist())
            for req in required:
                self.assertIn(req, names, f"Required entry {req} missing from APK")

    def test_manifest_xml_structure(self):
        """AndroidManifest.xml is well-formed XML and declares Xposed module metadata."""
        with zipfile.ZipFile(str(self.APK_PATH), "r") as z:
            manifest_raw = z.read("AndroidManifest.xml")
            root = ET.fromstring(manifest_raw)

            self.assertEqual(root.tag, "manifest")
            self.assertEqual(root.attrib.get("package"), "me.phonelink.xposed")

            app = root.find("application")
            self.assertIsNotNone(app, "<application> missing from AndroidManifest.xml")

            # Check meta-data tags
            meta_dict = {}
            for m in app.findall("meta-data"):
                name = m.attrib.get("{http://schemas.android.com/apk/res/android}name") or m.attrib.get("name")
                val = m.attrib.get("{http://schemas.android.com/apk/res/android}value") or m.attrib.get("value")
                res = m.attrib.get("{http://schemas.android.com/apk/res/android}resource") or m.attrib.get("resource")
                meta_dict[name] = val or res

            self.assertEqual(meta_dict.get("xposedmodule"), "true")
            self.assertEqual(meta_dict.get("xposedminversion"), "93")
            self.assertEqual(meta_dict.get("xposeddescription"), "@string/xposed_description")
            self.assertEqual(meta_dict.get("xposedscope"), "@array/xposed_scope")

    def test_xposed_init_entrypoint(self):
        """assets/xposed_init must point to me.phonelink.xposed.XposedInit."""
        with zipfile.ZipFile(str(self.APK_PATH), "r") as z:
            init_content = z.read("assets/xposed_init").decode("utf-8").strip()
            self.assertEqual(init_content, "me.phonelink.xposed.XposedInit")

    def test_xml_resources(self):
        """res/values/strings.xml and arrays.xml must be valid XML."""
        with zipfile.ZipFile(str(self.APK_PATH), "r") as z:
            # strings.xml
            strings_raw = z.read("res/values/strings.xml")
            root_s = ET.fromstring(strings_raw)
            self.assertEqual(root_s.tag, "resources")
            string_names = {el.attrib.get("name") for el in root_s.findall("string")}
            self.assertIn("app_name", string_names)
            self.assertIn("xposed_description", string_names)

            # arrays.xml
            arrays_raw = z.read("res/values/arrays.xml")
            root_a = ET.fromstring(arrays_raw)
            self.assertEqual(root_a.tag, "resources")
            array_names = {el.attrib.get("name") for el in root_a.findall("string-array")}
            self.assertIn("xposed_scope", array_names)

            # verify scope targets
            scope_array = root_a.find("string-array")
            items = {item.text for item in scope_array.findall("item")}
            self.assertIn("com.microsoft.appmanager", items)
            self.assertIn("com.samsung.android.mdx", items)
            self.assertIn("android", items)

    def test_classes_dex_format_and_version(self):
        """classes.dex must be genuine DEX 039 format with correct header sizes."""
        with zipfile.ZipFile(str(self.APK_PATH), "r") as z:
            dex = z.read("classes.dex")
            names = z.namelist()
            init_content = z.read("assets/xposed_init").decode("utf-8")

        # Magic: DEX 039
        magic = dex[:8]
        self.assertEqual(magic, b"dex\n039\x00", f"Unexpected DEX magic: {magic!r}")

        # Unpack header fields
        fields = struct.unpack_from("<20I", dex, 32)
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

        self.assertEqual(header_size, 112)
        self.assertEqual(endian_tag, 0x12345678)
        self.assertEqual(file_size, len(dex))

        # Deep parse classes
        types, defs = PackagingValidator.parse_dex_classes(dex)
        self.assertEqual(len(defs), 47, f"Expected 47 defined classes, got {len(defs)}")
        self.assertEqual(len(types), 93, f"Expected 93 types, got {len(types)}")

        # Verify entrypoint in class_defs
        self.assertIn("Lme/phonelink/xposed/XposedInit;", defs)
        self.assertIn("Lcom/samsung/android/feature/SemFloatingFeature;", defs)
        self.assertIn("Lme/phonelink/xposed/hooks/AppManagerHooks;", defs)
        self.assertIn("Lme/phonelink/xposed/hooks/MdxVersionHooks;", defs)
        self.assertIn("Lme/phonelink/xposed/hooks/PackageManagerHooks;", defs)
        self.assertIn("Lme/phonelink/xposed/hooks/SystemServerHooks;", defs)
        self.assertIn("Lme/phonelink/xposed/stubs/OneUIStubs;", defs)
        self.assertIn("Lme/phonelink/xposed/utils/CertConstants;", defs)

        # Confirm zero foreign/ayra classes
        self.assertFalse(any("ayra" in t.lower() for t in types), "Foreign ayra type found in DEX!")
        self.assertFalse(any("ayra" in d.lower() for d in defs), "Foreign ayra class def found in DEX!")

        # Full PackagingValidator check
        valid, errors = PackagingValidator.validate_lsposed_apk(names, init_content, dex)
        self.assertTrue(valid, f"PackagingValidator.validate_lsposed_apk failed: {errors}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
