#!/system/bin/sh
##########################################################################################
# uninstall.sh - Module Removal Cleanup Script
# Executed by Magisk Manager when the module is removed
##########################################################################################

PKG_MDX="com.samsung.android.mdx"

# Clear residual application cache and database
if command -v pm >/dev/null 2>&1; then
    pm clear "$PKG_MDX" >/dev/null 2>&1 || true
fi

# Remove runtime log files
rm -f /data/local/tmp/phonelink_service.log 2>/dev/null || true

exit 0
