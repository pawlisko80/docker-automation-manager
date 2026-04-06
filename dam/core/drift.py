"""
dam/core/drift.py

Detects configuration drift between:
  - Two snapshots (snapshot-to-snapshot comparison)
  - A snapshot and the current live container state (snapshot-to-live)

Drift categories (in severity order):
  CRITICAL  — container missing entirely (new or deleted)
  HIGH      — image changed, network/IP changed, privilege change
  MEDIUM    — volume mounts changed, port bindings changed, restart policy changed
  LOW       — env vars changed, labels changed, capabilities changed

Each drift produces a DriftItem with:
  - container name
  - field that drifted
  - severity level
  - human-readable description
  - old value / new value for display

The DriftReport aggregates all DriftItems for a full comparison run
and provides helpers for TUI rendering and log output.

Design goals:
  - Never modifies anything — pure read/compare
  - Works on ContainerConfig objects directly (no Docker daemon needed)
  - Rich enough for TUI diff display (old/new values always present)
  - Structured enough for log output and future alerting
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from dam.core.inspector import ContainerConfig, NetworkConfig


# ------------------------------------------------------------
# Severity levels
# ------------------------------------------------------------

class DriftSeverity(Enum):
    CRITICAL = "critical"   # container missing / new container appeared
    HIGH     = "high"       # image, network, IP, privileges changed
    MEDIUM   = "medium"     # volumes, ports, restart policy changed
    LOW      = "low"        # env, labels, caps changed
    INFO     = "info"       # status change only (running→exited etc.)

    @property
    def order(self) -> int:
        return {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}[self.value]

    def __lt__(self, other: "DriftSeverity") -> bool:
        return self.order < other.order


# ------------------------------------------------------------
# Drift item
# ------------------------------------------------------------

@dataclass
class DriftItem:
    container_name: str
    field: str                      # e.g. "image", "ip_address", "env.TZ"
    severity: DriftSeverity
    description: str                # human-readable summary
    old_value: Optional[str] = None
    new_value: Optional[str] = None

    def __str__(self) -> str:
        parts = [f"[{self.severity.value.upper()}] {self.container_name} / {self.field}: {self.description}"]
        if self.old_value is not None:
            parts.append(f"  was: {self.old_value}")
        if self.new_value is not None:
            parts.append(f"  now: {self.new_value}")
        return "\n".join(parts)


# ------------------------------------------------------------
# Drift report
# ------------------------------------------------------------

@dataclass
class DriftReport:
    items: list[DriftItem] = field(default_factory=list)
    snapshot_a_label: str = "previous"   # label for left side (older)
    snapshot_b_label: str = "current"    # label for right side (newer)

    def add(self, item: DriftItem) -> None:
        self.items.append(item)

    @property
    def has_drift(self) -> bool:
        return len(self.items) > 0

    @property
    def critical(self) -> list[DriftItem]:
        return [i for i in self.items if i.severity == DriftSeverity.CRITICAL]

    @property
    def high(self) -> list[DriftItem]:
        return [i for i in self.items if i.severity == DriftSeverity.HIGH]

    @property
    def medium(self) -> list[DriftItem]:
        return [i for i in self.items if i.severity == DriftSeverity.MEDIUM]

    @property
    def low(self) -> list[DriftItem]:
        return [i for i in self.items if i.severity == DriftSeverity.LOW]

    @property
    def info(self) -> list[DriftItem]:
        return [i for i in self.items if i.severity == DriftSeverity.INFO]

    def by_container(self) -> dict[str, list[DriftItem]]:
        """Return drift items grouped by container name."""
        result: dict[str, list[DriftItem]] = {}
        for item in self.items:
            result.setdefault(item.container_name, []).append(item)
        return result

    def sorted_by_severity(self) -> list[DriftItem]:
        """Return all items sorted critical→info."""
        return sorted(self.items, key=lambda i: i.severity.order)

    def containers_with_drift(self) -> set[str]:
        return {i.container_name for i in self.items}

    def summary(self) -> dict:
        return {
            "total_drift_items": len(self.items),
            "containers_affected": len(self.containers_with_drift()),
            "critical": len(self.critical),
            "high": len(self.high),
            "medium": len(self.medium),
            "low": len(self.low),
            "info": len(self.info),
        }

    def __str__(self) -> str:
        if not self.has_drift:
            return "No drift detected."
        lines = [f"Drift Report ({self.snapshot_a_label} → {self.snapshot_b_label})",
                 "=" * 60]
        for item in self.sorted_by_severity():
            lines.append(str(item))
        return "\n".join(lines)


# ------------------------------------------------------------
# Core diff engine
# ------------------------------------------------------------

class DriftDetector:
    """
    Compares two sets of ContainerConfig objects and produces a DriftReport.

    Usage:
        detector = DriftDetector()

        # Compare two snapshots
        report = detector.compare(old_configs, new_configs)

        # Compare snapshot against live containers
        report = detector.compare(snapshot_configs, live_configs,
                                  label_a="last snapshot",
                                  label_b="live")
    """

    def compare(
        self,
        configs_a: list[ContainerConfig],
        configs_b: list[ContainerConfig],
        label_a: str = "previous",
        label_b: str = "current",
    ) -> DriftReport:
        """
        Compare two sets of container configs.
        configs_a = older / reference (snapshot)
        configs_b = newer / current (live or newer snapshot)
        """
        report = DriftReport(snapshot_a_label=label_a, snapshot_b_label=label_b)

        map_a = {c.name: c for c in configs_a}
        map_b = {c.name: c for c in configs_b}

        all_names = set(map_a.keys()) | set(map_b.keys())

        for name in sorted(all_names):
            cfg_a = map_a.get(name)
            cfg_b = map_b.get(name)

            if cfg_a is None:
                # New container — appeared in B but not in A
                report.add(DriftItem(
                    container_name=name,
                    field="existence",
                    severity=DriftSeverity.CRITICAL,
                    description=f"New container appeared in {label_b}",
                    old_value=None,
                    new_value=cfg_b.image if cfg_b else "unknown",
                ))
                continue

            if cfg_b is None:
                # Container removed — in A but not in B
                report.add(DriftItem(
                    container_name=name,
                    field="existence",
                    severity=DriftSeverity.CRITICAL,
                    description=f"Container removed (was in {label_a}, missing in {label_b})",
                    old_value=cfg_a.image,
                    new_value=None,
                ))
                continue

            # Both exist — compare field by field
            self._diff_container(cfg_a, cfg_b, report)

        return report

    # ------------------------------------------------------------
    # Per-field comparators
    # ------------------------------------------------------------

    def _diff_container(
        self,
        a: ContainerConfig,
        b: ContainerConfig,
        report: DriftReport,
    ) -> None:
        name = a.name

        # --- Image ---
        if a.image != b.image:
            report.add(DriftItem(
                container_name=name,
                field="image",
                severity=DriftSeverity.HIGH,
                description="Image reference changed",
                old_value=a.image,
                new_value=b.image,
            ))
        elif a.image_id != b.image_id and a.image_id and b.image_id:
            report.add(DriftItem(
                container_name=name,
                field="image_id",
                severity=DriftSeverity.HIGH,
                description="Image updated (same tag, new digest)",
                old_value=a.image_id[:19] if a.image_id else None,
                new_value=b.image_id[:19] if b.image_id else None,
            ))

        # --- Status ---
        if a.status != b.status:
            report.add(DriftItem(
                container_name=name,
                field="status",
                severity=DriftSeverity.INFO,
                description="Container status changed",
                old_value=a.status,
                new_value=b.status,
            ))

        # --- Restart policy ---
        if a.restart_policy != b.restart_policy:
            report.add(DriftItem(
                container_name=name,
                field="restart_policy",
                severity=DriftSeverity.MEDIUM,
                description="Restart policy changed",
                old_value=a.restart_policy,
                new_value=b.restart_policy,
            ))

        # --- Privileged ---
        if a.privileged != b.privileged:
            report.add(DriftItem(
                container_name=name,
                field="privileged",
                severity=DriftSeverity.HIGH,
                description="Privilege mode changed",
                old_value=str(a.privileged),
                new_value=str(b.privileged),
            ))

        # --- Network mode ---
        if a.network_mode != b.network_mode:
            report.add(DriftItem(
                container_name=name,
                field="network_mode",
                severity=DriftSeverity.HIGH,
                description="Network mode changed",
                old_value=a.network_mode,
                new_value=b.network_mode,
            ))

        # --- Static IPs ---
        self._diff_ips(a, b, report)

        # --- Networks attached ---
        self._diff_networks(a, b, report)

        # --- Port bindings ---
        self._diff_ports(a, b, report)

        # --- Volume binds ---
        self._diff_binds(a, b, report)

        # --- Environment variables ---
        self._diff_env(a, b, report)

        # --- Capabilities ---
        self._diff_caps(a, b, report)

        # --- Devices ---
        self._diff_devices(a, b, report)

        # --- Extra hosts ---
        self._diff_extra_hosts(a, b, report)

        # --- Labels ---
        self._diff_labels(a, b, report)

        # --- Version strategy ---
        if a.version_strategy != b.version_strategy:
            report.add(DriftItem(
                container_name=name,
                field="version_strategy",
                severity=DriftSeverity.LOW,
                description="Version strategy changed",
                old_value=a.version_strategy,
                new_value=b.version_strategy,
            ))

    def _diff_ips(
        self,
        a: ContainerConfig,
        b: ContainerConfig,
        report: DriftReport,
    ) -> None:
        """Compare static IP assignments across all networks."""
        nets_a = {n.name: n for n in a.networks}
        nets_b = {n.name: n for n in b.networks}

        for net_name in set(nets_a.keys()) | set(nets_b.keys()):
            na = nets_a.get(net_name)
            nb = nets_b.get(net_name)

            if na and nb and na.ip_address != nb.ip_address:
                if na.ip_address or nb.ip_address:  # at least one is non-None
                    report.add(DriftItem(
                        container_name=a.name,
                        field=f"ip_address[{net_name}]",
                        severity=DriftSeverity.HIGH,
                        description=f"Static IP changed on network '{net_name}'",
                        old_value=na.ip_address or "(dynamic)",
                        new_value=nb.ip_address or "(dynamic)",
                    ))

    def _diff_networks(
        self,
        a: ContainerConfig,
        b: ContainerConfig,
        report: DriftReport,
    ) -> None:
        """Detect networks added or removed."""
        nets_a = {n.name for n in a.networks}
        nets_b = {n.name for n in b.networks}

        for added in nets_b - nets_a:
            report.add(DriftItem(
                container_name=a.name,
                field="networks",
                severity=DriftSeverity.HIGH,
                description=f"Connected to new network '{added}'",
                old_value=None,
                new_value=added,
            ))

        for removed in nets_a - nets_b:
            report.add(DriftItem(
                container_name=a.name,
                field="networks",
                severity=DriftSeverity.HIGH,
                description=f"Disconnected from network '{removed}'",
                old_value=removed,
                new_value=None,
            ))

    def _diff_ports(
        self,
        a: ContainerConfig,
        b: ContainerConfig,
        report: DriftReport,
    ) -> None:
        """Compare port bindings as sets of 'container_port->host_port' strings."""
        def port_set(cfg: ContainerConfig) -> set[str]:
            return {
                f"{p.container_port}->{p.host_ip}:{p.host_port}"
                for p in cfg.ports
            }

        ports_a = port_set(a)
        ports_b = port_set(b)

        for added in ports_b - ports_a:
            report.add(DriftItem(
                container_name=a.name,
                field="ports",
                severity=DriftSeverity.MEDIUM,
                description=f"Port binding added: {added}",
                old_value=None,
                new_value=added,
            ))

        for removed in ports_a - ports_b:
            report.add(DriftItem(
                container_name=a.name,
                field="ports",
                severity=DriftSeverity.MEDIUM,
                description=f"Port binding removed: {removed}",
                old_value=removed,
                new_value=None,
            ))

    def _diff_binds(
        self,
        a: ContainerConfig,
        b: ContainerConfig,
        report: DriftReport,
    ) -> None:
        """Compare volume mount binds as sets."""
        binds_a = set(a.binds)
        binds_b = set(b.binds)

        for added in binds_b - binds_a:
            report.add(DriftItem(
                container_name=a.name,
                field="volumes",
                severity=DriftSeverity.MEDIUM,
                description=f"Volume mount added: {added}",
                old_value=None,
                new_value=added,
            ))

        for removed in binds_a - binds_b:
            report.add(DriftItem(
                container_name=a.name,
                field="volumes",
                severity=DriftSeverity.MEDIUM,
                description=f"Volume mount removed: {removed}",
                old_value=removed,
                new_value=None,
            ))

    def _diff_env(
        self,
        a: ContainerConfig,
        b: ContainerConfig,
        report: DriftReport,
    ) -> None:
        """Compare environment variable dicts key-by-key."""
        all_keys = set(a.env.keys()) | set(b.env.keys())

        for key in sorted(all_keys):
            val_a = a.env.get(key)
            val_b = b.env.get(key)

            if val_a is None and val_b is not None:
                report.add(DriftItem(
                    container_name=a.name,
                    field=f"env.{key}",
                    severity=DriftSeverity.LOW,
                    description=f"Env var added: {key}",
                    old_value=None,
                    new_value=val_b,
                ))
            elif val_a is not None and val_b is None:
                report.add(DriftItem(
                    container_name=a.name,
                    field=f"env.{key}",
                    severity=DriftSeverity.LOW,
                    description=f"Env var removed: {key}",
                    old_value=val_a,
                    new_value=None,
                ))
            elif val_a != val_b:
                report.add(DriftItem(
                    container_name=a.name,
                    field=f"env.{key}",
                    severity=DriftSeverity.LOW,
                    description=f"Env var changed: {key}",
                    old_value=val_a,
                    new_value=val_b,
                ))

    def _diff_caps(
        self,
        a: ContainerConfig,
        b: ContainerConfig,
        report: DriftReport,
    ) -> None:
        """Compare cap_add and cap_drop lists."""
        for field_name, list_a, list_b in [
            ("cap_add", a.cap_add, b.cap_add),
            ("cap_drop", a.cap_drop, b.cap_drop),
        ]:
            set_a = set(list_a or [])
            set_b = set(list_b or [])
            for added in set_b - set_a:
                report.add(DriftItem(
                    container_name=a.name,
                    field=field_name,
                    severity=DriftSeverity.LOW,
                    description=f"{field_name} gained: {added}",
                    old_value=None,
                    new_value=added,
                ))
            for removed in set_a - set_b:
                report.add(DriftItem(
                    container_name=a.name,
                    field=field_name,
                    severity=DriftSeverity.LOW,
                    description=f"{field_name} lost: {removed}",
                    old_value=removed,
                    new_value=None,
                ))

    def _diff_devices(
        self,
        a: ContainerConfig,
        b: ContainerConfig,
        report: DriftReport,
    ) -> None:
        """Compare device mappings."""
        def device_set(cfg: ContainerConfig) -> set[str]:
            return {f"{d.host_path}:{d.container_path}" for d in cfg.devices}

        devs_a = device_set(a)
        devs_b = device_set(b)

        for added in devs_b - devs_a:
            report.add(DriftItem(
                container_name=a.name,
                field="devices",
                severity=DriftSeverity.MEDIUM,
                description=f"Device mapping added: {added}",
                old_value=None,
                new_value=added,
            ))

        for removed in devs_a - devs_b:
            report.add(DriftItem(
                container_name=a.name,
                field="devices",
                severity=DriftSeverity.MEDIUM,
                description=f"Device mapping removed: {removed}",
                old_value=removed,
                new_value=None,
            ))

    def _diff_extra_hosts(
        self,
        a: ContainerConfig,
        b: ContainerConfig,
        report: DriftReport,
    ) -> None:
        """Compare extra host entries."""
        hosts_a = set(a.extra_hosts or [])
        hosts_b = set(b.extra_hosts or [])

        for added in hosts_b - hosts_a:
            report.add(DriftItem(
                container_name=a.name,
                field="extra_hosts",
                severity=DriftSeverity.LOW,
                description=f"Extra host added: {added}",
                old_value=None,
                new_value=added,
            ))

        for removed in hosts_a - hosts_b:
            report.add(DriftItem(
                container_name=a.name,
                field="extra_hosts",
                severity=DriftSeverity.LOW,
                description=f"Extra host removed: {removed}",
                old_value=removed,
                new_value=None,
            ))

    def _diff_labels(
        self,
        a: ContainerConfig,
        b: ContainerConfig,
        report: DriftReport,
    ) -> None:
        """Compare label dicts — only report user-defined label changes."""
        all_keys = set(a.labels.keys()) | set(b.labels.keys())

        for key in sorted(all_keys):
            val_a = a.labels.get(key)
            val_b = b.labels.get(key)

            if val_a != val_b:
                report.add(DriftItem(
                    container_name=a.name,
                    field=f"label.{key}",
                    severity=DriftSeverity.LOW,
                    description=f"Label changed: {key}",
                    old_value=val_a,
                    new_value=val_b,
                ))
