#!/usr/bin/env python3
"""
Adversarial MediaCodec & IPC Boundary Fuzzing Test Suite (Challenger M3-2)
Targets: VideoCodecHooks and CapabilityContentProvider for Milestone M3.

Verification checks:
1. Unknown, corrupt, empty, and proprietary Samsung codec names passed to MediaCodec.createByCodecName.
2. Malformed MediaFormat entries (missing color format, unsupported vendor color formats, missing bitrate modes,
   negative framerates/resolutions).
3. Sync frame parameter variations (vendor.sec-ext-enc-request-sync, request-sync, empty bundles).
4. Unknown or malformed capability queries passed to CapabilityContentProvider.call (null methods,
   unexpected prefixes, malformed @ syntax).
5. Verify that all bad inputs are safely sanitized or rejected without crashing the host process.
"""

import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.e2e.tier2_boundary_corner.test_b08_videocodec_capability_fuzz import (
    TestMediaCodecCreateByCodecNameFuzzing,
    TestMediaCodecConfigureFormatFuzzing,
    TestMediaCodecSetParametersSyncFrameFuzzing,
    TestCapabilityContentProviderCallFuzzing,
    TestEndToEndCodecAndProviderHostStability,
)


if __name__ == "__main__":
    unittest.main(verbosity=2)
