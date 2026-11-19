package me.phonelink.xposed.stubs;

import android.content.Context;

/**
 * SmartClip and S-Pen stubs for Link to Windows and MDX service.
 */
public class SmartClipStubs {

    public static class SemSmartClipDataRepository {
        public SemSmartClipDataRepository() {}
        public int getCapturedImageFileStyle() { return 0; }
        public String getCapturedImageFilePath() { return null; }
    }

    public static class SemSmartClipDataElement {
        public SemSmartClipDataElement() {}
    }

    public static class SemSmartClipDataCropper {
        public SemSmartClipDataCropper() {}
        public int doCrop() { return 0; }
    }

    public static class SpenGestureManager {
        public SpenGestureManager() {}
        public SpenGestureManager(Context context) {}
        public boolean isBleSpenConnected() { return false; }
        public void writeBleSpenCommand(String command) {}
    }
}
