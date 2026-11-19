#!/usr/bin/env python3
"""
phonelink_module E2E Test Suite Runner
Discovers and executes all 4 Tiers of E2E tests:
- Tier 1: Feature Coverage (Isolated Happy Path)
- Tier 2: Boundary & Corner Cases (Limits, Denial, Errors)
- Tier 3: Cross-Feature Combinations (Pairwise & Multi-Feature IPC)
- Tier 4: Real-World Application Scenarios (Full E2E Sessions)

Outputs structured executive summary reports and exits with code 0 on full pass.
"""

import os
import sys
import time
import unittest
import argparse
from typing import Dict, List, Tuple


# Ensure project root is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


TIERS: Dict[str, Dict[str, str]] = {
    "Tier 1": {
        "name": "Feature Coverage (Happy Path across 12 Features)",
        "path": os.path.join(SCRIPT_DIR, "e2e", "tier1_feature_coverage"),
    },
    "Tier 2": {
        "name": "Boundary & Corner Cases (Limits & Security Denials)",
        "path": os.path.join(SCRIPT_DIR, "e2e", "tier2_boundary_corner"),
    },
    "Tier 3": {
        "name": "Cross-Feature Combinations (IPC & Multi-Feature)",
        "path": os.path.join(SCRIPT_DIR, "e2e", "tier3_cross_feature"),
    },
    "Tier 4": {
        "name": "Real-World Application Scenarios (End-to-End Sessions)",
        "path": os.path.join(SCRIPT_DIR, "e2e", "tier4_real_world"),
    },
    "Tier 5": {
        "name": "Adversarial Coverage Hardening (Java Hooks & Runtime)",
        "path": os.path.join(SCRIPT_DIR, "e2e", "tier5_adversarial"),
    },
}


class TierResult:
    def __init__(self, tier_id: str, tier_name: str):
        self.tier_id = tier_id
        self.tier_name = tier_name
        self.tests_run = 0
        self.passed = 0
        self.failed = 0
        self.errors = 0
        self.duration = 0.0
        self.failure_details: List[Tuple[str, str]] = []


def run_tier(tier_id: str, tier_info: Dict[str, str], verbose: bool = False) -> TierResult:
    result = TierResult(tier_id, tier_info["name"])
    loader = unittest.TestLoader()

    if not os.path.isdir(tier_info["path"]):
        print(f"Warning: Directory not found: {tier_info['path']}")
        return result

    suite = loader.discover(start_dir=tier_info["path"], pattern="test_*.py", top_level_dir=PROJECT_ROOT)
    test_result = unittest.TestResult()

    start_time = time.perf_counter()
    suite.run(test_result)
    result.duration = time.perf_counter() - start_time

    result.tests_run = test_result.testsRun
    result.failed = len(test_result.failures)
    result.errors = len(test_result.errors)
    result.passed = result.tests_run - (result.failed + result.errors)

    for test, err in test_result.failures:
        result.failure_details.append((str(test), err))
    for test, err in test_result.errors:
        result.failure_details.append((str(test), err))

    return result


def print_banner():
    print("=" * 80)
    print("  PHONELINK MODULE — OPAQUE-BOX E2E TEST SUITE RUNNER")
    print("  Target: Xiaomi Mi 9 (cepheus) | AOSP Project Infinity X | Android 16 (SDK 36)")
    print("  Target App: Microsoft Link to Windows (com.microsoft.appmanager)")
    print("  Architecture: Hybrid (Magisk Priv-App Overlay + LSPosed Xposed Framework)")
    print("=" * 80)


def print_summary(results: List[TierResult]):
    print("\n" + "=" * 80)
    print(f"{'TIER':<10} | {'DESCRIPTION':<38} | {'RUN':<5} | {'PASS':<5} | {'FAIL':<5} | {'TIME'}")
    print("-" * 80)

    total_run = 0
    total_passed = 0
    total_failed = 0
    total_errors = 0
    total_duration = 0.0

    for r in results:
        status = "PASS" if (r.failed == 0 and r.errors == 0) else "FAIL"
        time_str = f"{r.duration:.3f}s"
        desc = r.tier_name[:36] + (".." if len(r.tier_name) > 36 else "")
        print(f"{r.tier_id:<10} | {desc:<38} | {r.tests_run:<5} | {r.passed:<5} | {r.failed + r.errors:<5} | {time_str}")

        total_run += r.tests_run
        total_passed += r.passed
        total_failed += r.failed
        total_errors += r.errors
        total_duration += r.duration

    print("-" * 80)
    grand_status = "PASSED" if (total_failed == 0 and total_errors == 0) else "FAILED"
    print(f"GRAND TOTAL | {grand_status:<38} | {total_run:<5} | {total_passed:<5} | {total_failed + total_errors:<5} | {total_duration:.3f}s")
    print("=" * 80)

    # Print failures if any
    for r in results:
        if r.failure_details:
            print(f"\n[!] Failures in {r.tier_id} ({r.tier_name}):")
            for test_name, trace in r.failure_details:
                print(f"  - {test_name}:")
                print(f"    {trace.strip()}\n")

    if total_failed == 0 and total_errors == 0:
        print("\n[SUCCESS] All E2E test tiers passed cleanly. Test suite verification complete.\n")
    else:
        print(f"\n[FAILURE] Test run completed with {total_failed} failure(s) and {total_errors} error(s).\n")


def main():
    parser = argparse.ArgumentParser(description="Run phonelink_module E2E test suite.")
    parser.add_argument("--tier", choices=["1", "2", "3", "4", "5"], help="Run only specific tier (1, 2, 3, 4, or 5)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose test execution output")
    args = parser.parse_args()

    print_banner()

    selected_tiers = {}
    if args.tier:
        tier_key = f"Tier {args.tier}"
        if tier_key in TIERS:
            selected_tiers[tier_key] = TIERS[tier_key]
    else:
        selected_tiers = TIERS

    results = []
    for tier_id, tier_info in selected_tiers.items():
        if args.verbose:
            print(f"\n[*] Executing {tier_id}: {tier_info['name']}...")
        r = run_tier(tier_id, tier_info, verbose=args.verbose)
        results.append(r)

    print_summary(results)

    all_passed = all(r.failed == 0 and r.errors == 0 for r in results)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
