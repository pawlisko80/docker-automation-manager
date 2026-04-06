"""
dam/platform/base.py

Abstract base class for platform adapters.
All platform-specific logic must implement this interface.
"""

from abc import ABC, abstractmethod
from typing import Optional


class BasePlatform(ABC):
    """
    Abstract base for platform adapters.
    Subclass this for QNAP, Synology, generic Linux, etc.
    """

    # Human-readable platform name
    name: str = "unknown"

    # ------------------------------------------------------------
    # Network helpers
    # ------------------------------------------------------------

    @abstractmethod
    def is_static_ip_network(self, network_name: str) -> bool:
        """
        Return True if the given Docker network supports static IP
        assignment (e.g. macvlan, qnet with static driver).
        """

    @abstractmethod
    def get_network_driver(self, network_name: str) -> Optional[str]:
        """
        Return the driver name for a given network, or None if unknown.
        Used to decide whether --ip flag is valid when recreating containers.
        """

    # ------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------

    @abstractmethod
    def get_default_data_root(self) -> str:
        """
        Return the default base path for container volume data.
        QNAP:     /share/Container
        Synology: /volume1/docker
        Generic:  /opt/docker
        """

    @abstractmethod
    def get_default_log_root(self) -> str:
        """
        Return the default base path for DAM logs.
        """

    # ------------------------------------------------------------
    # Daemon / scheduler helpers
    # ------------------------------------------------------------

    @abstractmethod
    def supports_systemd(self) -> bool:
        """Return True if systemd is available on this platform."""

    @abstractmethod
    def get_cron_path(self) -> str:
        """
        Return the path to write a cron job file, or the crontab
        method to use ('crontab' for user crontab, or a path like
        /etc/cron.d/dam for system-level cron).
        """

    # ------------------------------------------------------------
    # Platform info
    # ------------------------------------------------------------

    def describe(self) -> dict:
        """Return a dict of platform metadata for display in TUI."""
        return {
            "platform": self.name,
            "data_root": self.get_default_data_root(),
            "log_root": self.get_default_log_root(),
            "systemd": self.supports_systemd(),
            "cron_path": self.get_cron_path(),
        }
