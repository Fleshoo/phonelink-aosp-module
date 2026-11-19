package android.os;

/**
 * Samsung SemSystemProperties stub implementation for AOSP / Project Infinity X.
 * Emulates Samsung's framework wrapper around android.os.SystemProperties,
 * satisfying getAssetCategory() and OneUI version checks in Link to Windows.
 */
public class SemSystemProperties {

    public static String get(String key) {
        return get(key, "");
    }

    public static String get(String key, String def) {
        if ("ro.build.characteristics".equals(key)) {
            return "phone";
        }
        if ("ro.product.manufacturer".equals(key) || "ro.product.brand".equals(key)) {
            return "samsung";
        }
        if ("ro.product.model".equals(key)) {
            return "SM-G998B";
        }
        if ("ro.build.version.sem".equals(key)) {
            return "5001";
        }
        if ("ro.product_ship".equals(key)) {
            return "true";
        }
        try {
            Class<?> sp = Class.forName("android.os.SystemProperties");
            java.lang.reflect.Method m = sp.getMethod("get", String.class, String.class);
            return (String) m.invoke(null, key, def);
        } catch (Throwable t) {
            return def;
        }
    }

    public static int getInt(String key, int def) {
        if ("ro.build.version.sem".equals(key)) {
            return 5001;
        }
        try {
            Class<?> sp = Class.forName("android.os.SystemProperties");
            java.lang.reflect.Method m = sp.getMethod("getInt", String.class, int.class);
            return (Integer) m.invoke(null, key, def);
        } catch (Throwable t) {
            return def;
        }
    }

    public static long getLong(String key, long def) {
        try {
            Class<?> sp = Class.forName("android.os.SystemProperties");
            java.lang.reflect.Method m = sp.getMethod("getLong", String.class, long.class);
            return (Long) m.invoke(null, key, def);
        } catch (Throwable t) {
            return def;
        }
    }

    public static boolean getBoolean(String key, boolean def) {
        if ("ro.product_ship".equals(key)) {
            return true;
        }
        try {
            Class<?> sp = Class.forName("android.os.SystemProperties");
            java.lang.reflect.Method m = sp.getMethod("getBoolean", String.class, boolean.class);
            return (Boolean) m.invoke(null, key, def);
        } catch (Throwable t) {
            return def;
        }
    }

    public static void set(String key, String val) {
        // no-op
    }
}
