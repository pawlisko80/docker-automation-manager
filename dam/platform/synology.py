"""
dam/platform/synology.py

Synology-specific platform adapter.
Community-extendable stub — implements the base interface with
Synology DSM conventions for paths, networks, and cron.
"""

from typing import Optional
from .base import BasePlatform


class SynologyPlatform(BasePlatform):
    name = "Synology"

    def __init__(self):
        self._network_driver_cache: dict[str, str] = {}

    # ------------------------------------------------------------
    # Network helpers
    # ------------------------------------------------------------

    def is_static_ip_network(self, network_name: str) -> bool:
        driver = self.get_network_driver(network_name)
        if driver:
            return driver.lower() in {"macvlan", "bridge"}
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
        # Synology Docker data typically lives on volume1
        return "/volume1/docker"

    def get_default_log_root(self) -> str:
        return "/volume1/docker/dam/logs"

    # ------------------------------------------------------------
    # Daemon / scheduler helpers
    # ------------------------------------------------------------

    def supports_systemd(self) -> bool:
        # Synology DSM 7+ uses systemd
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
        # Synology persists user crontab here
        return "/etc/crontab"
