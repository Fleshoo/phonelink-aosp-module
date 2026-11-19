package me.phonelink.xposed.hooks;

import android.content.Context;
import android.os.Build;

import com.samsung.android.feature.SemFloatingFeature;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XC_MethodReplacement;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;
import me.phonelink.xposed.utils.XposedLog;

/**
 * Handles Process-Scoped Samsung Device Spoofing and Dynamic Class Injection
 * for com.microsoft.appmanager and com.samsung.android.mdx.
 */
public final class AppManagerHooks {

    private static final String TAG = "AppManagerHooks";

    public static void init(XC_LoadPackage.LoadPackageParam lpparam) {
        apply(lpparam);
    }

    public static void apply(XC_LoadPackage.LoadPackageParam lpparam) {
        // 1. Process-Scoped Device Spoofing
        spoofBuildFields();
        spoofSystemProperties();
        hookManufacturerChecks(lpparam.classLoader);

        // 2. Dynamic SemFloatingFeature Class Injection
        injectSemFloatingFeature(lpparam.classLoader);

        // 3. Signature & Bluetooth Transport hooks
        hookShipBuild(lpparam.classLoader);

        // 4. RCS & Missing Provider Guard
        hookRcsProvider(lpparam.classLoader);

        // 5. JustInTips & OneUI Version Guard
        hookJustInTips(lpparam.classLoader);

        // 6. CompanionDevice Permission & MediaProjection Auto-Grant
        hookCompanionDevicePermission(lpparam.classLoader);

        // 7. Recent Tasks Guard (Prevent NPE on AOSP)
        hookRecentTasksGuard(lpparam.classLoader);

        // 8. AppExecutionServiceManager Guard (Prevent NPE on AOSP)
        hookAppExecutionServiceManager(lpparam.classLoader);
    }

    private static void spoofBuildFields() {
        try {
            XposedHelpers.setStaticObjectField(Build.class, "MANUFACTURER", "samsung");
            XposedHelpers.setStaticObjectField(Build.class, "BRAND", "samsung");
            XposedHelpers.setStaticObjectField(Build.class, "MODEL", "SM-G998B");
            XposedHelpers.setStaticObjectField(Build.class, "PRODUCT", "p3sxx");
            XposedHelpers.setStaticObjectField(Build.class, "DEVICE", "p3s");
            XposedLog.i(TAG, "Build fields spoofed to Samsung Galaxy S21 Ultra (SM-G998B)");
        } catch (Throwable t) {
            XposedLog.e(TAG, "Failed to spoof Build fields", t);
        }
    }

    private static void spoofSystemProperties() {
        try {
            Class<?> sysPropClass = Class.forName("android.os.SystemProperties");

            XC_MethodHook propHook = new XC_MethodHook() {
                @Override
                protected void beforeHookedMethod(MethodHookParam param) {
                    String key = (String) param.args[0];
                    if ("ro.product.manufacturer".equals(key) || "ro.product.brand".equals(key)) {
                        param.setResult("samsung");
                    } else if ("ro.product.model".equals(key)) {
                        param.setResult("SM-G998B");
                    } else if ("ro.product.name".equals(key)) {
                        param.setResult("p3sxx");
                    } else if ("ro.product.device".equals(key)) {
                        param.setResult("p3s");
                    } else if ("ro.build.version.sem".equals(key)) {
                        param.setResult("5001");
                    } else if ("ro.build.characteristics".equals(key)) {
                        param.setResult("phone");
                    }
                }
            };

            XposedHelpers.findAndHookMethod(sysPropClass, "get", String.class, propHook);
            XposedHelpers.findAndHookMethod(sysPropClass, "get", String.class, String.class, propHook);
            XposedLog.i(TAG, "SystemProperties.get hooks applied");
        } catch (Throwable t) {
            XposedLog.w(TAG, "SystemProperties hook skipped: " + t.getMessage());
        }
    }

    private static void hookManufacturerChecks(ClassLoader classLoader) {
        // Hook ManufacturerUtils.isSamsungDevice() -> true
        try {
            XposedHelpers.findAndHookMethod(
                "com.google.android.material.internal.ManufacturerUtils",
                classLoader,
                "isSamsungDevice",
                XC_MethodReplacement.returnConstant(Boolean.TRUE)
            );
            XposedLog.i(TAG, "Hooked ManufacturerUtils.isSamsungDevice -> true");
        } catch (Throwable t) {
            XposedLog.w(TAG, "ManufacturerUtils.isSamsungDevice skipped: " + t.getMessage());
        }

        // Hook SamsungDeviceControlledAPI.checkSupportedSamsungVersion -> true
        try {
            XposedHelpers.findAndHookMethod(
                "com.microsoft.workaccount.workplacejoin.core.SamsungDeviceControlledAPI",
                classLoader,
                "checkSupportedSamsungVersion",
                Context.class,
                XC_MethodReplacement.returnConstant(Boolean.TRUE)
            );
            XposedLog.i(TAG, "Hooked checkSupportedSamsungVersion -> true");
        } catch (Throwable t) {
            XposedLog.w(TAG, "checkSupportedSamsungVersion skipped: " + t.getMessage());
        }

        // Hook DeviceInfo.getAssetCategory -> PHONE
        try {
            Class<?> categoryEnum = XposedHelpers.findClass(
                "com.samsung.android.sdk.mdx.windowslink.deviceinfo.DeviceInfo$AssetCategory",
                classLoader
            );
            Object phoneConstant = XposedHelpers.getStaticObjectField(categoryEnum, "PHONE");
            XposedHelpers.findAndHookMethod(
                "com.samsung.android.sdk.mdx.windowslink.deviceinfo.DeviceInfo",
                classLoader,
                "getAssetCategory",
                XC_MethodReplacement.returnConstant(phoneConstant)
            );
            XposedLog.i(TAG, "Hooked DeviceInfo.getAssetCategory -> PHONE");

            try {
                XposedHelpers.findAndHookMethod(
                    "com.samsung.android.sdk.mdx.windowslink.deviceinfo.DeviceInfo",
                    classLoader,
                    "getAssetCategory",
                    Context.class,
                    XC_MethodReplacement.returnConstant(phoneConstant)
                );
            } catch (Throwable ignored) {}
        } catch (Throwable t) {
            XposedLog.w(TAG, "DeviceInfo.getAssetCategory hook skipped: " + t.getMessage());
        }

        // Hook OemDeviceInfoImpl.getAssetCategory -> com.microsoft.deviceExperiences.AssetCategory.PHONE
        try {
            Class<?> msCategoryEnum = XposedHelpers.findClass(
                "com.microsoft.deviceExperiences.AssetCategory",
                classLoader
            );
            Object msPhoneConstant = XposedHelpers.getStaticObjectField(msCategoryEnum, "PHONE");
            XposedHelpers.findAndHookMethod(
                "com.microsoft.appmanager.ext.OemDeviceInfoImpl",
                classLoader,
                "getAssetCategory",
                XC_MethodReplacement.returnConstant(msPhoneConstant)
            );
            XposedLog.i(TAG, "Hooked OemDeviceInfoImpl.getAssetCategory -> PHONE");
        } catch (Throwable t) {
            XposedLog.w(TAG, "OemDeviceInfoImpl.getAssetCategory hook skipped: " + t.getMessage());
        }
    }

    private static void hookShipBuild(ClassLoader classLoader) {
        try {
            XposedHelpers.findAndHookMethod(
                "com.samsung.android.sdk.mdx.windowslink.bluetoothtransport.PackageSignatureChecker",
                classLoader,
                "isShipBuild",
                XC_MethodReplacement.returnConstant(Boolean.TRUE)
            );
            XposedLog.i(TAG, "Hooked PackageSignatureChecker.isShipBuild -> true");
        } catch (Throwable t) {
            XposedLog.w(TAG, "PackageSignatureChecker.isShipBuild hook skipped: " + t.getMessage());
        }
    }

    private static void hookRcsProvider(ClassLoader classLoader) {
        // 1. Hook ContentResolver to suppress authority "im" and catch missing provider errors
        try {
            Class<?> resolverClass = Class.forName("android.content.ContentResolver");

            XC_MethodHook imObserverHook = new XC_MethodHook() {
                @Override
                protected void beforeHookedMethod(MethodHookParam param) throws Throwable {
                    if (param.args.length > 0 && param.args[0] != null) {
                        String uriStr = param.args[0].toString();
                        if (uriStr != null && (uriStr.startsWith("content://im") || uriStr.contains("://im/"))) {
                            XposedLog.d(TAG, "Suppressed registerContentObserver for authority 'im'");
                            param.setResult(null);
                        }
                    }
                }
            };
            XposedBridge.hookAllMethods(resolverClass, "registerContentObserver", imObserverHook);

            XC_MethodHook imQueryHook = new XC_MethodHook() {
                @Override
                protected void beforeHookedMethod(MethodHookParam param) throws Throwable {
                    if (param.args.length > 0 && param.args[0] != null) {
                        String uriStr = param.args[0].toString();
                        if (uriStr != null && (uriStr.startsWith("content://im") || uriStr.contains("://im/"))) {
                            XposedLog.d(TAG, "Suppressed query for authority 'im'");
                            param.setResult(null);
                        }
                    }
                }
            };
            XposedBridge.hookAllMethods(resolverClass, "query", imQueryHook);
            XposedLog.i(TAG, "ContentResolver hooks applied for 'im' authority");
        } catch (Throwable t) {
            XposedLog.w(TAG, "ContentResolver im authority hook skipped: " + t.getMessage());
        }

        // 2. Hook RcsChecker to disable Samsung RCS
        try {
            Class<?> rcsCheckerClass = XposedHelpers.findClass(
                "com.samsung.android.sdk.mdx.windowslink.messaging.RcsChecker",
                classLoader
            );
            XposedBridge.hookAllMethods(rcsCheckerClass, "isRcsAvailable", XC_MethodReplacement.returnConstant(Boolean.FALSE));
            XposedBridge.hookAllMethods(rcsCheckerClass, "isRcsEnabled", XC_MethodReplacement.returnConstant(Boolean.FALSE));
            XposedBridge.hookAllMethods(rcsCheckerClass, "isRcsSendAvailable", XC_MethodReplacement.returnConstant(Boolean.FALSE));
            XposedBridge.hookAllMethods(rcsCheckerClass, "isRcsReceiveAvailable", XC_MethodReplacement.returnConstant(Boolean.FALSE));
            XposedBridge.hookAllMethods(rcsCheckerClass, "setRcsMessageListener", XC_MethodReplacement.DO_NOTHING);
            XposedLog.i(TAG, "Hooked RcsChecker to disable Samsung RCS");
        } catch (Throwable t) {
            XposedLog.w(TAG, "RcsChecker hook skipped: " + t.getMessage());
        }

        // 3. Hook ExtMessagingExtensions to disable Samsung RCS
        try {
            Class<?> extMsgClass = XposedHelpers.findClass(
                "com.microsoft.appmanager.ext.ExtMessagingExtensions",
                classLoader
            );
            XposedBridge.hookAllMethods(extMsgClass, "setRcsMessageListener", XC_MethodReplacement.DO_NOTHING);
            XposedBridge.hookAllMethods(extMsgClass, "isRcsAvailable", XC_MethodReplacement.returnConstant(Boolean.FALSE));
            XposedLog.i(TAG, "Hooked ExtMessagingExtensions to disable Samsung RCS");
        } catch (Throwable t) {
            XposedLog.w(TAG, "ExtMessagingExtensions hook skipped: " + t.getMessage());
        }
    }

    private static void hookJustInTips(ClassLoader classLoader) {
        // Hook JustInTipsUtils.getSemPlatformInt -> 140100 (OneUI 5.1)
        try {
            Class<?> tipsUtilsClass = XposedHelpers.findClass(
                "com.samsung.android.sdk.mdx.windowslink.tips.JustInTipsUtils",
                classLoader
            );
            XposedBridge.hookAllMethods(tipsUtilsClass, "getSemPlatformInt", XC_MethodReplacement.returnConstant(140100));
            XposedLog.i(TAG, "Hooked JustInTipsUtils.getSemPlatformInt -> 140100");
        } catch (Throwable t) {
            XposedLog.w(TAG, "JustInTipsUtils hook skipped: " + t.getMessage());
        }

        // Hook JustInTips.isSupported -> false
        try {
            Class<?> justInTipsClass = XposedHelpers.findClass(
                "com.samsung.android.sdk.mdx.windowslink.tips.JustInTips",
                classLoader
            );
            XposedBridge.hookAllMethods(justInTipsClass, "isSupported", XC_MethodReplacement.returnConstant(Boolean.FALSE));
            XposedLog.i(TAG, "Hooked JustInTips.isSupported -> false");
        } catch (Throwable t) {
            XposedLog.w(TAG, "JustInTips hook skipped: " + t.getMessage());
        }

        // Hook ExtTipsHelper.isAvailable -> false
        try {
            Class<?> tipsHelperClass = XposedHelpers.findClass(
                "com.microsoft.appmanager.ext.ExtTipsHelper",
                classLoader
            );
            XposedBridge.hookAllMethods(tipsHelperClass, "isAvailable", XC_MethodReplacement.returnConstant(Boolean.FALSE));
            XposedLog.i(TAG, "Hooked ExtTipsHelper.isAvailable -> false");
        } catch (Throwable t) {
            XposedLog.w(TAG, "ExtTipsHelper hook skipped: " + t.getMessage());
        }
    }

    private static final java.util.Set<ClassLoader> sInjectedClassLoaders =
            java.util.Collections.synchronizedSet(java.util.Collections.newSetFromMap(new java.util.WeakHashMap<ClassLoader, Boolean>()));

    private static void injectSamsungStubsDex(ClassLoader appClassLoader) {
        if (appClassLoader == null || !sInjectedClassLoaders.add(appClassLoader)) {
            return;
        }
        try {
            byte[] dexBytes = me.phonelink.xposed.stubs.EmbeddedSamsungStubsDex.getDexBytes();
            Object targetPathList = XposedHelpers.getObjectField(appClassLoader, "pathList");
            if (targetPathList == null) {
                XposedLog.w(TAG, "appClassLoader has null pathList: " + appClassLoader.getClass().getName());
                return;
            }
            Object[] targetElements = (Object[]) XposedHelpers.getObjectField(targetPathList, "dexElements");

            Class<?> imdclClass = Class.forName("dalvik.system.InMemoryDexClassLoader");
            ClassLoader stubLoader = (ClassLoader) imdclClass
                    .getConstructor(java.nio.ByteBuffer.class, ClassLoader.class)
                    .newInstance(java.nio.ByteBuffer.wrap(dexBytes), appClassLoader.getParent());

            Object stubPathList = XposedHelpers.getObjectField(stubLoader, "pathList");
            Object[] stubElements = (Object[]) XposedHelpers.getObjectField(stubPathList, "dexElements");

            Object[] merged = (Object[]) java.lang.reflect.Array.newInstance(
                    targetElements.getClass().getComponentType(),
                    targetElements.length + stubElements.length
            );
            System.arraycopy(targetElements, 0, merged, 0, targetElements.length);
            System.arraycopy(stubElements, 0, merged, targetElements.length, stubElements.length);
            XposedHelpers.setObjectField(targetPathList, "dexElements", merged);

            Class<?> resolvedFeature = Class.forName("com.samsung.android.feature.SemFloatingFeature", false, appClassLoader);
            Class<?> resolvedTemp = Class.forName("com.samsung.android.os.SemTemperatureManager", false, appClassLoader);
            Class<?> resolvedProps = Class.forName("android.os.SemSystemProperties", false, appClassLoader);
            Class<?> resolvedDex = Class.forName("com.samsung.android.desktopmode.SemDesktopModeState", false, appClassLoader);
            XposedLog.i(TAG, "Injected in-memory Samsung stubs DEX (" + dexBytes.length + "B, dexElements "
                    + targetElements.length + "->" + merged.length + ") resolved="
                    + resolvedFeature.getName() + "@" + resolvedFeature.getClassLoader()
                    + ", temp=" + resolvedTemp.getSimpleName()
                    + ", props=" + resolvedProps.getSimpleName()
                    + ", dex=" + resolvedDex.getSimpleName());
        } catch (Throwable t) {
            XposedLog.e(TAG, "Failed to inject in-memory Samsung stubs DEX into " + appClassLoader, t);
        }
    }

    private static void injectSemFloatingFeature(ClassLoader appClassLoader) {
        injectSamsungStubsDex(appClassLoader);

        try {
            XC_MethodHook classHook = new XC_MethodHook() {
                @Override
                protected void afterHookedMethod(MethodHookParam param) {
                    if (!param.hasThrowable() && param.getResult() != null) {
                        return;
                    }
                    String className = (String) param.args[0];
                    if ("com.samsung.android.feature.SemFloatingFeature".equals(className)) {
                        param.setResult(SemFloatingFeature.class);
                    } else if ("com.samsung.android.desktopmode.DesktopModeManager".equals(className) ||
                               "com.samsung.android.desktopmode.SemDesktopModeManager".equals(className)) {
                        param.setResult(com.samsung.android.desktopmode.SemDesktopModeManager.class);
                    } else if ("com.samsung.android.desktopmode.SemDesktopModeState".equals(className)) {
                        param.setResult(com.samsung.android.desktopmode.SemDesktopModeState.class);
                    } else if ("android.os.SemSystemProperties".equals(className)) {
                        param.setResult(android.os.SemSystemProperties.class);
                    } else if ("com.samsung.android.os.SemTemperatureManager".equals(className)) {
                        param.setResult(com.samsung.android.os.SemTemperatureManager.class);
                    } else if ("com.samsung.android.os.SemTemperatureManager$Thermistor".equals(className)) {
                        param.setResult(com.samsung.android.os.SemTemperatureManager.Thermistor.class);
                    }
                }
            };

            XposedHelpers.findAndHookMethod(ClassLoader.class, "loadClass", String.class, boolean.class, classHook);
            XposedHelpers.findAndHookMethod(ClassLoader.class, "loadClass", String.class, classHook);
            XposedLog.i(TAG, "SemFloatingFeature, SemSystemProperties, and DesktopMode dynamic class injection hooked successfully");
        } catch (Throwable t) {
            XposedLog.e(TAG, "Failed to hook ClassLoader.loadClass", t);
        }

        try {
            Class<?> semFloatingClass = XposedHelpers.findClassIfExists("com.samsung.android.feature.SemFloatingFeature", appClassLoader);
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
                XposedLog.i(TAG, "Directly hooked loaded SemFloatingFeature class in AppManager");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook loaded SemFloatingFeature: " + t.getMessage());
        }
    }

    private static void hookCompanionDevicePermission(ClassLoader classLoader) {
        // 1. Hook ExtCompanionDevicePermissionManagerImpl
        try {
            Class<?> implClass = XposedHelpers.findClass(
                "com.microsoft.appmanager.ext.companiondevice.ExtCompanionDevicePermissionManagerImpl",
                classLoader
            );
            if (implClass != null) {
                XposedBridge.hookAllMethods(implClass, "isAssociated", XC_MethodReplacement.returnConstant(Boolean.TRUE));
                XposedBridge.hookAllMethods(implClass, "isMediaProjectionPermanentlyGranted", XC_MethodReplacement.returnConstant(Boolean.TRUE));
                XposedBridge.hookAllMethods(implClass, "isCompanionDeviceAppStreamingSupported", XC_MethodReplacement.returnConstant(Boolean.TRUE));
                XposedBridge.hookAllMethods(implClass, "isVirtualDeviceStreamingSupported", XC_MethodReplacement.returnConstant(Boolean.TRUE));

                XposedBridge.hookAllMethods(implClass, "grantMediaProjection", new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) throws Throwable {
                        XposedLog.i(TAG, "ExtCompanionDevicePermissionManagerImpl.grantMediaProjection intercepted -> auto-granting");
                        if (param.args.length > 0 && param.args[0] != null) {
                            try {
                                XposedHelpers.callMethod(param.args[0], "onMediaProjectionGranted");
                                XposedLog.i(TAG, "Invoked onMediaProjectionGranted on callback");
                            } catch (Throwable t) {
                                XposedLog.w(TAG, "Failed to invoke onMediaProjectionGranted: " + t.getMessage());
                            }
                        }
                        param.setResult(null);
                    }
                });

                XposedBridge.hookAllMethods(implClass, "associate", new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) throws Throwable {
                        XposedLog.i(TAG, "ExtCompanionDevicePermissionManagerImpl.associate intercepted");
                        if (param.args.length > 0 && param.args[0] != null) {
                            try {
                                XposedHelpers.callMethod(param.args[0], "onAssociationSuccess");
                            } catch (Throwable ignored) {}
                        }
                        param.setResult(null);
                    }
                });
                XposedLog.i(TAG, "Hooked ExtCompanionDevicePermissionManagerImpl successfully");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "ExtCompanionDevicePermissionManagerImpl hooks skipped: " + t.getMessage());
        }

        // 2. Hook Samsung SDK CompanionDevicePermissionManager inside com.microsoft.appmanager
        try {
            Class<?> cdmClass = XposedHelpers.findClass(
                "com.samsung.android.sdk.mdx.windowslink.companiondevice.CompanionDevicePermissionManager",
                classLoader
            );
            if (cdmClass != null) {
                XposedBridge.hookAllMethods(cdmClass, "isAssociated", XC_MethodReplacement.returnConstant(Boolean.TRUE));
                XposedBridge.hookAllMethods(cdmClass, "isMediaProjectionPermanentlyGranted", XC_MethodReplacement.returnConstant(Boolean.TRUE));
                XposedLog.i(TAG, "Hooked Samsung CompanionDevicePermissionManager isAssociated & isMediaProjectionPermanentlyGranted -> true");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "Samsung CompanionDevicePermissionManager hook skipped: " + t.getMessage());
        }

        // 3. Hook ScreenScrapePermissionState & IScreenScrapePermissionState
        try {
            Class<?> intentClass = XposedHelpers.findClass("android.content.Intent", classLoader);
            Object dummyIntent = intentClass != null ? intentClass.newInstance() : null;

            Class<?> sspsClass = XposedHelpers.findClass(
                "com.microsoft.mmx.agents.permissions.mirroring.ScreenScrapePermissionState",
                classLoader
            );
            if (sspsClass != null) {
                XposedBridge.hookAllMethods(sspsClass, "isPermissionAvailable", XC_MethodReplacement.returnConstant(Boolean.TRUE));
                if (dummyIntent != null) {
                    XposedBridge.hookAllMethods(sspsClass, "getPermissionIntent", XC_MethodReplacement.returnConstant(dummyIntent));
                }
                XposedLog.i(TAG, "Hooked ScreenScrapePermissionState isPermissionAvailable -> true");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "ScreenScrapePermissionState hook skipped: " + t.getMessage());
        }

        // 4. Hook ExtScreenMirrorCapabilities
        try {
            Class<?> smcClass = XposedHelpers.findClass(
                "com.microsoft.appmanager.ext.ExtScreenMirrorCapabilities",
                classLoader
            );
            if (smcClass != null) {
                XposedBridge.hookAllMethods(smcClass, "isPermissionGranted", XC_MethodReplacement.returnConstant(Boolean.TRUE));
                XposedBridge.hookAllMethods(smcClass, "isCompanionDeviceAppStreamingSupported", XC_MethodReplacement.returnConstant(Boolean.TRUE));
                XposedBridge.hookAllMethods(smcClass, "isVirtualDeviceStreamingSupported", XC_MethodReplacement.returnConstant(Boolean.TRUE));
                // BlackScreen relies on Samsung SurfaceFlinger private flags to hide from MediaProjection
                // and on .spr drawables; disable it on AOSP so Phone Screen never captures a black overlay.
                XposedBridge.hookAllMethods(smcClass, "isBlackScreenSupported", XC_MethodReplacement.returnConstant(Boolean.FALSE));
                XposedBridge.hookAllMethods(smcClass, "isSecureBlackScreenSupported", XC_MethodReplacement.returnConstant(Boolean.FALSE));
                XposedLog.i(TAG, "Hooked ExtScreenMirrorCapabilities (mirroring=true, blackScreen=false)");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "ExtScreenMirrorCapabilities hook skipped: " + t.getMessage());
        }

        // 5. Hook ExtCompanionDeviceScreenMirroringPermissionAdapter
        try {
            Class<?> cdaClass = XposedHelpers.findClass(
                "com.microsoft.appmanager.ext.appremote.ExtCompanionDeviceScreenMirroringPermissionAdapter",
                classLoader
            );
            Class<?> statusClass = XposedHelpers.findClass(
                "com.microsoft.mmx.screenmirroringsrc.permission.MirrorPermissionStatus",
                classLoader
            );
            Class<?> intentClass = XposedHelpers.findClass("android.content.Intent", classLoader);
            Class<?> pairClass = XposedHelpers.findClass("kotlin.Pair", classLoader);

            if (cdaClass != null) {
                XposedBridge.hookAllMethods(cdaClass, "requestMediaProjectionPermission", XC_MethodReplacement.returnConstant(Boolean.TRUE));
                XposedBridge.hookAllMethods(cdaClass, "requestCompanionDeviceAppStreamingPermission", XC_MethodReplacement.returnConstant(Boolean.TRUE));

                if (statusClass != null && pairClass != null && intentClass != null) {
                    Object acceptedStatus = XposedHelpers.getStaticObjectField(statusClass, "ACCEPTED");
                    java.lang.reflect.Constructor<?> pairCtor = pairClass.getConstructor(Object.class, Object.class);
                    Object grantedPair = pairCtor.newInstance(acceptedStatus, intentClass.newInstance());

                    XposedBridge.hookAllMethods(cdaClass, "requestScreenScrapePermission", XC_MethodReplacement.returnConstant(grantedPair));
                    XposedBridge.hookAllMethods(cdaClass, "accessScreenScrapePermission", XC_MethodReplacement.returnConstant(grantedPair));
                    XposedLog.i(TAG, "Hooked ExtCompanionDeviceScreenMirroringPermissionAdapter -> MirrorPermissionStatus.ACCEPTED");
                } else {
                    XposedLog.w(TAG, "ExtCompanionDeviceScreenMirroringPermissionAdapter Pair hook skipped: missing MirrorPermissionStatus/Pair/Intent");
                }
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "ExtCompanionDeviceScreenMirroringPermissionAdapter hook skipped: " + t.getMessage());
        }

        // 6. Hook ExtLegacyScreenMirroringPermissionAdapter
        try {
            Class<?> legacyClass = XposedHelpers.findClass(
                "com.microsoft.appmanager.ext.appremote.ExtLegacyScreenMirroringPermissionAdapter",
                classLoader
            );
            Class<?> statusClass = XposedHelpers.findClass(
                "com.microsoft.mmx.screenmirroringsrc.permission.MirrorPermissionStatus",
                classLoader
            );
            Class<?> intentClass = XposedHelpers.findClass("android.content.Intent", classLoader);
            Class<?> pairClass = XposedHelpers.findClass("kotlin.Pair", classLoader);

            if (legacyClass != null && statusClass != null) {
                Object acceptedStatus = XposedHelpers.getStaticObjectField(statusClass, "ACCEPTED");

                XposedBridge.hookAllMethods(legacyClass, "checkPermission", XC_MethodReplacement.returnConstant(acceptedStatus));
                XposedBridge.hookAllMethods(legacyClass, "checkAndroidPermission", XC_MethodReplacement.returnConstant(acceptedStatus));
                XposedBridge.hookAllMethods(legacyClass, "checkOemAudioPermission", XC_MethodReplacement.returnConstant(acceptedStatus));
                XposedBridge.hookAllMethods(legacyClass, "requestAndroidPermission", XC_MethodReplacement.returnConstant(acceptedStatus));
                XposedBridge.hookAllMethods(legacyClass, "requestOemAudioPermission", XC_MethodReplacement.returnConstant(acceptedStatus));

                if (pairClass != null && intentClass != null) {
                    java.lang.reflect.Constructor<?> pairCtor = pairClass.getConstructor(Object.class, Object.class);
                    Object acceptedPair = pairCtor.newInstance(acceptedStatus, intentClass.newInstance());

                    XposedBridge.hookAllMethods(legacyClass, "requestPermission", XC_MethodReplacement.returnConstant(acceptedPair));
                    XposedBridge.hookAllMethods(legacyClass, "requestScreenScrapePermission", XC_MethodReplacement.returnConstant(acceptedPair));
                    XposedBridge.hookAllMethods(legacyClass, "accessScreenScrapePermission", XC_MethodReplacement.returnConstant(acceptedPair));
                }
                XposedLog.i(TAG, "Hooked ExtLegacyScreenMirroringPermissionAdapter -> auto-accepted");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "ExtLegacyScreenMirroringPermissionAdapter hook skipped: " + t.getMessage());
        }
    }

    private static void hookRecentTasksGuard(ClassLoader classLoader) {
        try {
            Class<?> recentTaskClass = XposedHelpers.findClass(
                "com.microsoft.appmanager.ext.appremote.ExtRecentTaskProvider",
                classLoader
            );
            if (recentTaskClass != null) {
                XposedBridge.hookAllMethods(recentTaskClass, "getRecentTasks", new XC_MethodHook() {
                    @Override
                    protected void afterHookedMethod(MethodHookParam param) {
                        if (param.getResult() == null) {
                            param.setResult(java.util.Collections.emptyList());
                        }
                    }
                });
                XposedLog.i(TAG, "Hooked ExtRecentTaskProvider.getRecentTasks -> empty list guard applied");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "ExtRecentTaskProvider hook skipped: " + t.getMessage());
        }

        try {
            Class<?> recentSubscriberClass = XposedHelpers.findClass(
                "com.microsoft.mmx.agents.taskcontinuity.subscriber.RecentTaskSubscriber",
                classLoader
            );
            if (recentSubscriberClass != null) {
                XposedBridge.hookAllMethods(recentSubscriberClass, "getRecentTaskList", new XC_MethodHook() {
                    @Override
                    protected void afterHookedMethod(MethodHookParam param) {
                        if (param.getResult() == null) {
                            param.setResult(java.util.Collections.emptyList());
                        }
                    }
                });
                XposedLog.i(TAG, "Hooked RecentTaskSubscriber.getRecentTaskList -> empty list guard applied");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "RecentTaskSubscriber hook skipped: " + t.getMessage());
        }
    }

    private static void hookAppExecutionServiceManager(ClassLoader classLoader) {
        try {
            Class<?> managerClass = XposedHelpers.findClass(
                "com.samsung.android.sdk.mdx.windowslink.appsonwindows.appexecutioncontainer.AppExecutionServiceManager",
                classLoader
            );
            if (managerClass != null) {
                XposedBridge.hookAllMethods(managerClass, "init", new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) {
                        param.setResult(Boolean.TRUE);
                    }
                });
                XposedLog.i(TAG, "Hooked AppExecutionServiceManager.init -> returns true directly");
            }
        } catch (Throwable t) {
            XposedLog.w(TAG, "AppExecutionServiceManager hook skipped: " + t.getMessage());
        }
    }
}
