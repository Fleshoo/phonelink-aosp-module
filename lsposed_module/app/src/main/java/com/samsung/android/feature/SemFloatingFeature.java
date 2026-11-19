package com.samsung.android.feature;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Synthetic in-memory stub for Samsung SemFloatingFeature.
 * Provides feature flags required by com.microsoft.appmanager and com.samsung.android.mdx.
 */
public final class SemFloatingFeature {

    private static volatile SemFloatingFeature sInstance;
    private final Map<String, Object> mFeatures = new ConcurrentHashMap<>();

    private SemFloatingFeature() {
        // Core Link to Windows & Screen Mirroring features
        mFeatures.put("SEC_FLOATING_FEATURE_COMMON_SUPPORT_LINK_TO_WINDOWS", Boolean.TRUE);
        mFeatures.put("SEC_FLOATING_FEATURE_LINK_TO_WINDOWS", Boolean.TRUE);
        mFeatures.put("SEC_FLOATING_FEATURE_COMMON_SUPPORT_LTW_REMOTE_APP", Boolean.TRUE);

        // Brand & Default Samsung package configurations
        mFeatures.put("SEC_FLOATING_FEATURE_SETTINGS_CONFIG_BRAND_NAME", "Samsung");
        mFeatures.put("SEC_FLOATING_FEATURE_SIP_CONFIG_PACKAGE_NAME", "com.samsung.android.honeyboard");
        mFeatures.put("SEC_FLOATING_FEATURE_MESSAGE_CONFIG_PACKAGE_NAME", "com.samsung.android.messaging");
        mFeatures.put("SEC_FLOATING_FEATURE_SMARTMANAGER_CONFIG_PACKAGE_NAME", "com.samsung.android.lool");
        mFeatures.put("SEC_FLOATING_FEATURE_AUDIO_SUPPORT_SOUND_ALIVE", Boolean.TRUE);

        // Hardware exemptions (Mi 9 is standard candy-bar form factor, no Knox hardware chip)
        mFeatures.put("SEC_FLOATING_FEATURE_COMMON_SUPPORT_KNOX", Boolean.FALSE);
        mFeatures.put("SEC_FLOATING_FEATURE_CONTEXTSERVICE_ENABLE_SURVEY_MODE", Boolean.FALSE);
        mFeatures.put("SEC_FLOATING_FEATURE_FRAMEWORK_SUPPORT_FOLDABLE_TYPE_FLIP", Boolean.FALSE);
        mFeatures.put("SEC_FLOATING_FEATURE_FRAMEWORK_SUPPORT_FOLDABLE_TYPE_FOLD", Boolean.FALSE);
        mFeatures.put("SEC_FLOATING_FEATURE_FRAMEWORK_SUPPORT_MULTI_FOLD", Boolean.FALSE);
        mFeatures.put("SEC_FLOATING_FEATURE_FRAMEWORK_SUPPORT_HALF_FOLDED_MODE", Boolean.FALSE);
        mFeatures.put("SEC_FLOATING_FEATURE_FRAMEWORK_SUPPORT_SECONDARY_DISPLAY_AS_COVER", Boolean.FALSE);
    }

    public static SemFloatingFeature getInstance() {
        if (sInstance == null) {
            synchronized (SemFloatingFeature.class) {
                if (sInstance == null) {
                    sInstance = new SemFloatingFeature();
                }
            }
        }
        return sInstance;
    }

    public static void resetInstance() {
        synchronized (SemFloatingFeature.class) {
            sInstance = null;
        }
    }

    public boolean getBoolean(String tag) {
        return getBoolean(tag, false);
    }

    public boolean getBoolean(String tag, boolean defaultValue) {
        if (tag == null) return defaultValue;
        Object val = mFeatures.get(tag);
        if (val instanceof Boolean) {
            return (Boolean) val;
        }
        return defaultValue;
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
        if (val != null) {
            return val.toString();
        }
        return defaultValue;
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

    public void setFeature(String tag, Object value) {
        if (tag != null && value != null) {
            mFeatures.put(tag, value);
        }
    }
}
