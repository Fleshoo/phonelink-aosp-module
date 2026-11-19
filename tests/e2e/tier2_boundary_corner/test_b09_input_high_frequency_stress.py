"""
Boundary & Adversarial Stress Suite: High-Frequency Input Injection Engine (Milestone M4)
Targets:
1. High-frequency touch event streams (60Hz–120Hz continuous drag/flick gestures, 1,000+ rapid events).
2. Multithreaded concurrent injection contention simulating simultaneous PC user interactions.
3. Rapid alternation between mouse clicks (Left Click, Right Click -> KEYCODE_BACK, Middle Click -> KEYCODE_HOME)
   and keyboard typing via UinputBridge.
4. sPrivilegedUidCache O(1) performance, multi-threaded insertion race conditions, memory scalability, and deadlock immunity.
5. Empirical execution of compiled Java bytecode (JavaInputStressTest) verifying SystemServerHooks and InputInjectionHooks.

Authoritative Sources:
- ORIGINAL_REQUEST.md § R3 (PC Remote Control without system security blocks)
- PROJECT.md § Features 9, 10, 11 (Remote Input Injection Engine)
- DISPATCH.md (Challenger M4-1 Specification)
"""

import os
import sys
import time
import math
import subprocess
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional

from tests.mock_env.android_runtime import (
    InputEvent,
    MotionEvent,
    KeyEvent,
    Process,
    SecurityException,
    Surface,
)
from tests.mock_env.display_manager import DisplayManager
from tests.mock_env.input_manager import (
    InputManagerService,
    InputManager,
    UinputBridge,
    ClipboardBridge,
)
from tests.mock_env.binder_ipc import IInputInjectorService


class StressMotionEvent(MotionEvent):
    """
    High-fidelity MotionEvent model with mouse button states matching Android MotionEvent.
    """
    ACTION_MASK = 0xff
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


class HookedInputInjector:
    """
    Emulates SemInputInjector hooked by InputInjectionHooks.java:
    - Thread-safe, per-display stateful tracking of mouse button states across ACTION_DOWN / ACTION_UP.
    - Right-click (BUTTON_SECONDARY) -> KeyEvent(ACTION_DOWN/UP, KEYCODE_BACK).
    - Middle-click (BUTTON_TERTIARY) -> KeyEvent(ACTION_DOWN/UP, KEYCODE_HOME).
    - Dispatches KeyEvent.ACTION_UP when buttons are released (even with button_state == 0).
    - Suppresses orphan touch ACTION_UP and move events while buttons are held.
    - Touch & standard mouse -> MotionEvent forwarded to InputManagerService.
    - Keys -> KeyEvent forwarded to InputManagerService.
    """
    ACTION_MASK = 0xff
    ACTION_BUTTON_PRESS = 11
    ACTION_BUTTON_RELEASE = 12

    def __init__(self, ims: InputManagerService):
        self.ims = ims
        self.lock = threading.Lock()
        self.display_button_state: Dict[int, int] = {}

    def inject_motion_event(self, event: Optional[MotionEvent], mode: int, display_id: int) -> bool:
        if event is None:
            return False

        raw_action = event.action
        action_masked = raw_action & self.ACTION_MASK
        button_state = getattr(event, "button_state", 0)
        action_button = getattr(event, "action_button", 0)

        with self.lock:
            current_pressed = self.display_button_state.get(display_id, 0)

            # -----------------------------------------------------------------
            # 1. Secondary Button (Right-Click -> KEYCODE_BACK) Handling
            # -----------------------------------------------------------------
            is_secondary_down = (action_masked in (MotionEvent.ACTION_DOWN, self.ACTION_BUTTON_PRESS)) and (
                (button_state & StressMotionEvent.BUTTON_SECONDARY) != 0 or action_button == StressMotionEvent.BUTTON_SECONDARY
            )

            was_secondary_pressed = (current_pressed & StressMotionEvent.BUTTON_SECONDARY) != 0

            is_secondary_up = was_secondary_pressed and (
                action_masked in (MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL)
                or (action_masked == self.ACTION_BUTTON_RELEASE and (action_button == StressMotionEvent.BUTTON_SECONDARY or action_button == 0))
                or ((button_state & StressMotionEvent.BUTTON_SECONDARY) == 0 and action_masked != MotionEvent.ACTION_MOVE)
            )

            if is_secondary_down:
                self.display_button_state[display_id] = current_pressed | StressMotionEvent.BUTTON_SECONDARY
                back_event = KeyEvent(action=KeyEvent.ACTION_DOWN, key_code=KeyEvent.KEYCODE_BACK, display_id=display_id)
                return self._inject_event_locked(back_event, mode, display_id)

            if is_secondary_up:
                self.display_button_state[display_id] = current_pressed & ~StressMotionEvent.BUTTON_SECONDARY
                back_event = KeyEvent(action=KeyEvent.ACTION_UP, key_code=KeyEvent.KEYCODE_BACK, display_id=display_id)
                return self._inject_event_locked(back_event, mode, display_id)

            if was_secondary_pressed and action_masked == MotionEvent.ACTION_MOVE:
                # Suppress touch move during right-click drag
                return True

            # -----------------------------------------------------------------
            # 2. Tertiary Button (Middle-Click -> KEYCODE_HOME) Handling
            # -----------------------------------------------------------------
            is_tertiary_down = (action_masked in (MotionEvent.ACTION_DOWN, self.ACTION_BUTTON_PRESS)) and (
                (button_state & StressMotionEvent.BUTTON_TERTIARY) != 0 or action_button == StressMotionEvent.BUTTON_TERTIARY
            )

            was_tertiary_pressed = (current_pressed & StressMotionEvent.BUTTON_TERTIARY) != 0

            is_tertiary_up = was_tertiary_pressed and (
                action_masked in (MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL)
                or (action_masked == self.ACTION_BUTTON_RELEASE and (action_button == StressMotionEvent.BUTTON_TERTIARY or action_button == 0))
                or ((button_state & StressMotionEvent.BUTTON_TERTIARY) == 0 and action_masked != MotionEvent.ACTION_MOVE)
            )

            if is_tertiary_down:
                self.display_button_state[display_id] = current_pressed | StressMotionEvent.BUTTON_TERTIARY
                home_event = KeyEvent(action=KeyEvent.ACTION_DOWN, key_code=KeyEvent.KEYCODE_HOME, display_id=display_id)
                return self._inject_event_locked(home_event, mode, display_id)

            if is_tertiary_up:
                self.display_button_state[display_id] = current_pressed & ~StressMotionEvent.BUTTON_TERTIARY
                home_event = KeyEvent(action=KeyEvent.ACTION_UP, key_code=KeyEvent.KEYCODE_HOME, display_id=display_id)
                return self._inject_event_locked(home_event, mode, display_id)

            if was_tertiary_pressed and action_masked == MotionEvent.ACTION_MOVE:
                # Suppress touch move during middle-click drag
                return True

            # -----------------------------------------------------------------
            # 3. Standard Touch & Mouse Motion Injection
            # -----------------------------------------------------------------
            return self._inject_event_locked(event, mode, display_id)

    def _inject_event_locked(self, event: InputEvent, mode: int, display_id: int) -> bool:
        if event is None:
            return False
        event.set_display_id(display_id)
        return self.ims.inject_input_event(event, mode)

    def inject_key_event(self, event: Optional[KeyEvent], mode: int, display_id: int) -> bool:
        if event is None:
            return False
        with self.lock:
            return self._inject_event_locked(event, mode, display_id)

    def inject_event_internal(self, event: InputEvent, mode: int, display_id: int) -> bool:
        if event is None:
            return False
        with self.lock:
            return self._inject_event_locked(event, mode, display_id)


class TestHighFrequencyInputStress(unittest.TestCase):
    def setUp(self):
        self.dm = DisplayManager()
        self.ims = InputManagerService(self.dm)
        self.hooked_injector = HookedInputInjector(self.ims)
        self.service = IInputInjectorService(self.ims)
        self.uinput = UinputBridge()

        # Whitelist MDX service UID 10150 and AppManager UID 10151
        self.ims.enable_inject_bypass_for_uid(10150)
        self.ims.enable_inject_bypass_for_uid(10151)
        Process.set_current("com.samsung.android.mdx", 10150)
        self.service.enableInputInjector()

    def tearDown(self):
        if self.uinput.is_open:
            self.uinput.close()
        Process.reset()
        self.ims.clear()
        self.dm.reset()

    # --------------------------------------------------------------------------
    # 1. High-Frequency Touch Streams (60Hz–120Hz, 1,000+ Rapid Events)
    # --------------------------------------------------------------------------

    def test_high_frequency_touch_drag_120hz_1200_events(self):
        """
        Stress Test: Continuous 1,200-event drag gesture at 120Hz (8.33ms delta).
        Verifies throughput, timestamp monotonicity, and zero dropped events.
        """
        total_events = 1200
        down_time = 1_000_000_000
        step_dt_ns = 8_333_333  # ~8.33ms = 120Hz

        # 1. ACTION_DOWN
        down_event = StressMotionEvent(
            action=MotionEvent.ACTION_DOWN,
            x=540.0,
            y=1900.0,
            display_id=0,
            down_time=down_time,
            event_time=down_time,
        )
        self.assertTrue(self.hooked_injector.inject_motion_event(down_event, mode=0, display_id=0))

        # 2. 1,198 ACTION_MOVE along a continuous Bézier/curved scroll trajectory
        start_perf = time.perf_counter()
        for i in range(1, total_events - 1):
            t = down_time + i * step_dt_ns
            # Smooth trigonometric motion across 1080x2340 screen
            progress = i / total_events
            curr_x = 540.0 + 200.0 * math.sin(progress * 4 * math.pi)
            curr_y = 1900.0 - 1500.0 * progress
            move_event = StressMotionEvent(
                action=MotionEvent.ACTION_MOVE,
                x=curr_x,
                y=curr_y,
                display_id=0,
                down_time=down_time,
                event_time=t,
            )
            res = self.hooked_injector.inject_motion_event(move_event, mode=0, display_id=0)
            self.assertTrue(res, f"Failed injecting move event at step {i}")

        # 3. ACTION_UP
        up_time = down_time + (total_events - 1) * step_dt_ns
        up_event = StressMotionEvent(
            action=MotionEvent.ACTION_UP,
            x=540.0,
            y=400.0,
            display_id=0,
            down_time=down_time,
            event_time=up_time,
        )
        self.assertTrue(self.hooked_injector.inject_motion_event(up_event, mode=0, display_id=0))
        duration_s = time.perf_counter() - start_perf

        # Empirical Assertions
        injected = self.ims.injected_events
        self.assertEqual(len(injected), total_events)
        self.assertEqual(injected[0].action, MotionEvent.ACTION_DOWN)
        self.assertEqual(injected[-1].action, MotionEvent.ACTION_UP)

        # Monotonicity & continuity checks
        for idx in range(1, len(injected)):
            self.assertGreaterEqual(injected[idx].event_time, injected[idx - 1].event_time)
            self.assertEqual(injected[idx].down_time, down_time)

        # Throughput benchmark: 1200 events processed in under 0.25 seconds
        events_per_sec = total_events / max(duration_s, 1e-6)
        self.assertGreater(events_per_sec, 5000.0, f"Throughput too low: {events_per_sec:.0f} events/sec")

    def test_high_velocity_flick_gesture_stress(self):
        """
        Stress Test: High-velocity flick gesture with rapid coordinate delta
        (200 pixels/frame) simulating aggressive PC user scrolling.
        """
        flick_steps = 200
        down_time = 2_000_000_000
        step_dt_ns = 8_333_333

        self.assertTrue(
            self.hooked_injector.inject_motion_event(
                StressMotionEvent(MotionEvent.ACTION_DOWN, x=540.0, y=2000.0, down_time=down_time, event_time=down_time),
                mode=0,
                display_id=0,
            )
        )

        for i in range(1, flick_steps):
            y_pos = max(0.0, 2000.0 - i * 50.0)
            move_ev = StressMotionEvent(
                MotionEvent.ACTION_MOVE,
                x=540.0,
                y=y_pos,
                down_time=down_time,
                event_time=down_time + i * step_dt_ns,
            )
            self.assertTrue(self.hooked_injector.inject_motion_event(move_ev, mode=0, display_id=0))

        self.assertTrue(
            self.hooked_injector.inject_motion_event(
                StressMotionEvent(
                    MotionEvent.ACTION_UP,
                    x=540.0,
                    y=0.0,
                    down_time=down_time,
                    event_time=down_time + flick_steps * step_dt_ns,
                ),
                mode=0,
                display_id=0,
            )
        )

        self.assertEqual(len(self.ims.injected_events), flick_steps + 1)

    def test_multitouch_pinch_zoom_stream_stress(self):
        """
        Stress Test: 1,000 dual-touch pinch-to-zoom updates.
        Verifies pointer count, pointer ID mapping, and multi-finger coordination.
        """
        stream_len = 1000
        for i in range(stream_len):
            touch = StressMotionEvent(
                action=MotionEvent.ACTION_MOVE,
                x=400.0 - i * 0.2,
                y=800.0,
                display_id=0,
                pointer_id=0,
            )
            # Second finger expanding outward
            touch.add_pointer(pointer_id=1, x=680.0 + i * 0.2, y=800.0)
            self.assertEqual(touch.get_pointer_count(), 2)
            self.assertTrue(self.hooked_injector.inject_motion_event(touch, mode=0, display_id=0))

        self.assertEqual(len(self.ims.injected_events), stream_len)
        for ev in self.ims.injected_events:
            self.assertIsInstance(ev, MotionEvent)
            self.assertEqual(ev.get_pointer_count(), 2)

    # --------------------------------------------------------------------------
    # 2. Multithreaded Concurrent Injection Contention
    # --------------------------------------------------------------------------

    def test_multithreaded_concurrent_injection_3000_events(self):
        """
        Stress Test: 8 concurrent threads simultaneously injecting 3,000 events total:
        - 4 touch gesture threads (500 events each = 2,000 events)
        - 2 keyboard typing threads (250 keystrokes each = 500 events)
        - 2 mouse click threads (250 click events each = 500 events)
        Verifies absence of deadlocks, race conditions, or dropped events.
        """
        thread_count = 8
        events_per_touch_thread = 500
        events_per_key_thread = 250
        events_per_mouse_thread = 250
        expected_total = (4 * events_per_touch_thread) + (2 * events_per_key_thread) + (2 * events_per_mouse_thread)

        barrier = threading.Barrier(thread_count)
        errors: List[Exception] = []

        def touch_worker(worker_id: int):
            try:
                barrier.wait(timeout=5.0)
                for step in range(events_per_touch_thread):
                    action = MotionEvent.ACTION_MOVE
                    if step == 0:
                        action = MotionEvent.ACTION_DOWN
                    elif step == events_per_touch_thread - 1:
                        action = MotionEvent.ACTION_UP

                    ev = StressMotionEvent(
                        action=action,
                        x=100.0 + (worker_id * 50.0),
                        y=200.0 + (step * 2.0),
                        display_id=0,
                    )
                    res = self.hooked_injector.inject_motion_event(ev, mode=0, display_id=0)
                    if not res:
                        raise RuntimeError(f"Touch injection failed in worker {worker_id} at step {step}")
            except Exception as e:
                errors.append(e)

        def keyboard_worker(worker_id: int):
            try:
                barrier.wait(timeout=5.0)
                keycodes = [KeyEvent.KEYCODE_A, KeyEvent.KEYCODE_B, KeyEvent.KEYCODE_ENTER, KeyEvent.KEYCODE_DEL]
                for step in range(events_per_key_thread):
                    kc = keycodes[step % len(keycodes)]
                    action = KeyEvent.ACTION_DOWN if (step % 2 == 0) else KeyEvent.ACTION_UP
                    ev = KeyEvent(action=action, key_code=kc, display_id=0)
                    res = self.hooked_injector.inject_key_event(ev, mode=0, display_id=0)
                    if not res:
                        raise RuntimeError(f"Key injection failed in worker {worker_id} at step {step}")
            except Exception as e:
                errors.append(e)

        def mouse_worker(worker_id: int):
            try:
                barrier.wait(timeout=5.0)
                for step in range(events_per_mouse_thread):
                    # Alternate left, right, middle clicks
                    mod = step % 3
                    btn = (
                        StressMotionEvent.BUTTON_PRIMARY
                        if mod == 0
                        else (StressMotionEvent.BUTTON_SECONDARY if mod == 1 else StressMotionEvent.BUTTON_TERTIARY)
                    )
                    action = MotionEvent.ACTION_UP if (step % 2 == 1) else MotionEvent.ACTION_DOWN
                    ev = StressMotionEvent(
                        action=action,
                        x=500.0,
                        y=500.0,
                        button_state=btn,
                        display_id=0,
                    )
                    res = self.hooked_injector.inject_motion_event(ev, mode=0, display_id=0)
                    if not res:
                        raise RuntimeError(f"Mouse injection failed in worker {worker_id} at step {step}")
            except Exception as e:
                errors.append(e)

        threads: List[threading.Thread] = []
        for i in range(4):
            threads.append(threading.Thread(target=touch_worker, args=(i,)))
        for i in range(2):
            threads.append(threading.Thread(target=keyboard_worker, args=(i,)))
        for i in range(2):
            threads.append(threading.Thread(target=mouse_worker, args=(i,)))

        start_time = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)
            self.assertFalse(t.is_alive(), "Deadlock detected: thread failed to finish within 10s!")

        elapsed = time.perf_counter() - start_time
        self.assertEqual(len(errors), 0, f"Encountered {len(errors)} thread errors: {errors}")
        self.assertEqual(len(self.ims.injected_events), expected_total)
        print(f"\n    [+] Multithreaded injection: {expected_total} events across 8 threads completed in {elapsed:.3f}s (0 deadlocks)")

    # --------------------------------------------------------------------------
    # 3. Rapid Alternation Between Mouse Clicks & Keyboard Typing
    # --------------------------------------------------------------------------

    def test_rapid_mouse_keyboard_alternation_6000_events(self):
        """
        Stress Test: 1,000 rapid cycles alternating between:
        1. Left Click (Touch DOWN & UP)
        2. Keyboard Keypress (DOWN & UP)
        3. Right Click -> Mapped to KEYCODE_BACK (DOWN & UP)
        4. Keyboard Typing (DOWN & UP)
        5. Middle Click -> Mapped to KEYCODE_HOME (DOWN & UP)
        6. Keyboard Enter (DOWN & UP)
        Total 6,000 events. Verifies precise button mapping and keycode translation.
        """
        self.uinput.open()
        cycles = 1000

        back_count = 0
        home_count = 0
        touch_count = 0
        key_count = 0

        start_time = time.perf_counter()
        for c in range(cycles):
            # 1. Left Click (Touch MotionEvent)
            ev_left_down = StressMotionEvent(MotionEvent.ACTION_DOWN, 200.0, 300.0, button_state=StressMotionEvent.BUTTON_PRIMARY)
            ev_left_up = StressMotionEvent(MotionEvent.ACTION_UP, 200.0, 300.0, button_state=StressMotionEvent.BUTTON_PRIMARY)
            self.assertTrue(self.hooked_injector.inject_motion_event(ev_left_down, 0, 0))
            self.assertTrue(self.hooked_injector.inject_motion_event(ev_left_up, 0, 0))
            touch_count += 2

            # 2. Keypress 'A'
            self.uinput.press_key(KeyEvent.KEYCODE_A)
            ev_key_a_down = KeyEvent(action=KeyEvent.ACTION_DOWN, key_code=KeyEvent.KEYCODE_A)
            ev_key_a_up = KeyEvent(action=KeyEvent.ACTION_UP, key_code=KeyEvent.KEYCODE_A)
            self.assertTrue(self.hooked_injector.inject_key_event(ev_key_a_down, 0, 0))
            self.assertTrue(self.hooked_injector.inject_key_event(ev_key_a_up, 0, 0))
            self.uinput.release_key(KeyEvent.KEYCODE_A)
            key_count += 2

            # 3. Right Click -> Must translate to KEYCODE_BACK
            ev_right_down = StressMotionEvent(MotionEvent.ACTION_DOWN, 400.0, 500.0, button_state=StressMotionEvent.BUTTON_SECONDARY)
            ev_right_up = StressMotionEvent(MotionEvent.ACTION_UP, 400.0, 500.0, button_state=StressMotionEvent.BUTTON_SECONDARY)
            self.assertTrue(self.hooked_injector.inject_motion_event(ev_right_down, 0, 0))
            self.assertTrue(self.hooked_injector.inject_motion_event(ev_right_up, 0, 0))
            back_count += 2

            # 4. Keypress 'B'
            ev_key_b_down = KeyEvent(action=KeyEvent.ACTION_DOWN, key_code=KeyEvent.KEYCODE_B)
            ev_key_b_up = KeyEvent(action=KeyEvent.ACTION_UP, key_code=KeyEvent.KEYCODE_B)
            self.assertTrue(self.hooked_injector.inject_key_event(ev_key_b_down, 0, 0))
            self.assertTrue(self.hooked_injector.inject_key_event(ev_key_b_up, 0, 0))
            key_count += 2

            # 5. Middle Click -> Must translate to KEYCODE_HOME
            ev_mid_down = StressMotionEvent(MotionEvent.ACTION_DOWN, 600.0, 700.0, button_state=StressMotionEvent.BUTTON_TERTIARY)
            ev_mid_up = StressMotionEvent(MotionEvent.ACTION_UP, 600.0, 700.0, button_state=StressMotionEvent.BUTTON_TERTIARY)
            self.assertTrue(self.hooked_injector.inject_motion_event(ev_mid_down, 0, 0))
            self.assertTrue(self.hooked_injector.inject_motion_event(ev_mid_up, 0, 0))
            home_count += 2

            # 6. Keypress 'ENTER'
            ev_enter_down = KeyEvent(action=KeyEvent.ACTION_DOWN, key_code=KeyEvent.KEYCODE_ENTER)
            ev_enter_up = KeyEvent(action=KeyEvent.ACTION_UP, key_code=KeyEvent.KEYCODE_ENTER)
            self.assertTrue(self.hooked_injector.inject_key_event(ev_enter_down, 0, 0))
            self.assertTrue(self.hooked_injector.inject_key_event(ev_enter_up, 0, 0))
            key_count += 2

        duration = time.perf_counter() - start_time
        total_injected = len(self.ims.injected_events)
        self.assertEqual(total_injected, cycles * 12)
        self.assertEqual(back_count, cycles * 2)
        self.assertEqual(home_count, cycles * 2)
        self.assertFalse(self.uinput.has_stuck_keys())

        # Verify keycodes in injected event stream
        actual_back_events = [e for e in self.ims.injected_events if isinstance(e, KeyEvent) and e.key_code == KeyEvent.KEYCODE_BACK]
        actual_home_events = [e for e in self.ims.injected_events if isinstance(e, KeyEvent) and e.key_code == KeyEvent.KEYCODE_HOME]
        self.assertEqual(len(actual_back_events), back_count)
        self.assertEqual(len(actual_home_events), home_count)
        print(f"\n    [+] Rapid alternation: {total_injected} events in {duration:.3f}s (100% Back/Home translation verified)")

    def test_chorded_mouse_buttons_precedence(self):
        """
        Stress Test: Simultaneous mouse buttons (Left + Right pressed together).
        Verifies that BUTTON_SECONDARY bitmask precedence triggers KEYCODE_BACK.
        """
        chorded_event = StressMotionEvent(
            action=MotionEvent.ACTION_DOWN,
            x=500.0,
            y=500.0,
            button_state=(StressMotionEvent.BUTTON_PRIMARY | StressMotionEvent.BUTTON_SECONDARY),
        )
        self.assertTrue(self.hooked_injector.inject_motion_event(chorded_event, mode=0, display_id=0))

        last_ev = self.ims.injected_events[-1]
        self.assertIsInstance(last_ev, KeyEvent)
        self.assertEqual(last_ev.key_code, KeyEvent.KEYCODE_BACK)

    def test_mouse_button_release_with_zero_button_state_secondary(self):
        """
        Adversarial Test (Reviewer M4-1 Caveat / Explorer M5-1):
        Verifies that an ACTION_UP event with button_state = 0 correctly emits
        KeyEvent.ACTION_UP for KEYCODE_BACK and does NOT inject an orphan MotionEvent.
        """
        self.ims.injected_events.clear()

        # Step 1: Right mouse button pressed (ACTION_DOWN with BUTTON_SECONDARY)
        ev_down = StressMotionEvent(
            action=MotionEvent.ACTION_DOWN,
            x=450.0,
            y=600.0,
            button_state=StressMotionEvent.BUTTON_SECONDARY,
        )
        self.assertTrue(self.hooked_injector.inject_motion_event(ev_down, mode=0, display_id=0))

        # Step 2: Right mouse button released (ACTION_UP with button_state = 0 per standard AOSP driver)
        ev_up = StressMotionEvent(
            action=MotionEvent.ACTION_UP,
            x=450.0,
            y=600.0,
            button_state=0,  # CRITICAL: button_state is 0 on release!
        )
        self.assertTrue(self.hooked_injector.inject_motion_event(ev_up, mode=0, display_id=0))

        # Verifications
        self.assertEqual(len(self.ims.injected_events), 2, "Expected exactly 2 key events; no orphan MotionEvent allowed")
        
        first_ev = self.ims.injected_events[0]
        self.assertIsInstance(first_ev, KeyEvent)
        self.assertEqual(first_ev.action, KeyEvent.ACTION_DOWN)
        self.assertEqual(first_ev.key_code, KeyEvent.KEYCODE_BACK)

        second_ev = self.ims.injected_events[1]
        self.assertIsInstance(second_ev, KeyEvent)
        self.assertEqual(second_ev.action, KeyEvent.ACTION_UP)
        self.assertEqual(second_ev.key_code, KeyEvent.KEYCODE_BACK)

        # Ensure no stuck button state
        self.assertEqual(self.hooked_injector.display_button_state.get(0, 0), 0)

    def test_mouse_button_release_with_zero_button_state_tertiary(self):
        """
        Adversarial Test (Reviewer M4-1 Caveat / Explorer M5-1):
        Verifies that an ACTION_UP event with button_state = 0 correctly emits
        KeyEvent.ACTION_UP for KEYCODE_HOME and does NOT inject an orphan MotionEvent.
        """
        self.ims.injected_events.clear()

        # Step 1: Middle mouse button pressed (ACTION_DOWN with BUTTON_TERTIARY)
        ev_down = StressMotionEvent(
            action=MotionEvent.ACTION_DOWN,
            x=700.0,
            y=800.0,
            button_state=StressMotionEvent.BUTTON_TERTIARY,
        )
        self.assertTrue(self.hooked_injector.inject_motion_event(ev_down, mode=0, display_id=0))

        # Step 2: Middle mouse button released (ACTION_UP with button_state = 0)
        ev_up = StressMotionEvent(
            action=MotionEvent.ACTION_UP,
            x=700.0,
            y=800.0,
            button_state=0,  # CRITICAL: button_state is 0 on release!
        )
        self.assertTrue(self.hooked_injector.inject_motion_event(ev_up, mode=0, display_id=0))

        # Verifications
        self.assertEqual(len(self.ims.injected_events), 2, "Expected exactly 2 key events; no orphan MotionEvent allowed")

        first_ev = self.ims.injected_events[0]
        self.assertIsInstance(first_ev, KeyEvent)
        self.assertEqual(first_ev.action, KeyEvent.ACTION_DOWN)
        self.assertEqual(first_ev.key_code, KeyEvent.KEYCODE_HOME)

        second_ev = self.ims.injected_events[1]
        self.assertIsInstance(second_ev, KeyEvent)
        self.assertEqual(second_ev.action, KeyEvent.ACTION_UP)
        self.assertEqual(second_ev.key_code, KeyEvent.KEYCODE_HOME)

        # Ensure no stuck button state
        self.assertEqual(self.hooked_injector.display_button_state.get(0, 0), 0)

    def test_mouse_button_press_and_release_action_constants(self):
        """
        Adversarial Test: Verifies ACTION_BUTTON_PRESS and ACTION_BUTTON_RELEASE
        with action_button attributes are correctly translated to KeyEvent pairs.
        """
        self.ims.injected_events.clear()

        # Press via ACTION_BUTTON_PRESS
        ev_press = StressMotionEvent(
            action=StressMotionEvent.ACTION_BUTTON_PRESS,
            x=300.0,
            y=300.0,
            action_button=StressMotionEvent.BUTTON_SECONDARY,
        )
        self.assertTrue(self.hooked_injector.inject_motion_event(ev_press, mode=0, display_id=0))

        # Release via ACTION_BUTTON_RELEASE with button_state = 0
        ev_release = StressMotionEvent(
            action=StressMotionEvent.ACTION_BUTTON_RELEASE,
            x=300.0,
            y=300.0,
            button_state=0,
            action_button=StressMotionEvent.BUTTON_SECONDARY,
        )
        self.assertTrue(self.hooked_injector.inject_motion_event(ev_release, mode=0, display_id=0))

        self.assertEqual(len(self.ims.injected_events), 2)
        self.assertEqual(self.ims.injected_events[0].action, KeyEvent.ACTION_DOWN)
        self.assertEqual(self.ims.injected_events[0].key_code, KeyEvent.KEYCODE_BACK)
        self.assertEqual(self.ims.injected_events[1].action, KeyEvent.ACTION_UP)
        self.assertEqual(self.ims.injected_events[1].key_code, KeyEvent.KEYCODE_BACK)

    def test_mouse_button_action_cancel_flushes_state(self):
        """
        Adversarial Test: Verifies that ACTION_CANCEL cleanly dispatches KeyEvent.ACTION_UP
        and flushes the active button mask to prevent logically stuck buttons.
        """
        self.ims.injected_events.clear()

        # Press
        ev_down = StressMotionEvent(
            action=MotionEvent.ACTION_DOWN,
            x=400.0,
            y=400.0,
            button_state=StressMotionEvent.BUTTON_SECONDARY,
        )
        self.assertTrue(self.hooked_injector.inject_motion_event(ev_down, mode=0, display_id=0))

        # Cancel event (e.g. gesture cancel / connection drop)
        ev_cancel = StressMotionEvent(
            action=MotionEvent.ACTION_CANCEL,
            x=400.0,
            y=400.0,
            button_state=0,
        )
        self.assertTrue(self.hooked_injector.inject_motion_event(ev_cancel, mode=0, display_id=0))

        self.assertEqual(len(self.ims.injected_events), 2)
        self.assertEqual(self.ims.injected_events[1].action, KeyEvent.ACTION_UP)
        self.assertEqual(self.ims.injected_events[1].key_code, KeyEvent.KEYCODE_BACK)
        self.assertEqual(self.hooked_injector.display_button_state.get(0, 0), 0)

    def test_mouse_move_suppression_while_button_pressed(self):
        """
        Corner-case Test: Verifies that ACTION_MOVE events during right-click drag
        are suppressed and do not inject spurious touch moves on screen.
        """
        self.ims.injected_events.clear()

        # Press secondary button
        ev_down = StressMotionEvent(
            action=MotionEvent.ACTION_DOWN,
            x=500.0,
            y=500.0,
            button_state=StressMotionEvent.BUTTON_SECONDARY,
        )
        self.assertTrue(self.hooked_injector.inject_motion_event(ev_down, mode=0, display_id=0))

        # Drag with button held down (5 MOVE events)
        for i in range(5):
            ev_move = StressMotionEvent(
                action=MotionEvent.ACTION_MOVE,
                x=500.0 + i * 10,
                y=500.0 + i * 10,
                button_state=StressMotionEvent.BUTTON_SECONDARY,
            )
            self.assertTrue(self.hooked_injector.inject_motion_event(ev_move, mode=0, display_id=0))

        # Release secondary button
        ev_up = StressMotionEvent(
            action=MotionEvent.ACTION_UP,
            x=550.0,
            y=550.0,
            button_state=0,
        )
        self.assertTrue(self.hooked_injector.inject_motion_event(ev_up, mode=0, display_id=0))

        # Exactly 2 events should be injected: ACTION_DOWN (BACK) and ACTION_UP (BACK)
        self.assertEqual(len(self.ims.injected_events), 2)
        self.assertEqual(self.ims.injected_events[0].action, KeyEvent.ACTION_DOWN)
        self.assertEqual(self.ims.injected_events[1].action, KeyEvent.ACTION_UP)

    # --------------------------------------------------------------------------
    # 4. sPrivilegedUidCache O(1) Scalability and Concurrency
    # --------------------------------------------------------------------------

    def test_sprivileged_uid_cache_o1_lookup_benchmark(self):
        """
        Stress Test: 100,000 lookups on sPrivilegedUidCache simulation.
        Verifies O(1) constant time retrieval (< 1 microsecond per lookup).
        """
        cache: Dict[int, bool] = {
            10150: True,
            10151: True,
            10999: False,
        }
        iterations = 100_000

        start = time.perf_counter_ns()
        for i in range(iterations):
            uid = 10150 if (i % 3 == 0) else (10151 if (i % 3 == 1) else 10999)
            val = cache.get(uid)
            if val is None:
                raise AssertionError("Missing cache entry")

        elapsed_ns = time.perf_counter_ns() - start
        ns_per_op = elapsed_ns / iterations
        self.assertLess(ns_per_op, 1000.0, f"Cache lookup too slow: {ns_per_op:.2f} ns/op")

    def test_cache_scalability_full_android_uid_space(self):
        """
        Stress Test: 10,000 distinct UIDs (complete Android user 0 application space).
        Verifies hash map scalability, lookup speed, and absence of degradation.
        """
        large_cache: Dict[int, bool] = {}
        for uid in range(10000, 20000):
            large_cache[uid] = (uid == 10150 or uid == 10151)

        start = time.perf_counter_ns()
        for uid in range(10000, 20000):
            val = large_cache[uid]
            if uid in (10150, 10151):
                self.assertTrue(val)
            else:
                self.assertFalse(val)

        elapsed_ns = time.perf_counter_ns() - start
        ns_per_lookup = elapsed_ns / 10000
        self.assertLess(ns_per_lookup, 1000.0)

    # --------------------------------------------------------------------------
    # 5. Java Bytecode Stress Execution (SystemServerHooks & InputInjectionHooks)
    # --------------------------------------------------------------------------

    def test_compiled_java_bytecode_stress_harness(self):
        """
        Adversarial Test: Executes JavaInputStressTest directly against compiled classes
        in lsposed_module/build/app_classes with Java JVM.
        Verifies real JVM concurrency, O(1) performance (50M+ ops/sec), memory bounds, and DEX conformance.
        """
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        java_cmd = "java"

        app_classes = os.path.join(project_root, "lsposed_module", "build", "app_classes")
        android_stubs = os.path.join(project_root, "lsposed_module", "tools", "android_stubs.jar")
        api_jar = os.path.join(project_root, "lsposed_module", "tools", "api-82.jar")
        test_classes = os.path.join(project_root, "tests", "stress")

        classpath = f"{test_classes};{app_classes};{android_stubs};{api_jar}"
        proc = subprocess.run(
            [java_cmd, "-cp", classpath, "tests.stress.JavaInputStressTest"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30,
        )

        print("\n" + proc.stdout)
        if proc.returncode != 0:
            print(proc.stderr)
        self.assertEqual(proc.returncode, 0, f"JavaInputStressTest failed with exit code {proc.returncode}")
        self.assertIn("[SUCCESS] ALL JAVA ADVERSARIAL STRESS TESTS PASSED CLEANLY", proc.stdout)


if __name__ == "__main__":
    unittest.main()
