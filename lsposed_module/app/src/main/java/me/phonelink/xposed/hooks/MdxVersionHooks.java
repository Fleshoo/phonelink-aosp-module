package me.phonelink.xposed.hooks;

import android.content.Context;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XC_MethodReplacement;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;
import me.phonelink.xposed.stubs.OneUIStubs;
import me.phonelink.xposed.utils.XposedLog;

public class MdxVersionHooks {

    private static final String TAG = "PhoneLink-MdxVersion";

    // One UI 5.1 / Android 13 configuration
    public static final int SEM_INT_VALUE = 5001;              // One UI 5.1
    public static final int SEM_PLATFORM_INT_VALUE = 140100;    // One UI 5.1 (14.1)

    public static void init(XC_LoadPackage.LoadPackageParam lpparam) {
        hook(lpparam);
    }

    public static void hook(XC_LoadPackage.LoadPackageParam lpparam) {
        if (!"com.samsung.android.mdx".equals(lpparam.packageName)) {
            return;
        }

        ClassLoader cl = lpparam.classLoader;

        // 1. Hook LL0/c (L0.c) methods to eliminate NoSuchFieldError and report One UI 5.1
        try {
            Class<?> versionClass = null;
            try {
                versionClass = XposedHelpers.findClass("L0.c", cl);
            } catch (Throwable t) {
                try {
                    versionClass = XposedHelpers.findClass("LL0.c", cl);
                } catch (Throwable ignored) {}
            }

            if (versionClass != null) {
                // Hook getSemIntValue() -> return 5001 (eliminates sget Build$VERSION.SEM_INT)
                XposedHelpers.findAndHookMethod(versionClass, "getSemIntValue", new XC_MethodReplacement() {
                    @Override
                    protected Object replaceHookedMethod(MethodHookParam param) {
                        XposedLog.d(TAG, "getSemIntValue intercepted -> returning " + SEM_INT_VALUE);
                        return SEM_INT_VALUE;
                    }
                });

                // Hook getSemPlatformIntValue() -> return 140100
                XposedHelpers.findAndHookMethod(versionClass, "getSemPlatformIntValue", new XC_MethodReplacement() {
                    @Override
                    protected Object replaceHookedMethod(MethodHookParam param) {
                        XposedLog.d(TAG, "getSemPlatformIntValue intercepted -> returning " + SEM_PLATFORM_INT_VALUE);
                        return SEM_PLATFORM_INT_VALUE;
                    }
                });

                // Hook isOneUI2_1OrLater() -> return true
                XposedHelpers.findAndHookMethod(versionClass, "isOneUI2_1OrLater", new XC_MethodReplacement() {
                    @Override
                    protected Object replaceHookedMethod(MethodHookParam param) {
                        return true;
                    }
                });

                XposedLog.i(TAG, "Successfully hooked L0.c One UI version checker methods");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook L0.c: " + t.getMessage());
        }

        // 2. Hook LE1/b (E1.b) - Samsung Experience Mobile capability checker
        try {
            Class<?> e1bClass = null;
            try {
                e1bClass = XposedHelpers.findClass("E1.b", cl);
            } catch (Throwable t) {
                try {
                    e1bClass = XposedHelpers.findClass("LE1.b", cl);
                } catch (Throwable ignored) {}
            }

            if (e1bClass != null) {
                // Hook isSemAvailable(Context) -> return true
                XposedHelpers.findAndHookMethod(e1bClass, "isSemAvailable", Context.class, new XC_MethodReplacement() {
                    @Override
                    protected Object replaceHookedMethod(MethodHookParam param) {
                        return true;
                    }
                });

                // Hook getOneUIVersion(Context) -> return 140100
                XposedHelpers.findAndHookMethod(e1bClass, "getOneUIVersion", Context.class, new XC_MethodReplacement() {
                    @Override
                    protected Object replaceHookedMethod(MethodHookParam param) {
                        return SEM_PLATFORM_INT_VALUE;
                    }
                });

                XposedLog.i(TAG, "Successfully hooked E1.b isSemAvailable & getOneUIVersion");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook E1.b: " + t.getMessage());
        }

        // 3. Hook LL0/b (L0.b) - ContentProvider caller signature verification bypass
        try {
            Class<?> l0bClass = null;
            try {
                l0bClass = XposedHelpers.findClass("L0.b", cl);
            } catch (Throwable t) {
                try {
                    l0bClass = XposedHelpers.findClass("LL0.b", cl);
                } catch (Throwable ignored) {}
            }

            if (l0bClass != null) {
                XposedHelpers.findAndHookMethod(l0bClass, "isAvailableCaller", Context.class, String.class, new XC_MethodReplacement() {
                    @Override
                    protected Object replaceHookedMethod(MethodHookParam param) {
                        return true;
                    }
                });
                XposedLog.i(TAG, "Successfully hooked L0.b isAvailableCaller bypass");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook L0.b: " + t.getMessage());
        }

        // 4. Hook ApplicationPackageManager.hasSystemFeature for com.samsung.feature.* inside MDX
        try {
            Class<?> pmClass = XposedHelpers.findClass("android.app.ApplicationPackageManager", cl);
            XposedHelpers.findAndHookMethod(pmClass, "hasSystemFeature", String.class, new XC_MethodHook() {
                @Override
                protected void beforeHookedMethod(MethodHookParam param) {
                    String feature = (String) param.args[0];
                    if ("com.samsung.feature.samsung_experience_mobile".equals(feature) ||
                        "com.sec.feature.samsung_experience_mobile".equals(feature)) {
                        param.setResult(true);
                    }
                }
            });
            XposedLog.i(TAG, "Hooked ApplicationPackageManager.hasSystemFeature for MDX");
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook ApplicationPackageManager.hasSystemFeature: " + t.getMessage());
        }

        // 5. Hook ClassLoader for OneUIStubs and DesktopMode fallbacks
        try {
            XposedHelpers.findAndHookMethod(
                ClassLoader.class,
                "loadClass",
                String.class,
                boolean.class,
                new XC_MethodHook() {
                    @Override
                    protected void afterHookedMethod(MethodHookParam param) throws Throwable {
                        if (!param.hasThrowable() && param.getResult() != null) {
                            return;
                        }
                        String className = (String) param.args[0];
                        if ("LL0.c".equals(className) || "L0.c".equals(className) ||
                            "com.samsung.android.os.SemVersion".equals(className)) {
                            param.setResult(OneUIStubs.class);
                        } else if ("com.samsung.android.desktopmode.DesktopModeManager".equals(className) ||
                                   "com.samsung.android.desktopmode.SemDesktopModeManager".equals(className)) {
                            param.setResult(com.samsung.android.desktopmode.SemDesktopModeManager.class);
                        } else if ("com.samsung.android.desktopmode.SemDesktopModeState".equals(className)) {
                            param.setResult(com.samsung.android.desktopmode.SemDesktopModeState.class);
                        } else if ("com.samsung.android.feature.SemFloatingFeature".equals(className)) {
                            param.setResult(com.samsung.android.feature.SemFloatingFeature.class);
                        } else if ("android.os.SemSystemProperties".equals(className)) {
                            param.setResult(android.os.SemSystemProperties.class);
                        } else if ("com.samsung.android.os.SemTemperatureManager".equals(className)) {
                            param.setResult(com.samsung.android.os.SemTemperatureManager.class);
                        } else if ("com.samsung.android.os.SemTemperatureManager$Thermistor".equals(className)) {
                            param.setResult(com.samsung.android.os.SemTemperatureManager.Thermistor.class);
                        }
                    }
                }
            );
            XposedLog.i(TAG, "MdxService ClassLoader hooked for OneUIStubs");
        } catch (Throwable t) {
            XposedLog.e(TAG, "Failed to hook ClassLoader for MdxService", t);
        }
    }
}
