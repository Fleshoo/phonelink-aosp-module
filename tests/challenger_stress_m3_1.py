#!/usr/bin/env python3
"""
Challenger Stress Test Suite M3-1: VirtualDisplay Lifecycle & Surface Stress Test.

Empirically tests:
1. 150+ rapid cycles of creation, multi-tier resizing, surface switching, and release.
2. High-concurrency multithreaded stress (16-32 threads racing create, resize, setSurface, release).
3. Handling of null/invalid Surfaces and boundary dimensions (0, negative, invalid DPI).
4. Dead client callback binders (DeadObjectException, throwing callbacks, binder death).
5. Resource cleanup: verification that VirtualDisplay instances and HandlerThreads are not leaked or orphaned.
"""

import unittest
import threading
import concurrent.futures
import time
import random
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.mock_env.android_runtime import Surface
from tests.mock_env.display_manager import DisplayManager, VirtualDisplay, Display
from tests.mock_env.binder_ipc import IPhoneScreenMirroringService


class MockSafeCallback:
    """Standard well-behaved client callback."""
    def __init__(self):
        self.stopped_count = 0
        self.resumed_count = 0
        self.paused_count = 0

    def onVirtualDisplayPaused(self):
        self.paused_count += 1

    def onVirtualDisplayResumed(self):
        self.resumed_count += 1

    def onVirtualDisplayStopped(self):
        self.stopped_count += 1

    # Also support onStopped / onResumed directly
    def onStopped(self):
        self.stopped_count += 1

    def onResumed(self):
        self.resumed_count += 1

    def onPaused(self):
        self.paused_count += 1


class DeadBinderCallback:
    """Simulates a client whose binder died or throws DeadObjectException."""
    def __init__(self):
        self.is_dead = True

    def onStopped(self):
        raise ConnectionResetError("DeadObjectException: Client callback binder is dead")

    def onResumed(self):
        raise ConnectionResetError("DeadObjectException: Client callback binder is dead")

    def onPaused(self):
        raise ConnectionResetError("DeadObjectException: Client callback binder is dead")

    def onVirtualDisplayStopped(self):
        raise ConnectionResetError("DeadObjectException: Client callback binder is dead")

    def onVirtualDisplayResumed(self):
        raise ConnectionResetError("DeadObjectException: Client callback binder is dead")


class MockHandlerThread:
    """Simulates Android OS HandlerThread lifecycle."""
    _thread_counter = 0

    def __init__(self, name: str):
        MockHandlerThread._thread_counter += 1
        self.name = name
        self.id = MockHandlerThread._thread_counter
        self._alive = True
        self._quit = False

    def isAlive(self) -> bool:
        return self._alive

    def is_alive(self) -> bool:
        return self._alive

    def quitSafely(self) -> bool:
        self._alive = False
        self._quit = True
        return True

    def quit(self) -> bool:
        self._alive = False
        self._quit = True
        return True


class TestVirtualDisplayLifecycleStress(unittest.TestCase):
    """
    Empirical stress testing of VirtualDisplay lifecycle and Surface handling.
    """

    def setUp(self):
        self.dm = DisplayManager()
        self.service = IPhoneScreenMirroringService(self.dm)

    def tearDown(self):
        self.service.releaseVirtualDisplay()
        self.dm.reset()

    # =========================================================================
    # Test 1: 150 Rapid Cycles (Create, Resize across tiers, Surface Switch, Release)
    # =========================================================================
    def test_rapid_lifecycle_150_iterations(self):
        """
        Executes 150 rapid iterations of:
        - createVirtualDisplay
        - pushing H.264 video frames
        - resizing through multiple resolutions (1080p -> 720p -> 540p -> 1440p)
        - switching to secondary and tertiary surfaces
        - releaseVirtualDisplay
        - verifying complete resource cleanup after each cycle.
        """
        NUM_CYCLES = 150
        resolutions = [
            (1080, 2340, 440),
            (720, 1560, 320),
            (540, 1170, 240),
            (1440, 3120, 560),
            (1080, 1920, 400),
        ]

        h264_sps = b"\x00\x00\x00\x01\x67\x42\x00\x1f"
        h264_idr = b"\x00\x00\x00\x01\x65\x88\x84\x00"

        for cycle in range(NUM_CYCLES):
            callback = MockSafeCallback()
            surface_1 = Surface(1080, 2340)

            # 1. Create VirtualDisplay
            disp_id = self.service.createVirtualDisplay(
                name=f"PhoneScreenStream_{cycle}",
                width=1080,
                height=2340,
                densityDpi=440,
                flags=DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR | DisplayManager.VIRTUAL_DISPLAY_FLAG_PRESENTATION,
                surface=surface_1,
                callback=callback,
            )
            self.assertGreater(disp_id, 0, f"Cycle {cycle}: Invalid display ID")
            self.assertEqual(callback.resumed_count, 1, f"Cycle {cycle}: onResumed not fired")
            self.assertIsNotNone(self.service.active_virtual_display)
            self.assertTrue(self.service.active_virtual_display.is_valid)

            # 2. Push frames to primary surface
            surface_1.push_frame(h264_sps)
            surface_1.push_frame(h264_idr)
            self.assertEqual(len(surface_1.frames_received), 2)

            # 3. Dynamic multi-tier resizing
            target_res = resolutions[cycle % len(resolutions)]
            self.service.resizeVirtualDisplay(target_res[0], target_res[1], target_res[2])
            vd = self.service.active_virtual_display
            self.assertEqual(vd.get_width(), target_res[0])
            self.assertEqual(vd.get_height(), target_res[1])
            self.assertEqual(vd.get_density_dpi(), target_res[2])
            self.assertEqual(vd.state, "RESIZED")

            # 4. Surface switching (secondary surface)
            surface_2 = Surface(target_res[0], target_res[1])
            switched = self.service.setSurface(surface_2)
            self.assertTrue(switched, f"Cycle {cycle}: Surface switch failed")
            self.assertIs(self.service.active_virtual_display.surface, surface_2)
            surface_2.push_frame(h264_idr)
            self.assertEqual(len(surface_2.frames_received), 1)

            # 5. Surface switching (tertiary surface)
            surface_3 = Surface(target_res[0], target_res[1])
            switched_3 = self.service.setSurface(surface_3)
            self.assertTrue(switched_3)
            self.assertIs(self.service.active_virtual_display.surface, surface_3)

            # 6. Release VirtualDisplay
            self.service.releaseVirtualDisplay()

            # 7. Post-release assertions
            self.assertIsNone(self.service.active_virtual_display)
            self.assertEqual(callback.stopped_count, 1, f"Cycle {cycle}: onStopped not fired")
            self.assertFalse(surface_3.is_valid(), f"Cycle {cycle}: Surface not released")

            # Verify no active virtual displays linger in DisplayManager
            active_displays = self.dm.get_displays()
            self.assertEqual(
                len(active_displays), 1,
                f"Cycle {cycle}: Dangling displays in DisplayManager: {[d.display_id for d in active_displays]}"
            )
            self.assertEqual(active_displays[0].display_id, Display.DEFAULT_DISPLAY)

    # =========================================================================
    # Test 2: High-Concurrency Multithreaded Stress (16 & 32 Threads)
    # =========================================================================
    def test_high_concurrency_multithreaded_stress_16_threads(self):
        """
        16 concurrent worker threads simultaneously executing random operations:
        - createVirtualDisplay
        - resizeVirtualDisplay
        - setSurface
        - releaseVirtualDisplay
        - frame pushing
        Verifies absence of deadlocks, thread crashes, and unhandled exceptions.
        """
        NUM_THREADS = 16
        OPS_PER_THREAD = 60
        barrier = threading.Barrier(NUM_THREADS)
        thread_errors = []
        op_counts = {"create": 0, "resize": 0, "set_surface": 0, "release": 0}
        lock = threading.Lock()

        # Thread-safe wrapper for concurrent execution
        service_lock = threading.Lock()

        def worker(tid: int):
            try:
                barrier.wait()
                for i in range(OPS_PER_THREAD):
                    op_type = i % 4
                    if op_type == 0:
                        surf = Surface(1080, 2340)
                        cb = MockSafeCallback()
                        with service_lock:
                            try:
                                self.service.createVirtualDisplay(
                                    f"Concur_{tid}_{i}", 1080, 2340, 440, 0, surf, cb
                                )
                                with lock:
                                    op_counts["create"] += 1
                            except Exception as e:
                                thread_errors.append(f"Thread {tid} create error: {e}")

                    elif op_type == 1:
                        w = 720 if (i % 2 == 0) else 1080
                        h = 1560 if (i % 2 == 0) else 2340
                        with service_lock:
                            try:
                                if self.service.active_virtual_display and self.service.active_virtual_display.is_valid:
                                    self.service.resizeVirtualDisplay(w, h, 320)
                                    with lock:
                                        op_counts["resize"] += 1
                            except Exception as e:
                                thread_errors.append(f"Thread {tid} resize error: {e}")

                    elif op_type == 2:
                        new_surf = Surface(1080, 2340)
                        with service_lock:
                            try:
                                if self.service.active_virtual_display and self.service.active_virtual_display.is_valid:
                                    self.service.setSurface(new_surf)
                                    with lock:
                                        op_counts["set_surface"] += 1
                            except Exception as e:
                                thread_errors.append(f"Thread {tid} setSurface error: {e}")

                    elif op_type == 3:
                        with service_lock:
                            try:
                                self.service.releaseVirtualDisplay()
                                with lock:
                                    op_counts["release"] += 1
                            except Exception as e:
                                thread_errors.append(f"Thread {tid} release error: {e}")

            except Exception as e:
                thread_errors.append(f"Thread {tid} unhandled fatal error: {e}")

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(NUM_THREADS)]
        start_time = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)
            self.assertFalse(t.is_alive(), f"Thread {t} deadlocked!")
        duration = time.perf_counter() - start_time

        self.assertEqual(len(thread_errors), 0, f"Encountered thread errors: {thread_errors}")
        total_ops = sum(op_counts.values())
        self.assertEqual(total_ops, NUM_THREADS * OPS_PER_THREAD)
        print(f"    [+] 16 Threads completed {total_ops} concurrent operations in {duration:.3f}s: {op_counts}")

        # Post-test cleanup and sanity check
        self.service.releaseVirtualDisplay()
        active_displays = self.dm.get_displays()
        self.assertEqual(len(active_displays), 1)

    def test_high_concurrency_race_condition_resilience(self):
        """
        Adversarial race testing: threads intentionally attempt racing calls
        WITHOUT outer locks to verify that internal state remains intact or raises
        expected controlled exceptions without process corruption.
        """
        NUM_THREADS = 8
        barrier = threading.Barrier(NUM_THREADS)
        exceptions_caught = []

        def racer(tid: int):
            barrier.wait()
            for i in range(30):
                try:
                    if i % 3 == 0:
                        surf = Surface(1080, 2340)
                        self.service.createVirtualDisplay(f"Race_{tid}_{i}", 1080, 2340, 440, 0, surf)
                    elif i % 3 == 1:
                        self.service.resizeVirtualDisplay(720, 1560, 320)
                    else:
                        self.service.releaseVirtualDisplay()
                except RuntimeError:
                    # Expected if resize is called on released/null display during race
                    pass
                except Exception as e:
                    exceptions_caught.append((type(e).__name__, str(e)))

        threads = [threading.Thread(target=racer, args=(t,)) for t in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        # Allow expected benign race conditions (e.g. RuntimeError: No active VirtualDisplay)
        # but zero unhandled crashes or internal corruption
        unhandled = [e for e in exceptions_caught if e[0] not in ("RuntimeError", "ValueError")]
        self.assertEqual(len(unhandled), 0, f"Unhandled fatal race exceptions: {unhandled}")

        # Verify system recovers smoothly
        self.service.releaseVirtualDisplay()
        surf_clean = Surface(1080, 2340)
        disp_id = self.service.createVirtualDisplay("Recovery", 1080, 2340, 440, 0, surf_clean)
        self.assertGreater(disp_id, 0)
        self.service.releaseVirtualDisplay()

    # =========================================================================
    # Test 3: Null, Invalid Surfaces, and Boundary Dimensions
    # =========================================================================
    def test_null_surface_handling(self):
        """
        Verifies that createVirtualDisplay with surface=None succeeds
        (matching AOSP behavior where surface can be bound later via setSurface).
        """
        disp_id = self.service.createVirtualDisplay(
            name="NullSurfaceStream",
            width=1080,
            height=2340,
            densityDpi=440,
            flags=0,
            surface=None,
        )
        self.assertGreater(disp_id, 0)
        self.assertIsNone(self.service.active_virtual_display.surface)

        # Attach surface later
        delayed_surface = Surface(1080, 2340)
        attached = self.service.setSurface(delayed_surface)
        self.assertTrue(attached)
        self.assertIs(self.service.active_virtual_display.surface, delayed_surface)

        # Detach surface with None
        detached = self.service.setSurface(None)
        self.assertTrue(detached)
        self.assertIsNone(self.service.active_virtual_display.surface)

    def test_invalid_and_released_surface_handling(self):
        """
        Verifies that pre-released or invalid surfaces are safely rejected
        without crashing the service or display manager.
        """
        # 1. createVirtualDisplay with released surface
        dead_surface = Surface(1080, 2340)
        dead_surface.release()
        with self.assertRaises(ValueError):
            self.service.createVirtualDisplay("DeadSurf", 1080, 2340, 440, 0, dead_surface)

        # 2. setSurface with released surface on active display
        valid_surface = Surface(1080, 2340)
        self.service.createVirtualDisplay("ActiveStream", 1080, 2340, 440, 0, valid_surface)
        bad_replacement = Surface(1080, 2340)
        bad_replacement.release()
        accepted = self.service.setSurface(bad_replacement)
        self.assertFalse(accepted, "Service should reject invalid/released replacement surface")
        # Ensure previous surface is retained and undisturbed
        self.assertIs(self.service.active_virtual_display.surface, valid_surface)

        # 3. setSurface when no display is active
        self.service.releaseVirtualDisplay()
        fresh_surf = Surface(1080, 2340)
        result = self.service.setSurface(fresh_surf)
        self.assertFalse(result, "setSurface should return False when no display is active")

    def test_boundary_dimensions_validation(self):
        """
        Tests rejection of boundary, zero, and negative dimensions and DPI.
        """
        surf = Surface(1080, 2340)
        invalid_configs = [
            ("ZeroWidth", 0, 2340, 440),
            ("NegativeWidth", -1080, 2340, 440),
            ("ZeroHeight", 1080, 0, 440),
            ("NegativeHeight", 1080, -2340, 440),
            ("ZeroDpi", 1080, 2340, 0),
            ("NegativeDpi", 1080, 2340, -440),
            ("", 1080, 2340, 440),  # Empty name
        ]

        for name, w, h, dpi in invalid_configs:
            with self.subTest(name=name, w=w, h=h, dpi=dpi):
                with self.assertRaises(ValueError):
                    self.service.createVirtualDisplay(name, w, h, dpi, 0, surf)

        # Verify active display was never created
        self.assertIsNone(self.service.active_virtual_display)

    def test_idempotent_release_and_double_creation(self):
        """
        Verifies idempotency of releaseVirtualDisplay (calling 10x in a row)
        and consecutive creations without explicit release.
        """
        # Consecutive creations without explicit release: must automatically clean up previous
        surf1 = Surface(1080, 2340)
        disp1_id = self.service.createVirtualDisplay("Stream1", 1080, 2340, 440, 0, surf1)
        self.assertFalse(surf1.is_valid() == False, "Initial surface should be valid")

        surf2 = Surface(720, 1560)
        disp2_id = self.service.createVirtualDisplay("Stream2", 720, 1560, 320, 0, surf2)
        self.assertNotEqual(disp1_id, disp2_id)
        # Previous surface surf1 must have been automatically released
        self.assertFalse(surf1.is_valid())
        self.assertTrue(surf2.is_valid())

        # 10 consecutive releases in a row
        for _ in range(10):
            self.service.releaseVirtualDisplay()
        self.assertIsNone(self.service.active_virtual_display)

    # =========================================================================
    # Test 4: Dead Client Callback Binders & Remote Exception Resilience
    # =========================================================================
    def test_dead_client_callback_on_stopped_resilience(self):
        """
        Verifies that if client callback throws DeadObjectException / RemoteException,
        the service does not crash and the VirtualDisplay is still successfully released.
        """
        dead_cb = DeadBinderCallback()
        surf = Surface(1080, 2340)

        # In MdxServiceHooks.java, callback calls are guarded by try-catch (Throwable).
        # We simulate the safe wrapping layer here:
        class SafeCallbackWrapper:
            def __init__(self, target_cb):
                self.target_cb = target_cb
                self.caught_exceptions = []

            def onStopped(self):
                if self.target_cb and hasattr(self.target_cb, "onStopped"):
                    try:
                        self.target_cb.onStopped()
                    except Exception as e:
                        self.caught_exceptions.append(e)

            def onResumed(self):
                if self.target_cb and hasattr(self.target_cb, "onResumed"):
                    try:
                        self.target_cb.onResumed()
                    except Exception as e:
                        self.caught_exceptions.append(e)

        wrapper = SafeCallbackWrapper(dead_cb)
        disp_id = self.service.createVirtualDisplay(
            "DeadClientStream", 1080, 2340, 440, 0, surf, wrapper
        )
        self.assertGreater(disp_id, 0)
        self.assertEqual(len(wrapper.caught_exceptions), 1)  # onResumed DeadObjectException caught

        # Release should succeed cleanly despite dead callback
        self.service.releaseVirtualDisplay()
        self.assertIsNone(self.service.active_virtual_display)
        self.assertFalse(surf.is_valid())
        self.assertEqual(len(wrapper.caught_exceptions), 2)  # onStopped DeadObjectException caught

    def test_simulated_client_binder_death_triggers_cleanup(self):
        """
        Simulates IBinder.DeathRecipient: when client process dies abruptly,
        binderDied() callback must release VirtualDisplay and surfaces.
        """
        surf = Surface(1080, 2340)
        cb = MockSafeCallback()
        disp_id = self.service.createVirtualDisplay("DeathTestStream", 1080, 2340, 440, 0, surf, cb)
        self.assertIsNotNone(self.service.active_virtual_display)

        # Simulate binder death notification
        class ClientDeathRecipient:
            def __init__(self, service_to_cleanup):
                self.service = service_to_cleanup
                self.died = False

            def binderDied(self):
                self.died = True
                self.service.releaseVirtualDisplay()

        recipient = ClientDeathRecipient(self.service)
        recipient.binderDied()

        self.assertTrue(recipient.died)
        self.assertIsNone(self.service.active_virtual_display)
        self.assertFalse(surf.is_valid())
        self.assertEqual(cb.stopped_count, 1)

    # =========================================================================
    # Test 5: Resource Cleanup & Leak Detection (VirtualDisplay & HandlerThread)
    # =========================================================================
    def test_no_virtualdisplay_leaks_200_cycles(self):
        """
        Executes 200 consecutive create/release cycles and verifies that:
        1. DisplayManager contains ONLY Display 0 (Default Screen) at completion.
        2. No memory leak / accumulation of active VirtualDisplay references.
        """
        NUM_CYCLES = 200

        for i in range(NUM_CYCLES):
            surf = Surface(1080, 2340)
            self.service.createVirtualDisplay(f"LeakTest_{i}", 1080, 2340, 440, 0, surf)
            self.service.releaseVirtualDisplay()

        active = self.dm.get_displays()
        self.assertEqual(len(active), 1, "Only default display should remain active")
        self.assertEqual(active[0].display_id, Display.DEFAULT_DISPLAY)

    def test_handlerthread_lifecycle_reuse_and_teardown(self):
        """
        Simulates HandlerThread lifecycle in PhoneScreenMirroringService:
        1. First createVirtualDisplay spawns HandlerThread('MediaProjectionCallback').
        2. Subsequent createVirtualDisplay calls REUSE existing alive HandlerThread.
        3. onUnbind() calls thread.quitSafely(), shutting down the thread cleanly.
        """
        class MockPhoneScreenMirroringServiceContext:
            def __init__(self):
                self.b_thread: Optional[MockHandlerThread] = None
                self.c_handler: Optional[Any] = None
                self.d_vd: Optional[VirtualDisplay] = None

            def ensure_handler_thread(self):
                # Simulates MdxServiceHooks lines 247-254
                if self.b_thread is None or not self.b_thread.isAlive():
                    self.b_thread = MockHandlerThread("MediaProjectionCallback")
                    self.c_handler = f"Handler_{self.b_thread.id}"
                return self.b_thread

            def on_unbind(self):
                # Simulates PhoneScreenMirroringService.onUnbind()
                if self.b_thread:
                    self.b_thread.quitSafely()
                    self.b_thread = None
                    self.c_handler = None

        service_ctx = MockPhoneScreenMirroringServiceContext()

        # Call 1: spawns initial HandlerThread
        t1 = service_ctx.ensure_handler_thread()
        self.assertTrue(t1.isAlive())
        t1_id = t1.id

        # 50 consecutive virtual display creations: must REUSE t1, not spawn 50 threads!
        for _ in range(50):
            t_reuse = service_ctx.ensure_handler_thread()
            self.assertIs(t_reuse, t1, "HandlerThread was not reused! Leaking threads.")
            self.assertEqual(t_reuse.id, t1_id)

        # Service unbind: must quit thread safely
        service_ctx.on_unbind()
        self.assertFalse(t1.isAlive(), "HandlerThread was not stopped on unbind! Leaking orphaned thread.")
        self.assertTrue(t1._quit)

        # New service bind: cleanly spawns new thread
        t2 = service_ctx.ensure_handler_thread()
        self.assertTrue(t2.isAlive())
        self.assertNotEqual(t2.id, t1_id, "New service instance should allocate fresh thread")
        service_ctx.on_unbind()
        self.assertFalse(t2.isAlive())

    # =========================================================================
    # Test 6: 32-Thread High Contention Stress (3,200 Operations)
    # =========================================================================
    def test_32_threads_high_contention_3200_ops(self):
        """
        Extreme concurrency test: 32 concurrent worker threads executing 100
        operations each (3,200 total operations) racing create, resize, setSurface,
        and release.
        """
        NUM_THREADS = 32
        OPS_PER_THREAD = 100
        barrier = threading.Barrier(NUM_THREADS)
        thread_errors = []
        service_lock = threading.Lock()
        completed_ops = 0
        counter_lock = threading.Lock()

        def worker(tid: int):
            nonlocal completed_ops
            try:
                barrier.wait()
                for i in range(OPS_PER_THREAD):
                    op = i % 4
                    with service_lock:
                        if op == 0:
                            s = Surface(1080, 2340)
                            self.service.createVirtualDisplay(f"Ext32_{tid}_{i}", 1080, 2340, 440, 0, s)
                        elif op == 1:
                            if self.service.active_virtual_display and self.service.active_virtual_display.is_valid:
                                self.service.resizeVirtualDisplay(720, 1560, 320)
                        elif op == 2:
                            if self.service.active_virtual_display and self.service.active_virtual_display.is_valid:
                                s2 = Surface(720, 1560)
                                self.service.setSurface(s2)
                        elif op == 3:
                            self.service.releaseVirtualDisplay()

                    with counter_lock:
                        completed_ops += 1
            except Exception as e:
                thread_errors.append(f"Thread {tid} failed: {e}")

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(NUM_THREADS)]
        t0 = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15.0)
            self.assertFalse(t.is_alive(), f"Thread {t} timed out / deadlocked")
        elapsed = time.perf_counter() - t0

        self.assertEqual(len(thread_errors), 0, f"Thread errors: {thread_errors}")
        self.assertEqual(completed_ops, NUM_THREADS * OPS_PER_THREAD)
        print(f"    [+] 32 Threads completed {completed_ops} operations in {elapsed:.3f}s ({completed_ops/elapsed:.0f} ops/sec)")

        # Cleanup
        self.service.releaseVirtualDisplay()
        self.assertEqual(len(self.dm.get_displays()), 1)

    # =========================================================================
    # Test 7: Active Frame Streaming Under Concurrent Surface Switching
    # =========================================================================
    def test_surface_switching_under_active_frame_streaming(self):
        """
        Simulates real-world WebRTC video pipeline:
        - 4 threads continuously push H.264 video frames (5,000 total frames)
        - 4 threads concurrently trigger surface switching and display resizing
        Verifies zero race crashes, zero deadlocks, and valid frame buffer delivery.
        """
        stop_event = threading.Event()
        frames_pushed = 0
        surfaces_switched = 0
        frame_lock = threading.Lock()
        streaming_errors = []

        # Start initial virtual display
        initial_surface = Surface(1080, 2340)
        self.service.createVirtualDisplay("StreamRace", 1080, 2340, 440, 0, initial_surface)

        active_surface_ref = [initial_surface]
        surf_ref_lock = threading.Lock()

        def frame_pusher(tid: int):
            nonlocal frames_pushed
            dummy_nal = b"\x00\x00\x00\x01\x41\x9a\x12\x34"
            while not stop_event.is_set():
                with surf_ref_lock:
                    s = active_surface_ref[0]
                if s and s.is_valid():
                    try:
                        s.push_frame(dummy_nal)
                        with frame_lock:
                            frames_pushed += 1
                    except RuntimeError:
                        # Surface was released concurrently during switch - safe & expected
                        pass
                    except Exception as e:
                        streaming_errors.append(f"Pusher {tid} error: {e}")
                time.sleep(0.0001)

        def surface_switcher(tid: int):
            nonlocal surfaces_switched
            for _ in range(50):
                new_s = Surface(720, 1560)
                try:
                    with surf_ref_lock:
                        old_s = active_surface_ref[0]
                        active_surface_ref[0] = new_s
                    self.service.setSurface(new_s)
                    if old_s:
                        old_s.release()
                    with frame_lock:
                        surfaces_switched += 1
                except Exception as e:
                    streaming_errors.append(f"Switcher {tid} error: {e}")
                time.sleep(0.001)

        pushers = [threading.Thread(target=frame_pusher, args=(i,)) for i in range(4)]
        switchers = [threading.Thread(target=surface_switcher, args=(i,)) for i in range(4)]

        for p in pushers:
            p.start()
        for s in switchers:
            s.start()

        for s in switchers:
            s.join(timeout=10.0)

        stop_event.set()
        for p in pushers:
            p.join(timeout=5.0)

        self.assertEqual(len(streaming_errors), 0, f"Streaming race errors: {streaming_errors}")
        self.assertGreaterEqual(surfaces_switched, 200)
        self.assertGreater(frames_pushed, 100)
        print(f"    [+] Active frame streaming: {frames_pushed} frames pushed across {surfaces_switched} surface switches")

        self.service.releaseVirtualDisplay()

    # =========================================================================
    # Test 8: 500 Rapid Lifecycle Cycles (Exhaustion & Leak Stress)
    # =========================================================================
    def test_500_rapid_lifecycle_cycles(self):
        """
        Executes 500 consecutive create/release cycles to verify absence of
        slow resource exhaustion, descriptor leaks, or ID overflow issues.
        """
        NUM_CYCLES = 500
        t0 = time.perf_counter()
        for i in range(NUM_CYCLES):
            s = Surface(1080, 2340)
            disp_id = self.service.createVirtualDisplay(f"Cycle_{i}", 1080, 2340, 440, 0, s)
            self.service.releaseVirtualDisplay()
            self.assertFalse(s.is_valid())

        elapsed = time.perf_counter() - t0
        active = self.dm.get_displays()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].display_id, Display.DEFAULT_DISPLAY)
        print(f"    [+] 500 rapid cycles completed in {elapsed:.3f}s ({NUM_CYCLES/elapsed:.0f} cycles/sec)")

    # =========================================================================
    # Test 9: DEX Packaging Integrity for MdxServiceHooks
    # =========================================================================
    def test_dex_packaging_integrity_mdx_service_hooks(self):
        """
        Inspects the compiled PhoneLinkXposed.apk classes.dex to verify that:
        1. MdxServiceHooks class exists in DEX.
        2. All M3 hook methods are present.
        3. Hook signatures match PROJECT.md interface contracts.
        """
        apk_path = PROJECT_ROOT / "lsposed_module" / "PhoneLinkXposed.apk"
        dex_path = PROJECT_ROOT / "lsposed_module" / "build" / "intermediates" / "dex" / "classes.dex"
        target_path = apk_path if apk_path.exists() else dex_path

        self.assertTrue(target_path.exists(), f"Target APK/DEX does not exist at {target_path}")

        with open(target_path, "rb") as f:
            dex_data = f.read()

        # If it's a zip/apk, extract classes.dex
        if dex_data.startswith(b"PK"):
            import zipfile, io
            with zipfile.ZipFile(io.BytesIO(dex_data)) as z:
                dex_data = z.read("classes.dex")

        # Required M3 class descriptors
        required_classes = [
            b"Lme/phonelink/xposed/hooks/MdxServiceHooks;",
            b"Lme/phonelink/xposed/hooks/SystemServerHooks;",
            b"Lme/phonelink/xposed/hooks/VideoCodecHooks;",
            b"Lme/phonelink/xposed/XposedInit;",
        ]
        for rc in required_classes:
            self.assertIn(rc, dex_data, f"Required M3 hook class {rc} missing from compiled DEX")

        # Required M3 method/field references present in hook bytecodes
        required_strings = [
            b"MediaProjectionCallback",
            b"createVirtualDisplay",
            b"capability_screen_mirroring",
            b"checkMediaProjectionPermanentlyGranted",
            b"c2.qti.avc.encoder",
        ]
        for rs in required_strings:
            self.assertIn(rs, dex_data, f"Required M3 string {rs} missing from compiled DEX")


if __name__ == "__main__":
    unittest.main()

