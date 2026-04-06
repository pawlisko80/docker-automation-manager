"""
dam/platform/qnap.py

QNAP-specific platform adapter.
Handles qnet network driver, /share paths, and QNAP cron.
"""

import subprocess
from typing import Optional

from .base import BasePlatform


# Network drivers that support --ip static assignment on QNAP
_STATIC_IP_DRIVERS = {"macvlan", "qnet"}

# QNAP qnet network names typically contain these substrings
_QNET_HINTS = {"qnet", "bond", "eth", "caeae"}


class QNAPPlatform(BasePlatform):
    name = "QNAP"

    def __init__(self):
        self._network_driver_cache: dict[str, str] = {}

    # ------------------------------------------------------------
    # Network helpers
    # ------------------------------------------------------------

    def is_static_ip_network(self, network_name: str) -> bool:
        driver = self.get_network_driver(network_name)
        if driver:
            return driver.lower() in _STATIC_IP_DRIVERS
        # Fallback: guess from name
        name_lower = network_name.lower()
        return any(hint in name_lower for hint in _QNET_HINTS) or \
               name_lower in {"macvlan_network", "macvlan"}

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
        return "/share/Container"

    def get_default_log_root(self) -> str:
        return "/share/Container/dam/logs"

    # ------------------------------------------------------------
    # Daemon / scheduler helpers
    # ------------------------------------------------------------

    def supports_systemd(self) -> bool:
        # QNAP uses BusyBox init, not systemd
        return False

    def get_cron_path(self) -> str:
        # QNAP uses /etc/config/crontab for persistent cron entries
        return "/etc/config/crontab"

    # ------------------------------------------------------------
    # QNAP-specific: restart cron daemon after writing crontab
    # ------------------------------------------------------------

    def reload_cron(self) -> bool:
        """
        QNAP requires crontab reload after editing /etc/config/crontab.
        Returns True on success.
        """
        try:
            subprocess.run(
                ["crontab", "/etc/config/crontab"],
                check=True,
                capture_output=True
            )
            return True
        except Exception:
            return False
