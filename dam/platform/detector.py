"""
dam/platform/detector.py

Auto-detects the host platform at runtime and returns the
appropriate platform adapter. Falls back to GenericPlatform
if the host cannot be identified.

Detection order:
  1. QNAP   — /etc/platform.conf or /usr/share/qnap-qpkg
  2. Synology — /etc/synoinfo.conf or /usr/syno
  3. Generic  — fallback

Each detector also inspects Docker network drivers as a secondary
signal, since some QNAP/Synology installs may not have the
expected config files in unusual setups.
"""

import os
import subprocess
from typing import Optional

from .base import BasePlatform
from .qnap import QNAPPlatform
from .synology import SynologyPlatform
from .generic import GenericPlatform


# ------------------------------------------------------------
# File-system fingerprints
# ------------------------------------------------------------

_QNAP_MARKERS = [
    "/etc/platform.conf",
    "/usr/share/qnap-qpkg",
    "/etc/config/qpkg.conf",
    "/sbin/qpkg",
]

_SYNOLOGY_MARKERS = [
    "/etc/synoinfo.conf",
    "/usr/syno",
    "/var/packages",
    "/usr/bin/synopkg",
]


def _file_exists_any(paths: list[str]) -> bool:
    return any(os.path.exists(p) for p in paths)


def _read_os_release() -> dict[str, str]:
    """Parse /etc/os-release into a dict."""
    result = {}
    try:
        with open("/etc/os-release") as f:
            for line in f:
                line = line.strip()
                if "=" in line:
                    k, _, v = line.partition("=")
                    result[k.strip()] = v.strip().strip('"')
    except Exception:
        pass
    return result


def _detect_via_docker_networks() -> Optional[str]:
    """
    Secondary signal: if we see qnet-named networks, it's likely QNAP.
    Returns 'qnap', 'synology', or None.
    """
    try:
        import docker
        client = docker.from_env()
        networks = client.networks.list()
        for net in networks:
            driver = net.attrs.get("Driver", "").lower()
            name = net.name.lower()
            if driver == "qnet" or "qnet" in name or "bond0" in name:
                return "qnap"
    except Exception:
        pass
    return None


def detect_platform() -> BasePlatform:
    """
    Auto-detect the host platform and return the appropriate adapter.
    Always returns a valid BasePlatform — never raises.
    """

    # --- QNAP ---
    if _file_exists_any(_QNAP_MARKERS):
        return QNAPPlatform()

    # --- Synology ---
    if _file_exists_any(_SYNOLOGY_MARKERS):
        return SynologyPlatform()

    # --- Check /proc/version for hints ---
    try:
        with open("/proc/version") as f:
            version_str = f.read().lower()
            if "qnap" in version_str:
                return QNAPPlatform()
            if "synology" in version_str:
                return SynologyPlatform()
    except Exception:
        pass

    # --- Check os-release ---
    os_release = _read_os_release()
    os_id = os_release.get("ID", "").lower()
    os_name = os_release.get("NAME", "").lower()
    if "qnap" in os_id or "qnap" in os_name:
        return QNAPPlatform()
    if "synology" in os_id or "synology" in os_name:
        return SynologyPlatform()

    # --- Secondary: Docker network driver signal ---
    net_hint = _detect_via_docker_networks()
    if net_hint == "qnap":
        return QNAPPlatform()

    # --- Fallback ---
    return GenericPlatform()


def get_platform_info(platform: BasePlatform) -> dict:
    """
    Return a human-readable info dict about the detected platform.
    Used by TUI to display environment summary on startup.
    """
    info = platform.describe()
    info["detected"] = True
    return info
