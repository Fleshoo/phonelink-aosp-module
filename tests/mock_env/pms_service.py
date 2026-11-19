"""
PackageManagerService and PackageSignatureChecker Simulation.
Validates /system/priv-app/ placement, privapp-permissions XML parsing,
sysconfig power-save/data-saver exemptions, and signature checking.
"""

import xml.etree.ElementTree as ET
from typing import Dict, Set, List, Optional
from .android_runtime import ApplicationInfo, SecurityException


class PackageInfo:
    def __init__(
        self,
        package_name: str,
        uid: int,
        source_dir: str,
        signatures: Optional[List[str]] = None,
        requested_permissions: Optional[List[str]] = None,
    ):
        self.packageName = package_name
        self.uid = uid
        self.sourceDir = source_dir
        self.signatures = signatures or ["cert_default"]
        self.requestedPermissions = requested_permissions or []
        self.grantedPermissions: Set[str] = set()

    @property
    def is_privileged(self) -> bool:
        return "/system/priv-app/" in self.sourceDir


class PackageSignatureChecker:
    SIGNATURE_MATCH = 0
    SIGNATURE_NO_MATCH = -1
    SIGNATURE_NEITHER_SIGNED = -2
    SIGNATURE_FIRST_NOT_SIGNED = -3
    SIGNATURE_UNKNOWN_PACKAGE = -4

    _bypass_active: bool = False
    _bypass_pairs: Set[tuple] = set()

    @classmethod
    def enable_bypass(cls) -> None:
        cls._bypass_active = True
        cls._bypass_pairs = {
            ("com.microsoft.appmanager", "com.samsung.android.mdx"),
            ("com.samsung.android.mdx", "com.microsoft.appmanager"),
        }

    @classmethod
    def disable_bypass(cls) -> None:
        cls._bypass_active = False
        cls._bypass_pairs.clear()

    @classmethod
    def isShipBuild(cls) -> bool:
        # Stock AOSP or debug returns False; hooked / production returns True
        return cls._bypass_active

    @classmethod
    def checkSignatures(cls, pms: "PackageManagerService", pkg1: str, pkg2: str) -> int:
        if not pkg1 or not pkg2:
            return cls.SIGNATURE_UNKNOWN_PACKAGE

        info1 = pms.get_package_info(pkg1)
        info2 = pms.get_package_info(pkg2)

        if not info1 or not info2:
            return cls.SIGNATURE_UNKNOWN_PACKAGE

        # Check bypass hook
        if cls._bypass_active and (pkg1, pkg2) in cls._bypass_pairs:
            return cls.SIGNATURE_MATCH

        # Check actual certificates
        if set(info1.signatures) == set(info2.signatures):
            return cls.SIGNATURE_MATCH
        return cls.SIGNATURE_NO_MATCH


class PackageManagerService:
    PRIVILEGED_PERMISSIONS = {
        "android.permission.WRITE_SECURE_SETTINGS",
        "android.permission.INTERACT_ACROSS_USERS",
        "android.permission.BATTERY_STATS",
        "android.permission.CAPTURE_VIDEO_OUTPUT",
        "android.permission.INTERNAL_SYSTEM_WINDOW",
        "android.permission.INJECT_EVENTS",
    }

    def __init__(self):
        self._packages: Dict[str, PackageInfo] = {}
        self._uid_map: Dict[int, str] = {}
        self._privapp_whitelist: Dict[str, Set[str]] = {}
        self._power_save_whitelist: Set[str] = set()
        self._data_saver_whitelist: Set[str] = set()

    def register_package(
        self,
        package_name: str,
        uid: int,
        source_dir: str,
        signatures: Optional[List[str]] = None,
        requested_permissions: Optional[List[str]] = None,
    ) -> PackageInfo:
        pkg = PackageInfo(package_name, uid, source_dir, signatures, requested_permissions)
        self._packages[package_name] = pkg
        self._uid_map[uid] = package_name
        self._evaluate_permissions(pkg)
        return pkg

    def get_package_info(self, package_name: str) -> Optional[PackageInfo]:
        return self._packages.get(package_name)

    def get_package_name_by_uid(self, uid: int) -> Optional[str]:
        return self._uid_map.get(uid)

    def load_privapp_permissions_xml(self, xml_content: str) -> None:
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            raise ValueError(f"Malformed XML: {e}")

        for privapp in root.findall("privapp-permissions"):
            pkg = privapp.get("package")
            if not pkg:
                continue
            if pkg not in self._privapp_whitelist:
                self._privapp_whitelist[pkg] = set()
            for perm in privapp.findall("permission"):
                name = perm.get("name")
                if name:
                    self._privapp_whitelist[pkg].add(name)

        # Re-evaluate all packages with updated whitelist
        for pkg in self._packages.values():
            self._evaluate_permissions(pkg)

    def load_sysconfig_xml(self, xml_content: str) -> None:
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            raise ValueError(f"Malformed XML: {e}")

        for elem in root.findall("allow-in-power-save"):
            pkg = elem.get("package")
            if pkg:
                self._power_save_whitelist.add(pkg)

        for elem in root.findall("allow-in-data-saver"):
            pkg = elem.get("package")
            if pkg:
                self._data_saver_whitelist.add(pkg)

    def _evaluate_permissions(self, pkg: PackageInfo) -> None:
        pkg.grantedPermissions.clear()
        whitelisted = self._privapp_whitelist.get(pkg.packageName, set())

        for perm in pkg.requestedPermissions:
            if perm in self.PRIVILEGED_PERMISSIONS:
                # Privileged permission: requires /system/priv-app/ AND presence in whitelist
                if pkg.is_privileged and perm in whitelisted:
                    pkg.grantedPermissions.add(perm)
                # Else: NOT granted
            else:
                # Standard permissions granted if requested
                pkg.grantedPermissions.add(perm)

    def check_permission(self, package_name: str, permission: str) -> bool:
        pkg = self._packages.get(package_name)
        if not pkg:
            return False
        return permission in pkg.grantedPermissions

    def check_uid_permission(self, uid: int, permission: str) -> bool:
        if uid == 1000:  # SYSTEM UID has all permissions
            return True
        pkg_name = self._uid_map.get(uid)
        if not pkg_name:
            return False
        return self.check_permission(pkg_name, permission)

    def is_power_save_exempt(self, package_name: str) -> bool:
        return package_name in self._power_save_whitelist

    def is_data_saver_exempt(self, package_name: str) -> bool:
        return package_name in self._data_saver_whitelist

    def clear(self) -> None:
        self._packages.clear()
        self._uid_map.clear()
        self._privapp_whitelist.clear()
        self._power_save_whitelist.clear()
        self._data_saver_whitelist.clear()
