package me.phonelink.xposed.stubs;

import java.util.HashMap;
import java.util.Map;

/**
 * In-memory synthetic replacement for com.samsung.android.feature.SemFloatingFeature.
 * Eliminates NoClassDefFoundError on AOSP bootclasspath.
 */
public class SemFloatingFeatureStub {
    private static volatile SemFloatingFeatureStub sInstance;
    private final Map<String, Object> mFeatures = new HashMap<>();

    private SemFloatingFeatureStub() {
        mFeatures.put("SEC_FLOATING_FEATURE_COMMON_SUPPORT_LINK_TO_WINDOWS", Boolean.TRUE);
        mFeatures.put("SEC_FLOATING_FEATURE_LINK_TO_WINDOWS", Boolean.TRUE);
        mFeatures.put("SEC_FLOATING_FEATURE_COMMON_SUPPORT_LTW_REMOTE_APP", Boolean.TRUE);
        mFeatures.put("SEC_FLOATING_FEATURE_COMMON_SUPPORT_KNOX", Boolean.FALSE);
        mFeatures.put("SEC_FLOATING_FEATURE_SETTINGS_CONFIG_BRAND_NAME", "Samsung");
        mFeatures.put("SEC_FLOATING_FEATURE_SIP_CONFIG_PACKAGE_NAME", "com.samsung.android.honeyboard");
        mFeatures.put("SEC_FLOATING_FEATURE_MESSAGE_CONFIG_PACKAGE_NAME", "com.samsung.android.messaging");
        mFeatures.put("SEC_FLOATING_FEATURE_SMARTMANAGER_CONFIG_PACKAGE_NAME", "com.samsung.android.lool");
        mFeatures.put("SEC_FLOATING_FEATURE_AUDIO_SUPPORT_SOUND_ALIVE", Boolean.TRUE);
        mFeatures.put("SEC_FLOATING_FEATURE_CONTEXTSERVICE_ENABLE_SURVEY_MODE", Boolean.FALSE);
        mFeatures.put("SEC_FLOATING_FEATURE_FRAMEWORK_SUPPORT_FOLDABLE_TYPE_FLIP", Boolean.FALSE);
        mFeatures.put("SEC_FLOATING_FEATURE_FRAMEWORK_SUPPORT_FOLDABLE_TYPE_FOLD", Boolean.FALSE);
        mFeatures.put("SEC_FLOATING_FEATURE_FRAMEWORK_SUPPORT_HALF_FOLDED_MODE", Boolean.FALSE);
        mFeatures.put("SEC_FLOATING_FEATURE_FRAMEWORK_SUPPORT_SECONDARY_DISPLAY_AS_COVER", Boolean.FALSE);
    }

    public static SemFloatingFeatureStub getInstance() {
        if (sInstance == null) {
            synchronized (SemFloatingFeatureStub.class) {
                if (sInstance == null) {
                    sInstance = new SemFloatingFeatureStub();
                }
            }
        }
        return sInstance;
    }

    public static void resetInstance() {
        synchronized (SemFloatingFeatureStub.class) {
            sInstance = null;
        }
    }

    public boolean getBoolean(String tag) {
        return getBoolean(tag, false);
    }

    public boolean getBoolean(String tag, boolean defaultValue) {
        if (tag == null) return defaultValue;
        Object val = mFeatures.get(tag);
        return (val instanceof Boolean) ? (Boolean) val : defaultValue;
    }

    public boolean getEnableStatus(String tag) {
        return getBoolean(tag, false);
    }

    public String getString(String tag) {
        return getString(tag, "");
    }

    public String getString(String tag, String defaultValue) {
        if (tag == null) return defaultValue;
        Object val = mFeatures.get(tag);
        return (val != null) ? val.toString() : defaultValue;
    }

    public int getInt(String tag) {
        return getInt(tag, 0);
    }

    public int getInt(String tag, int defaultValue) {
        if (tag == null) return defaultValue;
        Object val = mFeatures.get(tag);
        if (val instanceof Number) {
            return ((Number) val).intValue();
        }
        return defaultValue;
    }

    public int getInteger(String tag, int defaultValue) {
        return getInt(tag, defaultValue);
    }
}
