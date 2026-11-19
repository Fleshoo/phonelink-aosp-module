package me.phonelink.xposed.hooks;

import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.content.pm.SigningInfo;
import android.os.Build;

import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;
import me.phonelink.xposed.utils.CertConstants;
import me.phonelink.xposed.utils.XposedLog;

public class PackageManagerHooks {
    private static final String TAG = "PackageManagerHooks";
    public static final String TARGET_MDX = "com.samsung.android.mdx";
    public static final String TARGET_APPMANAGER = "com.microsoft.appmanager";

    public static void init(XC_LoadPackage.LoadPackageParam lpparam) {
        hookApplicationPackageManager(lpparam.classLoader);
    }

    private static void hookApplicationPackageManager(ClassLoader classLoader) {
        Class<?> appPkgMgrClass;
        try {
            appPkgMgrClass = XposedHelpers.findClass("android.app.ApplicationPackageManager", classLoader);
        } catch (Throwable t) {
            XposedLog.e(TAG, "Failed to locate android.app.ApplicationPackageManager", t);
            return;
        }

        // 1. Hook getPackageInfo(String, int)
        try {
            XposedHelpers.findAndHookMethod(
                appPkgMgrClass,
                "getPackageInfo",
                String.class,
                int.class,
                new XC_MethodHook() {
                    @Override
                    protected void afterHookedMethod(MethodHookParam param) throws Throwable {
                        handleGetPackageInfoAfter(param);
                    }
                }
            );
            XposedLog.i(TAG, "Hooked ApplicationPackageManager.getPackageInfo(String, int)");
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook getPackageInfo(String, int): " + t.getMessage());
        }

        // 2. Hook getPackageInfo(String, PackageInfoFlags) (Android 13+ / SDK 33+)
        if (Build.VERSION.SDK_INT >= 33) {
            try {
                Class<?> flagsClass = XposedHelpers.findClass("android.content.pm.PackageManager$PackageInfoFlags", classLoader);
                XposedHelpers.findAndHookMethod(
                    appPkgMgrClass,
                    "getPackageInfo",
                    String.class,
                    flagsClass,
                    new XC_MethodHook() {
                        @Override
                        protected void afterHookedMethod(MethodHookParam param) throws Throwable {
                            handleGetPackageInfoAfter(param);
                        }
                    }
                );
                XposedLog.i(TAG, "Hooked ApplicationPackageManager.getPackageInfo(String, PackageInfoFlags)");
            } catch (Throwable t) {
                XposedLog.w(TAG, "Failed to hook getPackageInfo(String, PackageInfoFlags): " + t.getMessage());
            }
        }

        // 3. Hook getPackageInfoAsUser(String, int, int)
        try {
            XposedHelpers.findAndHookMethod(
                appPkgMgrClass,
                "getPackageInfoAsUser",
                String.class,
                int.class,
                int.class,
                new XC_MethodHook() {
                    @Override
                    protected void afterHookedMethod(MethodHookParam param) throws Throwable {
                        handleGetPackageInfoAfter(param);
                    }
                }
            );
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook getPackageInfoAsUser(String, int, int): " + t.getMessage());
        }

        // 4. Hook getPackageInfoAsUser(String, PackageInfoFlags, int) (Android 13+)
        if (Build.VERSION.SDK_INT >= 33) {
            try {
                Class<?> flagsClass = XposedHelpers.findClass("android.content.pm.PackageManager$PackageInfoFlags", classLoader);
                XposedHelpers.findAndHookMethod(
                    appPkgMgrClass,
                    "getPackageInfoAsUser",
                    String.class,
                    flagsClass,
                    int.class,
                    new XC_MethodHook() {
                        @Override
                        protected void afterHookedMethod(MethodHookParam param) throws Throwable {
                            handleGetPackageInfoAfter(param);
                        }
                    }
                );
            } catch (Throwable t) {
                XposedLog.w(TAG, "Failed to hook getPackageInfoAsUser(String, PackageInfoFlags, int): " + t.getMessage());
            }
        }

        // 5. Hook checkSignatures(String, String) -> Always match between AppManager and MDX
        try {
            XposedHelpers.findAndHookMethod(
                appPkgMgrClass,
                "checkSignatures",
                String.class,
                String.class,
                new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) throws Throwable {
                        String pkg1 = (String) param.args[0];
                        String pkg2 = (String) param.args[1];
                        if (isTargetPair(pkg1, pkg2)) {
                            XposedLog.d(TAG, "checkSignatures matched for target pair: " + pkg1 + " <-> " + pkg2);
                            param.setResult(PackageManager.SIGNATURE_MATCH);
                        }
                    }
                }
            );
            XposedLog.i(TAG, "Hooked ApplicationPackageManager.checkSignatures(String, String)");
        } catch (Throwable t) {
            XposedLog.w(TAG, "Failed to hook checkSignatures: " + t.getMessage());
        }

        // 6. Hook hasSigningCertificate(String, byte[], int) (Android 9+)
        if (Build.VERSION.SDK_INT >= 28) {
            try {
                XposedHelpers.findAndHookMethod(
                    appPkgMgrClass,
                    "hasSigningCertificate",
                    String.class,
                    byte[].class,
                    int.class,
                    new XC_MethodHook() {
                        @Override
                        protected void beforeHookedMethod(MethodHookParam param) throws Throwable {
                            String pkg = (String) param.args[0];
                            if (TARGET_MDX.equals(pkg)) {
                                param.setResult(true);
                            }
                        }
                    }
                );
            } catch (Throwable t) {
                XposedLog.w(TAG, "Failed to hook hasSigningCertificate: " + t.getMessage());
            }
        }
    }

    private static boolean isTargetPair(String pkg1, String pkg2) {
        if (pkg1 == null || pkg2 == null) return false;
        return (TARGET_APPMANAGER.equals(pkg1) && TARGET_MDX.equals(pkg2)) ||
               (TARGET_MDX.equals(pkg1) && TARGET_APPMANAGER.equals(pkg2));
    }

    private static void handleGetPackageInfoAfter(XC_MethodHook.MethodHookParam param) {
        String pkgName = (String) param.args[0];
        if (!TARGET_MDX.equals(pkgName)) return;

        PackageInfo pi = (PackageInfo) param.getResult();
        if (pi == null) return;

        // 1. Inject genuine Samsung signature into legacy signatures array
        Signature oemSig = CertConstants.getSamsungMdxSignature();
        pi.signatures = new Signature[] { oemSig };

        // 2. Inject genuine Samsung signature into modern SigningInfo (API 28+)
        if (Build.VERSION.SDK_INT >= 28) {
            try {
                SigningInfo spoofed = CertConstants.createSigningInfo(oemSig);
                if (spoofed != null) {
                    pi.signingInfo = spoofed;
                }
            } catch (Throwable t) {
                XposedLog.e(TAG, "Failed to inject spoofed SigningInfo", t);
            }
        }
        XposedLog.d(TAG, "Successfully spoofed OEM certificate signatures for " + pkgName);
    }
}
