package me.phonelink.xposed.utils;

import android.util.Log;

public class XposedLog {
    private static final String PREFIX = "[PhoneLink] ";

    public static void d(String tag, String msg) {
        try {
            Log.d(tag, PREFIX + msg);
        } catch (Throwable ignored) {}
    }

    public static void i(String tag, String msg) {
        try {
            Log.i(tag, PREFIX + msg);
        } catch (Throwable ignored) {}
        try {
            de.robv.android.xposed.XposedBridge.log(PREFIX + tag + ": " + msg);
        } catch (Throwable ignored) {}
    }

    public static void w(String tag, String msg) {
        try {
            Log.w(tag, PREFIX + msg);
        } catch (Throwable ignored) {}
        try {
            de.robv.android.xposed.XposedBridge.log(PREFIX + "WARN " + tag + ": " + msg);
        } catch (Throwable ignored) {}
    }

    public static void e(String tag, String msg, Throwable t) {
        try {
            Log.e(tag, PREFIX + msg, t);
        } catch (Throwable ignored) {}
        try {
            de.robv.android.xposed.XposedBridge.log(PREFIX + "ERR " + tag + ": " + msg + (t != null ? " - " + t.getMessage() : ""));
        } catch (Throwable ignored) {}
    }
}
