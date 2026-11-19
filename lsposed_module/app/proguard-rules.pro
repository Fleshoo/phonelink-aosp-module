# Preserve Xposed entrypoint
-keep class me.phonelink.xposed.XposedInit { *; }

# Preserve dynamic in-memory stubs
-keep class com.samsung.android.feature.SemFloatingFeature { *; }
-keep class com.samsung.android.desktopmode.** { *; }
-keep class com.samsung.android.content.smartclip.** { *; }

# Preserve module stubs and utilities
-keep class me.phonelink.xposed.stubs.** { *; }
-keep class me.phonelink.xposed.utils.** { *; }
-keep class me.phonelink.xposed.hooks.** { *; }

# Preserve Xposed API references
-dontwarn de.robv.android.xposed.**
-keep class de.robv.android.xposed.** { *; }
