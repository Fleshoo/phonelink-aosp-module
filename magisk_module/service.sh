#!/system/bin/sh
##########################################################################################
# service.sh - Late-start Service Script for Phone Link Magisk Module
# Executed by Magisk in late_start mode after boot completes
##########################################################################################

LOGFILE="/data/local/tmp/phonelink_service.log"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Phone Link service.sh starting..." > "$LOGFILE"

# 1. Wait until Android OS has completely booted
BOOT_TIMEOUT=120
TIMER=0
while [ "$(getprop sys.boot_completed)" != "1" ]; do
    sleep 2
    TIMER=$((TIMER + 2))
    if [ $TIMER -ge $BOOT_TIMEOUT ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Timed out waiting for sys.boot_completed." >> "$LOGFILE"
        exit 1
    fi
done
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Android boot completed. Initializing services..." >> "$LOGFILE"

# Allow system server and package manager to settle
sleep 5

PKG_MDX="com.samsung.android.mdx"
PKG_MS="com.microsoft.appmanager"

# 2. Wait up to 30 seconds for PackageManagerService to register MDX service
PM_WAIT=0
while ! pm list packages | grep -q "$PKG_MDX" && [ $PM_WAIT -lt 30 ]; do
    sleep 2
    PM_WAIT=$((PM_WAIT + 2))
done

if ! pm list packages | grep -q "$PKG_MDX"; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Warning: $PKG_MDX not yet found in pm list packages." >> "$LOGFILE"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Confirmed $PKG_MDX registered in PackageManagerService." >> "$LOGFILE"
fi

# 3. Grant Runtime Permissions for LinkToWindowsService (com.samsung.android.mdx)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Pre-granting runtime permissions for $PKG_MDX..." >> "$LOGFILE"
pm grant "$PKG_MDX" android.permission.RECORD_AUDIO 2>/dev/null || true
pm grant "$PKG_MDX" android.permission.BLUETOOTH_CONNECT 2>/dev/null || true
pm grant "$PKG_MDX" android.permission.BLUETOOTH_SCAN 2>/dev/null || true
pm grant "$PKG_MDX" android.permission.BLUETOOTH_ADVERTISE 2>/dev/null || true
pm grant "$PKG_MDX" android.permission.POST_NOTIFICATIONS 2>/dev/null || true
pm grant "$PKG_MDX" android.permission.READ_PHONE_STATE 2>/dev/null || true
pm grant "$PKG_MDX" android.permission.BATTERY_STATS 2>/dev/null || true
pm grant "$PKG_MDX" android.permission.WRITE_SECURE_SETTINGS 2>/dev/null || true
pm grant "$PKG_MDX" android.permission.INTERACT_ACROSS_USERS 2>/dev/null || true

# 4. Grant Runtime Permissions for Link to Windows App (com.microsoft.appmanager)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Pre-granting runtime permissions for $PKG_MS..." >> "$LOGFILE"
pm grant "$PKG_MS" android.permission.POST_NOTIFICATIONS 2>/dev/null || true
pm grant "$PKG_MS" android.permission.BLUETOOTH_CONNECT 2>/dev/null || true
pm grant "$PKG_MS" android.permission.BLUETOOTH_SCAN 2>/dev/null || true
pm grant "$PKG_MS" android.permission.READ_PHONE_STATE 2>/dev/null || true

# 5. Configure AppOps for Background Execution & Screen Projection
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Setting AppOps permissions..." >> "$LOGFILE"
# MDX Service AppOps
appops set "$PKG_MDX" SYSTEM_ALERT_WINDOW allow 2>/dev/null || true
appops set "$PKG_MDX" RECORD_AUDIO allow 2>/dev/null || true
appops set "$PKG_MDX" PROJECT_MEDIA allow 2>/dev/null || true
appops set "$PKG_MDX" LEGACY_STORAGE allow 2>/dev/null || true
appops set "$PKG_MDX" RUN_IN_BACKGROUND allow 2>/dev/null || true
appops set "$PKG_MDX" RUN_ANY_IN_BACKGROUND allow 2>/dev/null || true

# Microsoft AppManager AppOps
appops set "$PKG_MS" SYSTEM_ALERT_WINDOW allow 2>/dev/null || true
appops set "$PKG_MS" RUN_IN_BACKGROUND allow 2>/dev/null || true
appops set "$PKG_MS" RUN_ANY_IN_BACKGROUND allow 2>/dev/null || true

# 6. Exempt Both Apps from Battery Optimization (Doze Whitelist)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Adding packages to DeviceIdle power save whitelist..." >> "$LOGFILE"
dumpsys deviceidle whitelist +"$PKG_MDX" 2>/dev/null || true
dumpsys deviceidle whitelist +"$PKG_MS" 2>/dev/null || true
am set-standby-bucket "$PKG_MDX" active 2>/dev/null || true
am set-standby-bucket "$PKG_MS" active 2>/dev/null || true

# 7. Disable Android 12-16 Phantom Process Killer
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Configuring phantom process monitor..." >> "$LOGFILE"
settings put global settings_enable_monitor_phantom_procs false 2>/dev/null || true
device_config put activity_manager max_phantom_processes 2147483647 2>/dev/null || true

# 8. Hardware Input Bridge Permissions (/dev/uinput and /dev/uhid)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Setting permissions on /dev/uinput and /dev/uhid..." >> "$LOGFILE"
if [ -e /dev/uinput ]; then
    chmod 0666 /dev/uinput 2>/dev/null || true
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] /dev/uinput set to 0666." >> "$LOGFILE"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Warning: /dev/uinput not found." >> "$LOGFILE"
fi
if [ -e /dev/uhid ]; then
    chmod 0666 /dev/uhid 2>/dev/null || true
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] /dev/uhid set to 0666." >> "$LOGFILE"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Warning: /dev/uhid not found." >> "$LOGFILE"
fi

# 9. Apply Live SELinux Policies if magiskpolicy is available
if command -v magiskpolicy >/dev/null 2>&1; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Applying live SELinux policies via magiskpolicy..." >> "$LOGFILE"
    magiskpolicy --live "allow priv_app uinput_device chr_file { read write open ioctl getattr }" 2>/dev/null || true
    magiskpolicy --live "allow system_app uinput_device chr_file { read write open ioctl getattr }" 2>/dev/null || true
    magiskpolicy --live "allow platform_app uinput_device chr_file { read write open ioctl getattr }" 2>/dev/null || true
    magiskpolicy --live "allow priv_app uhid_device chr_file { read write open ioctl getattr }" 2>/dev/null || true
    magiskpolicy --live "allow system_app uhid_device chr_file { read write open ioctl getattr }" 2>/dev/null || true
    magiskpolicy --live "allow platform_app uhid_device chr_file { read write open ioctl getattr }" 2>/dev/null || true
    magiskpolicy --live "allow priv_app input_service service_manager find" 2>/dev/null || true
    magiskpolicy --live "allow priv_app surfaceflinger service_manager find" 2>/dev/null || true
    magiskpolicy --live "allow priv_app privapp_data_file file { execute execute_no_trans }" 2>/dev/null || true
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Phone Link service.sh completed successfully." >> "$LOGFILE"
exit 0
