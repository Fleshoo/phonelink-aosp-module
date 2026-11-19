package me.phonelink.xposed.hooks;

import android.hardware.input.InputManager;
import android.os.SystemClock;
import android.view.InputEvent;
import android.view.KeyEvent;
import android.view.MotionEvent;
import de.robv.android.xposed.XC_MethodReplacement;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;
import me.phonelink.xposed.utils.XposedLog;

import java.lang.reflect.Method;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * InputInjectionHooks: Intercepts and redirects input injection in com.samsung.android.mdx
 * for Milestone M4/M5 (Features 9, 10, 11).
 *
 * 1. Hooks SemInputInjector.injectMotionEvent:
 *    - Thread-safe, per-display stateful tracking of mouse button states across ACTION_DOWN / ACTION_UP.
 *    - Translates mouse right-click (BUTTON_SECONDARY) -> KEYCODE_BACK (clean DOWN and UP pair).
 *    - Translates mouse middle-click (BUTTON_TERTIARY) -> KEYCODE_HOME (clean DOWN and UP pair).
 *    - Suppresses orphan touch ACTION_UP and drag events during right/middle clicks.
 *    - Forwards touch/mouse events to standard AOSP InputManager.injectInputEvent with displayId.
 *
 * 2. Hooks SemInputInjector.injectKeyEvent:
 *    - Validates null safety.
 *    - Sets displayId on the KeyEvent.
 *    - Forwards key events to standard AOSP InputManager.injectInputEvent.
 *
 * 3. Hooks InputInjectorManagerImpl.changeMotionEventSource:
 *    - Returns unmodified MotionEvent to eliminate fatal MotionEvent.semObtain calls.
 */
public class InputInjectionHooks {
    private static final String TAG = "PhoneLink-InputInjectionHooks";

    // Action constants for compatibility
    private static final int ACTION_MASK = 0xff;
    private static final int ACTION_BUTTON_PRESS = 11;
    private static final int ACTION_BUTTON_RELEASE = 12;

    // Per-display bitmask of currently pressed mouse buttons:
    // Bit 1 (0x02) = BUTTON_SECONDARY (Right Click -> KEYCODE_BACK)
    // Bit 2 (0x04) = BUTTON_TERTIARY  (Middle Click -> KEYCODE_HOME)
    private static final ConcurrentHashMap<Integer, AtomicInteger> sDisplayButtonState = new ConcurrentHashMap<>();

    private static AtomicInteger getButtonStateForDisplay(int displayId) {
        AtomicInteger state = sDisplayButtonState.get(displayId);
        if (state == null) {
            state = new AtomicInteger(0);
            AtomicInteger existing = sDisplayButtonState.putIfAbsent(displayId, state);
            if (existing != null) {
                state = existing;
            }
        }
        return state;
    }

    public static void onDisplayRemoved(int displayId) {
        sDisplayButtonState.remove(displayId);
        XposedLog.d(TAG, "Removed button state tracking for displayId: " + displayId);
    }

    private static int getActionButtonSafe(MotionEvent event) {
        try {
            return event.getActionButton();
        } catch (Throwable t) {
            try {
                return (Integer) XposedHelpers.callMethod(event, "getActionButton");
            } catch (Throwable ignored) {
                return 0;
            }
        }
    }

    public static void init(XC_LoadPackage.LoadPackageParam lpparam) {
        if (!"com.samsung.android.mdx".equals(lpparam.packageName)) {
            return;
        }

        XposedLog.i(TAG, "Initializing InputInjectionHooks in process: " + lpparam.processName);
        ClassLoader cl = lpparam.classLoader;

        hookSemInputInjector(cl);
        hookInputInjectorManagerImpl(cl);
    }

    private static void hookSemInputInjector(ClassLoader cl) {
        Class<?> semInjectorClass;
        try {
            semInjectorClass = XposedHelpers.findClass(
                "com.samsung.android.mdx.windowslink.system.impl.SemInputInjector", cl
            );
        } catch (Throwable t) {
            XposedLog.w(TAG, "Could not find SemInputInjector: " + t.getMessage());
            return;
        }

        // 1. Replace injectMotionEvent(MotionEvent event, int mode, int displayId)
        try {
            XposedHelpers.findAndHookMethod(
                semInjectorClass,
                "injectMotionEvent",
                MotionEvent.class,
                int.class,
                int.class,
                new XC_MethodReplacement() {
                    @Override
                    protected Object replaceHookedMethod(MethodHookParam param) {
                        MotionEvent event = (MotionEvent) param.args[0];
                        if (event == null) {
                            return null;
                        }
                        int mode = (Integer) param.args[1];
                        int displayId = (Integer) param.args[2];

                        int rawAction = event.getAction();
                        int actionMasked = rawAction & ACTION_MASK;
                        int buttonState = event.getButtonState();
                        int actionButton = getActionButtonSafe(event);

                        AtomicInteger pressedMask = getButtonStateForDisplay(displayId);
                        int currentPressed = pressedMask.get();

                        // -----------------------------------------------------------------
                        // 1. Secondary Button (Right-Click -> KEYCODE_BACK) Handling
                        // -----------------------------------------------------------------
                        boolean isSecondaryDown = (actionMasked == MotionEvent.ACTION_DOWN || actionMasked == ACTION_BUTTON_PRESS)
                                && ((buttonState & MotionEvent.BUTTON_SECONDARY) != 0 || actionButton == MotionEvent.BUTTON_SECONDARY);

                        boolean wasSecondaryPressed = (currentPressed & MotionEvent.BUTTON_SECONDARY) != 0;

                        boolean isSecondaryUp = wasSecondaryPressed && (
                                actionMasked == MotionEvent.ACTION_UP ||
                                actionMasked == MotionEvent.ACTION_CANCEL ||
                                (actionMasked == ACTION_BUTTON_RELEASE && (actionButton == MotionEvent.BUTTON_SECONDARY || actionButton == 0)) ||
                                ((buttonState & MotionEvent.BUTTON_SECONDARY) == 0 && actionMasked != MotionEvent.ACTION_MOVE)
                        );

                        if (isSecondaryDown) {
                            pressedMask.updateAndGet(s -> s | MotionEvent.BUTTON_SECONDARY);
                            injectKeyEventInternal(param.thisObject, KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_BACK, mode, displayId);
                            return null;
                        }

                        if (isSecondaryUp) {
                            pressedMask.updateAndGet(s -> s & ~MotionEvent.BUTTON_SECONDARY);
                            injectKeyEventInternal(param.thisObject, KeyEvent.ACTION_UP, KeyEvent.KEYCODE_BACK, mode, displayId);
                        }

                        // -----------------------------------------------------------------
                        // 2. Tertiary Button (Middle-Click -> KEYCODE_HOME) Handling
                        // -----------------------------------------------------------------
                        boolean isTertiaryDown = (actionMasked == MotionEvent.ACTION_DOWN || actionMasked == ACTION_BUTTON_PRESS)
                                && ((buttonState & MotionEvent.BUTTON_TERTIARY) != 0 || actionButton == MotionEvent.BUTTON_TERTIARY);

                        boolean wasTertiaryPressed = (currentPressed & MotionEvent.BUTTON_TERTIARY) != 0;

                        boolean isTertiaryUp = wasTertiaryPressed && (
                                actionMasked == MotionEvent.ACTION_UP ||
                                actionMasked == MotionEvent.ACTION_CANCEL ||
                                (actionMasked == ACTION_BUTTON_RELEASE && (actionButton == MotionEvent.BUTTON_TERTIARY || actionButton == 0)) ||
                                ((buttonState & MotionEvent.BUTTON_TERTIARY) == 0 && actionMasked != MotionEvent.ACTION_MOVE)
                        );

                        if (isTertiaryDown) {
                            pressedMask.updateAndGet(s -> s | MotionEvent.BUTTON_TERTIARY);
                            injectKeyEventInternal(param.thisObject, KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_HOME, mode, displayId);
                            return null;
                        }

                        if (isTertiaryUp) {
                            pressedMask.updateAndGet(s -> s & ~MotionEvent.BUTTON_TERTIARY);
                            injectKeyEventInternal(param.thisObject, KeyEvent.ACTION_UP, KeyEvent.KEYCODE_HOME, mode, displayId);
                        }

                        if (isSecondaryUp || isTertiaryUp) {
                            return null;
                        }

                        if ((wasSecondaryPressed || wasTertiaryPressed) && actionMasked == MotionEvent.ACTION_MOVE) {
                            // Suppress touch move during right-click or middle-click drag
                            return null;
                        }

                        // -----------------------------------------------------------------
                        // 3. Standard Touch & Mouse Motion Injection
                        // -----------------------------------------------------------------
                        injectEventInternal(param.thisObject, event, mode, displayId);
                        return null;
                    }
                }
            );
            XposedLog.i(TAG, "Successfully hooked SemInputInjector.injectMotionEvent");
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook SemInputInjector.injectMotionEvent: " + t.getMessage());
        }

        // 2. Replace injectKeyEvent(KeyEvent event, int mode, int displayId)
        try {
            XposedHelpers.findAndHookMethod(
                semInjectorClass,
                "injectKeyEvent",
                KeyEvent.class,
                int.class,
                int.class,
                new XC_MethodReplacement() {
                    @Override
                    protected Object replaceHookedMethod(MethodHookParam param) {
                        KeyEvent event = (KeyEvent) param.args[0];
                        if (event == null) {
                            return null;
                        }
                        int mode = (Integer) param.args[1];
                        int displayId = (Integer) param.args[2];

                        injectEventInternal(param.thisObject, event, mode, displayId);
                        return null;
                    }
                }
            );
            XposedLog.i(TAG, "Successfully hooked SemInputInjector.injectKeyEvent");
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook SemInputInjector.injectKeyEvent: " + t.getMessage());
        }
    }

    private static void hookInputInjectorManagerImpl(ClassLoader cl) {
        Class<?> implClass;
        try {
            implClass = XposedHelpers.findClass(
                "com.samsung.android.mdx.windowslink.system.impl.InputInjectorManagerImpl", cl
            );
        } catch (Throwable t) {
            XposedLog.w(TAG, "Could not find InputInjectorManagerImpl: " + t.getMessage());
            return;
        }

        // Replace changeMotionEventSource(int, MotionEvent, boolean) -> return original MotionEvent
        try {
            XposedHelpers.findAndHookMethod(
                implClass,
                "changeMotionEventSource",
                int.class,
                MotionEvent.class,
                boolean.class,
                new XC_MethodReplacement() {
                    @Override
                    protected Object replaceHookedMethod(MethodHookParam param) {
                        // Return unmodified MotionEvent to eliminate fatal MotionEvent.semObtain calls
                        return param.args[1];
                    }
                }
            );
            XposedLog.i(TAG, "Successfully hooked InputInjectorManagerImpl.changeMotionEventSource");
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook InputInjectorManagerImpl.changeMotionEventSource: " + t.getMessage());
        }
    }

    private static void injectKeyEventInternal(Object injectorInstance, int action, int keyCode, int mode, int displayId) {
        long now = SystemClock.uptimeMillis();
        KeyEvent keyEvent = new KeyEvent(now, now, action, keyCode, 0);
        injectEventInternal(injectorInstance, keyEvent, mode, displayId);
    }

    private static void injectEventInternal(Object injectorInstance, InputEvent event, int mode, int displayId) {
        if (event == null) {
            return;
        }

        try {
            // Set displayId on event via reflection / hidden API
            try {
                XposedHelpers.callMethod(event, "setDisplayId", displayId);
            } catch (Throwable ignored) {}

            InputManager im = null;
            if (injectorInstance != null) {
                try {
                    im = (InputManager) XposedHelpers.getObjectField(injectorInstance, "mInputManager");
                } catch (Throwable ignored) {}
            }

            if (im != null) {
                XposedHelpers.callMethod(im, "injectInputEvent", event, mode);
            } else {
                // Fallback: obtain InputManager via getInstance()
                try {
                    Method m = InputManager.class.getMethod("getInstance");
                    im = (InputManager) m.invoke(null);
                    if (im != null) {
                        XposedHelpers.callMethod(im, "injectInputEvent", event, mode);
                    }
                } catch (Throwable t) {
                    XposedLog.w(TAG, "InputManager fallback injection failed: " + t.getMessage());
                }
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Error injecting event: " + t.getMessage());
        }
    }
}
