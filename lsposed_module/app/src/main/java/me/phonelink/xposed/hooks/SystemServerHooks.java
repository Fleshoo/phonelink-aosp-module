package me.phonelink.xposed.hooks;

import android.content.Context;
import android.content.pm.PackageManager;
import android.os.Binder;
import android.os.UserHandle;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;
import me.phonelink.xposed.utils.XposedLog;

import java.lang.reflect.Method;
import java.util.concurrent.ConcurrentHashMap;

/**
 * SystemServerHooks: Hooks MediaProjectionManagerService and InputManagerService in system_server.
 * For Milestone 3: Bypasses MANAGE_MEDIA_PROJECTION and foreground service checks for MDX.
 * For Milestone 4: INJECT_EVENTS permission bypass for touch and mouse injection.
 */
public class SystemServerHooks {
    private static final String TAG = "PhoneLink-SystemServerHooks";

    public static final String PKG_MDX = "com.samsung.android.mdx";
    public static final String PKG_APPMANAGER = "com.microsoft.appmanager";

    private static final ConcurrentHashMap<Integer, Boolean> sPrivilegedUidCache = new ConcurrentHashMap<>();

    public static void init(XC_LoadPackage.LoadPackageParam lpparam) {
        if (!"android".equals(lpparam.packageName) && !"system_server".equals(lpparam.processName)) {
            return;
        }
        XposedLog.i(TAG, "Initializing SystemServerHooks in process: " + lpparam.processName);
        hookMediaProjectionService(lpparam);
        hookInputManagerService(lpparam);
    }

    private static void hookMediaProjectionService(XC_LoadPackage.LoadPackageParam lpparam) {
        ClassLoader cl = lpparam.classLoader;

        // 1. Hook MediaProjectionManagerService$BinderService.createProjection & hasProjectionPermission
        try {
            Class<?> binderServiceClass = XposedHelpers.findClass(
                "com.android.server.media.projection.MediaProjectionManagerService$BinderService", cl
            );

            XposedHelpers.findAndHookMethod(
                binderServiceClass,
                "createProjection",
                int.class,          // processUid
                String.class,       // packageName
                int.class,          // type
                boolean.class,      // isPermanentGrant
                int.class,          // displayId
                new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) throws Throwable {
                        String pkg = (String) param.args[1];
                        if (PKG_MDX.equals(pkg) || PKG_APPMANAGER.equals(pkg)) {
                            XposedLog.i(TAG, "createProjection requested for privileged client: " + pkg + ", bypassing MANAGE_MEDIA_PROJECTION check");
                            Object service = XposedHelpers.getSurroundingThis(param.thisObject);
                            UserHandle callingUser = Binder.getCallingUserHandle();
                            Object projection = XposedHelpers.callMethod(
                                service,
                                "createProjectionInternal",
                                param.args[0], // processUid
                                param.args[1], // packageName
                                param.args[2], // type
                                param.args[3], // isPermanentGrant
                                callingUser,
                                param.args[4]  // displayId
                            );
                            param.setResult(projection);
                        }
                    }
                }
            );

            XposedHelpers.findAndHookMethod(
                binderServiceClass,
                "hasProjectionPermission",
                int.class,
                String.class,
                new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) {
                        String pkg = (String) param.args[1];
                        if (PKG_MDX.equals(pkg) || PKG_APPMANAGER.equals(pkg)) {
                            param.setResult(true);
                        }
                    }
                }
            );

            XposedLog.i(TAG, "Successfully hooked MediaProjectionManagerService$BinderService");
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook MediaProjectionManagerService$BinderService: " + t.getMessage());
        }

        // 2. Hook MediaProjectionManagerService$MediaProjection validation & foreground checks
        try {
            Class<?> projectionClass = XposedHelpers.findClass(
                "com.android.server.media.projection.MediaProjectionManagerService$MediaProjection", cl
            );

            // Hook requiresForegroundService -> return false for MDX
            XposedHelpers.findAndHookMethod(projectionClass, "requiresForegroundService", new XC_MethodHook() {
                @Override
                protected void beforeHookedMethod(MethodHookParam param) {
                    String pkg = (String) XposedHelpers.getObjectField(param.thisObject, "packageName");
                    if (PKG_MDX.equals(pkg) || PKG_APPMANAGER.equals(pkg)) {
                        param.setResult(false);
                    }
                }
            });

            // Hook isValid -> return true for MDX
            XposedHelpers.findAndHookMethod(projectionClass, "isValid", new XC_MethodHook() {
                @Override
                protected void beforeHookedMethod(MethodHookParam param) {
                    String pkg = (String) XposedHelpers.getObjectField(param.thisObject, "packageName");
                    if (PKG_MDX.equals(pkg) || PKG_APPMANAGER.equals(pkg)) {
                        param.setResult(true);
                    }
                }
            });

            XposedLog.i(TAG, "Successfully hooked MediaProjectionManagerService$MediaProjection validation");
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook MediaProjectionManagerService$MediaProjection: " + t.getMessage());
        }

        // 3. Hook Injector.shouldMediaProjectionPreventReusingConsent -> return false for MDX
        try {
            Class<?> injectorClass = XposedHelpers.findClass(
                "com.android.server.media.projection.MediaProjectionManagerService$Injector", cl
            );
            Class<?> projClass = XposedHelpers.findClass(
                "com.android.server.media.projection.MediaProjectionManagerService$MediaProjection", cl
            );

            if (injectorClass != null && projClass != null) {
                XposedHelpers.findAndHookMethod(injectorClass, "shouldMediaProjectionPreventReusingConsent", projClass, new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) {
                        Object proj = param.args[0];
                        if (proj != null) {
                            String pkg = (String) XposedHelpers.getObjectField(proj, "packageName");
                            if (PKG_MDX.equals(pkg) || PKG_APPMANAGER.equals(pkg)) {
                                param.setResult(false);
                            }
                        }
                    }
                });
                XposedLog.i(TAG, "Successfully hooked shouldMediaProjectionPreventReusingConsent");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook Injector.shouldMediaProjectionPreventReusingConsent: " + t.getMessage());
        }
    }

    private static void hookInputManagerService(XC_LoadPackage.LoadPackageParam lpparam) {
        ClassLoader cl = lpparam.classLoader;
        Class<?> imsClass;
        try {
            imsClass = XposedHelpers.findClass("com.android.server.input.InputManagerService", cl);
        } catch (Throwable t) {
            XposedLog.e(TAG, "Failed to locate com.android.server.input.InputManagerService", t);
            return;
        }

        // 1. Hook checkCallingPermission(String, String, boolean) (Android 13..16 standard)
        try {
            XposedHelpers.findAndHookMethod(
                imsClass,
                "checkCallingPermission",
                String.class,
                String.class,
                boolean.class,
                new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) {
                        String permission = (String) param.args[0];
                        if ("android.permission.INJECT_EVENTS".equals(permission)) {
                            int callingUid = Binder.getCallingUid();
                            if (isPrivilegedInputCaller(param.thisObject, callingUid)) {
                                param.setResult(true);
                            }
                        }
                    }
                }
            );
            XposedLog.i(TAG, "Successfully hooked InputManagerService.checkCallingPermission(3 args)");
        } catch (Throwable t) {
            XposedLog.w(TAG, "Could not hook checkCallingPermission(3 args): " + t.getMessage());
        }

        // 2. Hook checkCallingPermission(String, String) (Overload fallback)
        try {
            XposedHelpers.findAndHookMethod(
                imsClass,
                "checkCallingPermission",
                String.class,
                String.class,
                new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) {
                        String permission = (String) param.args[0];
                        if ("android.permission.INJECT_EVENTS".equals(permission)) {
                            int callingUid = Binder.getCallingUid();
                            if (isPrivilegedInputCaller(param.thisObject, callingUid)) {
                                param.setResult(true);
                            }
                        }
                    }
                }
            );
            XposedLog.i(TAG, "Successfully hooked InputManagerService.checkCallingPermission(2 args)");
        } catch (Throwable t) {
            XposedLog.w(TAG, "Could not hook checkCallingPermission(2 args): " + t.getMessage());
        }

        // 3. Dynamic scan & hook for legacy/custom injectInputEventInternal variations
        try {
            for (Method m : imsClass.getDeclaredMethods()) {
                if ("injectInputEventInternal".equals(m.getName())) {
                    XposedBridge.hookMethod(m, new XC_MethodHook() {
                        @Override
                        protected void beforeHookedMethod(MethodHookParam param) {
                            int callingUid = Binder.getCallingUid();
                            if (isPrivilegedInputCaller(param.thisObject, callingUid)) {
                                // Allow legacy injection
                            }
                        }
                    });
                    XposedLog.i(TAG, "Hooked custom/legacy injectInputEventInternal method: " + m.toString());
                }
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Error inspecting injectInputEventInternal methods: " + t.getMessage());
        }
    }

    private static boolean isPrivilegedInputCaller(Object inputManagerService, int uid) {
        if (uid == 1000 || uid == 0) { // SYSTEM or ROOT
            return true;
        }

        Boolean cached = sPrivilegedUidCache.get(uid);
        if (cached != null) {
            return cached.booleanValue();
        }

        try {
            Context context = (Context) XposedHelpers.getObjectField(inputManagerService, "mContext");
            if (context != null) {
                PackageManager pm = context.getPackageManager();
                if (pm != null) {
                    String[] pkgs = pm.getPackagesForUid(uid);
                    if (pkgs != null) {
                        for (String pkg : pkgs) {
                            if (PKG_MDX.equals(pkg) || PKG_APPMANAGER.equals(pkg)) {
                                sPrivilegedUidCache.put(uid, Boolean.TRUE);
                                XposedLog.i(TAG, "Whitelisted privileged input caller UID: " + uid + " (" + pkg + ")");
                                return true;
                            }
                        }
                        // Definitive PMS package list without target packages: safe to cache FALSE
                        sPrivilegedUidCache.put(uid, Boolean.FALSE);
                        return false;
                    }
                }
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed resolving packages for UID " + uid + ": " + t.getMessage());
            return false;
        }

        // Context, pm, or pkgs was null (transient PMS failure/race) - do NOT cache FALSE!
        return false;
    }
}
