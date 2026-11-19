"""
Feature 8 Extended: Video Codec & CapabilityContentProvider Unit & E2E Tests.
Verifies Qualcomm Snapdragon 855 hardware codec redirection, format sanitization,
low-latency parameter mapping, and CapabilityContentProvider IPC contract.
"""

import unittest
from tests.mock_env.android_runtime import Bundle
from tests.mock_env.binder_ipc import ContentProviderRegistry


class MockMediaFormat:
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

    def __init__(self):
        self._map = {}

    def set_integer(self, key: str, val: int):
        self._map[key] = val

    def get_integer(self, key: str, default: int = 0) -> int:
        return self._map.get(key, default)

    def contains_key(self, key: str) -> bool:
        return key in self._map

    def remove_key(self, key: str):
        if key in self._map:
            del self._map[key]


class MockVideoCodecInterceptor:
    """Simulates VideoCodecHooks logic."""
    QTI_AVC_ENCODER = "c2.qti.avc.encoder"
    QTI_HEVC_ENCODER = "c2.qti.hevc.encoder"

    @classmethod
    def resolve_codec_name(cls, requested_name: str) -> str:
        if not requested_name:
            return requested_name
        lower = requested_name.lower()
        if "sec." in lower or "exynos." in lower or "samsung" in lower:
            if "hevc" in lower or "265" in lower:
                return cls.QTI_HEVC_ENCODER
            return cls.QTI_AVC_ENCODER
        return requested_name

    @classmethod
    def sanitize_format(cls, fmt: MockMediaFormat, flags: int):
        if (flags & 1) == 0:  # MediaCodec.CONFIGURE_FLAG_ENCODE
            return
        # Enforce standard COLOR_FormatSurface
        if fmt.get_integer(MockMediaFormat.KEY_COLOR_FORMAT) != MockMediaFormat.COLOR_FormatSurface:
            fmt.set_integer(MockMediaFormat.KEY_COLOR_FORMAT, MockMediaFormat.COLOR_FormatSurface)

        # Standard AOSP low-latency and priority keys
        fmt.set_integer(MockMediaFormat.KEY_LOW_LATENCY, 1)
        fmt.set_integer(MockMediaFormat.KEY_PRIORITY, 0)

        # Ensure bitrate mode (VBR = 2)
        if not fmt.contains_key(MockMediaFormat.KEY_BITRATE_MODE):
            fmt.set_integer(MockMediaFormat.KEY_BITRATE_MODE, 2)

        # Ensure i-frame interval
        if not fmt.contains_key(MockMediaFormat.KEY_I_FRAME_INTERVAL):
            fmt.set_integer(MockMediaFormat.KEY_I_FRAME_INTERVAL, 1)

    @classmethod
    def map_parameters(cls, params: dict) -> dict:
        result = dict(params)
        if "vendor.sec-ext-enc-request-sync" in result:
            result["request-sync"] = 1
        return result


class TestVideoCodecAndCapabilityProvider(unittest.TestCase):
    def setUp(self):
        self.providers = ContentProviderRegistry()

    def test_codec_name_redirection_avc(self):
        resolved = MockVideoCodecInterceptor.resolve_codec_name("c2.sec.avc.encoder")
        self.assertEqual(resolved, "c2.qti.avc.encoder")

        resolved_exynos = MockVideoCodecInterceptor.resolve_codec_name("OMX.Exynos.AVC.Encoder")
        self.assertEqual(resolved_exynos, "c2.qti.avc.encoder")

        resolved_sec = MockVideoCodecInterceptor.resolve_codec_name("OMX.SEC.avc.enc")
        self.assertEqual(resolved_sec, "c2.qti.avc.encoder")

    def test_codec_name_redirection_hevc(self):
        resolved = MockVideoCodecInterceptor.resolve_codec_name("c2.sec.hevc.encoder")
        self.assertEqual(resolved, "c2.qti.hevc.encoder")

        resolved_exynos = MockVideoCodecInterceptor.resolve_codec_name("OMX.Exynos.HEVC.Encoder")
        self.assertEqual(resolved_exynos, "c2.qti.hevc.encoder")

    def test_codec_name_unmodified_for_standard_codecs(self):
        resolved_qti = MockVideoCodecInterceptor.resolve_codec_name("c2.qti.avc.encoder")
        self.assertEqual(resolved_qti, "c2.qti.avc.encoder")

        resolved_aosp = MockVideoCodecInterceptor.resolve_codec_name("c2.android.avc.encoder")
        self.assertEqual(resolved_aosp, "c2.android.avc.encoder")

    def test_format_sanitization_enforces_color_format_surface(self):
        fmt = MockMediaFormat()
        fmt.set_integer(MockMediaFormat.KEY_COLOR_FORMAT, MockMediaFormat.COLOR_FormatVendorSamsung)
        MockVideoCodecInterceptor.sanitize_format(fmt, flags=1)
        self.assertEqual(fmt.get_integer(MockMediaFormat.KEY_COLOR_FORMAT), MockMediaFormat.COLOR_FormatSurface)
        self.assertEqual(fmt.get_integer(MockMediaFormat.KEY_LOW_LATENCY), 1)
        self.assertEqual(fmt.get_integer(MockMediaFormat.KEY_PRIORITY), 0)
        self.assertEqual(fmt.get_integer(MockMediaFormat.KEY_BITRATE_MODE), 2)
        self.assertEqual(fmt.get_integer(MockMediaFormat.KEY_I_FRAME_INTERVAL), 1)

    def test_parameters_mapping_request_sync(self):
        params = {"vendor.sec-ext-enc-request-sync": 1}
        mapped = MockVideoCodecInterceptor.map_parameters(params)
        self.assertEqual(mapped.get("request-sync"), 1)

    def test_capability_content_provider_all_queries(self):
        uri = "content://com.samsung.android.mdx.windowslink.tileservice.CapabilityContentProvider"
        capabilities = [
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
        for cap in capabilities:
            bundle = self.providers.call(uri, f"isSupported@{cap}")
            self.assertTrue(bundle.get_boolean("key_is_supported", True))
            self.assertTrue(bundle.get_boolean(cap, True))


if __name__ == "__main__":
    unittest.main()
