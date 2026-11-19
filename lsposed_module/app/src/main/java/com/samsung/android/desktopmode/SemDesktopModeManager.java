package com.samsung.android.desktopmode;

import android.content.Context;
import android.os.Bundle;
import android.os.IBinder;

public class SemDesktopModeManager {

    public interface DesktopModeListener {
        default void onDesktopModeChanged(boolean enabled) {}
        default void onDesktopModeStateChanged(SemDesktopModeState state) {}
    }

    public interface DesktopModeBlocker {
        String onBlock();
    }

    public interface EventListener {
        void onChange(boolean enabled);
    }

    public interface OnMessageReceivedListener {
        void onMessageReceived(Bundle bundle);
    }

    public SemDesktopModeManager() {}

    public SemDesktopModeManager(Context context, Object service) {
        // Empty stub constructor
    }

    public static boolean isDesktopMode() {
        return false;
    }

    public static boolean isDesktopDockConnected() {
        return false;
    }

    public boolean isDeviceConnected() {
        return false;
    }

    public boolean isAllowed() {
        return false;
    }

    public SemDesktopModeState getDesktopModeState() {
        return new SemDesktopModeState();
    }

    public void registerListener(DesktopModeListener listener) {}
    public void unregisterListener(DesktopModeListener listener) {}

    public void registerBlocker(DesktopModeBlocker blocker) {}
    public void unregisterBlocker(DesktopModeBlocker blocker) {}

    public static void registerListener(EventListener listener) {}
    public static void unregisterListener(EventListener listener) {}

    public boolean setOnMessageReceivedListener(OnMessageReceivedListener listener) {
        return false;
    }

    public Bundle sendMessage(Bundle bundle) {
        return new Bundle();
    }

    public void forceSetHdmiSettings(boolean enabled) {}
    public void onSecuredAppLaunched(IBinder token, String pkg) {}
}
