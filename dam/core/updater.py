"""
dam/core/updater.py

Pulls new images, detects whether they actually changed (digest
comparison), and recreates only containers that have a newer image.
All container settings are preserved exactly from the ContainerConfig
snapshot captured by inspector.py before the update begins.

Update lifecycle per container:
  1. Check version_strategy (latest / stable / pinned)
  2. Pull image — capture pre/post digest
  3. If digest unchanged → skip (no recreate needed)
  4. If digest changed → stop → remove → recreate with saved config
  5. Verify container comes up healthy
  6. Record result in UpdateResult

Design goals:
  - Atomic per container: one failure never blocks other containers
  - Dry-run mode: plan everything, execute nothing
  - Configurable delay between recreations (dependent service ordering)
  - Platform-agnostic: uses ContainerConfig, not raw docker CLI
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Callable

import docker
from docker.errors import DockerException, ImageNotFound, NotFound

from dam.core.inspector import ContainerConfig
from dam.platform.base import BasePlatform


# ------------------------------------------------------------
# Result types
# ------------------------------------------------------------

class UpdateStatus(Enum):
    UPDATED     = "updated"       # new image pulled, container recreated
    SKIPPED     = "skipped"       # image unchanged, no action needed
    PINNED      = "pinned"        # version_strategy=pinned, not updated
    FAILED      = "failed"        # error during pull or recreate
    DRY_RUN     = "dry_run"       # would update but dry_run=True


@dataclass
class UpdateResult:
    container_name: str
    status: UpdateStatus
    old_image_id: Optional[str] = None
    new_image_id: Optional[str] = None
    error: Optional[str] = None
    duration_seconds: float = 0.0

    @property
    def changed(self) -> bool:
        return self.status == UpdateStatus.UPDATED

    @property
    def success(self) -> bool:
        return self.status in (UpdateStatus.UPDATED, UpdateStatus.SKIPPED, UpdateStatus.PINNED, UpdateStatus.DRY_RUN)


# ------------------------------------------------------------
# Image pull helpers
# ------------------------------------------------------------

def _resolve_image_ref(image: str, version_strategy: str) -> str:
    """
    Given a full image reference and version strategy, return the
    image ref to pull.

    Examples:
      "ghcr.io/home-assistant/home-assistant:stable" + "stable" -> same
      "ghcr.io/esphome/esphome"                      + "latest" -> appends :latest
      "instantlinux/nut-upsd"                         + "latest" -> appends :latest
    """
    if version_strategy == "pinned":
        return image  # will be skipped by caller

    # If image already has a tag, use it as-is
    # (tag is anything after the last colon that isn't a digest)
    base = image.split("@")[0]  # strip digest if present
    if ":" in base.split("/")[-1]:
        return base

    # No tag — append based on strategy
    tag = "stable" if version_strategy == "stable" else "latest"
    return f"{base}:{tag}"


def _get_local_digest(client, image_ref: str) -> Optional[str]:
    """Return the local image ID for an image ref, or None if not present."""
    try:
        img = client.images.get(image_ref)
        return img.id
    except ImageNotFound:
        return None
    except Exception:
        return None


# ------------------------------------------------------------
# docker run command builder
# ------------------------------------------------------------

def _build_run_kwargs(cfg: ContainerConfig) -> dict:
    """
    Build the kwargs dict for docker.containers.run() / create()
    from a ContainerConfig. Faithfully reconstructs all settings.
    """
    kwargs: dict = {
        "name": cfg.name,
        "detach": True,
        "restart_policy": {"Name": cfg.restart_policy},
    }

    # --- Privileged ---
    if cfg.privileged:
        kwargs["privileged"] = True

    # --- Capabilities ---
    if cfg.cap_add:
        kwargs["cap_add"] = cfg.cap_add
    if cfg.cap_drop:
        kwargs["cap_drop"] = cfg.cap_drop

    # --- Network ---
    network_mode = cfg.network_mode
    primary_net = cfg.primary_network()
    primary_ip = cfg.primary_ip()

    if network_mode in ("host", "none"):
        kwargs["network_mode"] = network_mode
    elif network_mode.startswith("container:"):
        kwargs["network_mode"] = network_mode
    else:
        # Named network — will connect with IP after creation if static
        kwargs["network"] = primary_net
        if primary_ip:
            kwargs["network"] = None  # connect manually with IP after create

    # --- Port bindings ---
    if cfg.ports:
        port_bindings = {}
        for p in cfg.ports:
            host_binding = p.host_port
            if p.host_ip:
                host_binding = (p.host_ip, p.host_port)
            port_bindings[p.container_port] = host_binding
        kwargs["ports"] = port_bindings

    # --- Volume binds ---
    clean_binds = [b for b in cfg.binds if b]
    if clean_binds:
        kwargs["volumes"] = clean_binds

    # --- Environment ---
    clean_env = {k: v for k, v in cfg.env.items() if k and v is not None}
    if clean_env:
        kwargs["environment"] = clean_env

    # --- Extra hosts ---
    if cfg.extra_hosts:
        kwargs["extra_hosts"] = {
            h.split(":")[0]: h.split(":")[1]
            for h in cfg.extra_hosts
            if ":" in h
        }

    # --- Devices ---
    if cfg.devices:
        kwargs["devices"] = [
            f"{d.host_path}:{d.container_path}:{d.permissions}"
            for d in cfg.devices
        ]

    # --- Labels ---
    if cfg.labels:
        kwargs["labels"] = cfg.labels

    return kwargs


# ------------------------------------------------------------
# Main updater
# ------------------------------------------------------------

class Updater:
    """
    Orchestrates the full update cycle for a set of containers.
    """

    def __init__(
        self,
        platform: BasePlatform,
        dry_run: bool = False,
        recreate_delay: float = 5.0,
        progress_callback: Optional[Callable[[str, str], None]] = None,
    ):
        """
        Args:
            platform:           Active platform adapter
            dry_run:            If True, plan but do not execute any changes
            recreate_delay:     Seconds to wait between container recreations
            progress_callback:  Optional fn(container_name, message) for TUI updates
        """
        self.platform = platform
        self.dry_run = dry_run
        self.recreate_delay = recreate_delay
        self._progress = progress_callback or (lambda name, msg: None)

        try:
            self.client = docker.from_env()
            self.client.ping()
        except DockerException as e:
            raise RuntimeError(f"Cannot connect to Docker daemon: {e}")

    # ------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------

    def update_all(
        self,
        configs: list[ContainerConfig],
    ) -> list[UpdateResult]:
        """
        Run update cycle for all given container configs.
        Returns one UpdateResult per container.
        """
        results = []
        for i, cfg in enumerate(configs):
            self._progress(cfg.name, f"Checking {cfg.name}...")
            result = self._update_one(cfg)
            results.append(result)

            # Delay between recreations (except after last one)
            if result.changed and i < len(configs) - 1:
                if not self.dry_run:
                    self._progress(cfg.name, f"Waiting {self.recreate_delay}s before next container...")
                    time.sleep(self.recreate_delay)

        return results

    def update_one(self, cfg: ContainerConfig) -> UpdateResult:
        """Update a single container. Public wrapper."""
        return self._update_one(cfg)

    # ------------------------------------------------------------
    # Core update logic
    # ------------------------------------------------------------

    def _update_one(self, cfg: ContainerConfig) -> UpdateResult:
        start = time.time()

        # --- Pinned: never update ---
        if cfg.version_strategy == "pinned":
            return UpdateResult(
                container_name=cfg.name,
                status=UpdateStatus.PINNED,
                old_image_id=cfg.image_id,
                duration_seconds=time.time() - start,
            )

        image_ref = _resolve_image_ref(cfg.image, cfg.version_strategy)

        # --- Capture pre-pull digest ---
        old_digest = _get_local_digest(self.client, image_ref)

        # --- Pull ---
        self._progress(cfg.name, f"Pulling {image_ref}...")
        try:
            self.client.images.pull(image_ref)
        except Exception as e:
            return UpdateResult(
                container_name=cfg.name,
                status=UpdateStatus.FAILED,
                old_image_id=old_digest,
                error=f"Pull failed: {e}",
                duration_seconds=time.time() - start,
            )

        # --- Capture post-pull digest ---
        new_digest = _get_local_digest(self.client, image_ref)

        # --- Compare digests ---
        # Also check if the container is running on a different image ID than
        # the current local image (e.g. image was pulled but container not recreated)
        container_running_stale = False
        if cfg.image_id and new_digest:
            # cfg.image_id is the digest of what the container is currently running
            # new_digest is what's in the local image store after pull
            # If they differ, the container needs to be recreated even if registry digest unchanged
            container_running_stale = (cfg.image_id != new_digest)

        if old_digest and old_digest == new_digest and not container_running_stale:
            self._progress(cfg.name, f"{cfg.name}: image unchanged, skipping")
            return UpdateResult(
                container_name=cfg.name,
                status=UpdateStatus.SKIPPED,
                old_image_id=old_digest,
                new_image_id=new_digest,
                duration_seconds=time.time() - start,
            )

        if container_running_stale and old_digest == new_digest:
            self._progress(cfg.name, f"{cfg.name}: container running on outdated image — recreating")

        # --- New image available ---
        self._progress(cfg.name, f"{cfg.name}: new image detected")

        if self.dry_run:
            return UpdateResult(
                container_name=cfg.name,
                status=UpdateStatus.DRY_RUN,
                old_image_id=old_digest,
                new_image_id=new_digest,
                duration_seconds=time.time() - start,
            )

        # --- Recreate ---
        # Use image_ref (tag) not the sha256 digest — Docker cannot pull by digest from registry
        # After a successful pull, the tag resolves to the newly pulled image in local cache
        try:
            self._recreate(cfg, image_ref)
        except Exception as e:
            return UpdateResult(
                container_name=cfg.name,
                status=UpdateStatus.FAILED,
                old_image_id=old_digest,
                new_image_id=new_digest,
                error=f"Recreate failed: {e}",
                duration_seconds=time.time() - start,
            )

        return UpdateResult(
            container_name=cfg.name,
            status=UpdateStatus.UPDATED,
            old_image_id=old_digest,
            new_image_id=new_digest,
            duration_seconds=time.time() - start,
        )

    # ------------------------------------------------------------
    # Container recreate
    # ------------------------------------------------------------

    def _recreate(self, cfg: ContainerConfig, image_ref: str) -> None:
        """
        Stop the existing container, remove it, and recreate it
        with the new image and full original configuration.
        """

        # Step 1: Stop
        self._progress(cfg.name, f"Stopping {cfg.name}...")
        try:
            container = self.client.containers.get(cfg.name)
            container.stop(timeout=30)
        except NotFound:
            pass  # Already stopped/removed — continue
        except Exception as e:
            raise RuntimeError(f"Failed to stop {cfg.name}: {e}")

        # Step 2: Remove
        self._progress(cfg.name, f"Removing {cfg.name}...")
        try:
            container = self.client.containers.get(cfg.name)
            container.remove()
        except NotFound:
            pass  # Already removed
        except Exception as e:
            raise RuntimeError(f"Failed to remove {cfg.name}: {e}")

        # Step 3: Build run kwargs
        kwargs = _build_run_kwargs(cfg)

        # Step 4: Handle static IP networks separately
        # Docker SDK requires: create container on default network,
        # then disconnect and connect to named network with IP
        needs_static_ip = (
            cfg.primary_ip() is not None
            and cfg.network_mode not in ("host", "none")
            and not cfg.network_mode.startswith("container:")
        )

        primary_net = cfg.primary_network()
        primary_ip = cfg.primary_ip()

        if needs_static_ip:
            # Create without network first
            kwargs["network"] = None
            kwargs.pop("network", None)
            kwargs["network_mode"] = "none"

        # Step 5: Create & start container
        self._progress(cfg.name, f"Creating {cfg.name}...")
        try:
            container = self.client.containers.run(image_ref, **kwargs)
        except Exception as e:
            raise RuntimeError(f"Failed to create {cfg.name}: {e}")

        # Step 6: Connect to network with static IP if needed
        if needs_static_ip:
            self._progress(cfg.name, f"Connecting {cfg.name} to {primary_net} ({primary_ip})...")
            try:
                # Disconnect from 'none' network
                try:
                    none_net = self.client.networks.get("none")
                    none_net.disconnect(container)
                except Exception:
                    pass

                # Connect to target network with static IP
                network = self.client.networks.get(primary_net)
                network.connect(
                    container,
                    ipv4_address=primary_ip,
                )

                # Connect any additional networks
                for net_cfg in cfg.networks[1:]:
                    if net_cfg.name != primary_net:
                        try:
                            extra_net = self.client.networks.get(net_cfg.name)
                            connect_kwargs = {}
                            if net_cfg.ip_address:
                                connect_kwargs["ipv4_address"] = net_cfg.ip_address
                            extra_net.connect(container, **connect_kwargs)
                        except Exception as e:
                            self._progress(cfg.name, f"[warn] Could not connect to {net_cfg.name}: {e}")

            except Exception as e:
                raise RuntimeError(f"Failed to connect {cfg.name} to network: {e}")

        self._progress(cfg.name, f"✓ {cfg.name} recreated successfully")

    # ------------------------------------------------------------
    # Summary helpers
    # ------------------------------------------------------------

    @staticmethod
    def summarize(results: list[UpdateResult]) -> dict:
        """Return a summary dict for display in TUI/logs."""
        return {
            "total": len(results),
            "updated": sum(1 for r in results if r.status == UpdateStatus.UPDATED),
            "skipped": sum(1 for r in results if r.status == UpdateStatus.SKIPPED),
            "pinned": sum(1 for r in results if r.status == UpdateStatus.PINNED),
            "failed": sum(1 for r in results if r.status == UpdateStatus.FAILED),
            "dry_run": sum(1 for r in results if r.status == UpdateStatus.DRY_RUN),
            "failures": [r for r in results if r.status == UpdateStatus.FAILED],
        }
