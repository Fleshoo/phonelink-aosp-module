#!/system/bin/sh
##########################################################################################
# post-fs-data.sh - Early Boot Initialization for Phone Link Magisk Module
# Executed by Magisk in post-fs-data mode before Zygote starts
##########################################################################################

MODDIR=${0%/*}

# Early permission setup for virtual input injection (/dev/uinput and /dev/uhid)
if [ -e /dev/uinput ]; then
    chmod 0666 /dev/uinput 2>/dev/null || true
fi
if [ -e /dev/uhid ]; then
    chmod 0666 /dev/uhid 2>/dev/null || true
fi

exit 0
