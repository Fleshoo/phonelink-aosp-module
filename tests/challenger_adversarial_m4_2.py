#!/usr/bin/env python3
"""
Adversarial Input Injection & Boundary Fuzzing Test Suite (Challenger M4-2)
Targets: InputInjectionHooks, SystemServerHooks (IMS bypass), UinputBridge, and IInputInjectorService.

Verification checks:
1. Null and empty MotionEvent and KeyEvent injection (graceful rejection without crashes).
2. Malformed coordinates (negative x/y, NaN, infinity, extreme off-screen 100000x100000).
3. Invalid display IDs (negative displayId -1, unallocated displayId 9999, released virtual displays).
4. Unprivileged caller UID injection attempts (SecurityException rejection for non-whitelisted apps, spoofing defense).
5. Rapid key event flooding (rapid down/up, simultaneous multiple modifier keys Ctrl+Alt+Shift+Meta, stuck key prevention).
6. Comprehensive test suite execution and verification report.
"""

import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.e2e.tier2_boundary_corner.test_b10_input_injection_fuzz import (
    TestNullAndEmptyEventFuzzing,
    TestCoordinateBoundaryFuzzing,
    TestDisplayIdBoundaryFuzzing,
    TestUnauthorizedUidRejectionFuzzing,
    TestModifierKeyFloodAndStormStress,
)


if __name__ == "__main__":
    unittest.main(verbosity=2)
