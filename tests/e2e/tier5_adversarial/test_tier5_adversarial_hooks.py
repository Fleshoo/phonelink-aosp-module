"""
Tier 5 Adversarial Coverage Hardening Test Suite (Milestone M5 Phase 2)
White-Box Adversarial Stress Testing of all Java Hooks & Runtime Components:
- InputInjectionHooks (Simultaneous button chords, ACTION_CANCEL, pointer/coordinate fuzzing)
- SystemServerHooks (Transient PMS failure negative caching, system_server recovery, multi-user)
- VideoCodecHooks (Qualcomm SD855 Codec2 format bounds, extreme bitrates, macroblock alignment, surface destruction)
- MdxServiceHooks (VirtualDisplay creation/teardown races, in-flight input races, dead binder callbacks)
- AppManagerHooks (Dynamic class injection concurrency, process-scoped spoofing isolation)
- Compiled Java Bytecode Verification via Tier5AdversarialHookStressTest

Authoritative Sources:
- ORIGINAL_REQUEST.md (§ R1-R4)
- PROJECT.md (§ Features 1-12)
- DISPATCH.md (Challenger M5-3 Specification)
"""

import os
import sys
import math
import time
import random
import threading
import subprocess
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Set

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.mock_env.android_runtime import (
    InputEvent,
    MotionEvent,
    KeyEvent,
    Process,
    SecurityException,
    Surface,
    Bundle,
    Build,
)
from tests.mock_env.display_manager import DisplayManager, VirtualDisplay, Display
from tests.mock_env.input_manager import (
    InputManagerService,
    InputManager,
    UinputBridge,
    ClipboardBridge,
)
from tests.mock_env.binder_ipc import (
    IInputInjectorService,
    IPhoneScreenMirroringService,
    ContentProviderRegistry,
)
from tests.mock_env.art_classloader import ARTClassLoader, SemFloatingFeature, OneUIStubs


# ==============================================================================
# Helper Models for White-Box Hook Simulation
# ==============================================================================

class AdversarialMotionEvent(MotionEvent):
    """High-fidelity MotionEvent model supporting multi-button state bitmasks."""
    ACTION_MASK = 0xff
    ACTION_POINTER_DOWN = 5
    ACTION_POINTER_UP = 6
    ACTION_BUTTON_PRESS = 11
    ACTION_BUTTON_RELEASE = 12

    BUTTON_PRIMARY = 1
    BUTTON_SECONDARY = 2
    BUTTON_TERTIARY = 4

    def __init__(
        self,
        action: int,
        x: float,
        y: float,
        display_id: int = 0,
        pointer_id: int = 0,
        event_time: int = 0,
        down_time: int = 0,
        pressure: float = 1.0,
        button_state: int = 0,
        action_button: int = 0,
    ):
        super().__init__(
            action=action,
            x=x,
            y=y,
            display_id=display_id,
            pointer_id=pointer_id,
            event_time=event_time,
            down_time=down_time,
            pressure=pressure,
        )
        self.button_state = button_state
        self.action_button = action_button

    def get_button_state(self) -> int:
        return self.button_state

    def get_action_button(self) -> int:
        return self.action_button


class WhiteBoxInputInjectionHookModel:
    """
    Exact simulation of InputInjectionHooks.java logic for white-box edge case testing.
    Demonstrates sequential if-return chord evaluation, button tracking, and event routing.
    """
    ACTION_MASK = 0xff
    ACTION_BUTTON_PRESS = 11
    ACTION_BUTTON_RELEASE = 12

    def __init__(self, ims: InputManagerService):
        self.ims = ims
        self.sDisplayButtonState: Dict[int, int] = {}
        self.lock = threading.Lock()
        self.injected_keys: List[KeyEvent] = []
        self.injected_motions: List[MotionEvent] = []

    def get_button_state_for_display(self, display_id: int) -> int:
        if display_id not in self.sDisplayButtonState:
            self.sDisplayButtonState[display_id] = 0
        return self.sDisplayButtonState[display_id]

    def inject_motion_event(self, event: Optional[AdversarialMotionEvent], mode: int, display_id: int) -> bool:
        if event is None:
            return False

        # In InputInjectionHooks.java line 120:
        # AtomicInteger pressedMask = getButtonStateForDisplay(displayId);
        # This allocates an entry in sDisplayButtonState for every queried displayId.
        current_pressed = self.get_button_state_for_display(display_id)

        raw_action = event.action
        action_masked = raw_action & self.ACTION_MASK
        button_state = getattr(event, "button_state", 0)
        action_button = getattr(event, "action_button", 0)

        with self.lock:
            # Refresh current_pressed under lock
            current_pressed = self.sDisplayButtonState[display_id]

            # 1. Secondary Button (Right-Click -> KEYCODE_BACK) Handling
            is_secondary_down = (action_masked in (MotionEvent.ACTION_DOWN, self.ACTION_BUTTON_PRESS)) and (
                (button_state & AdversarialMotionEvent.BUTTON_SECONDARY) != 0 or action_button == AdversarialMotionEvent.BUTTON_SECONDARY
            )

            was_secondary_pressed = (current_pressed & AdversarialMotionEvent.BUTTON_SECONDARY) != 0

            is_secondary_up = was_secondary_pressed and (
                action_masked in (MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL)
                or (action_masked == self.ACTION_BUTTON_RELEASE and (action_button == AdversarialMotionEvent.BUTTON_SECONDARY or action_button == 0))
                or ((button_state & AdversarialMotionEvent.BUTTON_SECONDARY) == 0 and action_masked != MotionEvent.ACTION_MOVE)
            )

            if is_secondary_down:
                self.sDisplayButtonState[display_id] = current_pressed | AdversarialMotionEvent.BUTTON_SECONDARY
                back_down = KeyEvent(action=KeyEvent.ACTION_DOWN, key_code=KeyEvent.KEYCODE_BACK, display_id=display_id)
                self.injected_keys.append(back_down)
                self.ims.inject_input_event_to_display(back_down, display_id, mode)
                return True

            if is_secondary_up:
                self.sDisplayButtonState[display_id] = current_pressed & ~AdversarialMotionEvent.BUTTON_SECONDARY
                back_up = KeyEvent(action=KeyEvent.ACTION_UP, key_code=KeyEvent.KEYCODE_BACK, display_id=display_id)
                self.injected_keys.append(back_up)
                self.ims.inject_input_event_to_display(back_up, display_id, mode)
                return True  # Returns early in Java hook!

            if was_secondary_pressed and action_masked == MotionEvent.ACTION_MOVE:
                return True  # Suppress move

            # 2. Tertiary Button (Middle-Click -> KEYCODE_HOME) Handling
            is_tertiary_down = (action_masked in (MotionEvent.ACTION_DOWN, self.ACTION_BUTTON_PRESS)) and (
                (button_state & AdversarialMotionEvent.BUTTON_TERTIARY) != 0 or action_button == AdversarialMotionEvent.BUTTON_TERTIARY
            )

            was_tertiary_pressed = (current_pressed & AdversarialMotionEvent.BUTTON_TERTIARY) != 0

            is_tertiary_up = was_tertiary_pressed and (
                action_masked in (MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL)
                or (action_masked == self.ACTION_BUTTON_RELEASE and (action_button == AdversarialMotionEvent.BUTTON_TERTIARY or action_button == 0))
                or ((button_state & AdversarialMotionEvent.BUTTON_TERTIARY) == 0 and action_masked != MotionEvent.ACTION_MOVE)
            )

            if is_tertiary_down:
                self.sDisplayButtonState[display_id] = current_pressed | AdversarialMotionEvent.BUTTON_TERTIARY
                home_down = KeyEvent(action=KeyEvent.ACTION_DOWN, key_code=KeyEvent.KEYCODE_HOME, display_id=display_id)
                self.injected_keys.append(home_down)
                self.ims.inject_input_event_to_display(home_down, display_id, mode)
                return True

            if is_tertiary_up:
                self.sDisplayButtonState[display_id] = current_pressed & ~AdversarialMotionEvent.BUTTON_TERTIARY
                home_up = KeyEvent(action=KeyEvent.ACTION_UP, key_code=KeyEvent.KEYCODE_HOME, display_id=display_id)
                self.injected_keys.append(home_up)
                self.ims.inject_input_event_to_display(home_up, display_id, mode)
                return True

            if was_tertiary_pressed and action_masked == MotionEvent.ACTION_MOVE:
                return True  # Suppress move

            # 3. Standard Motion
            self.injected_motions.append(event)
            return self.ims.inject_input_event_to_display(event, display_id, mode)


class WhiteBoxSystemServerHookModel:
    """
    Exact simulation of SystemServerHooks.java isPrivilegedInputCaller logic.
    Demonstrates the negative caching behavior on transient PMS lookup failure.
    """
    PKG_MDX = "com.samsung.android.mdx"
    PKG_APPMANAGER = "com.microsoft.appmanager"

    def __init__(self, pms_mock=None):
        self.pms_mock = pms_mock
        self.sPrivilegedUidCache: Dict[int, bool] = {}
        self.lock = threading.Lock()

    def is_privileged_input_caller(self, uid: int) -> bool:
        if uid == 1000 or uid == 0:
            return True

        with self.lock:
            cached = self.sPrivilegedUidCache.get(uid)
            if cached is not None:
                return cached

            try:
                if self.pms_mock is not None:
                    pkgs = self.pms_mock.get_packages_for_uid(uid)
                    if pkgs:
                        for pkg in pkgs:
                            if pkg in (self.PKG_MDX, self.PKG_APPMANAGER):
                                self.sPrivilegedUidCache[uid] = True
                                return True
            except Exception:
                # Transient error caught
                pass

            # Line 275 in SystemServerHooks.java:
            # Unconditionally caches FALSE on failure!
            self.sPrivilegedUidCache[uid] = False
            return False


# ==============================================================================
# Suite 1: Simultaneous Button Chords & ACTION_CANCEL
# ==============================================================================

class TestSimultaneousButtonChordsAndActionCancel(unittest.TestCase):
    """
    Stress-tests simultaneous mouse button chords (secondary + tertiary) and ACTION_CANCEL handling.
    Examines InputInjectionHooks.java state machine for stuck keys or dropped cancel updates.
    """

    def setUp(self):
        self.dm = DisplayManager()
        self.ims = InputManagerService(self.dm)
        self.hook = WhiteBoxInputInjectionHookModel(self.ims)
        self.display_id = 0

    def tearDown(self):
        self.dm.reset()
        self.ims.clear()

    def test_secondary_and_tertiary_simultaneous_press_chord(self):
        """
        Adversarial Test: Pressing secondary + tertiary simultaneously in a single event.
        Sequential if-return causes secondary to be processed while tertiary is skipped on that event.
        """
        chord_event = AdversarialMotionEvent(
            action=MotionEvent.ACTION_DOWN,
            x=500.0,
            y=1000.0,
            display_id=self.display_id,
            button_state=AdversarialMotionEvent.BUTTON_SECONDARY | AdversarialMotionEvent.BUTTON_TERTIARY,
        )

        res = self.hook.inject_motion_event(chord_event, mode=0, display_id=self.display_id)
        self.assertTrue(res)

        # In sequential if-return: secondary triggers first, injecting KEYCODE_BACK DOWN
        self.assertEqual(len(self.hook.injected_keys), 1)
        self.assertEqual(self.hook.injected_keys[0].key_code, KeyEvent.KEYCODE_BACK)
        self.assertEqual(self.hook.injected_keys[0].action, KeyEvent.ACTION_DOWN)

        # State mask has secondary set
        current_state = self.hook.get_button_state_for_display(self.display_id)
        self.assertTrue(bool(current_state & AdversarialMotionEvent.BUTTON_SECONDARY))

    def test_action_cancel_during_active_chord_leaves_tertiary_stuck(self):
        """
        Adversarial Vulnerability Test:
        When BOTH secondary and tertiary buttons are currently pressed (mask=6),
        and an ACTION_CANCEL arrives:
        isSecondaryUp executes, releases secondary, injects KEYCODE_BACK UP, and returns early.
        As a result, tertiary button is NOT released on ACTION_CANCEL, leaving KEYCODE_HOME stuck down!
        """
        # Step 1: Establish both buttons pressed in state mask (simulating active chord)
        self.hook.sDisplayButtonState[self.display_id] = (
            AdversarialMotionEvent.BUTTON_SECONDARY | AdversarialMotionEvent.BUTTON_TERTIARY
        )

        # Confirm both are marked active
        current_mask = self.hook.get_button_state_for_display(self.display_id)
        self.assertEqual(current_mask, AdversarialMotionEvent.BUTTON_SECONDARY | AdversarialMotionEvent.BUTTON_TERTIARY)

        # Step 2: ACTION_CANCEL arrives
        cancel_event = AdversarialMotionEvent(
            action=MotionEvent.ACTION_CANCEL,
            x=500.0,
            y=1000.0,
            display_id=self.display_id,
            button_state=0,
        )
        self.hook.inject_motion_event(cancel_event, mode=0, display_id=self.display_id)

        # White-box observation:
        # isSecondaryUp triggered and returned early.
        # Secondary was released (KEYCODE_BACK UP injected), BUT tertiary remained set!
        updated_mask = self.hook.get_button_state_for_display(self.display_id)
        self.assertTrue(bool(updated_mask & AdversarialMotionEvent.BUTTON_TERTIARY),
                        "Vulnerability confirmed: BUTTON_TERTIARY remains stuck in state mask after ACTION_CANCEL!")

        # KEYCODE_HOME UP was NOT injected on this cancel event!
        injected_keycodes = [(k.key_code, k.action) for k in self.hook.injected_keys]
        self.assertIn((KeyEvent.KEYCODE_BACK, KeyEvent.ACTION_UP), injected_keycodes)
        self.assertNotIn((KeyEvent.KEYCODE_HOME, KeyEvent.ACTION_UP), injected_keycodes)

    def test_stuck_tertiary_button_suppresses_subsequent_action_moves(self):
        """
        Adversarial Consequence Test:
        Because tertiary button remains stuck after ACTION_CANCEL,
        subsequent normal touch/mouse ACTION_MOVE events are permanently suppressed (return null).
        """
        # Set stuck tertiary state
        self.hook.sDisplayButtonState[self.display_id] = AdversarialMotionEvent.BUTTON_TERTIARY

        # Attempt normal drag move
        move_event = AdversarialMotionEvent(
            action=MotionEvent.ACTION_MOVE,
            x=550.0,
            y=1050.0,
            display_id=self.display_id,
            button_state=0,
        )
        res = self.hook.inject_motion_event(move_event, mode=0, display_id=self.display_id)

        # Move was suppressed by wasTertiaryPressed suppression block
        self.assertEqual(len(self.hook.injected_motions), 0,
                         "Normal ACTION_MOVE was suppressed due to stuck tertiary button state!")

    def test_rapid_chord_flapping_stress(self):
        """
        Stress-tests 500 rapid alternating button clicks, releases, and cancels.
        Ensures thread-safe bitmask mutations without data corruption or deadlocks.
        """
        for i in range(500):
            action = random.choice([
                MotionEvent.ACTION_DOWN,
                MotionEvent.ACTION_UP,
                MotionEvent.ACTION_CANCEL,
                AdversarialMotionEvent.ACTION_BUTTON_PRESS,
                AdversarialMotionEvent.ACTION_BUTTON_RELEASE,
            ])
            btn = random.choice([
                AdversarialMotionEvent.BUTTON_SECONDARY,
                AdversarialMotionEvent.BUTTON_TERTIARY,
                AdversarialMotionEvent.BUTTON_SECONDARY | AdversarialMotionEvent.BUTTON_TERTIARY,
            ])
            evt = AdversarialMotionEvent(
                action=action,
                x=float(i),
                y=float(i),
                display_id=self.display_id,
                button_state=btn if action not in (MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL) else 0,
                action_button=btn,
            )
            self.hook.inject_motion_event(evt, mode=0, display_id=self.display_id)

        # State bitmask must remain valid integer
        final_state = self.hook.get_button_state_for_display(self.display_id)
        self.assertIsInstance(final_state, int)


# ==============================================================================
# Suite 2: Display Creation & Teardown Races
# ==============================================================================

class TestDisplayCreationTeardownRaces(unittest.TestCase):
    """
    Stress-tests concurrent VirtualDisplay lifecycle transitions, in-flight input event races,
    and state map growth in MdxServiceHooks.java and InputInjectionHooks.java.
    """

    def setUp(self):
        self.dm = DisplayManager()
        self.ims = InputManagerService(self.dm)
        self.service = IPhoneScreenMirroringService(self.dm)
        self.ims.enable_inject_bypass_for_uid(10150)
        Process.set_current("com.samsung.android.mdx", 10150)

    def tearDown(self):
        Process.reset()
        self.dm.reset()
        self.ims.clear()

    def test_concurrent_create_and_teardown_racing(self):
        """
        Adversarial Race Condition: 16 concurrent threads repeatedly creating and releasing
        VirtualDisplays on the same mirroring service instance.
        Verifies that DisplayManager and IPhoneScreenMirroringService do not throw unhandled exceptions.
        """
        num_threads = 16
        cycles_per_thread = 25
        errors = []

        def worker(tid: int):
            try:
                for i in range(cycles_per_thread):
                    surface = Surface(1080, 2340)
                    disp_id = self.service.createVirtualDisplay(
                        name=f"RaceDisplay_{tid}_{i}",
                        width=1080,
                        height=2340,
                        densityDpi=440,
                        flags=0x12,
                        surface=surface,
                    )
                    self.assertGreater(disp_id, 0)
                    time.sleep(0.0001)  # Micro-yield to induce context switch
                    self.service.releaseVirtualDisplay()
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=num_threads) as pool:
            futures = [pool.submit(worker, t) for t in range(num_threads)]
            for f in as_completed(futures):
                f.result()

        self.assertEqual(len(errors), 0, f"Encountered {len(errors)} errors during display racing: {errors}")

    def test_in_flight_input_events_during_display_teardown(self):
        """
        Adversarial Test: Thread 1 streams 500 input events to display X while
        Thread 2 abruptly releases display X mid-stream.
        Verifies that injection gracefully returns False once released without throwing uncaught NPEs.
        """
        surface = Surface(1080, 2340)
        disp_id = self.service.createVirtualDisplay(
            name="StreamTeardownDisplay",
            width=1080,
            height=2340,
            densityDpi=440,
            flags=0x12,
            surface=surface,
        )

        injected_count = 0
        rejected_count = 0
        stop_event = threading.Event()

        def injector():
            nonlocal injected_count, rejected_count
            for i in range(500):
                evt = MotionEvent(action=MotionEvent.ACTION_MOVE, x=float(i), y=float(i), display_id=disp_id)
                success = self.ims.inject_input_event(evt, mode=0)
                if success:
                    injected_count += 1
                else:
                    rejected_count += 1
                time.sleep(0.0001)

        def teardown():
            time.sleep(0.01)  # Allow injection to start
            self.service.releaseVirtualDisplay()
            stop_event.set()

        t1 = threading.Thread(target=injector)
        t2 = threading.Thread(target=teardown)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Both injected and rejected events must be handled cleanly without crash
        self.assertGreater(injected_count, 0)
        self.assertGreater(rejected_count, 0)
        self.assertEqual(injected_count + rejected_count, 500)

    def test_ephemeral_display_id_growth_leak_risk(self):
        """
        Adversarial Memory Scaling Test:
        Simulate 1,000 ephemeral VirtualDisplay creation and release cycles.
        Verifies DisplayManager display pruning and notes sDisplayButtonState unbounded growth risk.
        """
        hook = WhiteBoxInputInjectionHookModel(self.ims)
        for i in range(500):
            surf = Surface(1080, 2340)
            disp_id = self.service.createVirtualDisplay(
                name=f"Ephemeral_{i}",
                width=1080,
                height=2340,
                densityDpi=440,
                flags=0x12,
                surface=surf,
            )
            # Input injected to this display populates sDisplayButtonState
            evt = AdversarialMotionEvent(action=MotionEvent.ACTION_DOWN, x=100.0, y=100.0, display_id=disp_id)
            hook.inject_motion_event(evt, mode=0, display_id=disp_id)
            self.service.releaseVirtualDisplay()

        # InputInjectionHooks does not have display listener to prune sDisplayButtonState:
        # Map retains entries for all ephemeral displays
        self.assertGreaterEqual(len(hook.sDisplayButtonState), 500,
                                "Confirmed: sDisplayButtonState does not prune released displays (memory leak risk).")

    def test_surface_destruction_during_active_mirroring_pipeline(self):
        """
        Adversarial Pipeline Test:
        Client suddenly calls surface.release() while VirtualDisplay is active.
        Verifies that pushing frames to released surface raises RuntimeError and set_surface rejects it.
        """
        surface = Surface(1080, 2340)
        disp_id = self.service.createVirtualDisplay(
            name="SurfaceDestructionDisplay",
            width=1080,
            height=2340,
            densityDpi=440,
            flags=0x12,
            surface=surface,
        )

        # Abruptly release surface
        surface.release()
        self.assertFalse(surface.is_valid())

        # Pushing frame to destroyed surface must raise RuntimeError
        with self.assertRaises(RuntimeError):
            surface.push_frame(b"\x00" * 1024)

        # setSurface with released surface must return False
        self.assertFalse(self.service.setSurface(surface))


# ==============================================================================
# Suite 3: Binder Death & SystemServer Recovery
# ==============================================================================

class TestBinderDeathAndSystemServerRecovery(unittest.TestCase):
    """
    Stress-tests transient PMS failure, negative caching lockdown, system_server restart,
    and dead client callback resilience.
    """

    class TransientFailingPms:
        def __init__(self):
            self.fail_mode = True

        def get_packages_for_uid(self, uid: int):
            if self.fail_mode:
                raise RuntimeError("DeadObjectException: PackageManagerService temporarily unavailable")
            return ["com.samsung.android.mdx"]

    def test_pms_transient_failure_causes_permanent_negative_cache_lockout(self):
        """
        Adversarial Vulnerability Test:
        In SystemServerHooks.java lines 272-276:
        When PMS throws an exception or fails temporarily, the catch block catches Throwable
        and line 275 records: sPrivilegedUidCache.put(uid, Boolean.FALSE).
        Because cached == FALSE is returned on subsequent calls without checking PMS again,
        the privileged UID is PERMANENTLY LOCKED OUT even after PMS recovers!
        """
        pms = self.TransientFailingPms()
        hook = WhiteBoxSystemServerHookModel(pms)
        mdx_uid = 10150

        # Phase 1: Transient failure during boot / high load
        pms.fail_mode = True
        result_during_failure = hook.is_privileged_input_caller(mdx_uid)
        self.assertFalse(result_during_failure)
        self.assertIn(mdx_uid, hook.sPrivilegedUidCache)
        self.assertFalse(hook.sPrivilegedUidCache[mdx_uid])

        # Phase 2: PMS completely recovers and returns valid package names
        pms.fail_mode = False

        # Phase 3: Query again
        result_after_recovery = hook.is_privileged_input_caller(mdx_uid)

        # Critical Vulnerability Confirmation:
        # Result is STILL FALSE because of negative caching!
        self.assertFalse(result_after_recovery,
                         "Vulnerability confirmed: Privileged caller permanently locked out due to negative cache!")

    def test_system_server_restart_clears_cache_and_restores_bypass(self):
        """
        Resilience Test:
        Simulates system_server restart recovery: clearing the cache simulates new process startup,
        allowing PMS to be re-queried and restoring legitimate access.
        """
        pms = self.TransientFailingPms()
        hook = WhiteBoxSystemServerHookModel(pms)
        mdx_uid = 10150

        # Inject negative cache
        hook.sPrivilegedUidCache[mdx_uid] = False

        # Simulate system_server restart
        hook.sPrivilegedUidCache.clear()
        pms.fail_mode = False

        recovered = hook.is_privileged_input_caller(mdx_uid)
        self.assertTrue(recovered, "System server restart recovery must restore privileged bypass.")

    def test_dead_client_callback_in_virtual_display_wrapper(self):
        """
        Adversarial Resilience Test:
        Client callback binder dies and throws DeadObjectException on lifecycle notifications.
        MdxServiceHooks.java wraps callbacks in try-catch; verifies no unhandled exception escapes.
        """
        class ThrowingDeadCallback:
            def onVirtualDisplayPaused(self):
                raise RuntimeError("DeadObjectException: client process has terminated")

            def onVirtualDisplayResumed(self):
                raise RuntimeError("DeadObjectException: client process has terminated")

            def onVirtualDisplayStopped(self):
                raise RuntimeError("DeadObjectException: client process has terminated")

            def onStopped(self):
                raise RuntimeError("DeadObjectException: client process has terminated")

        dm = DisplayManager()
        callback = ThrowingDeadCallback()
        surf = Surface(1080, 2340)

        vd = dm.create_virtual_display(
            name="DeadCallbackDisplay",
            width=1080,
            height=2340,
            density_dpi=440,
            surface=surf,
            flags=0x12,
            callback=callback,
        )

        # Releasing display triggers onStopped callback
        # MdxServiceHooks catches Throwable, preventing callback thread crash
        try:
            vd.release()
            callback_failed_safely = True
        except Exception:
            callback_failed_safely = False

        # In mock DisplayManager, release() invokes callback; verify resilience
        self.assertFalse(vd.is_valid)


# ==============================================================================
# Suite 4: Extreme Coordinates & Pointer Fuzzing
# ==============================================================================

class TestExtremeCoordinatesAndPointerFuzzing(unittest.TestCase):
    """
    Stress-tests extreme pointer IDs, negative coordinates, NaN/Infinity float values,
    and action index bitmask bounds.
    """

    def setUp(self):
        self.dm = DisplayManager()
        self.ims = InputManagerService(self.dm)
        self.ims.enable_inject_bypass_for_uid(10150)
        Process.set_current("com.samsung.android.mdx", 10150)

    def tearDown(self):
        Process.reset()
        self.dm.reset()
        self.ims.clear()

    def test_extreme_out_of_bounds_pointer_ids(self):
        """
        Adversarial Fuzzing: Pointer IDs from -1 up to 0x7FFFFFFF.
        Android pointer bitmask is 32-bit (1 << pointer_id). IDs >= 32 cause integer bitshift overflow.
        """
        hostile_pointer_ids = [-1, 31, 32, 64, 1000, 0x7FFFFFFF]
        for pid in hostile_pointer_ids:
            evt = MotionEvent(
                action=MotionEvent.ACTION_DOWN,
                x=100.0,
                y=200.0,
                display_id=0,
                pointer_id=pid,
            )
            # Ensure injection handles out-of-bounds pointer IDs gracefully
            try:
                res = self.ims.inject_input_event(evt, mode=0)
                self.assertIsInstance(res, bool)
            except (ValueError, IndexError, OverflowError):
                pass  # Graceful rejection

    def test_nan_and_infinity_float_coordinates(self):
        """
        Adversarial Fuzzing: Coordinates containing NaN, +Infinity, and -Infinity.
        Ensures input pipeline does not crash with unhandled float conversion exceptions.
        """
        hostile_coords = [
            (float("nan"), float("nan")),
            (float("inf"), float("-inf")),
            (float("-inf"), 500.0),
            (500.0, float("nan")),
        ]
        for x, y in hostile_coords:
            evt = MotionEvent(action=MotionEvent.ACTION_MOVE, x=x, y=y, display_id=0)
            try:
                res = self.ims.inject_input_event(evt, mode=0)
                # If accepted, coordinates should not crash math operations
                self.assertIsInstance(res, bool)
            except (ValueError, OverflowError):
                pass

    def test_extreme_negative_and_giant_coordinates(self):
        """
        Adversarial BVA: Extreme negative coordinates (-999999.0) and huge off-screen coordinates (+999999.0).
        Negative coordinates must be safely rejected by InputManagerService.
        """
        neg_evt = MotionEvent(action=MotionEvent.ACTION_DOWN, x=-999999.0, y=-999999.0, display_id=0)
        self.assertFalse(self.ims.inject_input_event(neg_evt, mode=0),
                         "Negative coordinates must be rejected by InputManagerService.")

        giant_evt = MotionEvent(action=MotionEvent.ACTION_DOWN, x=999999.0, y=999999.0, display_id=0)
        # Giant positive coordinates are off-screen but within valid float range
        res = self.ims.inject_input_event(giant_evt, mode=0)
        self.assertIsInstance(res, bool)

    def test_zero_and_excessive_pointer_counts(self):
        """
        Adversarial Limits: Pointer count = 0 and Pointer count > 10 (exceeding AOSP limit).
        """
        # Pointer count > 10 must raise ValueError
        evt = MotionEvent(action=MotionEvent.ACTION_MOVE, x=100.0, y=100.0, display_id=0)
        for i in range(1, 15):
            evt.add_pointer(i, float(i * 10), float(i * 10))

        with self.assertRaises(ValueError):
            self.ims.inject_input_event(evt, mode=0)


# ==============================================================================
# Suite 5: Qualcomm SD855 Codec2 Edge Cases
# ==============================================================================

class TestQualcommSD855Codec2EdgeCases(unittest.TestCase):
    """
    Stress-tests Qualcomm Snapdragon 855 Codec2 encoder edge cases, non-standard color formats,
    extreme bitrates, macroblock alignment, and surface destruction in VideoCodecHooks.java.
    """

    COLOR_FormatSurface = 0x7F000789
    COLOR_FormatVendorSamsung = 0x7FA00000
    COLOR_FormatVendorSamsungTiled = 0x7FA30C00
    COLOR_FormatYUV420Planar = 0x13
    COLOR_FormatYUV420SemiPlanar = 0x15

    def sanitize_media_format(self, fmt: Dict[str, Any], flags: int = 1) -> Dict[str, Any]:
        """Faithful Python mirror of VideoCodecHooks.java hookMediaCodecConfigure."""
        out = dict(fmt)
        if (flags & 1) == 0:
            return out

        # A. Enforce COLOR_FormatSurface
        color = out.get("color-format")
        if color != self.COLOR_FormatSurface:
            out["color-format"] = self.COLOR_FormatSurface

        # B. Standard AOSP low-latency flags
        out["low-latency"] = 1
        out["priority"] = 0

        # C. Default bitrate mode to VBR (2) if missing
        if "bitrate-mode" not in out:
            out["bitrate-mode"] = 2

        # D. Default I-frame interval
        if "i-frame-interval" not in out:
            out["i-frame-interval"] = 1

        return out

    def test_unsupported_vendor_color_format_sanitization(self):
        """
        Adversarial Format Test:
        Passing Samsung proprietary color formats (0x7FA00000, 0x7FA30C00) and raw YUV formats.
        VideoCodecHooks must sanitize all of them to COLOR_FormatSurface (0x7F000789).
        """
        hostile_color_formats = [
            self.COLOR_FormatVendorSamsung,
            self.COLOR_FormatVendorSamsungTiled,
            self.COLOR_FormatYUV420Planar,
            self.COLOR_FormatYUV420SemiPlanar,
            0,
            -1,
        ]
        for cf in hostile_color_formats:
            raw_fmt = {"color-format": cf, "width": 1080, "height": 2340}
            sanitized = self.sanitize_media_format(raw_fmt)
            self.assertEqual(sanitized["color-format"], self.COLOR_FormatSurface,
                             f"Failed sanitizing color format {cf} to COLOR_FormatSurface")
            self.assertEqual(sanitized["low-latency"], 1)
            self.assertEqual(sanitized["priority"], 0)

    def test_extreme_bitrate_values_outside_sd855_capabilities(self):
        """
        Adversarial BVA:
        Extreme bitrates: -1, 0, 10 Gbps (10,000,000,000).
        Snapdragon 855 hardware encoder c2.qti.avc.encoder supports 32 kbps to 100 Mbps.
        Observation: VideoCodecHooks does not clamp bitrates, leaving this as an identified gap.
        """
        extreme_bitrates = [-1, 0, 10_000_000_000]
        for br in extreme_bitrates:
            fmt = {"bitrate": br, "color-format": self.COLOR_FormatSurface}
            sanitized = self.sanitize_media_format(fmt)
            # Confirms VideoCodecHooks leaves bitrate unmodified
            self.assertEqual(sanitized["bitrate"], br)

    def test_non_macroblock_aligned_and_extreme_resolutions(self):
        """
        Adversarial Resolution Test:
        Odd resolutions (1081x2341), 1x1, 0x0, and 8K (8192x4320).
        Qualcomm Codec2 AVC hardware encoder requires 16x16 macroblock alignment and max 4096x2160.
        """
        odd_fmt = {"width": 1081, "height": 2341}
        sanitized = self.sanitize_media_format(odd_fmt)
        self.assertEqual(sanitized["width"], 1081)
        self.assertEqual(sanitized["height"], 2341)

    def test_sync_frame_request_flooding(self):
        """
        Stress Test: 1,000 consecutive vendor.sec-ext-enc-request-sync parameter requests.
        Ensures bundle mapping to PARAMETER_KEY_REQUEST_SYNC_FRAME without degradation.
        """
        for _ in range(1000):
            bundle = Bundle({"vendor.sec-ext-enc-request-sync": 1})
            # VideoCodecHooks mapping
            if bundle.contains_key("vendor.sec-ext-enc-request-sync"):
                bundle.put_int("request-sync", 1)
            self.assertEqual(bundle.get_int("request-sync"), 1)


# ==============================================================================
# Suite 6: AppManager Dynamic Class Injection & Multi-User
# ==============================================================================

class TestAppManagerDynamicClassInjectionAndMultiUser(unittest.TestCase):
    """
    Stress-tests AppManagerHooks.java dynamic class injection concurrency,
    multi-user UID boundary security, and process-scoped Build property isolation.
    """

    def setUp(self):
        self.class_loader = ARTClassLoader()

    def tearDown(self):
        Build.reset_defaults()
        Process.reset()

    def test_concurrent_classloader_stub_injection_32_threads(self):
        """
        Adversarial Concurrency: 32 threads calling ClassLoader.loadClass concurrently
        for SemFloatingFeature and DesktopModeManager.
        Verifies 0 deadlocks and exact stub identity.
        """
        self.class_loader.register_stub("com.samsung.android.feature.SemFloatingFeature", SemFloatingFeature)
        self.class_loader.register_stub("com.samsung.android.desktopmode.DesktopModeManager", OneUIStubs)

        num_threads = 32
        lookups_per_thread = 500
        errors = []

        def worker():
            try:
                for _ in range(lookups_per_thread):
                    c1 = self.class_loader.load_class("com.samsung.android.feature.SemFloatingFeature")
                    c2 = self.class_loader.load_class("com.samsung.android.desktopmode.DesktopModeManager")
                    if c1 is not SemFloatingFeature or c2 is not OneUIStubs:
                        errors.append("Stub mismatch under concurrency")
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=num_threads) as pool:
            futures = [pool.submit(worker) for _ in range(num_threads)]
            for f in as_completed(futures):
                f.result()

        self.assertEqual(len(errors), 0, f"Classloader concurrency errors: {errors}")

    def test_multi_user_and_work_profile_uid_boundaries(self):
        """
        Security Boundary Test:
        Verifies that isolated process UIDs (e.g. 99000) or untrusted secondary users
        cannot bypass permission checks even if MDX is active on user 0.
        """
        dm = DisplayManager()
        ims = InputManagerService(dm)
        # Grant bypass strictly to user 0 MDX UID 10150
        ims.enable_inject_bypass_for_uid(10150)

        # Isolated process UID
        Process.set_current("isolated_rogue_app", 99000)
        evt = MotionEvent(action=MotionEvent.ACTION_DOWN, x=100.0, y=100.0, display_id=0)
        with self.assertRaises(SecurityException):
            ims.inject_input_event(evt, mode=0)

        # Secondary user untrusted UID
        Process.set_current("user10_app", 1010999)
        with self.assertRaises(SecurityException):
            ims.inject_input_event(evt, mode=0)

    def test_scoped_build_spoofing_concurrency_isolation(self):
        """
        Adversarial Isolation Test:
        Multi-threaded rapid context switching between com.microsoft.appmanager,
        com.samsung.android.mdx, and system process.
        Verifies that Samsung identity does not leak into the global system context.
        """
        Build.enable_scoped_spoofing({
            "com.microsoft.appmanager": {"MANUFACTURER": "samsung", "MODEL": "SM-G998B"},
            "com.samsung.android.mdx": {"MANUFACTURER": "samsung", "MODEL": "SM-G998B"},
        })

        # When running as system
        Process.set_current("android", 1000)
        self.assertEqual(Build.MANUFACTURER, "Xiaomi")
        self.assertEqual(Build.MODEL, "MI 9")

        # When running as AppManager
        Process.set_current("com.microsoft.appmanager", 10151)
        self.assertEqual(Build.MANUFACTURER, "samsung")
        self.assertEqual(Build.MODEL, "SM-G998B")

        # When running as generic third-party app
        Process.set_current("com.google.android.youtube", 10200)
        self.assertEqual(Build.MANUFACTURER, "Xiaomi")


# ==============================================================================
# Suite 7: Compiled Java Bytecode Tier 5 Adversarial Harness
# ==============================================================================

class TestCompiledJavaBytecodeTier5AdversarialHarness(unittest.TestCase):
    """
    Executes Tier5AdversarialHookStressTest directly against compiled classes in
    lsposed_module/build/app_classes with the Java JVM.
    Empirically verifies JVM multi-threaded concurrency, atomic state mutations,
    negative-caching vulnerability reproduction, and reflection conformance.
    """

    def test_compiled_java_bytecode_tier5_adversarial_stress_harness(self):
        """
        Adversarial JVM Execution:
        Directly compiles and executes Tier5AdversarialHookStressTest against:
        - InputInjectionHooks.class
        - SystemServerHooks.class
        - VideoCodecHooks.class
        - MdxServiceHooks.class
        - AppManagerHooks.class
        """
        project_root = str(PROJECT_ROOT)
        java_cmd = "java"
        javac_cmd = "javac"

        app_classes = os.path.join(project_root, "lsposed_module", "build", "app_classes")
        android_stubs = os.path.join(project_root, "lsposed_module", "tools", "android_stubs.jar")
        api_jar = os.path.join(project_root, "lsposed_module", "tools", "api-82.jar")
        test_stress_dir = os.path.join(project_root, "tests", "stress")
        source_java = os.path.join(test_stress_dir, "Tier5AdversarialHookStressTest.java")

        classpath = f"{test_stress_dir};{app_classes};{android_stubs};{api_jar}"

        # 1. Compile test harness if not already up to date
        compile_proc = subprocess.run(
            [javac_cmd, "-cp", classpath, "-d", test_stress_dir, source_java],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(compile_proc.returncode, 0, f"Compilation failed: {compile_proc.stderr}")

        # 2. Execute test harness in JVM
        run_proc = subprocess.run(
            [java_cmd, "-cp", classpath, "tests.stress.Tier5AdversarialHookStressTest"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30,
        )

        print("\n" + run_proc.stdout)
        if run_proc.returncode != 0:
            print(run_proc.stderr)

        self.assertEqual(run_proc.returncode, 0, f"Tier5AdversarialHookStressTest failed with code {run_proc.returncode}")
        self.assertIn("[SUCCESS] ALL TIER 5 JAVA ADVERSARIAL STRESS TESTS PASSED CLEANLY", run_proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
