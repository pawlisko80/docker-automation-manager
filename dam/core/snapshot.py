"""
dam/core/snapshot.py

Saves and loads ContainerConfig snapshots as YAML files.
Each run produces a timestamped snapshot before any changes are made,
giving a full audit trail and the data needed for drift detection.

Snapshot format: snapshots/YYYY-MM-DD_HH-MM-SS.yaml
Latest snapshot always symlinked as: snapshots/latest.yaml

Schema example:
  ---
  dam_version: "0.1.0"
  captured_at: "2026-04-05T14:30:00"
  platform: "QNAP"
  containers:
    homeassistant:
      image: ghcr.io/home-assistant/home-assistant:stable
      image_id: sha256:abc123...
      status: running
      restart_policy: unless-stopped
      network_mode: macvlan_network
      networks:
        - name: macvlan_network
          driver: macvlan
          ip_address: 10.20.30.33
          mac_address: "02:42:0a:14:1e:21"
          is_static: true
      ports: []
      binds:
        - /share/Container/homeassistant/config:/config
      env:
        TZ: America/New_York
      privileged: true
      cap_add: []
      cap_drop: []
      devices: []
      extra_hosts: []
      labels: {}
      version_strategy: stable
      pinned_digest: null
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from dam import __version__
from dam.core.inspector import (
    ContainerConfig,
    DeviceMapping,
    NetworkConfig,
    PortBinding,
)
from dam.platform.base import BasePlatform


# ------------------------------------------------------------
# Paths
# ------------------------------------------------------------

DEFAULT_SNAPSHOT_DIR = Path(__file__).parent.parent.parent / "snapshots"
LATEST_LINK_NAME = "latest.yaml"


# ------------------------------------------------------------
# Serialization helpers
# ------------------------------------------------------------

def _config_to_dict(cfg: ContainerConfig) -> dict:
    """Convert a ContainerConfig dataclass to a plain dict for YAML."""
    return {
        "image": cfg.image,
        "image_id": cfg.image_id,
        "status": cfg.status,
        "restart_policy": cfg.restart_policy,
        "network_mode": cfg.network_mode,
        "networks": [
            {
                "name": n.name,
                "driver": n.driver,
                "ip_address": n.ip_address,
                "mac_address": n.mac_address,
                "is_static": n.is_static,
            }
            for n in cfg.networks
        ],
        "ports": [
            {
                "container_port": p.container_port,
                "host_ip": p.host_ip,
                "host_port": p.host_port,
            }
            for p in cfg.ports
        ],
        "binds": cfg.binds,
        "env": cfg.env,
        "privileged": cfg.privileged,
        "cap_add": cfg.cap_add,
        "cap_drop": cfg.cap_drop,
        "devices": [
            {
                "host_path": d.host_path,
                "container_path": d.container_path,
                "permissions": d.permissions,
            }
            for d in cfg.devices
        ],
        "extra_hosts": cfg.extra_hosts,
        "labels": cfg.labels,
        "version_strategy": cfg.version_strategy,
        "pinned_digest": cfg.pinned_digest,
    }


def _dict_to_config(name: str, data: dict) -> ContainerConfig:
    """Reconstruct a ContainerConfig from a snapshot dict."""
    return ContainerConfig(
        name=name,
        image=data.get("image", ""),
        image_id=data.get("image_id", ""),
        status=data.get("status", "unknown"),
        restart_policy=data.get("restart_policy", "no"),
        network_mode=data.get("network_mode", "bridge"),
        networks=[
            NetworkConfig(
                name=n["name"],
                driver=n.get("driver"),
                ip_address=n.get("ip_address"),
                mac_address=n.get("mac_address"),
                is_static=n.get("is_static", False),
            )
            for n in data.get("networks", [])
        ],
        ports=[
            PortBinding(
                container_port=p["container_port"],
                host_ip=p.get("host_ip", ""),
                host_port=p.get("host_port", ""),
            )
            for p in data.get("ports", [])
        ],
        binds=data.get("binds", []),
        env=data.get("env", {}),
        privileged=data.get("privileged", False),
        cap_add=data.get("cap_add", []),
        cap_drop=data.get("cap_drop", []),
        devices=[
            DeviceMapping(
                host_path=d["host_path"],
                container_path=d["container_path"],
                permissions=d.get("permissions", "rwm"),
            )
            for d in data.get("devices", [])
        ],
        extra_hosts=data.get("extra_hosts", []),
        labels=data.get("labels", {}),
        version_strategy=data.get("version_strategy", "latest"),
        pinned_digest=data.get("pinned_digest"),
    )


# ------------------------------------------------------------
# Snapshot manager
# ------------------------------------------------------------

class SnapshotManager:
    """
    Saves and loads YAML snapshots of container configurations.
    Maintains a rotating set of snapshots with a 'latest' symlink.
    """

    def __init__(
        self,
        snapshot_dir: Optional[Path] = None,
        retention: int = 10,
    ):
        self.snapshot_dir = Path(snapshot_dir or DEFAULT_SNAPSHOT_DIR)
        self.retention = retention
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------
    # Save
    # ------------------------------------------------------------

    def save(
        self,
        configs: list[ContainerConfig],
        platform: BasePlatform,
        label: Optional[str] = None,
    ) -> Path:
        """
        Save a snapshot of all container configs.
        Returns the path to the written snapshot file.
        """
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{ts}.yaml" if not label else f"{ts}_{label}.yaml"
        path = self.snapshot_dir / filename

        document = {
            "dam_version": __version__,
            "captured_at": datetime.now().isoformat(timespec="seconds"),
            "platform": platform.name,
            "containers": {
                cfg.name: _config_to_dict(cfg)
                for cfg in configs
            },
        }

        with open(path, "w") as f:
            yaml.dump(document, f, default_flow_style=False, sort_keys=False)

        # Update latest symlink
        self._update_latest_link(path)

        # Rotate old snapshots
        self._rotate()

        return path

    # ------------------------------------------------------------
    # Load
    # ------------------------------------------------------------

    def load_latest(self) -> Optional[tuple[dict, list[ContainerConfig]]]:
        """
        Load the most recent snapshot.
        Returns (metadata_dict, list[ContainerConfig]) or None if no snapshots exist.
        """
        latest = self.snapshot_dir / LATEST_LINK_NAME
        if not latest.exists():
            return None
        return self._load_file(latest)

    def load(self, path: Path) -> Optional[tuple[dict, list[ContainerConfig]]]:
        """Load a specific snapshot file."""
        if not path.exists():
            return None
        return self._load_file(path)

    def _load_file(self, path: Path) -> tuple[dict, list[ContainerConfig]]:
        with open(path) as f:
            doc = yaml.safe_load(f)

        metadata = {
            "dam_version": doc.get("dam_version", "unknown"),
            "captured_at": doc.get("captured_at", "unknown"),
            "platform": doc.get("platform", "unknown"),
            "path": str(path),
        }

        configs = [
            _dict_to_config(name, data)
            for name, data in doc.get("containers", {}).items()
        ]

        return metadata, configs

    # ------------------------------------------------------------
    # List snapshots
    # ------------------------------------------------------------

    def list_snapshots(self) -> list[Path]:
        """Return all snapshot files sorted newest first."""
        files = sorted(
            [
                p for p in self.snapshot_dir.glob("*.yaml")
                if p.name != LATEST_LINK_NAME
            ],
            reverse=True,
        )
        return files

    def snapshot_count(self) -> int:
        return len(self.list_snapshots())

    # ------------------------------------------------------------
    # Diff helpers (used by drift.py)
    # ------------------------------------------------------------

    def load_previous(self, skip: int = 0) -> Optional[tuple[dict, list[ContainerConfig]]]:
        """
        Load the Nth most recent snapshot (skip=0 is latest, skip=1 is one before, etc.).
        """
        snapshots = self.list_snapshots()
        if len(snapshots) <= skip:
            return None
        return self._load_file(snapshots[skip])

    # ------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------

    def _update_latest_link(self, target: Path) -> None:
        """Update or create the latest.yaml symlink."""
        link = self.snapshot_dir / LATEST_LINK_NAME
        # Use a copy instead of symlink for compatibility with QNAP/Synology
        # filesystems that may not support symlinks reliably
        import shutil
        shutil.copy2(target, link)

    def _rotate(self) -> None:
        """Delete oldest snapshots beyond retention limit."""
        snapshots = self.list_snapshots()
        for old in snapshots[self.retention:]:
            try:
                old.unlink()
            except Exception:
                pass
