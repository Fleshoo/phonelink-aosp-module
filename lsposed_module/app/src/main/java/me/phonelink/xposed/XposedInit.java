package me.phonelink.xposed;

import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.IXposedHookZygoteInit;
import de.robv.android.xposed.callbacks.XC_LoadPackage;
import me.phonelink.xposed.hooks.AppManagerHooks;
import me.phonelink.xposed.hooks.InputInjectionHooks;
import me.phonelink.xposed.hooks.MdxServiceHooks;
import me.phonelink.xposed.hooks.MdxVersionHooks;
import me.phonelink.xposed.hooks.PackageManagerHooks;
import me.phonelink.xposed.hooks.SystemServerHooks;
import me.phonelink.xposed.hooks.VideoCodecHooks;
import me.phonelink.xposed.utils.XposedLog;

public class XposedInit implements IXposedHookLoadPackage, IXposedHookZygoteInit {
    private static final String TAG = "PhoneLinkInit";

    public static final String PKG_MICROSOFT_APPMANAGER = "com.microsoft.appmanager";
    public static final String PKG_SAMSUNG_MDX = "com.samsung.android.mdx";
    public static final String PKG_SYSTEM_SERVER = "android";

    @Override
    public void initZygote(StartupParam startupParam) throws Throwable {
        XposedLog.i(TAG, "PhoneLink LSPosed Companion Module Zygote Initialized");
    }

    @Override
    public void handleLoadPackage(XC_LoadPackage.LoadPackageParam lpparam) throws Throwable {
        if (lpparam == null || lpparam.packageName == null) return;

        switch (lpparam.packageName) {
            case PKG_MICROSOFT_APPMANAGER:
                XposedLog.i(TAG, "Dispatching hooks for Microsoft AppManager (" + lpparam.processName + ")");
                AppManagerHooks.init(lpparam);
                PackageManagerHooks.init(lpparam);
                VideoCodecHooks.init(lpparam);
                break;

            case PKG_SAMSUNG_MDX:
                XposedLog.i(TAG, "Dispatching hooks for Samsung MDX Service (" + lpparam.processName + ")");
                AppManagerHooks.init(lpparam);
                MdxVersionHooks.init(lpparam);
                MdxServiceHooks.init(lpparam);
                InputInjectionHooks.init(lpparam);
                PackageManagerHooks.init(lpparam);
                VideoCodecHooks.init(lpparam);
                break;

            case PKG_SYSTEM_SERVER:
                if ("android".equals(lpparam.processName) || "system_server".equals(lpparam.processName)) {
                    XposedLog.i(TAG, "Dispatching hooks for system_server");
                    SystemServerHooks.init(lpparam);
                }
                break;

            default:
                break;
        }
    }
}
