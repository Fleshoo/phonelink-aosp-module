package me.phonelink.xposed.hooks;

import android.app.KeyguardManager;
import android.content.Context;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.graphics.PixelFormat;
import android.media.projection.MediaProjection;
import android.os.Bundle;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.os.PowerManager;
import android.os.Process;
import android.os.SystemClock;
import android.view.Surface;
import android.view.WindowManager;

import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XC_MethodReplacement;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;
import java.lang.reflect.Constructor;
import me.phonelink.xposed.utils.XposedLog;

/**
 * Milestone 3: VirtualDisplay Lifecycle, MediaProjection & Surface Hooks for Samsung MDX.
 * Bridges Samsung Phone Screen mirroring pipeline to standard AOSP Android 16 DisplayManager.
 */
public class MdxServiceHooks {

    private static final String TAG = "PhoneLink-MdxService";

    public static void init(XC_LoadPackage.LoadPackageParam lpparam) {
        if (!"com.samsung.android.mdx".equals(lpparam.packageName)) {
            return;
        }
        hook(lpparam);
    }

    public static void hook(XC_LoadPackage.LoadPackageParam lpparam) {
        ClassLoader cl = lpparam.classLoader;

        hookCallerSignatureChecker(cl);
        hookBaseContentProvider(cl);
        hookCompanionDeviceAppStreamingRole(cl);
        hookMediaProjectionController(cl);
        hookVirtualDisplayLifecycle(cl);
        hookCapabilityContentProvider(cl);
        hookCompanionDevicePermissionProvider(cl);
        hookKeyguardChecker(cl);
        hookSemWindowManager(cl);
        hookDisplayManagerWifiStatus(cl);
        hookPowerManagerWakeUp(cl);
        hookPreviewModeAndTasks(cl);
        hookPresentationScreenWakeHolder(cl);
        hookBlackScreenLayoutParams(cl);
        hookOtherOverlayLayoutParams(cl);
        hookRemoteAppModeManagerAndTaskInfo(cl);
        hookBlackScreenNotificationService(cl);
        hookBlackScreenMediaView(cl);
        hookBlackScreenOverlayAndDrawables(cl);
        hookSemLockNowAndAudio(cl);
        hookAppExecutionContainerService(cl);
    }

    /**
     * 1. Bypass ServiceCallerChecker (M0.b, P0.b)
     */
    private static void hookCallerSignatureChecker(ClassLoader cl) {
        try {
            Class<?> m0bClass = findClassSafe(cl, "M0.b", "LM0.b");
            if (m0bClass != null) {
                XposedBridge.hookAllMethods(m0bClass, "checkValidCallerBySignature", XC_MethodReplacement.returnConstant(Boolean.TRUE));
                XposedLog.i(TAG, "Hooked M0.b checkValidCallerBySignature -> true");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook M0.b checkValidCallerBySignature: " + t.getMessage());
        }

        try {
            Class<?> p0bClass = findClassSafe(cl, "P0.b", "LP0.b");
            if (p0bClass != null) {
                XposedBridge.hookAllMethods(p0bClass, "checkSignature", XC_MethodReplacement.returnConstant(Boolean.TRUE));
                XposedLog.i(TAG, "Hooked P0.b checkSignature -> true");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook P0.b checkSignature: " + t.getMessage());
        }
    }

    private static void hookBaseContentProvider(ClassLoader cl) {
        try {
            Class<?> l0aClass = findClassSafe(cl, "L0.a", "LL0.a");
            if (l0aClass != null) {
                XposedBridge.hookAllMethods(l0aClass, "checkCallerAvailable", XC_MethodReplacement.returnConstant(Boolean.TRUE));
                XposedLog.i(TAG, "Hooked L0.a checkCallerAvailable -> true");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook L0.a checkCallerAvailable: " + t.getMessage());
        }

        try {
            Class<?> l0bClass = findClassSafe(cl, "L0.b", "LL0.b");
            if (l0bClass != null) {
                XposedBridge.hookAllMethods(l0bClass, "isAvailableCaller", XC_MethodReplacement.returnConstant(Boolean.TRUE));
                XposedLog.i(TAG, "Hooked L0.b isAvailableCaller -> true");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook L0.b isAvailableCaller: " + t.getMessage());
        }
    }

    /**
     * 2. Bypass Companion Device App Streaming role checks (W0.c / LW0.c)
     * isSupported(Context) -> true
     * isCDASAssociated(Context) -> true
     * disassociate(Context) -> no-op
     */
    private static void hookCompanionDeviceAppStreamingRole(ClassLoader cl) {
        try {
            Class<?> w0cClass = findClassSafe(cl, "W0.c", "LW0.c");
            if (w0cClass != null) {
                XposedHelpers.findAndHookMethod(w0cClass, "isSupported", Context.class, new XC_MethodReplacement() {
                    @Override
                    protected Object replaceHookedMethod(MethodHookParam param) {
                        return true;
                    }
                });

                XposedHelpers.findAndHookMethod(w0cClass, "isCDASAssociated", Context.class, new XC_MethodReplacement() {
                    @Override
                    protected Object replaceHookedMethod(MethodHookParam param) {
                        return true;
                    }
                });

                try {
                    XposedHelpers.findAndHookMethod(w0cClass, "disassociate", Context.class, new XC_MethodReplacement() {
                        @Override
                        protected Object replaceHookedMethod(MethodHookParam param) {
                            return null;
                        }
                    });
                } catch (Throwable ignored) {}

                XposedLog.i(TAG, "Hooked W0.c isSupported & isCDASAssociated -> true");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook W0.c CDAS checks: " + t.getMessage());
        }
    }

    /**
     * 3. Intercept W0.p MediaProjectionController
     * isPermanentlyGranted(Context) -> true
     * initMediaProjection(Context) -> sets b and e=true (eliminates semGetMediaProjection NoSuchMethodError)
     * grantMediaProjection(Context, callback) -> onGranted(true)
     */
    private static void hookMediaProjectionController(final ClassLoader cl) {
        try {
            Class<?> w0pClass = findClassSafe(cl, "W0.p", "LW0.p");
            if (w0pClass != null) {
                XposedHelpers.findAndHookMethod(w0pClass, "isPermanentlyGranted", Context.class, new XC_MethodReplacement() {
                    @Override
                    protected Object replaceHookedMethod(MethodHookParam param) {
                        return true;
                    }
                });

                XposedHelpers.findAndHookMethod(w0pClass, "initMediaProjection", Context.class, new XC_MethodReplacement() {
                    @Override
                    protected Object replaceHookedMethod(MethodHookParam param) {
                        Context context = (Context) param.args[0];
                        XposedLog.d(TAG, "W0.p.initMediaProjection intercepted -> ensuring active projection state");
                        try {
                            XposedHelpers.setBooleanField(param.thisObject, "e", true);

                            // Attempt to populate W0.p.b with an authentic MediaProjection token if possible
                            Class<?> smClass = XposedHelpers.findClass("android.os.ServiceManager", cl);
                            IBinder binder = (IBinder) XposedHelpers.callStaticMethod(smClass, "getService", Context.MEDIA_PROJECTION_SERVICE);
                            if (binder != null) {
                                Class<?> stubClass = XposedHelpers.findClass("android.media.projection.IMediaProjectionManager$Stub", cl);
                                Object projectionService = XposedHelpers.callStaticMethod(stubClass, "asInterface", binder);
                                int uid = Process.myUid();
                                String pkg = context != null ? context.getPackageName() : "com.samsung.android.mdx";
                                Object iMediaProjection = XposedHelpers.callMethod(
                                    projectionService, "createProjection", uid, pkg, 0, true, 0
                                );
                                if (iMediaProjection != null) {
                                    Class<?> iMediaProjClass = XposedHelpers.findClass("android.media.projection.IMediaProjection", cl);
                                    Constructor<?> ctor = MediaProjection.class.getDeclaredConstructor(Context.class, iMediaProjClass);
                                    ctor.setAccessible(true);
                                    MediaProjection projection = (MediaProjection) ctor.newInstance(context, iMediaProjection);
                                    XposedHelpers.setObjectField(param.thisObject, "b", projection);
                                    XposedLog.i(TAG, "Successfully injected authentic MediaProjection into W0.p.b");
                                }
                            }
                        } catch (Throwable t) {
                            XposedLog.w(TAG, "W0.p.initMediaProjection failed: " + t + " cause=" + t.getCause());
                            XposedBridge.log(t);
                        }
                        return null;
                    }
                });

                // grantMediaProjection(Context, Object callback) -> notify onGranted(true)
                try {
                    Class<?> callbackClass = findClassSafe(cl, "W0.o", "LW0.o");
                    if (callbackClass != null) {
                        XposedHelpers.findAndHookMethod(w0pClass, "grantMediaProjection", Context.class, callbackClass, new XC_MethodReplacement() {
                            @Override
                            protected Object replaceHookedMethod(MethodHookParam param) {
                                Object cb = param.args[1];
                                XposedHelpers.setBooleanField(param.thisObject, "e", true);
                                if (cb != null) {
                                    try {
                                        XposedHelpers.callMethod(cb, "onGranted", true);
                                    } catch (Throwable t) {
                                        XposedLog.w(TAG, "Failed to invoke onGranted: " + t.getMessage());
                                    }
                                }
                                return null;
                            }
                        });
                    }
                } catch (Throwable ignored) {}

                XposedLog.i(TAG, "Hooked W0.p MediaProjectionController methods");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook W0.p: " + t.getMessage());
        }
    }

    /**
     * 4. VirtualDisplay Lifecycle Bridge in W0.t (LW0.t)
     * createVirtualDisplay(String, int, int, int, int, Surface, W0.m) -> delegates directly to DisplayManager
     */
    private static void hookVirtualDisplayLifecycle(final ClassLoader cl) {
        try {
            Class<?> w0tClass = findClassSafe(cl, "W0.t", "LW0.t");
            if (w0tClass != null) {
                Class<?> cbClass = findClassSafe(cl, "W0.m", "LW0.m");

                XposedHelpers.findAndHookMethod(
                    w0tClass,
                    "createVirtualDisplay",
                    String.class,
                    int.class,
                    int.class,
                    int.class,
                    int.class,
                    Surface.class,
                    cbClass != null ? cbClass : Object.class,
                    new XC_MethodReplacement() {
                        @Override
                        protected Object replaceHookedMethod(MethodHookParam param) throws Throwable {
                            Object thiz = param.thisObject;
                            Object service = XposedHelpers.getObjectField(thiz, "b");
                            Context context = (Context) service;

                            String name = (String) param.args[0];
                            int width = (Integer) param.args[1];
                            int height = (Integer) param.args[2];
                            int densityDpi = (Integer) param.args[3];
                            int flags = (Integer) param.args[4];
                            Surface argSurface = (Surface) param.args[5];
                            final Object clientCallback = param.args[6];
                            Surface cachedSurface = (Surface) XposedHelpers.getObjectField(service, "e");
                            Surface surface = argSurface != null ? argSurface : cachedSurface;

                            XposedLog.i(TAG, "createVirtualDisplay requested: " + name + " " + width + "x" + height + " @" + densityDpi + "dpi surface=" + surface);

                            // 1. Release any existing VirtualDisplay
                            VirtualDisplay existingVd = (VirtualDisplay) XposedHelpers.getObjectField(service, "d");
                            if (existingVd != null) {
                                try {
                                    if (existingVd.getDisplay() != null) {
                                        InputInjectionHooks.onDisplayRemoved(existingVd.getDisplay().getDisplayId());
                                    }
                                    existingVd.release();
                                } catch (Throwable t) {
                                    XposedLog.w(TAG, "Error releasing previous VirtualDisplay: " + t.getMessage());
                                }
                                XposedHelpers.setObjectField(service, "d", null);
                            }

                            // 2. Ensure background HandlerThread exists
                            HandlerThread thread = (HandlerThread) XposedHelpers.getObjectField(service, "b");
                            if (thread == null || !thread.isAlive()) {
                                thread = new HandlerThread("MediaProjectionCallback");
                                thread.start();
                                XposedHelpers.setObjectField(service, "b", thread);
                                Handler handler = new Handler(thread.getLooper());
                                XposedHelpers.setObjectField(service, "c", handler);
                            }
                            Handler handler = (Handler) XposedHelpers.getObjectField(service, "c");

                            // 3. Store client callback and latest non-null surface on service
                            XposedHelpers.setObjectField(service, "h", clientCallback);
                            if (surface != null) {
                                XposedHelpers.setObjectField(service, "e", surface);
                            }

                            // 4. Wrap VirtualDisplay.Callback to trigger client callbacks
                            VirtualDisplay.Callback vdCallback = new VirtualDisplay.Callback() {
                                @Override
                                public void onPaused() {
                                    if (clientCallback != null) {
                                        try {
                                            XposedHelpers.callMethod(clientCallback, "onVirtualDisplayPaused");
                                        } catch (Throwable t) {
                                            XposedLog.w(TAG, "Failed client onVirtualDisplayPaused: " + t.getMessage());
                                        }
                                    }
                                }

                                @Override
                                public void onResumed() {
                                    if (clientCallback != null) {
                                        try {
                                            XposedHelpers.callMethod(clientCallback, "onVirtualDisplayResumed");
                                        } catch (Throwable t) {
                                            XposedLog.w(TAG, "Failed client onVirtualDisplayResumed: " + t.getMessage());
                                        }
                                    }
                                }

                                @Override
                                public void onStopped() {
                                    try {
                                        VirtualDisplay curVd = (VirtualDisplay) XposedHelpers.getObjectField(service, "d");
                                        if (curVd != null && curVd.getDisplay() != null) {
                                            InputInjectionHooks.onDisplayRemoved(curVd.getDisplay().getDisplayId());
                                        }
                                    } catch (Throwable ignored) {}
                                    if (clientCallback != null) {
                                        try {
                                            XposedHelpers.callMethod(clientCallback, "onVirtualDisplayStopped");
                                        } catch (Throwable t) {
                                            XposedLog.w(TAG, "Failed client onVirtualDisplayStopped: " + t.getMessage());
                                        }
                                    }
                                }
                            };

                            // 5. Allocate VirtualDisplay via authentic MediaProjection token
                            VirtualDisplay vd = null;
                            try {
                                Class<?> w0pClass = findClassSafe(cl, "W0.p", "LW0.p");
                                if (w0pClass != null) {
                                    Object pInstance = XposedHelpers.callStaticMethod(w0pClass, "getInstance");
                                    if (pInstance != null) {
                                        MediaProjection projection = (MediaProjection) XposedHelpers.callMethod(pInstance, "getMediaProjection");
                                        if (projection == null) {
                                            projection = (MediaProjection) XposedHelpers.getObjectField(pInstance, "b");
                                        }
                                        if (projection == null) {
                                            XposedHelpers.callMethod(pInstance, "initMediaProjection", context);
                                            projection = (MediaProjection) XposedHelpers.callMethod(pInstance, "getMediaProjection");
                                            if (projection == null) {
                                                projection = (MediaProjection) XposedHelpers.getObjectField(pInstance, "b");
                                            }
                                        }
                                        MediaProjection.Callback mpCb = null;
                                        try {
                                            mpCb = (MediaProjection.Callback) XposedHelpers.getObjectField(thiz, "a");
                                        } catch (Throwable ignored) {}
                                        if (mpCb == null) {
                                            mpCb = new MediaProjection.Callback() {};
                                        }

                                        if (projection != null) {
                                            int mpFlags = DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR | DisplayManager.VIRTUAL_DISPLAY_FLAG_PUBLIC;
                                            try {
                                                projection.registerCallback(mpCb, handler);
                                                XposedLog.i(TAG, "Creating VirtualDisplay via authentic MediaProjection token");
                                                vd = projection.createVirtualDisplay(
                                                    name, width, height, densityDpi, mpFlags, surface, vdCallback, handler
                                                );
                                            } catch (Throwable firstTryErr) {
                                                XposedLog.w(TAG, "First createVirtualDisplay attempt failed (" + firstTryErr.getMessage() + "), minting fresh MediaProjection token");
                                                try {
                                                    XposedHelpers.setObjectField(pInstance, "b", null);
                                                    XposedHelpers.callMethod(pInstance, "initMediaProjection", context);
                                                    MediaProjection fresh = (MediaProjection) XposedHelpers.getObjectField(pInstance, "b");
                                                    if (fresh != null) {
                                                        fresh.registerCallback(mpCb, handler);
                                                        vd = fresh.createVirtualDisplay(
                                                            name, width, height, densityDpi, mpFlags, surface, vdCallback, handler
                                                        );
                                                    }
                                                } catch (Throwable retryErr) {
                                                    XposedLog.w(TAG, "Retry MediaProjection createVirtualDisplay failed: " + retryErr + " cause=" + retryErr.getCause());
                                                    XposedBridge.log(retryErr);
                                                }
                                            }
                                        }
                                    }
                                }
                            } catch (Throwable t) {
                                XposedLog.w(TAG, "Failed creating VirtualDisplay via MediaProjection: " + t + " cause=" + t.getCause());
                                XposedBridge.log(t);
                            }

                            if (vd == null) {
                                XposedLog.i(TAG, "Fallback: Creating VirtualDisplay via DisplayManager");
                                DisplayManager dm = (DisplayManager) context.getSystemService(Context.DISPLAY_SERVICE);
                                int displayFlags = DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR | DisplayManager.VIRTUAL_DISPLAY_FLAG_PUBLIC;
                                vd = dm.createVirtualDisplay(
                                    name, width, height, densityDpi, surface, displayFlags, vdCallback, handler
                                );
                            }

                            XposedHelpers.setObjectField(service, "d", vd);
                            // Apply any Surface delivered via concurrent W0.t.setSurface while VD was initializing
                            Surface latestSurface = (Surface) XposedHelpers.getObjectField(service, "e");
                            if (vd != null && latestSurface != null && latestSurface != surface) {
                                try {
                                    boolean valid = (Boolean) XposedHelpers.callMethod(latestSurface, "isValid");
                                    if (valid) {
                                        vd.setSurface(latestSurface);
                                        XposedLog.i(TAG, "Applied concurrently set Surface to newly created VirtualDisplay");
                                    }
                                } catch (Throwable t) {
                                    XposedLog.w(TAG, "Failed applying latestSurface: " + t.getMessage());
                                }
                            }

                            // 6. Notify MirroringStateRepository
                            try {
                                Class<?> sysInjClass = findClassSafe(cl, "com.samsung.android.mdx.windowslink.system.SystemInjection");
                                if (sysInjClass != null) {
                                    Object repo = XposedHelpers.callStaticMethod(sysInjClass, "provideMirroringStateRepository");
                                    if (repo != null) {
                                        XposedHelpers.callMethod(repo, "setPhoneScreenMirroringRunning", true);
                                    }
                                }
                            } catch (Throwable t) {
                                XposedLog.w(TAG, "Failed to update MirroringStateRepository: " + t.getMessage());
                            }

                            int displayId = (vd != null && vd.getDisplay() != null) ? vd.getDisplay().getDisplayId() : 0;
                            XposedLog.i(TAG, "VirtualDisplay created successfully with displayId: " + displayId);
                            return displayId;
                        }
                    }
                );
                XposedLog.i(TAG, "Hooked W0.t.createVirtualDisplay -> DisplayManager bridge active");

                try {
                    XposedHelpers.findAndHookMethod(w0tClass, "setSurface", Surface.class, new XC_MethodHook() {
                        @Override
                        protected void afterHookedMethod(MethodHookParam param) {
                            try {
                                Object svc = XposedHelpers.getObjectField(param.thisObject, "b");
                                Object vdObj = svc != null ? XposedHelpers.getObjectField(svc, "d") : null;
                                Surface s = (Surface) param.args[0];
                                Object isValidObj = s != null ? XposedHelpers.callMethod(s, "isValid") : null;
                                XposedLog.i(TAG, "W0.t.setSurface(surface=" + s + " valid=" + isValidObj + ") -> result=" + param.getResult() + ", vd=" + vdObj);
                            } catch (Throwable ignored) {}
                        }
                    });
                } catch (Throwable ignored) {}

                try {
                    XposedHelpers.findAndHookMethod(w0tClass, "releaseVirtualDisplay", new XC_MethodHook() {
                        @Override
                        protected void beforeHookedMethod(MethodHookParam param) {
                            try {
                                Object service = XposedHelpers.getObjectField(param.thisObject, "b");
                                if (service != null) {
                                    VirtualDisplay curVd = (VirtualDisplay) XposedHelpers.getObjectField(service, "d");
                                    if (curVd != null && curVd.getDisplay() != null) {
                                        InputInjectionHooks.onDisplayRemoved(curVd.getDisplay().getDisplayId());
                                    }
                                }
                            } catch (Throwable t) {
                                XposedLog.w(TAG, "Failed display button state cleanup in releaseVirtualDisplay: " + t.getMessage());
                            }
                        }
                    });
                } catch (Throwable ignored) {}
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook W0.t createVirtualDisplay: " + t.getMessage());
        }
    }

    /**
     * 5. CapabilityContentProvider IPC Hook
     * Intercepts call to ensure key_is_supported = true for all queried capabilities.
     */
    private static void hookCapabilityContentProvider(ClassLoader cl) {
        try {
            Class<?> providerClass = findClassSafe(
                cl,
                "com.samsung.android.mdx.windowslink.tileservice.CapabilityContentProvider"
            );
            if (providerClass != null) {
                XposedHelpers.findAndHookMethod(
                    providerClass,
                    "call",
                    String.class,
                    String.class,
                    Bundle.class,
                    new XC_MethodHook() {
                        @Override
                        protected void afterHookedMethod(MethodHookParam param) {
                            String method = (String) param.args[0];
                            Bundle result = (Bundle) param.getResult();
                            if (result == null) {
                                result = new Bundle();
                            }

                            if (method != null && method.contains("capability_black_screen_control")) {
                                result.putBoolean("key_is_supported", false);
                                result.putBoolean("capability_black_screen_control", false);
                                param.setResult(result);
                                XposedLog.d(TAG, "CapabilityContentProvider.call intercepted [" + method + "] -> key_is_supported=false");
                                return;
                            }

                            result.putBoolean("key_is_supported", true);
                            result.putBoolean("capability_input_inject", true);
                            result.putBoolean("capability_companion_device_app_streaming_role", true);
                            result.putBoolean("capability_pre_granted_permissions", true);
                            result.putBoolean("capability_screen_mirroring", true);
                            result.putString("capability_version", "2.5.0");

                            if (method != null) {
                                String subMethod = method;
                                int atIdx = method.lastIndexOf("@");
                                if (atIdx != -1) {
                                    subMethod = method.substring(atIdx + 1);
                                }
                                result.putBoolean(subMethod, true);

                                if (method.contains("capability_version_remote_app_mode_service")) {
                                    result.putInt("key_version", 1);
                                }
                            }

                            param.setResult(result);
                            XposedLog.d(TAG, "CapabilityContentProvider.call intercepted [" + method + "] -> key_is_supported=true");
                        }
                    }
                );
                XposedLog.i(TAG, "Hooked CapabilityContentProvider.call successfully");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook CapabilityContentProvider: " + t.getMessage());
        }
    }

    /**
     * 6. CompanionDevicePermissionProvider IPC Hook
     * Intercepts call for checkAssociationMade, checkMediaProjectionPermanentlyGranted, requestGrantMediaProjection
     */
    private static void hookCompanionDevicePermissionProvider(ClassLoader cl) {
        try {
            Class<?> providerClass = findClassSafe(
                cl,
                "com.samsung.android.mdx.windowslink.companiondevice.CompanionDevicePermissionProvider"
            );
            if (providerClass != null) {
                XposedHelpers.findAndHookMethod(
                    providerClass,
                    "call",
                    String.class,
                    String.class,
                    Bundle.class,
                    new XC_MethodHook() {
                        @Override
                        protected void beforeHookedMethod(MethodHookParam param) {
                            String method = (String) param.args[0];
                            if (method == null) return;
                            if (method.endsWith("checkAssociationMade") ||
                                method.endsWith("checkMediaProjectionPermanentlyGranted") ||
                                method.endsWith("requestGrantMediaProjection") ||
                                method.endsWith("requestAssociateWithCompanionDevice")) {
                                Bundle result = new Bundle();
                                result.putBoolean("keyResult", true);
                                result.putBoolean("granted", true);
                                result.putString("status", "PERMANENTLY_GRANTED");
                                param.setResult(result);

                                try {
                                    Object ctx = XposedHelpers.callMethod(param.thisObject, "getContext");
                                    if (ctx != null) {
                                        Class<?> intentClass = XposedHelpers.findClass("android.content.Intent", cl);
                                        Constructor<?> intentCtor = intentClass.getConstructor(String.class);
                                        if (method.endsWith("requestGrantMediaProjection")) {
                                            XposedLog.i(TAG, "Broadcasting ACTION_MEDIA_PROJECTION_GRANTED");
                                            Object intent = intentCtor.newInstance("com.samsung.android.mdx.windowslink.companiondevice.ACTION_MEDIA_PROJECTION_GRANTED");
                                            XposedHelpers.callMethod(intent, "putExtra", "com.samsung.android.mdx.windowslink.companiondevice.EXTRA_MEDIA_PROJECTION_PERMANENTLY_GRANTED", true);
                                            XposedHelpers.callMethod(ctx, "sendBroadcast", intent);
                                        } else if (method.endsWith("requestAssociateWithCompanionDevice")) {
                                            XposedLog.i(TAG, "Broadcasting ACTION_ASSOCIATION_SUCCESS");
                                            Object intent = intentCtor.newInstance("com.samsung.android.mdx.windowslink.companiondevice.ACTION_ASSOCIATION_SUCCESS");
                                            XposedHelpers.callMethod(ctx, "sendBroadcast", intent);
                                        }
                                    }
                                } catch (Throwable t) {
                                    XposedLog.w(TAG, "Failed sending companion device broadcast: " + t.getMessage());
                                }
                            }
                        }
                    }
                );
                XposedLog.i(TAG, "Hooked CompanionDevicePermissionProvider.call successfully");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook CompanionDevicePermissionProvider: " + t.getMessage());
        }
    }

    /**
     * 7. Eliminate semIsKeyguardShowingAndNotOccluded NoSuchMethodError
     * CompanionDevicePermissionProvider.isKeyguardLocked(Context) -> return standard isKeyguardLocked()
     */
    private static void hookKeyguardChecker(ClassLoader cl) {
        try {
            Class<?> providerClass = findClassSafe(cl, "com.samsung.android.mdx.windowslink.companiondevice.CompanionDevicePermissionProvider");
            if (providerClass != null) {
                XposedHelpers.findAndHookMethod(providerClass, "isKeyguardLocked", Context.class, new XC_MethodReplacement() {
                    @Override
                    protected Object replaceHookedMethod(MethodHookParam param) {
                        Context ctx = (Context) param.args[0];
                        if (ctx != null) {
                            KeyguardManager km = (KeyguardManager) ctx.getSystemService(Context.KEYGUARD_SERVICE);
                            if (km != null) {
                                return km.isKeyguardLocked();
                            }
                        }
                        return false;
                    }
                });
                XposedLog.i(TAG, "Hooked CompanionDevicePermissionProvider.isKeyguardLocked");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook isKeyguardLocked: " + t.getMessage());
        }

        try {
            Class<?> sysRepoClass = findClassSafe(cl, "com.samsung.android.mdx.windowslink.system.impl.SystemRepository");
            if (sysRepoClass != null) {
                // 1. Hook isKeyguardLocked(Context)
                try {
                    XposedHelpers.findAndHookMethod(sysRepoClass, "isKeyguardLocked", Context.class, new XC_MethodReplacement() {
                        @Override
                        protected Object replaceHookedMethod(MethodHookParam param) {
                            Context ctx = (Context) param.args[0];
                            if (ctx != null) {
                                try {
                                    KeyguardManager km = (KeyguardManager) ctx.getSystemService(Context.KEYGUARD_SERVICE);
                                    if (km != null) return km.isKeyguardLocked();
                                } catch (Throwable ignored) {}
                            }
                            return false;
                        }
                    });
                    XposedLog.i(TAG, "Hooked SystemRepository.isKeyguardLocked(Context)");
                } catch (Throwable ignored) {}

                // 2. Hook isKeyguardLocked() [0 args fallback]
                try {
                    XposedHelpers.findAndHookMethod(sysRepoClass, "isKeyguardLocked", new XC_MethodReplacement() {
                        @Override
                        protected Object replaceHookedMethod(MethodHookParam param) {
                            Context ctx = (Context) XposedHelpers.getObjectField(param.thisObject, "mAppContext");
                            if (ctx != null) {
                                KeyguardManager km = (KeyguardManager) ctx.getSystemService(Context.KEYGUARD_SERVICE);
                                if (km != null) {
                                    return km.isKeyguardLocked();
                                }
                            }
                            return false;
                        }
                    });
                    XposedLog.i(TAG, "Hooked SystemRepository.isKeyguardLocked (0 args)");
                } catch (Throwable ignored) {}

                // 3. Hook isDeviceLocked(Context)
                try {
                    XposedHelpers.findAndHookMethod(sysRepoClass, "isDeviceLocked", Context.class, new XC_MethodReplacement() {
                        @Override
                        protected Object replaceHookedMethod(MethodHookParam param) {
                            return false;
                        }
                    });
                    XposedLog.i(TAG, "Hooked SystemRepository.isDeviceLocked(Context)");
                } catch (Throwable ignored) {}

                // 4. Hook isDeviceLocked() [0 args fallback]
                try {
                    XposedHelpers.findAndHookMethod(sysRepoClass, "isDeviceLocked", new XC_MethodReplacement() {
                        @Override
                        protected Object replaceHookedMethod(MethodHookParam param) {
                            return false;
                        }
                    });
                } catch (Throwable ignored) {}
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook SystemRepository: " + t.getMessage());
        }

        try {
            Class<?> b1dClass = findClassSafe(cl, "b1.d", "Lb1.d");
            if (b1dClass != null) {
                XposedHelpers.findAndHookMethod(b1dClass, "isKeyguardLocked", new XC_MethodReplacement() {
                    @Override
                    protected Object replaceHookedMethod(MethodHookParam param) {
                        return false;
                    }
                });
                XposedLog.i(TAG, "Hooked b1.d.isKeyguardLocked()");
            }
        } catch (Throwable ignored) {}
    }

    /**
     * 8. Stub SemWindowManager fold and table mode methods
     */
    private static void hookSemWindowManager(ClassLoader cl) {
        try {
            Class<?> semWmClass = findClassSafe(cl, "com.samsung.android.view.SemWindowManager");
            if (semWmClass != null) {
                XposedHelpers.findAndHookMethod(semWmClass, "isFolded", new XC_MethodReplacement() {
                    @Override
                    protected Object replaceHookedMethod(MethodHookParam param) {
                        return false;
                    }
                });

                XposedHelpers.findAndHookMethod(semWmClass, "isTableMode", new XC_MethodReplacement() {
                    @Override
                    protected Object replaceHookedMethod(MethodHookParam param) {
                        return false;
                    }
                });

                XposedBridge.hookAllMethods(
                    semWmClass,
                    "requestSystemKeyEvent",
                    XC_MethodReplacement.returnConstant(Boolean.FALSE)
                );
                XposedLog.i(TAG, "Hooked SemWindowManager isFolded, isTableMode & requestSystemKeyEvent");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook SemWindowManager: " + t.getMessage());
        }

        // Also bypass PhoneScreenMirroringService.a(PhoneScreenMirroringService) which checks fold features
        try {
            Class<?> serviceClass = findClassSafe(cl, "com.samsung.android.mdx.windowslink.companiondevice.PhoneScreenMirroringService");
            if (serviceClass != null) {
                XposedHelpers.findAndHookMethod(serviceClass, "a", serviceClass, new XC_MethodReplacement() {
                    @Override
                    protected Object replaceHookedMethod(MethodHookParam param) {
                        return false; // not a foldable/flip phone
                    }
                });
                XposedLog.i(TAG, "Hooked PhoneScreenMirroringService.a (folding check bypassed)");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook PhoneScreenMirroringService.a: " + t.getMessage());
        }
    }

    /**
     * 9. Hook DisplayManager semGetWifiDisplayStatus caller (i1.d.isHotspotAvailable)
     */
    private static void hookDisplayManagerWifiStatus(ClassLoader cl) {
        try {
            Class<?> i1dClass = findClassSafe(cl, "i1.d", "Li1.d");
            if (i1dClass != null) {
                XposedHelpers.findAndHookMethod(i1dClass, "isHotspotAvailable", Context.class, new XC_MethodReplacement() {
                    @Override
                    protected Object replaceHookedMethod(MethodHookParam param) {
                        return true;
                    }
                });
                XposedLog.i(TAG, "Hooked i1.d isHotspotAvailable (bypassed semGetWifiDisplayStatus)");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook i1.d: " + t.getMessage());
        }
    }

    /**
     * 10. Hook PowerManager semWakeUp callers
     */
    private static void hookPowerManagerWakeUp(ClassLoader cl) {
        try {
            Class<?> sysRepoClass = findClassSafe(cl, "com.samsung.android.mdx.windowslink.system.impl.SystemRepository");
            if (sysRepoClass != null) {
                XposedHelpers.findAndHookMethod(sysRepoClass, "turnOnScreen", Context.class, new XC_MethodReplacement() {
                    @Override
                    protected Object replaceHookedMethod(MethodHookParam param) {
                        Context ctx = (Context) param.args[0];
                        if (ctx != null) {
                            PowerManager pm = (PowerManager) ctx.getSystemService(Context.POWER_SERVICE);
                            if (pm != null && !pm.isInteractive()) {
                                try {
                                    pm.wakeUp(SystemClock.uptimeMillis(), PowerManager.WAKE_REASON_APPLICATION, "LinkToWindows");
                                } catch (Throwable t) {
                                    XposedLog.w(TAG, "Failed to wakeUp via standard PowerManager: " + t.getMessage());
                                }
                            }
                        }
                        return null;
                    }
                });
                XposedLog.i(TAG, "Hooked SystemRepository.turnOnScreen -> PowerManager.wakeUp");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook turnOnScreen: " + t.getMessage());
        }
    }

    /**
     * 11. Hook PreviewModeContentProvider & TaskInfoManagerContentProvider
     */
    private static void hookPreviewModeAndTasks(ClassLoader cl) {
        try {
            Class<?> previewProviderClass = findClassSafe(cl, "com.samsung.android.mdx.windowslink.previewmode.PreviewModeContentProvider");
            if (previewProviderClass != null) {
                XposedHelpers.findAndHookMethod(previewProviderClass, "call", String.class, String.class, Bundle.class, new XC_MethodHook() {
                    @Override
                    protected void afterHookedMethod(MethodHookParam param) {
                        Bundle res = (Bundle) param.getResult();
                        if (res == null) {
                            res = new Bundle();
                        }
                        res.putBoolean("isPreviewModeEnabledValue", false);
                        res.putBoolean("result", true);
                        param.setResult(res);
                    }
                });
                XposedLog.i(TAG, "Hooked PreviewModeContentProvider.call");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook PreviewModeContentProvider: " + t.getMessage());
        }

        try {
            Class<?> taskInfoProviderClass = findClassSafe(
                cl,
                "com.samsung.android.mdx.windowslink.interactor.multidisplay.appsonwindows.appexecutioncontainer.TaskInfoManagerContentProvider"
            );
            if (taskInfoProviderClass != null) {
                XposedHelpers.findAndHookMethod(taskInfoProviderClass, "call", String.class, String.class, Bundle.class, new XC_MethodHook() {
                    @Override
                    protected void afterHookedMethod(MethodHookParam param) {
                        Bundle res = (Bundle) param.getResult();
                        if (res == null) {
                            res = new Bundle();
                        }
                        if (!res.containsKey("RecentAppTask")) {
                            try {
                                XposedHelpers.callMethod(res, "putParcelableArrayList", "RecentAppTask", new java.util.ArrayList());
                            } catch (Throwable ignored) {}
                        }
                        param.setResult(res);
                    }
                });
                XposedLog.i(TAG, "Hooked TaskInfoManagerContentProvider.call");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook TaskInfoManagerContentProvider: " + t.getMessage());
        }
    }

    /**
     * 12. Hook PresentationScreenWakeHolder (E0.c / LE0.c)
     * holdScreen() / releaseScreen() / a() -> DO_NOTHING
     * Prevents fatal NoSuchMethodError on WindowManager$LayoutParams.semAddExtensionFlags
     */
    private static void hookPresentationScreenWakeHolder(ClassLoader cl) {
        try {
            Class<?> e0cClass = findClassSafe(cl, "E0.c", "LE0.c;");
            if (e0cClass != null) {
                XposedBridge.hookAllMethods(e0cClass, "holdScreen", XC_MethodReplacement.DO_NOTHING);
                XposedBridge.hookAllMethods(e0cClass, "releaseScreen", XC_MethodReplacement.DO_NOTHING);
                XposedBridge.hookAllMethods(e0cClass, "a", new XC_MethodReplacement() {
                    @Override
                    protected Object replaceHookedMethod(MethodHookParam param) {
                        WindowManager.LayoutParams params = new WindowManager.LayoutParams(
                            WindowManager.LayoutParams.MATCH_PARENT,
                            WindowManager.LayoutParams.MATCH_PARENT,
                            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                            PixelFormat.TRANSLUCENT
                        );
                        params.setTitle("PresentationScreenWakeHolder");
                        return params;
                    }
                });
                XposedLog.i(TAG, "Hooked E0.c (PresentationScreenWakeHolder) holdScreen/releaseScreen/a");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook E0.c: " + t.getMessage());
        }
    }

    /**
     * 13. Hook BlackScreen LayoutParams (v, z, x) and WindowContext helper (K.E0.c)
     * Prevents fatal NoSuchMethodError on semAddExtensionFlags / semAddPrivateFlags,
     * preserves FLAG_NOT_TOUCHABLE & short-edges cutout mode, and replaces Samsung window type 2407.
     */
    private static final int FLAG_NOT_TOUCHABLE = 0x00000010;

    private static WindowManager.LayoutParams buildSafeBlackScreenLayoutParams(int w, int h, boolean nonTouchable) {
        int flags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
            | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
            | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS;
        if (nonTouchable) {
            flags |= FLAG_NOT_TOUCHABLE;
        }
        WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
            w, h,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            flags,
            PixelFormat.TRANSLUCENT
        );
        try {
            XposedHelpers.setIntField(lp, "layoutInDisplayCutoutMode", 1); // LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES
        } catch (Throwable ignored) {}
        lp.setTitle("BlackScreen");
        return lp;
    }

    private static void hookBlackScreenLayoutParams(ClassLoader cl) {
        final XC_MethodReplacement touchableLpRepl = new XC_MethodReplacement() {
            @Override
            protected Object replaceHookedMethod(MethodHookParam param) {
                int w = WindowManager.LayoutParams.MATCH_PARENT;
                int h = WindowManager.LayoutParams.MATCH_PARENT;
                if (param.args != null && param.args.length >= 2 && param.args[0] instanceof Integer && param.args[1] instanceof Integer) {
                    w = (Integer) param.args[0];
                    h = (Integer) param.args[1];
                }
                return buildSafeBlackScreenLayoutParams(w, h, false);
            }
        };
        final XC_MethodReplacement nonTouchableLpRepl = new XC_MethodReplacement() {
            @Override
            protected Object replaceHookedMethod(MethodHookParam param) {
                return buildSafeBlackScreenLayoutParams(
                    WindowManager.LayoutParams.MATCH_PARENT,
                    WindowManager.LayoutParams.MATCH_PARENT,
                    true
                );
            }
        };

        try {
            Class<?> bsvClass = findClassSafe(cl, "com.samsung.android.continuity.blackscreen.v");
            if (bsvClass != null) {
                XposedBridge.hookAllMethods(bsvClass, "createLayoutParam", touchableLpRepl);
                XposedBridge.hookAllMethods(bsvClass, "createLayoutParamNonTouchableBG", nonTouchableLpRepl);
                XposedBridge.hookAllMethods(bsvClass, "createLayoutParamTouchableBG", touchableLpRepl);
                XposedLog.i(TAG, "Hooked blackscreen.v createLayoutParam* -> safe LayoutParams");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook blackscreen.v: " + t.getMessage());
        }

        try {
            Class<?> bszClass = findClassSafe(cl, "com.samsung.android.continuity.blackscreen.z");
            if (bszClass != null) {
                XposedBridge.hookAllMethods(bszClass, "createLayoutParam", touchableLpRepl);
                XposedLog.i(TAG, "Hooked blackscreen.z createLayoutParam -> safe LayoutParams");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook blackscreen.z: " + t.getMessage());
        }

        try {
            Class<?> bsxClass = findClassSafe(cl, "com.samsung.android.continuity.blackscreen.x");
            if (bsxClass != null) {
                XposedBridge.hookAllMethods(bsxClass, "createLayoutParamNonTouchableBG", nonTouchableLpRepl);
                XposedBridge.hookAllMethods(bsxClass, "createLayoutParamTouchableBG", touchableLpRepl);
                XposedLog.i(TAG, "Hooked blackscreen.x createLayoutParam* -> safe LayoutParams");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook blackscreen.x: " + t.getMessage());
        }

        // Replace K.E0.c(Context) createWindowContext(2407, null) with TYPE_APPLICATION_OVERLAY (2038)
        try {
            Class<?> ke0Class = findClassSafe(cl, "K.E0", "LK.E0;");
            if (ke0Class != null) {
                XposedHelpers.findAndHookMethod(ke0Class, "c", Context.class, new XC_MethodReplacement() {
                    @Override
                    protected Object replaceHookedMethod(MethodHookParam param) {
                        Context ctx = (Context) param.args[0];
                        if (ctx == null) {
                            return null;
                        }
                        try {
                            return XposedHelpers.callMethod(
                                ctx,
                                "createWindowContext",
                                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                                null
                            );
                        } catch (Throwable ignored) {
                            return ctx;
                        }
                    }
                });
                XposedLog.i(TAG, "Hooked K.E0.c WindowContext -> TYPE_APPLICATION_OVERLAY (replaced 2407)");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook K.E0.c: " + t.getMessage());
        }
    }

    /**
     * 14. Hook DragAndDropView and PausedDisplayDimmingView LayoutParams
     */
    private static void hookOtherOverlayLayoutParams(ClassLoader cl) {
        try {
            Class<?> dndClass = findClassSafe(cl, "com.samsung.android.mdx.windowslink.interactor.dragdrop.DragAndDropView");
            if (dndClass != null) {
                XC_MethodReplacement dndRepl = new XC_MethodReplacement() {
                    @Override
                    protected Object replaceHookedMethod(MethodHookParam param) {
                        WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                            WindowManager.LayoutParams.WRAP_CONTENT,
                            WindowManager.LayoutParams.WRAP_CONTENT,
                            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                                | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                            PixelFormat.TRANSLUCENT
                        );
                        lp.setTitle("DragAndDropView");
                        return lp;
                    }
                };
                XposedBridge.hookAllMethods(dndClass, "getDispatchDragLayoutParams", dndRepl);
                XposedBridge.hookAllMethods(dndClass, "getStartDragLayoutParams", dndRepl);
                XposedLog.i(TAG, "Hooked DragAndDropView get*DragLayoutParams");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook DragAndDropView: " + t.getMessage());
        }

        try {
            Class<?> dimClass = findClassSafe(cl, "com.samsung.android.mdx.windowslink.interactor.multidisplay.view.PausedDisplayDimmingView");
            if (dimClass != null) {
                XC_MethodReplacement dimRepl = new XC_MethodReplacement() {
                    @Override
                    protected Object replaceHookedMethod(MethodHookParam param) {
                        WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                            WindowManager.LayoutParams.MATCH_PARENT,
                            WindowManager.LayoutParams.MATCH_PARENT,
                            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                                | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                            PixelFormat.TRANSLUCENT
                        );
                        lp.setTitle("PausedDisplayDimmingView");
                        return lp;
                    }
                };
                XposedBridge.hookAllMethods(dimClass, "getDimmingLayoutParams", dimRepl);
                XposedLog.i(TAG, "Hooked PausedDisplayDimmingView getDimmingLayoutParams");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook PausedDisplayDimmingView: " + t.getMessage());
        }
    }

    /**
     * 15. Hook RemoteAppModeManager and TaskInfoService
     * Prevents fatal NPE in unregisterTaskChangedListener on unbind
     */
    private static void hookRemoteAppModeManagerAndTaskInfo(ClassLoader cl) {
        try {
            Class<?> rammClass = findClassSafe(cl, "com.samsung.android.mdx.semremoteappmodemanagerlib.RemoteAppModeManager");
            if (rammClass != null) {
                XposedBridge.hookAllMethods(rammClass, "registerTaskChangedListener", XC_MethodReplacement.returnConstant(Boolean.TRUE));
                XposedBridge.hookAllMethods(rammClass, "unregisterTaskChangedListener", XC_MethodReplacement.returnConstant(Boolean.TRUE));
                XposedBridge.hookAllMethods(rammClass, "registerRotationWatcher", XC_MethodReplacement.returnConstant(Boolean.TRUE));
                XposedBridge.hookAllMethods(rammClass, "unregisterRotationWatcher", XC_MethodReplacement.returnConstant(Boolean.TRUE));
                XposedBridge.hookAllMethods(rammClass, "registerRotationChangedListener", XC_MethodReplacement.DO_NOTHING);
                XposedBridge.hookAllMethods(rammClass, "registerSecureAppChangedListener", XC_MethodReplacement.DO_NOTHING);
                XposedBridge.hookAllMethods(rammClass, "registerStartActivityInterceptedListener", XC_MethodReplacement.DO_NOTHING);
                XposedBridge.hookAllMethods(rammClass, "ensureInit", XC_MethodReplacement.DO_NOTHING);
                XposedBridge.hookAllMethods(rammClass, "init", XC_MethodReplacement.DO_NOTHING);
                XposedBridge.hookAllMethods(rammClass, "deInit", XC_MethodReplacement.DO_NOTHING);
                XposedLog.i(TAG, "Hooked RemoteAppModeManager methods -> safe stubs");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook RemoteAppModeManager: " + t.getMessage());
        }

        try {
            Class<?> taskInfoServiceClass = findClassSafe(cl, "com.samsung.android.mdx.windowslink.interactor.multidisplay.TaskInfoService");
            if (taskInfoServiceClass != null) {
                XposedBridge.hookAllMethods(taskInfoServiceClass, "onUnbind", XC_MethodReplacement.returnConstant(Boolean.FALSE));
                XposedLog.i(TAG, "Hooked TaskInfoService.onUnbind -> false");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook TaskInfoService.onUnbind: " + t.getMessage());
        }

        // Also stub task remove callers (semRemoveTask)
        try {
            Class<?> m1pClass = findClassSafe(cl, "m1.p", "Lm1.p;");
            if (m1pClass != null) {
                XposedBridge.hookAllMethods(m1pClass, "closeTask", XC_MethodReplacement.returnConstant(Boolean.TRUE));
            }
            Class<?> m1hClass = findClassSafe(cl, "m1.h", "Lm1.h;");
            if (m1hClass != null) {
                XposedBridge.hookAllMethods(m1hClass, "a", XC_MethodReplacement.returnConstant(Boolean.TRUE));
            }
            Class<?> b1qClass = findClassSafe(cl, "B1.q", "LB1.q;");
            if (b1qClass != null) {
                XposedBridge.hookAllMethods(b1qClass, "b", XC_MethodReplacement.returnConstant(Boolean.TRUE));
            }
            Class<?> v1gClass = findClassSafe(cl, "v1.g", "Lv1.g;");
            if (v1gClass != null) {
                XposedBridge.hookAllMethods(v1gClass, "b", XC_MethodReplacement.returnConstant(Boolean.TRUE));
            }
        } catch (Throwable ignored) {}
    }

    /**
     * 16. Hook BlackScreen NotificationService
     * Prevents calling semBindNotificationListener / semUnBindNotificationListener
     */
    private static void hookBlackScreenNotificationService(ClassLoader cl) {
        try {
            Class<?> notifServiceClass = findClassSafe(cl, "com.samsung.android.mdx.windowslink.interactor.blackscreen.NotificationService");
            if (notifServiceClass != null) {
                XposedBridge.hookAllMethods(notifServiceClass, "bindService", XC_MethodReplacement.DO_NOTHING);
                XposedBridge.hookAllMethods(notifServiceClass, "unbindService", XC_MethodReplacement.DO_NOTHING);
                XposedBridge.hookAllMethods(notifServiceClass, "a", XC_MethodReplacement.DO_NOTHING);
                XposedLog.i(TAG, "Hooked NotificationService bindService/unbindService/a -> DO_NOTHING");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook NotificationService: " + t.getMessage());
        }
    }

    /**
     * 16b. Hook BlackScreen MediaView
     * Prevents SecurityException ("Missing permission to control media.") in MediaSessionManager
     * when com.samsung.android.mdx lacks MEDIA_CONTENT_CONTROL on non-Samsung AOSP ROMs.
     */
    private static void hookBlackScreenMediaView(ClassLoader cl) {
        try {
            Class<?> mediaViewClass = findClassSafe(
                cl,
                "com.samsung.android.continuity.blackscreen.MediaView"
            );
            if (mediaViewClass != null) {
                XposedBridge.hookAllMethods(mediaViewClass, "createView", new XC_MethodReplacement() {
                    @Override
                    protected Object replaceHookedMethod(MethodHookParam param) {
                        try {
                            XposedHelpers.callMethod(param.thisObject, "a");
                        } catch (Throwable ignored) {}
                        XposedLog.d(TAG, "Bypassed MediaView.createView -> prevented MEDIA_CONTENT_CONTROL crash");
                        return null;
                    }
                });
                XposedBridge.hookAllMethods(mediaViewClass, "removeView", new XC_MethodReplacement() {
                    @Override
                    protected Object replaceHookedMethod(MethodHookParam param) {
                        try {
                            XposedHelpers.callMethod(param.thisObject, "a");
                            XposedHelpers.setIntField(param.thisObject, "l", 0);
                        } catch (Throwable ignored) {}
                        return null;
                    }
                });
                XposedLog.i(TAG, "Hooked blackscreen.MediaView createView/removeView -> safe hide");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook blackscreen.MediaView: " + t.getMessage());
        }
    }

    /**
     * 16c. Suppress BlackScreen overlay on AOSP and guard Samsung .spr battery drawables.
     * On AOSP, MediaProjection captures Display 0 overlays (causing a black screen/box in the stream),
     * and res/raw/stat_sys_battery_aod.spr returns null causing BatteryIconView.draw NPE & ANR.
     */
    private static void hookBlackScreenOverlayAndDrawables(ClassLoader cl) {
        try {
            Class<?> bsvClass = findClassSafe(cl, "com.samsung.android.continuity.blackscreen.v");
            if (bsvClass != null) {
                XposedBridge.hookAllMethods(bsvClass, "showBlackScreen", XC_MethodReplacement.DO_NOTHING);
                XposedBridge.hookAllMethods(bsvClass, "removeBlackScreen", XC_MethodReplacement.DO_NOTHING);
                XposedBridge.hookAllMethods(bsvClass, "isShown", XC_MethodReplacement.returnConstant(Boolean.FALSE));
                XposedLog.i(TAG, "Hooked blackscreen.v showBlackScreen/removeBlackScreen -> disabled for AOSP");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook blackscreen.v show/remove: " + t.getMessage());
        }

        try {
            Class<?> bsbClass = findClassSafe(cl, "com.samsung.android.continuity.blackscreen.b");
            if (bsbClass != null) {
                XC_MethodHook fallbackDrawableHook = new XC_MethodHook() {
                    @Override
                    protected void afterHookedMethod(MethodHookParam param) {
                        if (param.getResult() != null) {
                            return;
                        }
                        try {
                            Class<?> bitmapCls = XposedHelpers.findClass("android.graphics.Bitmap", cl);
                            Class<?> cfgCls = XposedHelpers.findClass("android.graphics.Bitmap$Config", cl);
                            Object argb = XposedHelpers.getStaticObjectField(cfgCls, "ARGB_8888");
                            Object bmp = XposedHelpers.callStaticMethod(bitmapCls, "createBitmap", 16, 16, argb);
                            Object iconView = XposedHelpers.getObjectField(param.thisObject, "a");
                            Context ctx = iconView != null ? (Context) XposedHelpers.getObjectField(iconView, "b") : null;
                            Class<?> bdCls = XposedHelpers.findClass("android.graphics.drawable.BitmapDrawable", cl);
                            Object res = ctx != null ? XposedHelpers.callMethod(ctx, "getResources") : null;
                            Object drawable = res != null
                                ? XposedHelpers.newInstance(bdCls, res, bmp)
                                : XposedHelpers.newInstance(bdCls, bmp);
                            param.setResult(drawable);
                        } catch (Throwable ignored) {}
                    }
                };
                XposedBridge.hookAllMethods(bsbClass, "getBatteryOutlineDrawable", fallbackDrawableHook);
                XposedBridge.hookAllMethods(bsbClass, "getChargingDrawable", fallbackDrawableHook);
                XposedLog.i(TAG, "Hooked blackscreen.b battery drawables -> BitmapDrawable fallback");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook blackscreen.b: " + t.getMessage());
        }
    }

    /**
     * 17. Hook semLockNow & Clipboard secure folder
     */
    private static void hookSemLockNowAndAudio(ClassLoader cl) {
        try {
            Class<?> bsCtrlClass = findClassSafe(cl, "com.samsung.android.mdx.windowslink.interactor.blackscreen.BlackScreenControllerService");
            if (bsCtrlClass != null) {
                XposedBridge.hookAllMethods(bsCtrlClass, "d", XC_MethodReplacement.DO_NOTHING);
                XposedBridge.hookAllMethods(bsCtrlClass, "f", XC_MethodReplacement.DO_NOTHING);
                XposedLog.i(TAG, "Hooked BlackScreenControllerService.d/f -> DO_NOTHING");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook BlackScreenControllerService.d/f: " + t.getMessage());
        }

        try {
            Class<?> c1jClass = findClassSafe(cl, "c1.j", "Lc1.j;");
            if (c1jClass != null) {
                XposedBridge.hookAllMethods(c1jClass, "onHide", XC_MethodReplacement.DO_NOTHING);
                XposedLog.i(TAG, "Hooked c1.j.onHide -> DO_NOTHING");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook c1.j: " + t.getMessage());
        }

        try {
            Class<?> clipRepoClass = findClassSafe(cl, "com.samsung.android.mdx.windowslink.system.impl.ClipboardRepositoryROrPrior");
            if (clipRepoClass != null) {
                XposedBridge.hookAllMethods(clipRepoClass, "isAllowToCopyFromSecureFolder", XC_MethodReplacement.returnConstant(Boolean.TRUE));
                XposedLog.i(TAG, "Hooked ClipboardRepositoryROrPrior.isAllowToCopyFromSecureFolder -> true");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook ClipboardRepositoryROrPrior: " + t.getMessage());
        }
    }

    /**
     * 18. Hook AppExecutionContainerService and SemFloatingFeature in MDX
     * Eliminates "LTW_REMOTE_APP feature is not enabled in this device" RemoteException
     */
    private static void hookAppExecutionContainerService(ClassLoader cl) {
        try {
            Class<?> appExecClass = findClassSafe(cl, "com.samsung.android.mdx.windowslink.interactor.multidisplay.AppExecutionContainerService");
            if (appExecClass != null) {
                XposedBridge.hookAllMethods(appExecClass, "a", XC_MethodReplacement.returnConstant(Boolean.TRUE));
                XposedBridge.hookAllMethods(appExecClass, "c", XC_MethodReplacement.returnConstant(Boolean.TRUE));
                XposedBridge.hookAllMethods(appExecClass, "onCreate", new XC_MethodHook() {
                    @Override
                    protected void afterHookedMethod(MethodHookParam param) {
                        try {
                            XposedHelpers.setBooleanField(param.thisObject, "i", true);
                            XposedLog.i(TAG, "Forced AppExecutionContainerService.i = true");
                        } catch (Throwable t) {
                            XposedLog.w(TAG, "Failed to set AppExecutionContainerService.i: " + t.getMessage());
                        }
                    }
                });
                XposedLog.i(TAG, "Hooked AppExecutionContainerService (a -> true, c -> true, forced i=true)");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook AppExecutionContainerService: " + t.getMessage());
        }

        try {
            Class<?> l1bClass = findClassSafe(cl, "l1.b", "Ll1.b;");
            if (l1bClass != null) {
                XposedBridge.hookAllMethods(l1bClass, "init", XC_MethodReplacement.returnConstant(Boolean.TRUE));
                XposedLog.i(TAG, "Hooked l1.b.init -> return true");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook l1.b.init: " + t.getMessage());
        }

        try {
            Class<?> semFloatingClass = findClassSafe(cl, "com.samsung.android.feature.SemFloatingFeature");
            if (semFloatingClass != null) {
                XC_MethodHook boolHook = new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) {
                        if (param.args.length > 0 && param.args[0] != null) {
                            String tag = (String) param.args[0];
                            if ("SEC_FLOATING_FEATURE_COMMON_SUPPORT_LTW_REMOTE_APP".equals(tag)
                                || "SEC_FLOATING_FEATURE_COMMON_SUPPORT_LINK_TO_WINDOWS".equals(tag)
                                || "SEC_FLOATING_FEATURE_LINK_TO_WINDOWS".equals(tag)
                                || "SEC_FLOATING_FEATURE_AUDIO_SUPPORT_SOUND_ALIVE".equals(tag)) {
                                param.setResult(Boolean.TRUE);
                            }
                        }
                    }
                };
                XposedBridge.hookAllMethods(semFloatingClass, "getBoolean", boolHook);
                XposedBridge.hookAllMethods(semFloatingClass, "getEnableStatus", boolHook);

                XposedBridge.hookAllMethods(semFloatingClass, "getString", new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) {
                        if (param.args.length > 0 && param.args[0] != null) {
                            String tag = (String) param.args[0];
                            if ("SEC_FLOATING_FEATURE_SETTINGS_CONFIG_BRAND_NAME".equals(tag)) {
                                param.setResult("Samsung");
                            } else if ("SEC_FLOATING_FEATURE_SIP_CONFIG_PACKAGE_NAME".equals(tag)) {
                                param.setResult("com.samsung.android.honeyboard");
                            }
                        }
                    }
                });
                XposedLog.i(TAG, "Hooked SemFloatingFeature methods in MDX");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook SemFloatingFeature in MDX: " + t.getMessage());
        }
    }

    private static Class<?> findClassSafe(ClassLoader cl, String... classNames) {
        for (String name : classNames) {
            try {
                return XposedHelpers.findClass(name, cl);
            } catch (Throwable ignored) {}
        }
        return null;
    }
}
