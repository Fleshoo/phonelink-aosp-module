#!/system/bin/sh
##########################################################################################
# customize.sh - Magisk Module Customization & Installation Script
# Target Device: Xiaomi Mi 9 (cepheus, Android 16 AOSP, arm64-v8a)
##########################################################################################

ui_print "*********************************************************"
ui_print "   Samsung Link to Windows (Phone Link) Port            "
ui_print "   Target: Xiaomi Mi 9 (cepheus, Android 16 AOSP)        "
ui_print "   Hybrid Architecture: Magisk Overlay + LSPosed Engine  "
ui_print "*********************************************************"

# 1. Device Architecture Validation
ui_print "- Checking device CPU architecture: $ARCH..."
if [ "$ARCH" != "arm64" ]; then
    ui_print "*********************************************************"
    ui_print "! Unsupported architecture: $ARCH"
    ui_print "! This module requires arm64-v8a (Xiaomi Mi 9 Snapdragon 855)."
    ui_print "*********************************************************"
    abort "Architecture check failed."
fi

# 2. Android API Level Validation
ui_print "- Checking Android API level: $API..."
if [ "$API" -lt 33 ]; then
    ui_print "! Unsupported Android version: API $API"
    ui_print "! Android 13+ (API 33+) is required (target: Android 16, API 36)."
    abort "Android API level too low."
fi

# 3. Clean up conflicting user-space installations and legacy modules
ui_print "- Cleaning up conflicting legacy ports and stale state..."

# 3a. Remove legacy AyraHikari / SamsungPhoneLinkPort modules from Magisk directory
for old_mod in SamsungPhoneLinkPort SamsungPhoneLink ayra_samsung_phonelink; do
    if [ -d "/data/adb/modules/$old_mod" ]; then
        ui_print "- Removing old conflicting Magisk module: $old_mod..."
        rm -rf "/data/adb/modules/$old_mod"
        rm -rf "/data/adb/modules_update/$old_mod" 2>/dev/null || true
    fi
done

# 3b. Remove user-space APKs and old port packages that shadow priv-app
MDX_PKG="com.samsung.android.mdx"
EXISTING_PATH=$(pm path $MDX_PKG 2>/dev/null | head -n 1 | cut -d: -f2)
if [ -n "$EXISTING_PATH" ] && echo "$EXISTING_PATH" | grep -q "^/data/"; then
    ui_print "- Found user-installed $MDX_PKG at: $EXISTING_PATH"
    ui_print "- Removing user-space APK to enable privileged system overlay..."
    pm uninstall $MDX_PKG >/dev/null 2>&1 || true
fi

# 3c. Remove old Ayra Xposed app if installed as standalone APK
pm uninstall me.ayra.samsung.mdx >/dev/null 2>&1 || true
pm uninstall me.ayra.samsung.mdx.lsposed >/dev/null 2>&1 || true

# 3d. Clear corrupted app data / crash cache of Link to Windows
ui_print "- Clearing app data and cache for Link to Windows..."
pm clear com.microsoft.appmanager >/dev/null 2>&1 || true
pm clear $MDX_PKG >/dev/null 2>&1 || true

# 3e. Invalidate Package Manager cache for clean rebuild
rm -rf /data/system/package_cache/* 2>/dev/null || true

# 4. Verify Presence of Critical Files in $MODPATH
ui_print "- Verifying module system payload..."
PAYLOAD_APK="$MODPATH/system/priv-app/LinkToWindowsService/LinkToWindowsService.apk"
PERM_XML="$MODPATH/system/etc/permissions/privapp-permissions-phonelink.xml"
FEAT_XML="$MODPATH/system/etc/permissions/com.samsung.feature.samsung_experience_mobile.xml"
WHITELIST_XML="$MODPATH/system/etc/sysconfig/phonelink-whitelist.xml"

if [ ! -f "$PAYLOAD_APK" ]; then
    ui_print "! Missing privileged service APK: $PAYLOAD_APK"
    abort "Installation payload incomplete."
fi

if [ ! -f "$PERM_XML" ] || [ ! -f "$WHITELIST_XML" ] || [ ! -f "$FEAT_XML" ]; then
    ui_print "! Missing system permission or sysconfig XML files!"
    abort "System configuration payload incomplete."
fi

# 5. Set Standard System Permissions
ui_print "- Setting permissions..."
# 0755 for directories, 0644 for system files (APKs, XMLs)
set_perm_recursive "$MODPATH/system" 0 0 0755 0644

# 0755 for executable daemon and lifecycle scripts
if [ -f "$MODPATH/service.sh" ]; then
    set_perm "$MODPATH/service.sh" 0 0 0755
fi

if [ -f "$MODPATH/uninstall.sh" ]; then
    set_perm "$MODPATH/uninstall.sh" 0 0 0755
fi

if [ -f "$MODPATH/post-fs-data.sh" ]; then
    set_perm "$MODPATH/post-fs-data.sh" 0 0 0755
fi

# 6. Hardware Input Bridge Permissions (/dev/uinput and /dev/uhid)
ui_print "- Configuring input bridge permissions..."
if [ -e /dev/uinput ]; then
    chmod 0666 /dev/uinput 2>/dev/null || true
fi
if [ -e /dev/uhid ]; then
    chmod 0666 /dev/uhid 2>/dev/null || true
fi
if command -v magiskpolicy >/dev/null 2>&1; then
    magiskpolicy --live "allow priv_app uinput_device chr_file { read write open ioctl getattr }" 2>/dev/null || true
    magiskpolicy --live "allow system_app uinput_device chr_file { read write open ioctl getattr }" 2>/dev/null || true
    magiskpolicy --live "allow platform_app uinput_device chr_file { read write open ioctl getattr }" 2>/dev/null || true
    magiskpolicy --live "allow priv_app uhid_device chr_file { read write open ioctl getattr }" 2>/dev/null || true
    magiskpolicy --live "allow system_app uhid_device chr_file { read write open ioctl getattr }" 2>/dev/null || true
    magiskpolicy --live "allow platform_app uhid_device chr_file { read write open ioctl getattr }" 2>/dev/null || true
fi

# 7. Inform user regarding LSPosed companion module
ui_print "---------------------------------------------------------"
ui_print "- Magisk priv-app overlay installed successfully."
ui_print "- IMPORTANT: Ensure PhoneLinkXposed.apk is installed and"
ui_print "  enabled in LSPosed Manager with target apps checked:"
ui_print "   - Link to Windows (com.microsoft.appmanager)"
ui_print "   - Link to Windows Service (com.samsung.android.mdx)"
ui_print "   - Android System (system_server)"
ui_print "---------------------------------------------------------"
