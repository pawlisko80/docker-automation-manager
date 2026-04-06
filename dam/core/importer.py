"""
dam/core/importer.py

Imports container configurations from DAM YAML export files and
optionally recreates the containers on the current host.

Supports:
  - Single container DAM YAML  (<name>.dam.yaml)
  - Multi container DAM YAML   (all-containers.dam.yaml)

Import modes:
  dry_run=True   — parse and validate, report what would be created, no changes
  dry_run=False  — actually recreate the container(s) on this host

The importer reuses _build_run_kwargs() and _recreate() from updater.py
so the actual container creation logic is shared and tested.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml

from dam.core.inspector import (
    ContainerConfig,
    DeviceMapping,
    NetworkConfig,
    PortBinding,
)
from dam.platform.base import BasePlatform


# ------------------------------------------------------------
# Result types
# ------------------------------------------------------------

class ImportStatus(Enum):
    CREATED   = "created"    # container successfully recreated
    SKIPPED   = "skipped"    # container already exists, not overwritten
    DRY_RUN   = "dry_run"    # would create but dry_run=True
    FAILED    = "failed"     # error during import


@dataclass
class ImportResult:
    container_name: str
    status: ImportStatus
    image: str = ""
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.status in (ImportStatus.CREATED, ImportStatus.DRY_RUN, ImportStatus.SKIPPED)


# ------------------------------------------------------------
# YAML parsing helpers
# ------------------------------------------------------------

def _dict_to_config(data: dict) -> ContainerConfig:
    """Reconstruct a ContainerConfig from a serialized dict."""
    return ContainerConfig(
        name=data.get("name", ""),
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


def load_import_file(path: Path) -> tuple[dict, list[ContainerConfig]]:
    """
    Load a DAM YAML export file and return (metadata, configs).
    Handles both single-container and multi-container files.
    Raises ValueError on invalid format.
    """
    if not path.exists():
        raise FileNotFoundError(f"Import file not found: {path}")

    with open(path) as f:
        doc = yaml.safe_load(f)

    if not isinstance(doc, dict):
        raise ValueError(f"Invalid DAM YAML format in {path}")

    if doc.get("format") != "dam-yaml":
        raise ValueError(
            f"File {path} does not appear to be a DAM export file. "
            f"Expected format: 'dam-yaml', got: '{doc.get('format', 'unknown')}'"
        )

    metadata = {
        "dam_version": doc.get("dam_version", "unknown"),
        "exported_at": doc.get("exported_at", "unknown"),
        "path": str(path),
    }

    configs: list[ContainerConfig] = []

    # Single container format
    if "container" in doc:
        configs.append(_dict_to_config(doc["container"]))

    # Multi container format
    elif "containers" in doc:
        for name, data in doc["containers"].items():
            data["name"] = name  # ensure name is set
            configs.append(_dict_to_config(data))

    else:
        raise ValueError(f"No container data found in {path}")

    return metadata, configs


# ------------------------------------------------------------
# Importer
# ------------------------------------------------------------

class Importer:
    """
    Imports containers from DAM YAML export files.
    Optionally recreates them on the current Docker host.
    """

    def __init__(
        self,
        platform: BasePlatform,
        dry_run: bool = False,
        overwrite: bool = False,
    ):
        """
        Args:
            platform:  Active platform adapter
            dry_run:   If True, validate and report but don't create containers
            overwrite: If True, stop and replace existing containers with same name.
                       If False, skip containers that already exist.
        """
        self.platform = platform
        self.dry_run = dry_run
        self.overwrite = overwrite

    def import_file(self, path: Path) -> list[ImportResult]:
        """
        Import all containers from a DAM YAML file.
        Returns one ImportResult per container.
        """
        try:
            metadata, configs = load_import_file(path)
        except (FileNotFoundError, ValueError) as e:
            return [ImportResult(
                container_name="<unknown>",
                status=ImportStatus.FAILED,
                error=str(e),
            )]

        return self.import_configs(configs)

    def import_configs(self, configs: list[ContainerConfig]) -> list[ImportResult]:
        """Import a list of ContainerConfig objects."""
        results = []
        for cfg in configs:
            result = self._import_one(cfg)
            results.append(result)
        return results

    def _import_one(self, cfg: ContainerConfig) -> ImportResult:
        """Import a single container config."""

        if self.dry_run:
            return ImportResult(
                container_name=cfg.name,
                status=ImportStatus.DRY_RUN,
                image=cfg.image,
            )

        try:
            import docker
            from docker.errors import NotFound

            client = docker.from_env()

            # Check if container already exists
            existing = None
            try:
                existing = client.containers.get(cfg.name)
            except NotFound:
                pass

            if existing and not self.overwrite:
                return ImportResult(
                    container_name=cfg.name,
                    status=ImportStatus.SKIPPED,
                    image=cfg.image,
                )

            # Use updater's recreate logic
            from dam.core.updater import Updater
            updater = Updater(platform=self.platform, dry_run=False)
            updater._recreate(cfg, cfg.image)

            return ImportResult(
                container_name=cfg.name,
                status=ImportStatus.CREATED,
                image=cfg.image,
            )

        except Exception as e:
            return ImportResult(
                container_name=cfg.name,
                status=ImportStatus.FAILED,
                image=cfg.image,
                error=str(e),
            )

    @staticmethod
    def summarize(results: list[ImportResult]) -> dict:
        """Return a summary dict for TUI/log display."""
        return {
            "total": len(results),
            "created": sum(1 for r in results if r.status == ImportStatus.CREATED),
            "skipped": sum(1 for r in results if r.status == ImportStatus.SKIPPED),
            "dry_run": sum(1 for r in results if r.status == ImportStatus.DRY_RUN),
            "failed":  sum(1 for r in results if r.status == ImportStatus.FAILED),
            "failures": [r for r in results if r.status == ImportStatus.FAILED],
        }
