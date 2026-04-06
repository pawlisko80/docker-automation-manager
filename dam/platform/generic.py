"""
dam/platform/generic.py

Generic Linux platform adapter.
Fallback for plain Debian/Ubuntu/RHEL Docker hosts.
"""

import os
from typing import Optional
from .base import BasePlatform


class GenericPlatform(BasePlatform):
    name = "Generic Linux"

    def __init__(self):
        self._network_driver_cache: dict[str, str] = {}

    # ------------------------------------------------------------
    # Network helpers
    # ------------------------------------------------------------

    def is_static_ip_network(self, network_name: str) -> bool:
        driver = self.get_network_driver(network_name)
        if driver:
            return driver.lower() in {"macvlan", "ipvlan"}
        return False

    def get_network_driver(self, network_name: str) -> Optional[str]:
        if network_name in self._network_driver_cache:
            return self._network_driver_cache[network_name]
        try:
            import docker
            client = docker.from_env()
            networks = client.networks.list(names=[network_name])
            if networks:
                driver = networks[0].attrs.get("Driver", "")
                self._network_driver_cache[network_name] = driver
                return driver
        except Exception:
            pass
        return None

    # ------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------

    def get_default_data_root(self) -> str:
        return "/opt/docker"

    def get_default_log_root(self) -> str:
        return "/var/log/dam"

    # ------------------------------------------------------------
    # Daemon / scheduler helpers
    # ------------------------------------------------------------

    def supports_systemd(self) -> bool:
        try:
            import subprocess
            result = subprocess.run(
                ["systemctl", "--version"],
                capture_output=True, timeout=3
            )
            return result.returncode == 0
        except Exception:
            return False

    def get_cron_path(self) -> str:
        # Prefer /etc/cron.d for system-wide cron on generic Linux
        if os.path.isdir("/etc/cron.d"):
            return "/etc/cron.d/dam"
        return "crontab"  # fall back to user crontab
