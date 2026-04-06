"""
tests/test_drift.py

Unit tests for dam/core/drift.py — DriftDetector, DriftReport, DriftItem.
No Docker daemon required — pure ContainerConfig object comparison.
"""

import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dam.core.inspector import (
    ContainerConfig, NetworkConfig, PortBinding, DeviceMapping
)
from dam.core.drift import (
    DriftDetector, DriftReport, DriftItem, DriftSeverity
)


# ------------------------------------------------------------
# Fixture helpers
# ------------------------------------------------------------

def make_cfg(
    name="homeassistant",
    image="ghcr.io/home-assistant/home-assistant:stable",
    image_id="sha256:abc123",
    status="running",
    restart_policy="unless-stopped",
    network_mode="macvlan_network",
    ip="10.20.30.33",
    privileged=True,
    env=None,
    binds=None,
    ports=None,
    devices=None,
    extra_hosts=None,
    labels=None,
    cap_add=None,
    cap_drop=None,
    version_strategy="latest",
    networks=None,
) -> ContainerConfig:
    return ContainerConfig(
        name=name,
        image=image,
        image_id=image_id,
        status=status,
        restart_policy=restart_policy,
        network_mode=network_mode,
        networks=networks or [NetworkConfig(
            name=network_mode,
            driver="macvlan",
            ip_address=ip,
            mac_address="02:42:0a:14:1e:21",
            is_static=True,
        )],
        ports=ports or [],
        binds=binds or ["/share/Container/homeassistant/config:/config"],
        env=env if env is not None else {"TZ": "America/New_York"},
        privileged=privileged,
        cap_add=cap_add or [],
        cap_drop=cap_drop or [],
        devices=devices or [],
        extra_hosts=extra_hosts or [],
        labels=labels or {},
        version_strategy=version_strategy,
    )


def detect(a_list, b_list, label_a="prev", label_b="curr") -> DriftReport:
    return DriftDetector().compare(a_list, b_list, label_a, label_b)


# ============================================================
# Tests: DriftSeverity ordering
# ============================================================

def test_severity_ordering():
    assert DriftSeverity.CRITICAL < DriftSeverity.HIGH
    assert DriftSeverity.HIGH < DriftSeverity.MEDIUM
    assert DriftSeverity.MEDIUM < DriftSeverity.LOW
    assert DriftSeverity.LOW < DriftSeverity.INFO


# ============================================================
# Tests: No drift
# ============================================================

def test_no_drift_identical_configs():
    cfg = make_cfg()
    report = detect([cfg], [deepcopy(cfg)])
    assert not report.has_drift

def test_no_drift_multiple_containers():
    cfgs = [make_cfg("ha"), make_cfg("esphome", image="ghcr.io/esphome/esphome", network_mode="host", ip=None)]
    report = detect(cfgs, [deepcopy(c) for c in cfgs])
    assert not report.has_drift

def test_no_drift_empty_sets():
    report = detect([], [])
    assert not report.has_drift


# ============================================================
# Tests: Container existence drift (CRITICAL)
# ============================================================

def test_new_container_detected():
    old = [make_cfg("ha")]
    new = [make_cfg("ha"), make_cfg("esphome", image="ghcr.io/esphome/esphome")]
    report = detect(old, new)
    assert len(report.critical) == 1
    item = report.critical[0]
    assert item.container_name == "esphome"
    assert item.field == "existence"
    assert item.old_value is None
    assert "esphome" in item.new_value

def test_removed_container_detected():
    old = [make_cfg("ha"), make_cfg("nut", image="instantlinux/nut-upsd")]
    new = [make_cfg("ha")]
    report = detect(old, new)
    assert len(report.critical) == 1
    item = report.critical[0]
    assert item.container_name == "nut"
    assert item.new_value is None

def test_all_containers_removed():
    old = [make_cfg("ha"), make_cfg("esphome")]
    report = detect(old, [])
    assert len(report.critical) == 2

def test_all_containers_new():
    new = [make_cfg("ha"), make_cfg("esphome")]
    report = detect([], new)
    assert len(report.critical) == 2


# ============================================================
# Tests: Image drift (HIGH)
# ============================================================

def test_image_reference_changed():
    old = [make_cfg(image="homeassistant:2024.1")]
    new = [make_cfg(image="homeassistant:2025.1")]
    report = detect(old, new)
    items = [i for i in report.high if i.field == "image"]
    assert len(items) == 1
    assert items[0].old_value == "homeassistant:2024.1"
    assert items[0].new_value == "homeassistant:2025.1"

def test_image_digest_changed_same_tag():
    old = [make_cfg(image_id="sha256:old000")]
    new = [make_cfg(image_id="sha256:new000")]
    report = detect(old, new)
    items = [i for i in report.high if i.field == "image_id"]
    assert len(items) == 1
    assert "sha256:old" in items[0].old_value
    assert "sha256:new" in items[0].new_value

def test_image_unchanged_no_drift():
    cfg = make_cfg(image="ha:stable", image_id="sha256:same")
    report = detect([cfg], [deepcopy(cfg)])
    image_drifts = [i for i in report.items if "image" in i.field]
    assert len(image_drifts) == 0

def test_image_id_same_no_drift():
    old = [make_cfg(image_id="sha256:identical")]
    new = [make_cfg(image_id="sha256:identical")]
    report = detect(old, new)
    assert not any(i.field == "image_id" for i in report.items)


# ============================================================
# Tests: Network / IP drift (HIGH)
# ============================================================

def test_ip_address_changed():
    old = [make_cfg(ip="10.20.30.33")]
    new = [make_cfg(ip="10.20.30.99")]
    report = detect(old, new)
    ip_items = [i for i in report.high if "ip_address" in i.field]
    assert len(ip_items) == 1
    assert ip_items[0].old_value == "10.20.30.33"
    assert ip_items[0].new_value == "10.20.30.99"

def test_network_mode_changed():
    old = [make_cfg(network_mode="macvlan_network")]
    new_cfg = make_cfg(network_mode="host", ip=None,
                       networks=[NetworkConfig("host", None, None, None, False)])
    new_cfg.network_mode = "host"
    report = detect(old, [new_cfg])
    items = [i for i in report.high if i.field == "network_mode"]
    assert len(items) == 1
    assert items[0].old_value == "macvlan_network"

def test_network_added():
    old_cfg = make_cfg()
    new_cfg = deepcopy(old_cfg)
    new_cfg.networks.append(NetworkConfig(
        name="bridge", driver="bridge",
        ip_address=None, mac_address=None, is_static=False
    ))
    report = detect([old_cfg], [new_cfg])
    net_items = [i for i in report.high if i.field == "networks"]
    assert any("bridge" in i.description for i in net_items)

def test_network_removed():
    old_cfg = make_cfg()
    old_cfg.networks.append(NetworkConfig("extra_net", "bridge", None, None, False))
    new_cfg = deepcopy(make_cfg())  # only has original network
    report = detect([old_cfg], [new_cfg])
    net_items = [i for i in report.high if i.field == "networks"]
    assert any("extra_net" in i.description for i in net_items)

def test_ip_unchanged_no_drift():
    old = [make_cfg(ip="10.20.30.33")]
    new = [make_cfg(ip="10.20.30.33")]
    report = detect(old, new)
    ip_items = [i for i in report.items if "ip_address" in i.field]
    assert len(ip_items) == 0


# ============================================================
# Tests: Privilege drift (HIGH)
# ============================================================

def test_privileged_gained():
    old = [make_cfg(privileged=False)]
    new = [make_cfg(privileged=True)]
    report = detect(old, new)
    items = [i for i in report.high if i.field == "privileged"]
    assert len(items) == 1
    assert items[0].old_value == "False"
    assert items[0].new_value == "True"

def test_privileged_lost():
    old = [make_cfg(privileged=True)]
    new = [make_cfg(privileged=False)]
    report = detect(old, new)
    items = [i for i in report.high if i.field == "privileged"]
    assert len(items) == 1


# ============================================================
# Tests: Volume drift (MEDIUM)
# ============================================================

def test_volume_added():
    old = [make_cfg(binds=["/share/Container/ha/config:/config"])]
    new = [make_cfg(binds=["/share/Container/ha/config:/config", "/extra:/extra"])]
    report = detect(old, new)
    items = [i for i in report.medium if i.field == "volumes"]
    assert len(items) == 1
    assert "/extra:/extra" in items[0].new_value

def test_volume_removed():
    old = [make_cfg(binds=["/share/Container/ha/config:/config", "/extra:/extra"])]
    new = [make_cfg(binds=["/share/Container/ha/config:/config"])]
    report = detect(old, new)
    items = [i for i in report.medium if i.field == "volumes"]
    assert len(items) == 1
    assert items[0].old_value is not None
    assert items[0].new_value is None

def test_volumes_unchanged():
    cfg = make_cfg(binds=["/share/Container/ha/config:/config"])
    report = detect([cfg], [deepcopy(cfg)])
    assert not any(i.field == "volumes" for i in report.items)


# ============================================================
# Tests: Port drift (MEDIUM)
# ============================================================

def test_port_added():
    p = PortBinding(container_port="8080/tcp", host_ip="0.0.0.0", host_port="8080")
    old = [make_cfg(ports=[])]
    new = [make_cfg(ports=[p])]
    report = detect(old, new)
    items = [i for i in report.medium if i.field == "ports"]
    assert len(items) == 1
    assert "8080" in items[0].new_value

def test_port_removed():
    p = PortBinding(container_port="8080/tcp", host_ip="0.0.0.0", host_port="8080")
    old = [make_cfg(ports=[p])]
    new = [make_cfg(ports=[])]
    report = detect(old, new)
    items = [i for i in report.medium if i.field == "ports"]
    assert len(items) == 1
    assert items[0].new_value is None


# ============================================================
# Tests: Restart policy drift (MEDIUM)
# ============================================================

def test_restart_policy_changed():
    old = [make_cfg(restart_policy="unless-stopped")]
    new = [make_cfg(restart_policy="always")]
    report = detect(old, new)
    items = [i for i in report.medium if i.field == "restart_policy"]
    assert len(items) == 1
    assert items[0].old_value == "unless-stopped"
    assert items[0].new_value == "always"


# ============================================================
# Tests: Env drift (LOW)
# ============================================================

def test_env_var_added():
    old = [make_cfg(env={"TZ": "America/New_York"})]
    new = [make_cfg(env={"TZ": "America/New_York", "PUID": "1000"})]
    report = detect(old, new)
    items = [i for i in report.low if i.field == "env.PUID"]
    assert len(items) == 1
    assert items[0].new_value == "1000"
    assert items[0].old_value is None

def test_env_var_removed():
    old = [make_cfg(env={"TZ": "America/New_York", "PUID": "1000"})]
    new = [make_cfg(env={"TZ": "America/New_York"})]
    report = detect(old, new)
    items = [i for i in report.low if i.field == "env.PUID"]
    assert len(items) == 1
    assert items[0].old_value == "1000"
    assert items[0].new_value is None

def test_env_var_value_changed():
    old = [make_cfg(env={"TZ": "America/New_York"})]
    new = [make_cfg(env={"TZ": "Europe/Warsaw"})]
    report = detect(old, new)
    items = [i for i in report.low if i.field == "env.TZ"]
    assert len(items) == 1
    assert items[0].old_value == "America/New_York"
    assert items[0].new_value == "Europe/Warsaw"

def test_env_unchanged_no_drift():
    cfg = make_cfg(env={"TZ": "America/New_York", "PUID": "1000"})
    report = detect([cfg], [deepcopy(cfg)])
    env_items = [i for i in report.items if i.field.startswith("env.")]
    assert len(env_items) == 0


# ============================================================
# Tests: Capability drift (LOW)
# ============================================================

def test_cap_add_gained():
    old = [make_cfg(cap_add=[])]
    new = [make_cfg(cap_add=["NET_ADMIN"])]
    report = detect(old, new)
    items = [i for i in report.low if i.field == "cap_add"]
    assert len(items) == 1
    assert "NET_ADMIN" in items[0].new_value

def test_cap_add_lost():
    old = [make_cfg(cap_add=["NET_ADMIN", "SYS_TIME"])]
    new = [make_cfg(cap_add=["NET_ADMIN"])]
    report = detect(old, new)
    items = [i for i in report.low if i.field == "cap_add"]
    assert len(items) == 1
    assert "SYS_TIME" in items[0].old_value


# ============================================================
# Tests: Device drift (MEDIUM)
# ============================================================

def test_device_added():
    d = DeviceMapping("/dev/ttyUSB0", "/dev/ttyUSB0", "rwm")
    old = [make_cfg(devices=[])]
    new = [make_cfg(devices=[d])]
    report = detect(old, new)
    items = [i for i in report.medium if i.field == "devices"]
    assert len(items) == 1
    assert "/dev/ttyUSB0" in items[0].new_value

def test_device_removed():
    d = DeviceMapping("/dev/ttyUSB0", "/dev/ttyUSB0", "rwm")
    old = [make_cfg(devices=[d])]
    new = [make_cfg(devices=[])]
    report = detect(old, new)
    items = [i for i in report.medium if i.field == "devices"]
    assert len(items) == 1
    assert items[0].new_value is None


# ============================================================
# Tests: Extra hosts drift (LOW)
# ============================================================

def test_extra_host_added():
    old = [make_cfg(extra_hosts=[])]
    new = [make_cfg(extra_hosts=["myhost:10.0.0.1"])]
    report = detect(old, new)
    items = [i for i in report.low if i.field == "extra_hosts"]
    assert len(items) == 1

def test_extra_host_removed():
    old = [make_cfg(extra_hosts=["myhost:10.0.0.1"])]
    new = [make_cfg(extra_hosts=[])]
    report = detect(old, new)
    items = [i for i in report.low if i.field == "extra_hosts"]
    assert len(items) == 1
    assert items[0].new_value is None


# ============================================================
# Tests: Label drift (LOW)
# ============================================================

def test_label_added():
    old = [make_cfg(labels={})]
    new = [make_cfg(labels={"com.example.env": "production"})]
    report = detect(old, new)
    items = [i for i in report.low if "label" in i.field]
    assert len(items) == 1

def test_label_changed():
    old = [make_cfg(labels={"com.example.env": "staging"})]
    new = [make_cfg(labels={"com.example.env": "production"})]
    report = detect(old, new)
    items = [i for i in report.low if "label" in i.field]
    assert len(items) == 1
    assert items[0].old_value == "staging"
    assert items[0].new_value == "production"


# ============================================================
# Tests: Status drift (INFO)
# ============================================================

def test_status_changed_running_to_exited():
    old = [make_cfg(status="running")]
    new = [make_cfg(status="exited")]
    report = detect(old, new)
    items = [i for i in report.info if i.field == "status"]
    assert len(items) == 1
    assert items[0].severity == DriftSeverity.INFO

def test_status_unchanged_no_drift():
    cfg = make_cfg(status="running")
    report = detect([cfg], [deepcopy(cfg)])
    assert not any(i.field == "status" for i in report.items)


# ============================================================
# Tests: Version strategy drift (LOW)
# ============================================================

def test_version_strategy_changed():
    old = [make_cfg(version_strategy="latest")]
    new = [make_cfg(version_strategy="stable")]
    report = detect(old, new)
    items = [i for i in report.low if i.field == "version_strategy"]
    assert len(items) == 1


# ============================================================
# Tests: DriftReport helpers
# ============================================================

def test_report_by_container():
    old = [make_cfg("ha", ip="10.20.30.33"), make_cfg("esphome", image="esphome:old")]
    new = [make_cfg("ha", ip="10.20.30.99"), make_cfg("esphome", image="esphome:new")]
    report = detect(old, new)
    by_container = report.by_container()
    assert "ha" in by_container
    assert "esphome" in by_container

def test_report_sorted_by_severity():
    old = [make_cfg(status="running", privileged=False, env={"TZ": "UTC"})]
    new = [make_cfg(status="exited", privileged=True, env={"TZ": "US/Eastern"})]
    report = detect(old, new)
    sorted_items = report.sorted_by_severity()
    severities = [i.severity.order for i in sorted_items]
    assert severities == sorted(severities)

def test_report_containers_with_drift():
    old = [make_cfg("ha", ip="10.20.30.33"), make_cfg("nut", image="nut:old")]
    new = [make_cfg("ha", ip="10.20.30.99"), make_cfg("nut", image="nut:new")]
    report = detect(old, new)
    affected = report.containers_with_drift()
    assert "ha" in affected
    assert "nut" in affected

def test_report_summary_structure():
    old = [make_cfg(ip="10.20.30.33", status="running")]
    new = [make_cfg(ip="10.20.30.99", status="exited")]
    report = detect(old, new)
    summary = report.summary()
    assert "total_drift_items" in summary
    assert "containers_affected" in summary
    assert "critical" in summary
    assert "high" in summary
    assert "medium" in summary
    assert "low" in summary
    assert "info" in summary
    assert summary["high"] >= 1
    assert summary["info"] >= 1

def test_report_str_no_drift():
    report = DriftReport()
    assert "No drift" in str(report)

def test_report_str_with_drift():
    report = DriftReport()
    report.add(DriftItem(
        container_name="ha",
        field="image",
        severity=DriftSeverity.HIGH,
        description="Image changed",
        old_value="ha:old",
        new_value="ha:new",
    ))
    output = str(report)
    assert "HIGH" in output
    assert "ha" in output
    assert "ha:old" in output
    assert "ha:new" in output

def test_drift_item_str():
    item = DriftItem(
        container_name="nut",
        field="ip_address[macvlan_network]",
        severity=DriftSeverity.HIGH,
        description="IP changed",
        old_value="10.20.30.36",
        new_value="10.20.30.99",
    )
    s = str(item)
    assert "HIGH" in s
    assert "nut" in s
    assert "10.20.30.36" in s
    assert "10.20.30.99" in s


# ============================================================
# Tests: Multi-container, multi-field drift in one shot
# ============================================================

def test_full_fleet_drift():
    """Simulate a realistic monthly drift scenario across all 6 containers."""
    old_configs = [
        make_cfg("homeassistant", image="ha:2024.12", image_id="sha256:old_ha",
                 ip="10.20.30.33", status="running"),
        make_cfg("esphome", image="esphome:2024.12", image_id="sha256:old_esp",
                 network_mode="host", ip=None,
                 networks=[NetworkConfig("host", None, None, None, False)]),
        make_cfg("nut", image="nut-upsd:latest", image_id="sha256:old_nut",
                 ip="10.20.30.36", network_mode="qnet-static-bond0-caeae4",
                 networks=[NetworkConfig("qnet-static-bond0-caeae4", "qnet",
                                        "10.20.30.36", None, True)]),
        make_cfg("peanut", image="peanut:latest", image_id="sha256:old_peanut",
                 ip="10.20.30.35", network_mode="qnet-static-bond0-caeae4",
                 networks=[NetworkConfig("qnet-static-bond0-caeae4", "qnet",
                                        "10.20.30.35", None, True)]),
        make_cfg("qbittorrent", image="linuxserver/qbittorrent:latest",
                 image_id="sha256:old_qb", ip="10.20.30.34",
                 network_mode="qnet-static-bond0-caeae4",
                 networks=[NetworkConfig("qnet-static-bond0-caeae4", "qnet",
                                        "10.20.30.34", None, True)]),
        make_cfg("matter-server", image="python-matter-server:stable",
                 image_id="sha256:old_matter", ip="10.20.30.32",
                 network_mode="macvlan_network"),
    ]

    new_configs = [
        # HA: new image digest
        make_cfg("homeassistant", image="ha:2024.12", image_id="sha256:new_ha",
                 ip="10.20.30.33", status="running"),
        # ESPHome: new image digest
        make_cfg("esphome", image="esphome:2024.12", image_id="sha256:new_esp",
                 network_mode="host", ip=None,
                 networks=[NetworkConfig("host", None, None, None, False)]),
        # NUT: unchanged
        make_cfg("nut", image="nut-upsd:latest", image_id="sha256:old_nut",
                 ip="10.20.30.36", network_mode="qnet-static-bond0-caeae4",
                 networks=[NetworkConfig("qnet-static-bond0-caeae4", "qnet",
                                        "10.20.30.36", None, True)]),
        # Peanut: unchanged
        make_cfg("peanut", image="peanut:latest", image_id="sha256:old_peanut",
                 ip="10.20.30.35", network_mode="qnet-static-bond0-caeae4",
                 networks=[NetworkConfig("qnet-static-bond0-caeae4", "qnet",
                                        "10.20.30.35", None, True)]),
        # qbittorrent: new image + env var added
        make_cfg("qbittorrent", image="linuxserver/qbittorrent:latest",
                 image_id="sha256:new_qb", ip="10.20.30.34",
                 network_mode="qnet-static-bond0-caeae4",
                 networks=[NetworkConfig("qnet-static-bond0-caeae4", "qnet",
                                        "10.20.30.34", None, True)],
                 env={"TZ": "America/New_York", "PUID": "1000", "PGID": "1000",
                      "WEBUI_PORT": "8080"}),
        # matter-server: unchanged
        make_cfg("matter-server", image="python-matter-server:stable",
                 image_id="sha256:old_matter", ip="10.20.30.32",
                 network_mode="macvlan_network"),
    ]

    report = detect(old_configs, new_configs, "last month", "this month")

    # HA and ESPHome: image_id changed
    assert any(i.container_name == "homeassistant" and i.field == "image_id"
               for i in report.high)
    assert any(i.container_name == "esphome" and i.field == "image_id"
               for i in report.high)

    # qbittorrent: image_id + env vars added
    assert any(i.container_name == "qbittorrent" and i.field == "image_id"
               for i in report.high)
    qb_env = [i for i in report.low
              if i.container_name == "qbittorrent" and i.field.startswith("env.")]
    assert len(qb_env) > 0

    # NUT, peanut, matter-server: no drift
    drifted = report.containers_with_drift()
    assert "nut" not in drifted
    assert "peanut" not in drifted
    assert "matter-server" not in drifted

    summary = report.summary()
    assert summary["containers_affected"] == 3  # ha, esphome, qbittorrent


# ============================================================
# Run
# ============================================================

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
