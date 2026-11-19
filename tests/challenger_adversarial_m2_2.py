#!/usr/bin/env python3
"""
Adversarial Packaging & Boundary Fuzzing Test Suite (Challenger M2-2)
Targets: PhoneLinkMagisk-v2.0.0.zip, build_magisk.py, and PackagingValidator.

Verification checks:
1. Write and run adversarial test suite fuzzing the Magisk packaging pipeline:
   - Corrupted ZIP files, missing mandatory files from module root.
   - Malformed XML in privapp-permissions and sysconfig allowlists (unclosed tags, missing package attributes).
   - Injected CRLF line endings in shell scripts.
   - Truncated or dummy APK files lacking arm64-v8a native libraries.
2. Confirm PackagingValidator accurately rejects all bad inputs and approves genuine builds.
3. Record test suite code, execution results, and verdict (CONFIRMED or FAILED).
"""

import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import all tests from the co-located fuzzing suite
from tests.e2e.tier2_boundary_corner.test_b12_adversarial_packaging_fuzz import (
    TestGenuineMagiskZipPackaging,
    TestAdversarialZipCorruption,
    TestAdversarialMissingMandatoryFilesFuzz,
    TestAdversarialMalformedPrivappXml,
    TestAdversarialMalformedSysconfigXml,
    TestAdversarialCrlfLineEndingsInPipeline,
    TestAdversarialApkValidation,
    TestAdversarialModulePropValidation,
    TestAdversarialBuildMagiskTreeValidation,
)


if __name__ == "__main__":
    unittest.main(verbosity=2)
