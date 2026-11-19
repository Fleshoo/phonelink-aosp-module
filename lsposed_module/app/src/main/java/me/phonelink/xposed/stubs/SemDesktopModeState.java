package me.phonelink.xposed.stubs;

public class SemDesktopModeState {
    public static final int DISABLED = 0;
    public static final int ENABLING = 1;
    public static final int ENABLED = 2;
    public static final int DISABLING = 3;

    public int getEnabled() {
        return DISABLED;
    }

    public int getState() {
        return DISABLED;
    }

    public int getDisplayType() {
        return 0;
    }
}
