"""
dam/core/inspector.py

Discovers all running (and stopped) containers via the Docker SDK
and extracts their full configuration into a normalized ContainerConfig
dataclass. This is the canonical data model consumed by snapshot.py,
updater.py, drift.py, and the TUI.

Design goals:
  - No shell parsing — pure Docker SDK calls
  - Platform-aware: uses the platform adapter to flag static-IP networks
  - Lossless: captures everything needed to exactly recreate a container
  - Safe: never modifies anything, read-only inspection only
"""

from __future__ import annotations

from typing import Optional

import docker
from docker.errors import DockerException

from dam.platform.base import BasePlatform


# ------------------------------------------------------------
# Data model
# ------------------------------------------------------------

@dataclass
class PortBinding:
    container_port: str        # e.g. "8080/tcp"
    host_ip: str               # e.g. "0.0.0.0" or ""
    host_port: str             # e.g. "8080"


@dataclass
class DeviceMapping:
    host_path: str
    container_path: str
    permissions: str = "rwm"


@dataclass
class NetworkConfig:
    name: str
    driver: Optional[str]
    ip_address: Optional[str]   # static IP if assigned
    mac_address: Optional[str]
    is_static: bool             # platform-determined


@dataclass
class ContainerConfig:
    # Identity
    name: str                           # container name (no leading /)
    image: str                          # full image reference
    image_id: str                       # sha256 of current image layer

    # Runtime
    status: str                         # running / exited / paused etc.
    restart_policy: str                 # unless-stopped / always / on-failure / no

    # Network
    network_mode: str                   # host / bridge / macvlan_network / etc.
    networks: list[NetworkConfig]       # all attached networks with IP info
    ports: list[PortBinding]            # explicit port bindings

    # Storage
    binds: list[str]                    # volume mounts as "host:container[:mode]"

    # Environment (user-set only — runtime injected vars filtered out)
    env: dict[str, str]

    # Capabilities & privileges
    privileged: bool
    cap_add: list[str]
    cap_drop: list[str]

    # Devices
    devices: list[DeviceMapping]

    # Misc
    extra_hosts: list[str]             # --add-host entries
    labels: dict[str, str]             # container labels (DAM uses these for metadata)

    # DAM metadata (not from Docker — populated by inspector)
    version_strategy: str = "latest"   # latest / stable / pinned
    pinned_digest: Optional[str] = None

    def primary_ip(self) -> Optional[str]:
        """Return the first static IP found across all networks, or None."""
        for net in self.networks:
            if net.ip_address:
                return net.ip_address
        return None

    def primary_network(self) -> Optional[str]:
        """Return the primary network name."""
        if self.networks:
            return self.networks[0].name
        return self.network_mode if self.network_mode not in ("host", "bridge", "") else self.network_mode


# ------------------------------------------------------------
# Runtime env vars injected by base images — filter these out
# when saving env to snapshot so we don't re-inject them on
# recreate (they'll come from the new image automatically).
# ------------------------------------------------------------

_RUNTIME_ENV_PREFIXES = (
    "PATH=",
    "LANG=",
    "LC_",
    "GPG_KEY=",
    "PYTHON_VERSION=",
    "PYTHON_SHA256=",
    "S6_",
    "UV_",
    "PIP_",
    "LSIO_",
    "VIRTUAL_ENV=",
    "HOME=",
    "TERM=",
    "PS1=",
    "XDG_",
    "chip_example_url=",
    "NODE_ENV=production",   # injected by node images
    "CI=true",               # injected by some images
    "NEXT_TELEMETRY_DISABLED=",
)


def _is_runtime_env(var: str) -> bool:
    """Return True if this env var is injected by the base image, not the user."""
    return any(var.startswith(prefix) for prefix in _RUNTIME_ENV_PREFIXES)


def _parse_env_list(env_list: list[str]) -> dict[str, str]:
    """Convert ['KEY=value', ...] to {'KEY': 'value'} filtering runtime vars."""
    result = {}
    for item in (env_list or []):
        if _is_runtime_env(item):
            continue
        if "=" in item:
            k, _, v = item.partition("=")
            result[k] = v
        else:
            result[item] = ""
    return result


def _parse_ports(port_bindings: dict) -> list[PortBinding]:
    """Parse HostConfig.PortBindings into PortBinding list."""
    result = []
    for container_port, bindings in (port_bindings or {}).items():
        for binding in (bindings or []):
            result.append(PortBinding(
                container_port=container_port,
                host_ip=binding.get("HostIp", ""),
                host_port=binding.get("HostPort", ""),
            ))
    return result


def _parse_devices(devices: list[dict]) -> list[DeviceMapping]:
    """Parse HostConfig.Devices into DeviceMapping list."""
    result = []
    for d in (devices or []):
        result.append(DeviceMapping(
            host_path=d.get("PathOnHost", ""),
            container_path=d.get("PathInContainer", ""),
            permissions=d.get("CgroupPermissions", "rwm"),
        ))
    return result


def _parse_networks(
    container_attrs: dict,
    platform: BasePlatform,
) -> list[NetworkConfig]:
    """Extract per-network info including static IPs and MAC addresses."""
    result = []
    networks_data = container_attrs.get("NetworkSettings", {}).get("Networks", {})
    for net_name, net_info in networks_data.items():
        ip = net_info.get("IPAMConfig", {}) or {}
        static_ip = ip.get("IPv4Address") or net_info.get("IPAddress") or None
        # Only treat as static if platform confirms the network supports it
        is_static = bool(static_ip) and platform.is_static_ip_network(net_name)
        result.append(NetworkConfig(
            name=net_name,
            driver=platform.get_network_driver(net_name),
            ip_address=static_ip if is_static else None,
            mac_address=net_info.get("MacAddress") or None,
            is_static=is_static,
        ))
    return result


# ------------------------------------------------------------
# Main inspector
# ------------------------------------------------------------

class Inspector:
    """
    Connects to the local Docker daemon and inspects all containers.
    Returns a list of ContainerConfig objects.
    """

    def __init__(self, platform: BasePlatform):
        self.platform = platform
        try:
            self.client = docker.from_env()
            self.client.ping()
        except DockerException as e:
            raise RuntimeError(f"Cannot connect to Docker daemon: {e}")

    def inspect_all(
        self,
        include_stopped: bool = True,
        settings_containers: dict = None,
    ) -> list[ContainerConfig]:
        """
        Inspect all containers and return their configs.

        Args:
            include_stopped: if True, include exited/stopped containers
            settings_containers: per-container overrides from settings.yaml
        """
        containers = self.client.containers.list(all=include_stopped)
        configs = []
        for c in containers:
            try:
                cfg = self._extract(c, settings_containers or {})
                configs.append(cfg)
            except Exception as e:
                # Never crash the whole inspection over one bad container
                print(f"[warn] Could not inspect {c.name}: {e}")
        return configs

    def inspect_one(self, name: str) -> Optional[ContainerConfig]:
        """Inspect a single container by name. Returns None if not found."""
        try:
            c = self.client.containers.get(name)
            return self._extract(c, {})
        except docker.errors.NotFound:
            return None
        except Exception as e:
            raise RuntimeError(f"Error inspecting {name}: {e}")

    def _extract(self, container, settings_containers: dict) -> ContainerConfig:
        """Extract a ContainerConfig from a Docker container object."""
        attrs = container.attrs
        hc = attrs.get("HostConfig", {})
        cc = attrs.get("Config", {})

        name = attrs["Name"].lstrip("/")

        # Network mode: normalize container:<id> references
        network_mode = hc.get("NetworkMode", "bridge")
        if network_mode.startswith("container:"):
            # Keep as-is — updater will handle this
            pass

        # Per-container settings overrides
        container_settings = settings_containers.get(name, {})
        version_strategy = container_settings.get("version_strategy", "latest")
        pinned_digest = container_settings.get("pinned_digest", None)

        return ContainerConfig(
            name=name,
            image=cc.get("Image", ""),
            image_id=attrs.get("Image", ""),
            status=attrs.get("State", {}).get("Status", "unknown"),
            restart_policy=hc.get("RestartPolicy", {}).get("Name", "no"),
            network_mode=network_mode,
            networks=_parse_networks(attrs, self.platform),
            ports=_parse_ports(hc.get("PortBindings", {})),
            binds=hc.get("Binds") or [],
            env=_parse_env_list(cc.get("Env", [])),
            privileged=hc.get("Privileged", False),
            cap_add=hc.get("CapAdd") or [],
            cap_drop=hc.get("CapDrop") or [],
            devices=_parse_devices(hc.get("Devices")),
            extra_hosts=hc.get("ExtraHosts") or [],
            labels={
                k: v for k, v in (cc.get("Labels") or {}).items()
                if not k.startswith("org.opencontainers")  # skip OCI standard labels
            },
            version_strategy=version_strategy,
            pinned_digest=pinned_digest,
        )

    def get_image_digest(self, image_ref: str) -> Optional[str]:
        """
        Return the current local digest for an image reference.
        Used by updater to detect whether a pull brought a new image.
        """
        try:
            img = self.client.images.get(image_ref)
            digests = img.attrs.get("RepoDigests", [])
            return digests[0] if digests else img.id
        except Exception:
            return None

    def docker_version(self) -> dict:
        """Return Docker daemon version info."""
        try:
            return self.client.version()
        except Exception:
            return {}
