"""
tests/test_exporter_importer_deprecation.py

Tests for:
  - dam/core/exporter.py   (all 3 formats, single + multi)
  - dam/core/importer.py   (load, parse, dry-run, overwrite logic)
  - dam/core/deprecation.py (bundled DB, normalize, checker)
"""

import sys
import os
import tempfile
import stat
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml

from dam.core.inspector import ContainerConfig, NetworkConfig, PortBinding, DeviceMapping
from dam.core.exporter import (
    Exporter, export_dam_yaml, export_dam_yaml_multi,
    export_docker_run, export_docker_run_multi,
    export_compose, export_compose_multi,
    _build_docker_run_command, _build_compose_document,
    FORMATS,
)
from dam.core.importer import (
    Importer, ImportResult, ImportStatus,
    load_import_file, _dict_to_config,
)
from dam.core.deprecation import (
    DeprecationChecker, DeprecationResult, DeprecationStatus, DeprecationSeverity,
    _normalize_image, load_eol_db,
)
from dam.platform.generic import GenericPlatform
from dam.platform.qnap import QNAPPlatform


# ------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------

def make_cfg(
    name="homeassistant",
    image="ghcr.io/home-assistant/home-assistant:stable",
    image_id="sha256:abc123",
    ip="10.20.30.33",
    network="macvlan_network",
    privileged=True,
    env=None,
    binds=None,
    ports=None,
    devices=None,
    extra_hosts=None,
    labels=None,
    cap_add=None,
    restart_policy="unless-stopped",
) -> ContainerConfig:
    return ContainerConfig(
        name=name,
        image=image,
        image_id=image_id,
        status="running",
        restart_policy=restart_policy,
        network_mode=network,
        networks=[NetworkConfig(
            name=network, driver="macvlan",
            ip_address=ip, mac_address="02:42:0a:14:1e:21",
            is_static=True,
        )],
        ports=ports or [],
        binds=binds or ["/share/Container/ha/config:/config"],
        env=env if env is not None else {"TZ": "America/New_York"},
        privileged=privileged,
        cap_add=cap_add or [],
        cap_drop=[],
        devices=devices or [],
        extra_hosts=extra_hosts or [],
        labels=labels or {},
        version_strategy="latest",
    )


def make_platform():
    p = QNAPPlatform()
    p._network_driver_cache = {"macvlan_network": "macvlan"}
    return p


SAMPLE_EOL_DB = {
    "deprecated": [
        {
            "image": "containrrr/watchtower",
            "status": "archived",
            "reason": "Archived December 2025",
            "archived_date": "2025-12-01",
            "alternatives": [
                {"name": "docker-automation-manager",
                 "url": "https://github.com/pawlisko80/docker-automation-manager"}
            ],
        },
        {
            "image": "portainer/portainer",
            "status": "deprecated",
            "reason": "Use portainer/portainer-ce instead",
            "alternatives": [
                {"name": "portainer/portainer-ce"}
            ],
        },
        {
            "image": "postgres",
            "status": "eol",
            "reason": "PostgreSQL 11 is end of life",
            "eol_date": "2023-11-09",
            "alternatives": [{"name": "postgres:16"}],
        },
    ]
}


# ============================================================
# Tests: _normalize_image
# ============================================================

def test_normalize_strips_tag():
    assert _normalize_image("nginx:latest") == "nginx"

def test_normalize_strips_digest():
    assert _normalize_image("nginx@sha256:abc123") == "nginx"

def test_normalize_preserves_registry():
    assert _normalize_image("ghcr.io/home-assistant/home-assistant:stable") == \
           "ghcr.io/home-assistant/home-assistant"

def test_normalize_docker_library():
    assert _normalize_image("docker.io/library/postgres:15") == "postgres"

def test_normalize_no_tag():
    assert _normalize_image("containrrr/watchtower") == "containrrr/watchtower"


# ============================================================
# Tests: DeprecationChecker — bundled DB
# ============================================================

def make_checker(db=None):
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(db or SAMPLE_EOL_DB, f)
        path = Path(f.name)
    checker = DeprecationChecker(eol_db_path=path)
    os.unlink(path)
    return checker

def test_checker_ok_for_unknown_image():
    checker = make_checker()
    cfg = make_cfg(image="ghcr.io/home-assistant/home-assistant:stable")
    result = checker.check(cfg)
    assert result.status == DeprecationStatus.OK
    assert result.is_ok

def test_checker_detects_archived():
    checker = make_checker()
    cfg = make_cfg(image="containrrr/watchtower")
    result = checker.check(cfg)
    assert result.status == DeprecationStatus.ARCHIVED
    assert result.severity == DeprecationSeverity.WARNING
    assert result.reason is not None
    assert result.has_alternatives

def test_checker_detects_deprecated():
    checker = make_checker()
    cfg = make_cfg(image="portainer/portainer:latest")
    result = checker.check(cfg)
    assert result.status == DeprecationStatus.DEPRECATED
    assert result.severity == DeprecationSeverity.WARNING

def test_checker_detects_eol():
    checker = make_checker()
    cfg = make_cfg(image="postgres:11")
    result = checker.check(cfg)
    assert result.status == DeprecationStatus.EOL
    assert result.severity == DeprecationSeverity.CRITICAL

def test_checker_alternatives_populated():
    checker = make_checker()
    cfg = make_cfg(image="containrrr/watchtower")
    result = checker.check(cfg)
    assert len(result.alternatives) == 1
    assert result.alternatives[0].name == "docker-automation-manager"
    assert result.alternatives[0].url is not None

def test_checker_check_all():
    checker = make_checker()
    configs = [
        make_cfg("ha", image="ghcr.io/home-assistant/home-assistant:stable"),
        make_cfg("wt", image="containrrr/watchtower"),
    ]
    results = checker.check_all(configs)
    assert len(results) == 2
    assert results[0].is_ok
    assert not results[1].is_ok

def test_checker_warnings_only():
    checker = make_checker()
    configs = [
        make_cfg("ha", image="ghcr.io/home-assistant/home-assistant:stable"),
        make_cfg("wt", image="containrrr/watchtower"),
        make_cfg("port", image="portainer/portainer"),
    ]
    results = checker.check_all(configs)
    warnings = checker.warnings_only(results)
    assert len(warnings) == 2
    assert all(not r.is_ok for r in warnings)

def test_checker_summary():
    checker = make_checker()
    configs = [
        make_cfg("ha", image="ghcr.io/home-assistant/home-assistant:stable"),
        make_cfg("wt", image="containrrr/watchtower"),
        make_cfg("pg", image="postgres:11"),
    ]
    results = checker.check_all(configs)
    summary = checker.summary(results)
    assert summary["total_checked"] == 3
    assert summary["ok"] == 1
    assert summary["archived"] == 1
    assert summary["eol"] == 1

def test_checker_empty_db_all_ok():
    checker = make_checker(db={"deprecated": []})
    cfg = make_cfg(image="containrrr/watchtower")
    result = checker.check(cfg)
    assert result.status == DeprecationStatus.OK

def test_checker_container_name_preserved():
    checker = make_checker()
    cfg = make_cfg(name="my-watchtower", image="containrrr/watchtower")
    result = checker.check(cfg)
    assert result.container_name == "my-watchtower"


# ============================================================
# Tests: load_eol_db
# ============================================================

def test_load_eol_db_missing_returns_empty():
    result = load_eol_db(Path("/nonexistent/path/eol.yaml"))
    assert result == {}

def test_load_eol_db_loads_correctly():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(SAMPLE_EOL_DB, f)
        path = Path(f.name)
    result = load_eol_db(path)
    os.unlink(path)
    assert "deprecated" in result
    assert len(result["deprecated"]) == 3


# ============================================================
# Tests: _build_docker_run_command
# ============================================================

def test_docker_run_basic():
    cfg = make_cfg()
    lines = _build_docker_run_command(cfg)
    full = "\n".join(lines)
    assert "docker run -d" in full
    assert "--name homeassistant" in full
    assert "--restart unless-stopped" in full
    assert "--privileged" in full
    assert "--network macvlan_network" in full
    assert "--ip 10.20.30.33" in full
    assert "ghcr.io/home-assistant/home-assistant:stable" in full

def test_docker_run_volumes():
    cfg = make_cfg(binds=["/share/Container/ha/config:/config",
                           "/share/Container/ha/data:/data"])
    lines = "\n".join(_build_docker_run_command(cfg))
    assert "-v '/share/Container/ha/config:/config'" in lines or \
           "-v /share/Container/ha/config:/config" in lines

def test_docker_run_env_vars():
    cfg = make_cfg(env={"TZ": "America/New_York", "PUID": "1000"})
    lines = "\n".join(_build_docker_run_command(cfg))
    assert "TZ=" in lines
    assert "PUID=" in lines

def test_docker_run_ports():
    p = PortBinding(container_port="8080/tcp", host_ip="", host_port="8080")
    cfg = make_cfg(ports=[p])
    lines = "\n".join(_build_docker_run_command(cfg))
    assert "-p 8080:8080/tcp" in lines

def test_docker_run_host_network():
    cfg = make_cfg(network="host", ip=None)
    cfg.networks = [NetworkConfig("host", None, None, None, False)]
    cfg.network_mode = "host"
    lines = "\n".join(_build_docker_run_command(cfg))
    assert "--network host" in lines
    assert "--ip" not in lines

def test_docker_run_no_privileges():
    cfg = make_cfg(privileged=False)
    lines = "\n".join(_build_docker_run_command(cfg))
    assert "--privileged" not in lines

def test_docker_run_cap_add():
    cfg = make_cfg(cap_add=["NET_ADMIN", "SYS_TIME"])
    lines = "\n".join(_build_docker_run_command(cfg))
    assert "--cap-add NET_ADMIN" in lines
    assert "--cap-add SYS_TIME" in lines

def test_docker_run_devices():
    d = DeviceMapping("/dev/ttyUSB0", "/dev/ttyUSB0", "rwm")
    cfg = make_cfg(devices=[d])
    lines = "\n".join(_build_docker_run_command(cfg))
    assert "--device /dev/ttyUSB0:/dev/ttyUSB0:rwm" in lines


# ============================================================
# Tests: export_docker_run (file output)
# ============================================================

def test_export_docker_run_creates_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = make_cfg()
        path = export_docker_run(cfg, Path(tmpdir))
        assert path.exists()
        assert path.suffix == ".sh"
        assert path.name == "homeassistant.sh"

def test_export_docker_run_is_executable():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = make_cfg()
        path = export_docker_run(cfg, Path(tmpdir))
        assert path.stat().st_mode & stat.S_IXUSR

def test_export_docker_run_contains_shebang():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = make_cfg()
        path = export_docker_run(cfg, Path(tmpdir))
        content = path.read_text()
        assert content.startswith("#!/bin/sh")

def test_export_docker_run_multi_single_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        configs = [make_cfg("ha"), make_cfg("esphome", image="ghcr.io/esphome/esphome")]
        path = export_docker_run_multi(configs, Path(tmpdir))
        assert path.exists()
        assert path.name == "all-containers.sh"
        content = path.read_text()
        assert "Container: ha" in content
        assert "esphome" in content


# ============================================================
# Tests: _build_compose_document
# ============================================================

def test_compose_basic_structure():
    cfg = make_cfg()
    doc = _build_compose_document([cfg])
    assert "services" in doc
    assert "homeassistant" in doc["services"]
    svc = doc["services"]["homeassistant"]
    assert svc["image"] == "ghcr.io/home-assistant/home-assistant:stable"
    assert svc["restart"] == "unless-stopped"
    assert svc["privileged"] is True

def test_compose_volumes():
    cfg = make_cfg(binds=["/share/Container/ha/config:/config"])
    doc = _build_compose_document([cfg])
    svc = doc["services"]["homeassistant"]
    assert "/share/Container/ha/config:/config" in svc["volumes"]

def test_compose_environment():
    cfg = make_cfg(env={"TZ": "America/New_York", "PUID": "1000"})
    doc = _build_compose_document([cfg])
    svc = doc["services"]["homeassistant"]
    assert svc["environment"]["TZ"] == "America/New_York"

def test_compose_network_with_static_ip():
    cfg = make_cfg(ip="10.20.30.33", network="macvlan_network")
    doc = _build_compose_document([cfg])
    svc = doc["services"]["homeassistant"]
    assert "macvlan_network" in svc["networks"]
    assert svc["networks"]["macvlan_network"]["ipv4_address"] == "10.20.30.33"
    # Top-level networks section should have external: true
    assert "networks" in doc
    assert doc["networks"]["macvlan_network"]["external"] is True

def test_compose_host_network():
    cfg = make_cfg(network="host", ip=None)
    cfg.networks = [NetworkConfig("host", None, None, None, False)]
    cfg.network_mode = "host"
    doc = _build_compose_document([cfg])
    svc = doc["services"]["homeassistant"]
    assert svc.get("network_mode") == "host"

def test_compose_multi_service():
    configs = [
        make_cfg("ha", ip="10.20.30.33"),
        make_cfg("esphome", image="ghcr.io/esphome/esphome", ip="10.20.30.34"),
    ]
    doc = _build_compose_document(configs)
    assert "ha" in doc["services"]
    assert "esphome" in doc["services"]

def test_compose_no_empty_sections():
    from dam.core.inspector import ContainerConfig, NetworkConfig
    cfg = ContainerConfig(
        name="homeassistant",
        image="ghcr.io/home-assistant/home-assistant:stable",
        image_id="sha256:abc",
        status="running", restart_policy="unless-stopped",
        network_mode="host",
        networks=[NetworkConfig("host", None, None, None, False)],
        ports=[], binds=[], env={}, privileged=False,
        cap_add=[], cap_drop=[], devices=[], extra_hosts=[], labels={}
    )
    cfg.network_mode = "host"
    doc = _build_compose_document([cfg])
    svc = doc["services"]["homeassistant"]
    assert "environment" not in svc
    assert "volumes" not in svc
    assert "ports" not in svc


# ============================================================
# Tests: export_compose (file output)
# ============================================================

def test_export_compose_creates_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = make_cfg()
        path = export_compose(cfg, Path(tmpdir))
        assert path.exists()
        assert "compose" in path.name

def test_export_compose_valid_yaml():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = make_cfg()
        path = export_compose(cfg, Path(tmpdir))
        content = yaml.safe_load(path.read_text().split("\n\n", 1)[1])  # skip header comments
        assert "services" in content

def test_export_compose_multi():
    with tempfile.TemporaryDirectory() as tmpdir:
        configs = [make_cfg("ha"), make_cfg("nut", image="instantlinux/nut-upsd")]
        path = export_compose_multi(configs, Path(tmpdir))
        assert path.name == "docker-compose.yml"
        content = path.read_text()
        assert "ha" in content
        assert "nut" in content


# ============================================================
# Tests: export_dam_yaml
# ============================================================

def test_export_dam_yaml_creates_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = make_cfg()
        path = export_dam_yaml(cfg, Path(tmpdir))
        assert path.exists()
        assert path.suffix == ".yaml"
        assert path.name == "homeassistant.dam.yaml"

def test_export_dam_yaml_valid_structure():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = make_cfg()
        path = export_dam_yaml(cfg, Path(tmpdir))
        doc = yaml.safe_load(path.read_text())
        assert doc["format"] == "dam-yaml"
        assert "dam_version" in doc
        assert "exported_at" in doc
        assert "container" in doc
        assert doc["container"]["name"] == "homeassistant"

def test_export_dam_yaml_preserves_all_fields():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = make_cfg(
            env={"TZ": "America/New_York"},
            binds=["/share/Container/ha/config:/config"],
            ip="10.20.30.33",
        )
        path = export_dam_yaml(cfg, Path(tmpdir))
        doc = yaml.safe_load(path.read_text())
        c = doc["container"]
        assert c["env"]["TZ"] == "America/New_York"
        assert "/share/Container/ha/config:/config" in c["binds"]
        assert c["networks"][0]["ip_address"] == "10.20.30.33"

def test_export_dam_yaml_multi():
    with tempfile.TemporaryDirectory() as tmpdir:
        configs = [make_cfg("ha"), make_cfg("esphome", image="ghcr.io/esphome/esphome")]
        path = export_dam_yaml_multi(configs, Path(tmpdir))
        assert path.name == "all-containers.dam.yaml"
        doc = yaml.safe_load(path.read_text())
        assert "containers" in doc
        assert "ha" in doc["containers"]
        assert "esphome" in doc["containers"]


# ============================================================
# Tests: Exporter class
# ============================================================

def test_exporter_dam_yaml_single():
    with tempfile.TemporaryDirectory() as tmpdir:
        exporter = Exporter()
        paths = exporter.export([make_cfg()], "dam-yaml", Path(tmpdir))
        assert len(paths) == 1
        assert paths[0].exists()

def test_exporter_docker_run_single():
    with tempfile.TemporaryDirectory() as tmpdir:
        exporter = Exporter()
        paths = exporter.export([make_cfg()], "docker-run", Path(tmpdir))
        assert len(paths) == 1
        assert paths[0].suffix == ".sh"

def test_exporter_compose_single():
    with tempfile.TemporaryDirectory() as tmpdir:
        exporter = Exporter()
        paths = exporter.export([make_cfg()], "compose", Path(tmpdir))
        assert len(paths) == 1

def test_exporter_invalid_format_raises():
    exporter = Exporter()
    try:
        exporter.export([make_cfg()], "invalid-format", Path("/tmp"))
        assert False, "Should raise ValueError"
    except ValueError:
        pass

def test_exporter_empty_list_returns_empty():
    exporter = Exporter()
    paths = exporter.export([], "dam-yaml", Path("/tmp"))
    assert paths == []

def test_exporter_all_formats():
    with tempfile.TemporaryDirectory() as tmpdir:
        exporter = Exporter()
        configs = [make_cfg("ha"), make_cfg("esphome", image="ghcr.io/esphome/esphome")]
        results = exporter.export_all_formats(configs, Path(tmpdir))
        assert set(results.keys()) == set(FORMATS)
        for fmt, paths in results.items():
            assert len(paths) == 1
            assert paths[0].exists()


# ============================================================
# Tests: load_import_file
# ============================================================

def test_load_import_file_single():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = make_cfg()
        export_path = export_dam_yaml(cfg, Path(tmpdir))
        meta, configs = load_import_file(export_path)
        assert len(configs) == 1
        assert configs[0].name == "homeassistant"
        assert "dam_version" in meta

def test_load_import_file_multi():
    with tempfile.TemporaryDirectory() as tmpdir:
        configs = [make_cfg("ha"), make_cfg("nut", image="instantlinux/nut-upsd")]
        export_path = export_dam_yaml_multi(configs, Path(tmpdir))
        meta, loaded = load_import_file(export_path)
        assert len(loaded) == 2
        names = {c.name for c in loaded}
        assert "ha" in names
        assert "nut" in names

def test_load_import_file_not_found():
    try:
        load_import_file(Path("/nonexistent/file.dam.yaml"))
        assert False, "Should raise FileNotFoundError"
    except FileNotFoundError:
        pass

def test_load_import_file_wrong_format():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump({"format": "something-else", "data": {}}, f)
        path = Path(f.name)
    try:
        load_import_file(path)
        assert False, "Should raise ValueError"
    except ValueError:
        pass
    finally:
        os.unlink(path)

def test_load_import_roundtrip_preserves_config():
    with tempfile.TemporaryDirectory() as tmpdir:
        original = make_cfg(
            env={"TZ": "America/New_York", "PUID": "1000"},
            binds=["/share/Container/ha/config:/config"],
            ip="10.20.30.33",
        )
        export_path = export_dam_yaml(original, Path(tmpdir))
        _, loaded = load_import_file(export_path)
        restored = loaded[0]

        assert restored.image == original.image
        assert restored.restart_policy == original.restart_policy
        assert restored.privileged == original.privileged
        assert restored.env == original.env
        assert restored.binds == original.binds
        assert restored.networks[0].ip_address == original.networks[0].ip_address


# ============================================================
# Tests: Importer — dry run
# ============================================================

def test_importer_dry_run_returns_dry_run_status():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = make_cfg()
        export_path = export_dam_yaml(cfg, Path(tmpdir))
        platform = make_platform()
        importer = Importer(platform, dry_run=True)
        results = importer.import_file(export_path)
        assert len(results) == 1
        assert results[0].status == ImportStatus.DRY_RUN
        assert results[0].container_name == "homeassistant"

def test_importer_dry_run_no_docker_calls():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = make_cfg()
        export_path = export_dam_yaml(cfg, Path(tmpdir))
        platform = make_platform()
        importer = Importer(platform, dry_run=True)
        with patch('docker.from_env') as mock_docker:
            results = importer.import_file(export_path)
            mock_docker.assert_not_called()
        assert results[0].status == ImportStatus.DRY_RUN

def test_importer_summarize():
    results = [
        ImportResult("ha", ImportStatus.CREATED, "ha:stable"),
        ImportResult("esphome", ImportStatus.SKIPPED, "esphome"),
        ImportResult("nut", ImportStatus.FAILED, "nut:latest", error="boom"),
    ]
    summary = Importer.summarize(results)
    assert summary["created"] == 1
    assert summary["skipped"] == 1
    assert summary["failed"] == 1
    assert len(summary["failures"]) == 1

def test_importer_file_not_found():
    platform = make_platform()
    importer = Importer(platform, dry_run=True)
    results = importer.import_file(Path("/nonexistent/file.dam.yaml"))
    assert results[0].status == ImportStatus.FAILED
    assert results[0].error is not None


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
