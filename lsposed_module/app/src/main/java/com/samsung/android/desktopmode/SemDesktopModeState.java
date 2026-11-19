package com.samsung.android.desktopmode;

public class SemDesktopModeState {
    public static final int DISABLED = 0;
    public static final int DISABLING = 1;
    public static final int ENABLING = 3;
    public static final int ENABLED = 4;

    public static final int DISPLAY_TYPE_NONE = 0;
    public static final int DISPLAY_TYPE_STANDALONE = 101;
    public static final int DISPLAY_TYPE_DUAL = 102;

    public int enabled = DISABLED;
    public int state = DISABLED;
    public int displayType = DISPLAY_TYPE_NONE;

    public SemDesktopModeState() {}

    public SemDesktopModeState(int enabled, int state) {
        this.enabled = enabled;
        this.state = state;
    }

    public SemDesktopModeState(int enabled, int state, int displayType) {
        this.enabled = enabled;
        this.state = state;
        this.displayType = displayType;
    }

    public int getEnabled() {
        return enabled;
    }

    public int getState() {
        return state;
    }

    public int getDisplayType() {
        return displayType;
    }
}
