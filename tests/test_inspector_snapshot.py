"""
tests/test_inspector_snapshot.py

Unit tests for dam/core/inspector.py and dam/core/snapshot.py.
Uses mock Docker objects — no live Docker daemon required.
"""

import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from dam.core.inspector import (
    Inspector,
    ContainerConfig,
    NetworkConfig,
    PortBinding,
    DeviceMapping,
    _parse_env_list,
    _parse_ports,
    _parse_devices,
    _parse_networks,
    _is_runtime_env,
)
from dam.core.snapshot import SnapshotManager, _config_to_dict, _dict_to_config
from dam.platform.generic import GenericPlatform
from dam.platform.qnap import QNAPPlatform


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def make_container_attrs(overrides: dict = {}) -> dict:
    """Build a minimal container attrs dict mimicking Docker SDK output."""
    base = {
        "Name": "/homeassistant",
        "Image": "sha256:abc123def456",
        "State": {"Status": "running"},
        "Config": {
            "Image": "ghcr.io/home-assistant/home-assistant:stable",
            "Env": [
                "TZ=America/New_York",
                "PATH=/usr/local/bin:/usr/bin:/bin",
                "LANG=C.UTF-8",
                "S6_BEHAVIOUR_IF_STAGE2_FAILS=2",
            ],
            "Labels": {
                "org.opencontainers.image.title": "Home Assistant",
                "com.example.custom": "myvalue",
            },
        },
        "HostConfig": {
            "RestartPolicy": {"Name": "unless-stopped"},
            "NetworkMode": "macvlan_network",
            "Binds": ["/share/Container/homeassistant/config:/config"],
            "PortBindings": {},
            "Privileged": True,
            "CapAdd": None,
            "CapDrop": None,
            "Devices": None,
            "ExtraHosts": None,
        },
        "NetworkSettings": {
            "Networks": {
                "macvlan_network": {
                    "IPAMConfig": {"IPv4Address": "10.20.30.33"},
                    "IPAddress": "10.20.30.33",
                    "MacAddress": "02:42:0a:14:1e:21",
                }
            }
        },
    }
    base.update(overrides)
    return base


def make_mock_container(attrs: dict) -> MagicMock:
    c = MagicMock()
    c.attrs = attrs
    c.name = attrs["Name"].lstrip("/")
    return c


def make_platform() -> GenericPlatform:
    p = GenericPlatform()
    return p


def make_qnap_platform() -> QNAPPlatform:
    p = QNAPPlatform()
    # Mock the docker client so network driver calls don't fail
    p._network_driver_cache = {"macvlan_network": "macvlan", "qnet-static-bond0-caeae4": "qnet"}
    return p


# ------------------------------------------------------------
# Tests: _is_runtime_env
# ------------------------------------------------------------

def test_runtime_env_filters_path():
    assert _is_runtime_env("PATH=/usr/bin") is True

def test_runtime_env_filters_lang():
    assert _is_runtime_env("LANG=C.UTF-8") is True

def test_runtime_env_filters_s6():
    assert _is_runtime_env("S6_BEHAVIOUR_IF_STAGE2_FAILS=2") is True

def test_runtime_env_keeps_tz():
    assert _is_runtime_env("TZ=America/New_York") is False

def test_runtime_env_keeps_puid():
    assert _is_runtime_env("PUID=1000") is False

def test_runtime_env_keeps_custom():
    assert _is_runtime_env("MY_CUSTOM_VAR=hello") is False


# ------------------------------------------------------------
# Tests: _parse_env_list
# ------------------------------------------------------------

def test_parse_env_list_filters_runtime():
    env_list = [
        "TZ=America/New_York",
        "PATH=/usr/bin",
        "LANG=C.UTF-8",
        "PUID=1000",
        "S6_CMD_WAIT_FOR_SERVICES=1",
    ]
    result = _parse_env_list(env_list)
    assert "TZ" in result
    assert "PUID" in result
    assert "PATH" not in result
    assert "LANG" not in result
    assert "S6_CMD_WAIT_FOR_SERVICES" not in result

def test_parse_env_list_empty():
    assert _parse_env_list([]) == {}

def test_parse_env_list_none():
    assert _parse_env_list(None) == {}

def test_parse_env_list_value_with_equals():
    # Values containing = should not be truncated
    result = _parse_env_list(["COMPLEX=value=with=equals"])
    assert result["COMPLEX"] == "value=with=equals"


# ------------------------------------------------------------
# Tests: _parse_ports
# ------------------------------------------------------------

def test_parse_ports_empty():
    assert _parse_ports({}) == []

def test_parse_ports_none():
    assert _parse_ports(None) == []

def test_parse_ports_single():
    bindings = {
        "8080/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]
    }
    result = _parse_ports(bindings)
    assert len(result) == 1
    assert result[0].container_port == "8080/tcp"
    assert result[0].host_port == "8080"
    assert result[0].host_ip == "0.0.0.0"

def test_parse_ports_multiple():
    bindings = {
        "80/tcp": [{"HostIp": "", "HostPort": "80"}],
        "443/tcp": [{"HostIp": "", "HostPort": "443"}],
    }
    result = _parse_ports(bindings)
    assert len(result) == 2


# ------------------------------------------------------------
# Tests: _parse_devices
# ------------------------------------------------------------

def test_parse_devices_none():
    assert _parse_devices(None) == []

def test_parse_devices_empty():
    assert _parse_devices([]) == []

def test_parse_devices_single():
    devices = [{"PathOnHost": "/dev/ttyUSB0", "PathInContainer": "/dev/ttyUSB0", "CgroupPermissions": "rwm"}]
    result = _parse_devices(devices)
    assert len(result) == 1
    assert result[0].host_path == "/dev/ttyUSB0"
    assert result[0].permissions == "rwm"


# ------------------------------------------------------------
# Tests: _parse_networks
# ------------------------------------------------------------

def test_parse_networks_macvlan_qnap():
    platform = make_qnap_platform()
    attrs = make_container_attrs()
    result = _parse_networks(attrs, platform)
    assert len(result) == 1
    net = result[0]
    assert net.name == "macvlan_network"
    assert net.ip_address == "10.20.30.33"
    assert net.is_static is True

def test_parse_networks_host_mode():
    platform = make_platform()
    attrs = make_container_attrs()
    attrs["NetworkSettings"]["Networks"] = {
        "host": {
            "IPAMConfig": None,
            "IPAddress": "",
            "MacAddress": "",
        }
    }
    result = _parse_networks(attrs, platform)
    assert len(result) == 1
    assert result[0].name == "host"
    assert result[0].ip_address is None
    assert result[0].is_static is False

def test_parse_networks_no_static_on_generic():
    # Generic platform doesn't know macvlan by name alone
    platform = make_platform()
    # Override to return macvlan driver
    platform._network_driver_cache = {}
    with patch.object(platform, 'get_network_driver', return_value='macvlan'):
        with patch.object(platform, 'is_static_ip_network', return_value=True):
            attrs = make_container_attrs()
            result = _parse_networks(attrs, platform)
            assert result[0].is_static is True


# ------------------------------------------------------------
# Tests: Inspector._extract
# ------------------------------------------------------------

def make_inspector_with_mock_client(platform=None):
    p = platform or make_qnap_platform()
    with patch('docker.from_env') as mock_docker:
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client
        inspector = Inspector(p)
        inspector.client = mock_client
        return inspector, mock_client


def test_inspector_extract_basic():
    inspector, _ = make_inspector_with_mock_client()
    attrs = make_container_attrs()
    container = make_mock_container(attrs)
    cfg = inspector._extract(container, {})

    assert cfg.name == "homeassistant"
    assert cfg.image == "ghcr.io/home-assistant/home-assistant:stable"
    assert cfg.status == "running"
    assert cfg.restart_policy == "unless-stopped"
    assert cfg.privileged is True
    assert "TZ" in cfg.env
    assert "PATH" not in cfg.env  # filtered
    assert cfg.binds == ["/share/Container/homeassistant/config:/config"]

def test_inspector_extract_labels_filters_oci():
    inspector, _ = make_inspector_with_mock_client()
    attrs = make_container_attrs()
    container = make_mock_container(attrs)
    cfg = inspector._extract(container, {})
    # OCI labels should be filtered
    assert "org.opencontainers.image.title" not in cfg.labels
    assert "com.example.custom" in cfg.labels

def test_inspector_extract_version_strategy_default():
    inspector, _ = make_inspector_with_mock_client()
    attrs = make_container_attrs()
    container = make_mock_container(attrs)
    cfg = inspector._extract(container, {})
    assert cfg.version_strategy == "latest"
    assert cfg.pinned_digest is None

def test_inspector_extract_version_strategy_override():
    inspector, _ = make_inspector_with_mock_client()
    attrs = make_container_attrs()
    container = make_mock_container(attrs)
    settings = {
        "homeassistant": {
            "version_strategy": "stable",
        }
    }
    cfg = inspector._extract(container, settings)
    assert cfg.version_strategy == "stable"

def test_inspector_primary_ip():
    inspector, _ = make_inspector_with_mock_client()
    attrs = make_container_attrs()
    container = make_mock_container(attrs)
    cfg = inspector._extract(container, {})
    assert cfg.primary_ip() == "10.20.30.33"

def test_inspector_primary_ip_host_network():
    inspector, _ = make_inspector_with_mock_client()
    attrs = make_container_attrs()
    attrs["HostConfig"]["NetworkMode"] = "host"
    attrs["NetworkSettings"]["Networks"] = {
        "host": {"IPAMConfig": None, "IPAddress": "", "MacAddress": ""}
    }
    container = make_mock_container(attrs)
    cfg = inspector._extract(container, {})
    assert cfg.primary_ip() is None
    assert cfg.primary_network() == "host"


# ------------------------------------------------------------
# Tests: SnapshotManager
# ------------------------------------------------------------

def make_sample_config(name="homeassistant") -> ContainerConfig:
    return ContainerConfig(
        name=name,
        image="ghcr.io/home-assistant/home-assistant:stable",
        image_id="sha256:abc123",
        status="running",
        restart_policy="unless-stopped",
        network_mode="macvlan_network",
        networks=[NetworkConfig(
            name="macvlan_network",
            driver="macvlan",
            ip_address="10.20.30.33",
            mac_address="02:42:0a:14:1e:21",
            is_static=True,
        )],
        ports=[],
        binds=["/share/Container/homeassistant/config:/config"],
        env={"TZ": "America/New_York"},
        privileged=True,
        cap_add=[],
        cap_drop=[],
        devices=[],
        extra_hosts=[],
        labels={"com.example.test": "1"},
    )


def test_snapshot_save_and_load():
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = SnapshotManager(snapshot_dir=Path(tmpdir), retention=10)
        platform = make_qnap_platform()
        configs = [make_sample_config("homeassistant"), make_sample_config("esphome")]

        path = sm.save(configs, platform)
        assert path.exists()

        meta, loaded = sm.load_latest()
        assert meta["platform"] == "QNAP"
        assert len(loaded) == 2
        names = {c.name for c in loaded}
        assert "homeassistant" in names
        assert "esphome" in names


def test_snapshot_roundtrip_preserves_config():
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = SnapshotManager(snapshot_dir=Path(tmpdir))
        platform = make_qnap_platform()
        original = make_sample_config()

        sm.save([original], platform)
        _, loaded = sm.load_latest()
        restored = loaded[0]

        assert restored.name == original.name
        assert restored.image == original.image
        assert restored.restart_policy == original.restart_policy
        assert restored.privileged == original.privileged
        assert restored.env == original.env
        assert restored.binds == original.binds
        assert len(restored.networks) == 1
        assert restored.networks[0].ip_address == "10.20.30.33"
        assert restored.networks[0].is_static is True


def test_snapshot_rotation():
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = SnapshotManager(snapshot_dir=Path(tmpdir), retention=3)
        platform = make_qnap_platform()
        configs = [make_sample_config()]

        # Save 5 snapshots
        import time
        for i in range(5):
            sm.save(configs, platform, label=f"run{i}")
            time.sleep(0.01)  # ensure distinct timestamps

        # Should only keep 3
        assert sm.snapshot_count() <= 3


def test_snapshot_load_previous():
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = SnapshotManager(snapshot_dir=Path(tmpdir), retention=10)
        platform = make_qnap_platform()
        import time

        c1 = make_sample_config()
        c1.image = "image:v1"
        sm.save([c1], platform, label="first")
        time.sleep(0.05)

        c2 = make_sample_config()
        c2.image = "image:v2"
        sm.save([c2], platform, label="second")

        # latest should be v2
        _, latest = sm.load_latest()
        assert latest[0].image == "image:v2"

        # previous (skip=1) should be v1
        result = sm.load_previous(skip=1)
        assert result is not None
        _, prev = result
        assert prev[0].image == "image:v1"


def test_snapshot_empty_returns_none():
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = SnapshotManager(snapshot_dir=Path(tmpdir))
        assert sm.load_latest() is None


def test_snapshot_list_sorted_newest_first():
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = SnapshotManager(snapshot_dir=Path(tmpdir), retention=10)
        platform = make_qnap_platform()
        import time
        for i in range(3):
            sm.save([make_sample_config()], platform, label=f"s{i}")
            time.sleep(0.05)
        snapshots = sm.list_snapshots()
        assert len(snapshots) == 3
        # Names should be sorted newest first
        names = [s.name for s in snapshots]
        assert names == sorted(names, reverse=True)


def test_config_to_dict_and_back():
    original = make_sample_config()
    d = _config_to_dict(original)
    restored = _dict_to_config(original.name, d)

    assert restored.name == original.name
    assert restored.image == original.image
    assert restored.networks[0].ip_address == original.networks[0].ip_address
    assert restored.env == original.env
    assert restored.privileged == original.privileged


# ------------------------------------------------------------
# Run
# ------------------------------------------------------------

if __name__ == "__main__":
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {t.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
