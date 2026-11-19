package me.phonelink.xposed.stubs;

/**
 * Stubs for One UI version detection.
 * SEM_INT = 5001 corresponds to One UI 5.1 (Project Infinity X Android 16 target).
 * SEM_PLATFORM_INT = 140100 corresponds to One UI 5.1 platform version.
 */
public class OneUIStubs {
    public static final int SEM_INT = 5001;
    public static final int SEM_PLATFORM_INT = 140100;
    public static final int SEM_INT_COMPAT = 3001;

    public static int getSemIntValue() {
        return SEM_INT;
    }

    public static int getSemPlatformIntValue() {
        return SEM_PLATFORM_INT;
    }

    public static boolean isOneUI2_1OrLater() {
        return true;
    }

    public static boolean isDesktopMode() {
        return false;
    }

    public static boolean isSmartClipSupported() {
        return false;
    }
}
