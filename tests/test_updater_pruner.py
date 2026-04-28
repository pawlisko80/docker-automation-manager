"""
tests/test_updater_pruner.py

Unit tests for dam/core/updater.py and dam/core/pruner.py.
All Docker API calls are mocked — no live daemon required.
"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call, PropertyMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from dam.core.inspector import (
    ContainerConfig, NetworkConfig, PortBinding, DeviceMapping
)
from dam.core.updater import (
    Updater, UpdateResult, UpdateStatus,
    _resolve_image_ref, _get_local_digest, _build_run_kwargs,
)
from dam.core.pruner import Pruner, PruneResult
from dam.platform.qnap import QNAPPlatform


# ------------------------------------------------------------
# Shared fixtures
# ------------------------------------------------------------

def make_platform():
    p = QNAPPlatform()
    p._network_driver_cache = {
        "macvlan_network": "macvlan",
        "qnet-static-bond0-caeae4": "qnet",
    }
    return p


def make_config(
    name="homeassistant",
    image="ghcr.io/home-assistant/home-assistant:stable",
    image_id="sha256:oldimage",
    status="running",
    network="macvlan_network",
    ip="10.20.30.33",
    privileged=True,
    version_strategy="latest",
    binds=None,  # pass [] explicitly to test empty
    env=None,
    ports=None,
    devices=None,
) -> ContainerConfig:
    return ContainerConfig(
        name=name,
        image=image,
        image_id=image_id,
        status=status,
        restart_policy="unless-stopped",
        network_mode=network,
        networks=[NetworkConfig(
            name=network,
            driver="macvlan",
            ip_address=ip,
            mac_address="02:42:0a:14:1e:21",
            is_static=True,
        )],
        ports=ports or [],
        binds=binds if binds is not None else ["/share/Container/homeassistant/config:/config"],
        env=env if env is not None else {"TZ": "America/New_York"},
        privileged=privileged,
        cap_add=[],
        cap_drop=[],
        devices=devices or [],
        extra_hosts=[],
        labels={},
        version_strategy=version_strategy,
    )


def make_updater(dry_run=False, delay=0):
    platform = make_platform()
    with patch('docker.from_env') as mock_docker:
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client
        updater = Updater(platform, dry_run=dry_run, recreate_delay=delay)
        updater.client = mock_client
        return updater, mock_client


def make_pruner(dry_run=False, remove_unreferenced=False):
    with patch('docker.from_env') as mock_docker:
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client
        pruner = Pruner(dry_run=dry_run, remove_unreferenced=remove_unreferenced)
        pruner.client = mock_client
        return pruner, mock_client


# ============================================================
# Tests: _resolve_image_ref
# ============================================================

def test_resolve_image_ref_tagged_unchanged():
    ref = _resolve_image_ref("ghcr.io/home-assistant/home-assistant:stable", "latest")
    assert ref == "ghcr.io/home-assistant/home-assistant:stable"

def test_resolve_image_ref_no_tag_latest():
    ref = _resolve_image_ref("instantlinux/nut-upsd", "latest")
    assert ref == "instantlinux/nut-upsd:latest"

def test_resolve_image_ref_no_tag_stable():
    ref = _resolve_image_ref("ghcr.io/esphome/esphome", "stable")
    assert ref == "ghcr.io/esphome/esphome:stable"

def test_resolve_image_ref_pinned_unchanged():
    ref = _resolve_image_ref("instantlinux/nut-upsd", "pinned")
    assert ref == "instantlinux/nut-upsd"

def test_resolve_image_ref_strips_digest():
    image = "myimage@sha256:abc123def"
    ref = _resolve_image_ref(image, "latest")
    # Should strip digest and add :latest
    assert "@" not in ref
    assert ":latest" in ref

def test_resolve_image_ref_preserves_registry():
    ref = _resolve_image_ref("ghcr.io/home-assistant-libs/python-matter-server:stable", "stable")
    assert ref == "ghcr.io/home-assistant-libs/python-matter-server:stable"


# ============================================================
# Tests: _build_run_kwargs
# ============================================================

def test_build_run_kwargs_basic():
    cfg = make_config()
    kwargs = _build_run_kwargs(cfg)
    assert kwargs["name"] == "homeassistant"
    assert kwargs["detach"] is True
    assert kwargs["restart_policy"] == {"Name": "unless-stopped"}
    assert kwargs["privileged"] is True
    assert kwargs["environment"] == {"TZ": "America/New_York"}
    assert kwargs["volumes"] == ["/share/Container/homeassistant/config:/config"]

def test_build_run_kwargs_host_network():
    cfg = make_config(network="host", ip=None)
    cfg.networks = [NetworkConfig(name="host", driver=None, ip_address=None, mac_address=None, is_static=False)]
    cfg.network_mode = "host"
    kwargs = _build_run_kwargs(cfg)
    assert kwargs["network_mode"] == "host"

def test_build_run_kwargs_no_env():
    cfg = make_config(env={})
    kwargs = _build_run_kwargs(cfg)
    assert "environment" not in kwargs

def test_build_run_kwargs_no_volumes():
    cfg = make_config(binds=[])
    kwargs = _build_run_kwargs(cfg)
    assert "volumes" not in kwargs

def test_build_run_kwargs_port_bindings():
    ports = [PortBinding(container_port="8080/tcp", host_ip="0.0.0.0", host_port="8080")]
    cfg = make_config(ports=ports)
    kwargs = _build_run_kwargs(cfg)
    assert "ports" in kwargs
    assert "8080/tcp" in kwargs["ports"]

def test_build_run_kwargs_devices():
    devices = [DeviceMapping(host_path="/dev/ttyUSB0", container_path="/dev/ttyUSB0", permissions="rwm")]
    cfg = make_config(devices=devices)
    kwargs = _build_run_kwargs(cfg)
    assert "devices" in kwargs
    assert kwargs["devices"] == ["/dev/ttyUSB0:/dev/ttyUSB0:rwm"]

def test_build_run_kwargs_no_privileges():
    cfg = make_config(privileged=False)
    kwargs = _build_run_kwargs(cfg)
    assert "privileged" not in kwargs

def test_build_run_kwargs_static_ip_sets_network_none():
    # When static IP needed, network is set to None (connected separately)
    cfg = make_config(ip="10.20.30.33")
    kwargs = _build_run_kwargs(cfg)
    # network key should be None or absent since static IP requires manual connect
    assert kwargs.get("network") is None or "network" not in kwargs


# ============================================================
# Tests: Updater._update_one — pinned strategy
# ============================================================

def test_update_pinned_skips():
    updater, _ = make_updater()
    cfg = make_config(version_strategy="pinned")
    result = updater._update_one(cfg)
    assert result.status == UpdateStatus.PINNED
    assert result.container_name == "homeassistant"


# ============================================================
# Tests: Updater._update_one — pull failure
# ============================================================

def test_update_pull_failure():
    updater, mock_client = make_updater()
    mock_client.images.get.side_effect = Exception("not found")
    mock_client.images.pull.side_effect = Exception("network error")
    cfg = make_config()
    result = updater._update_one(cfg)
    assert result.status == UpdateStatus.FAILED
    assert "Pull failed" in result.error


# ============================================================
# Tests: Updater._update_one — image unchanged (skip)
# ============================================================

def test_update_image_unchanged():
    updater, mock_client = make_updater()

    # Both pre and post pull return same digest
    mock_img = MagicMock()
    mock_img.id = "sha256:sameimage"
    mock_client.images.get.return_value = mock_img
    mock_client.images.pull.return_value = mock_img

    # Container must be running on the same image as local for skip
    cfg = make_config(image_id="sha256:sameimage")
    result = updater._update_one(cfg)
    assert result.status == UpdateStatus.SKIPPED
    assert result.old_image_id == result.new_image_id


def test_update_image_stale_container():
    """Container running on untagged (dangling) old image with newer tagged version — should recreate."""
    updater, mock_client = make_updater()

    # New image has the tag
    new_img = MagicMock()
    new_img.id = "sha256:newimage"
    new_img.tags = ["python:3.11-slim"]
    new_img.attrs = {"RepoDigests": ["python@sha256:newimage"]}

    # Old image is untagged (dangling) but has RepoDigests pointing to same repo
    old_img = MagicMock()
    old_img.id = "sha256:oldimage"
    old_img.tags = []  # no tags = dangling
    old_img.attrs = {"RepoDigests": ["python@sha256:olddigest"]}

    def get_image(ref):
        if "oldimage" in ref:
            return old_img
        return new_img

    mock_client.images.get.side_effect = get_image
    mock_client.images.pull.return_value = new_img
    # images.list() returns both — newer tagged one exists
    mock_client.images.list.return_value = [new_img, old_img]

    cfg = make_config(image_id="sha256:oldimage")
    result = updater._update_one(cfg)
    # Should recreate: running image is dangling AND newer tagged version exists
    assert result.status == UpdateStatus.UPDATED


# ============================================================
# Tests: Updater._update_one — dry run
# ============================================================

def test_update_dry_run_returns_dry_run_status():
    updater, mock_client = make_updater(dry_run=True)

    old_img = MagicMock()
    old_img.id = "sha256:oldimage"
    new_img = MagicMock()
    new_img.id = "sha256:newimage"

    # First call (pre-pull) returns old, second (post-pull) returns new
    mock_client.images.get.side_effect = [old_img, new_img]
    mock_client.images.pull.return_value = new_img

    cfg = make_config()
    result = updater._update_one(cfg)
    assert result.status == UpdateStatus.DRY_RUN
    assert result.old_image_id == "sha256:oldimage"
    assert result.new_image_id == "sha256:newimage"
    # Should NOT have called stop/remove/run
    mock_client.containers.get.assert_not_called()


# ============================================================
# Tests: Updater._update_one — successful update
# ============================================================

def test_update_success_full_flow():
    updater, mock_client = make_updater(delay=0)

    old_img = MagicMock()
    old_img.id = "sha256:oldimage"
    new_img = MagicMock()
    new_img.id = "sha256:newimage"

    mock_client.images.get.side_effect = [old_img, new_img]
    mock_client.images.pull.return_value = new_img

    mock_container = MagicMock()
    mock_client.containers.get.return_value = mock_container
    mock_client.containers.run.return_value = mock_container

    mock_network = MagicMock()
    mock_client.networks.get.return_value = mock_network
    mock_client.networks.list.return_value = []

    cfg = make_config()
    result = updater._update_one(cfg)

    assert result.status == UpdateStatus.UPDATED
    assert result.old_image_id == "sha256:oldimage"
    assert result.new_image_id == "sha256:newimage"
    mock_container.stop.assert_called_once()
    mock_container.remove.assert_called_once()
    mock_client.containers.run.assert_called_once()


# ============================================================
# Tests: Updater._update_one — first run (no old image)
# ============================================================

def test_update_first_run_no_old_image():
    """If image doesn't exist locally yet, treat as new."""
    updater, mock_client = make_updater(delay=0)

    from docker.errors import ImageNotFound

    new_img = MagicMock()
    new_img.id = "sha256:newimage"

    # Pre-pull: image not found locally
    mock_client.images.get.side_effect = [ImageNotFound("not found"), new_img]
    mock_client.images.pull.return_value = new_img

    mock_container = MagicMock()
    mock_client.containers.get.return_value = mock_container
    mock_client.containers.run.return_value = mock_container
    mock_client.networks.get.return_value = MagicMock()

    cfg = make_config()
    result = updater._update_one(cfg)
    # old_digest will be None, new_digest will be set → should update
    assert result.status == UpdateStatus.UPDATED
    assert result.old_image_id is None


# ============================================================
# Tests: Updater.update_all
# ============================================================

def test_update_all_returns_one_result_per_container():
    updater, mock_client = make_updater(delay=0)

    # All images unchanged
    mock_img = MagicMock()
    mock_img.id = "sha256:same"
    mock_client.images.get.return_value = mock_img
    mock_client.images.pull.return_value = mock_img

    configs = [make_config("ha", image_id="sha256:same"),
               make_config("esphome", image_id="sha256:same"),
               make_config("nut", image_id="sha256:same")]
    results = updater.update_all(configs)

    assert len(results) == 3
    assert all(r.status == UpdateStatus.SKIPPED for r in results)


def test_update_all_continues_after_failure():
    updater, mock_client = make_updater(delay=0)

    old_img = MagicMock()
    old_img.id = "sha256:old"
    same_img = MagicMock()
    same_img.id = "sha256:same"

    # First container: pull fails
    # Second container: image unchanged
    call_count = [0]
    def pull_side_effect(image_ref):
        call_count[0] += 1
        if call_count[0] == 1:
            raise Exception("network timeout")
        return same_img

    mock_client.images.get.return_value = same_img
    mock_client.images.pull.side_effect = pull_side_effect

    # Second container: image_id matches local so it gets skipped (not stale)
    configs = [make_config("ha"), make_config("esphome", image_id="sha256:same")]
    results = updater.update_all(configs)

    assert results[0].status == UpdateStatus.FAILED
    assert results[1].status == UpdateStatus.SKIPPED


# ============================================================
# Tests: Updater.summarize
# ============================================================

def test_summarize_counts():
    results = [
        UpdateResult("a", UpdateStatus.UPDATED, "sha256:old", "sha256:new"),
        UpdateResult("b", UpdateStatus.SKIPPED),
        UpdateResult("c", UpdateStatus.SKIPPED),
        UpdateResult("d", UpdateStatus.FAILED, error="boom"),
        UpdateResult("e", UpdateStatus.PINNED),
    ]
    summary = Updater.summarize(results)
    assert summary["updated"] == 1
    assert summary["skipped"] == 2
    assert summary["failed"] == 1
    assert summary["pinned"] == 1
    assert len(summary["failures"]) == 1
    assert summary["failures"][0].container_name == "d"


def test_summarize_empty():
    summary = Updater.summarize([])
    assert summary["total"] == 0
    assert summary["updated"] == 0


# ============================================================
# Tests: UpdateResult properties
# ============================================================

def test_update_result_changed_true():
    r = UpdateResult("x", UpdateStatus.UPDATED)
    assert r.changed is True

def test_update_result_changed_false_skipped():
    r = UpdateResult("x", UpdateStatus.SKIPPED)
    assert r.changed is False

def test_update_result_success_all_non_failed():
    for status in (UpdateStatus.UPDATED, UpdateStatus.SKIPPED, UpdateStatus.PINNED, UpdateStatus.DRY_RUN):
        r = UpdateResult("x", status)
        assert r.success is True

def test_update_result_success_false_on_failed():
    r = UpdateResult("x", UpdateStatus.FAILED, error="boom")
    assert r.success is False


# ============================================================
# Tests: Pruner
# ============================================================

def test_pruner_dry_run_no_removals():
    pruner, mock_client = make_pruner(dry_run=True)

    dangling_img = MagicMock()
    dangling_img.id = "sha256:dangling"
    dangling_img.attrs = {"Size": 500 * 1024 * 1024}  # 500MB

    mock_client.images.list.return_value = [dangling_img]
    mock_client.containers.list.return_value = []

    result = pruner.prune()

    assert result.dry_run is True
    mock_client.images.remove.assert_not_called()


def test_pruner_removes_dangling():
    pruner, mock_client = make_pruner()

    dangling_img = MagicMock()
    dangling_img.id = "sha256:dangling123"
    dangling_img.attrs = {"Size": 100 * 1024 * 1024}

    mock_client.images.list.side_effect = lambda filters=None: (
        [dangling_img] if filters and filters.get("dangling") else []
    )
    mock_client.images.get.return_value = dangling_img
    mock_client.containers.list.return_value = []

    result = pruner.prune()

    assert result.dry_run is False
    mock_client.images.remove.assert_called_once_with(
        "sha256:dangling123", force=False, noprune=False
    )
    assert result.space_reclaimed_bytes == 100 * 1024 * 1024


def test_pruner_never_removes_in_use_images():
    pruner, mock_client = make_pruner(remove_unreferenced=True)

    running_img = MagicMock()
    running_img.id = "sha256:inuse"
    running_img.attrs = {"Size": 200 * 1024 * 1024}

    mock_container = MagicMock()
    mock_container.attrs = {
        "Image": "sha256:inuse",
        "Config": {"Image": "homeassistant:stable"},
    }
    mock_client.containers.list.return_value = [mock_container]

    # images.get called when resolving image name → return same in-use image
    mock_client.images.get.return_value = running_img
    mock_client.images.list.return_value = [running_img]

    result = pruner.prune()

    # Should not have removed the in-use image
    mock_client.images.remove.assert_not_called()


def test_pruner_removes_old_image_from_update_results():
    pruner, mock_client = make_pruner()

    old_img = MagicMock()
    old_img.id = "sha256:oldimage"
    old_img.attrs = {"Size": 300 * 1024 * 1024}

    mock_client.images.list.return_value = []  # no dangling
    mock_client.images.get.return_value = old_img
    mock_client.containers.list.return_value = []  # nothing in use

    update_results = [
        UpdateResult(
            container_name="homeassistant",
            status=UpdateStatus.UPDATED,
            old_image_id="sha256:oldimage",
            new_image_id="sha256:newimage",
        )
    ]

    result = pruner.prune(update_results=update_results)

    mock_client.images.remove.assert_called_with(
        "sha256:oldimage", force=False, noprune=False
    )


def test_pruner_skips_failed_updates():
    pruner, mock_client = make_pruner()

    mock_client.images.list.return_value = []
    mock_client.containers.list.return_value = []

    # Failed update — old image should NOT be queued for removal
    update_results = [
        UpdateResult(
            container_name="homeassistant",
            status=UpdateStatus.FAILED,
            old_image_id="sha256:oldimage",
            error="pull failed",
        )
    ]

    pruner.prune(update_results=update_results)
    mock_client.images.remove.assert_not_called()


def test_pruner_space_reclaimed_human_mb():
    result = PruneResult(
        images_removed=["sha256:abc"],
        space_reclaimed_bytes=500 * 1024 * 1024,
        errors=[],
        dry_run=False,
    )
    assert "MB" in result.space_reclaimed_human
    assert "500" in result.space_reclaimed_human


def test_pruner_space_reclaimed_human_gb():
    result = PruneResult(
        images_removed=["sha256:abc"],
        space_reclaimed_bytes=3 * 1024 * 1024 * 1024,
        errors=[],
        dry_run=False,
    )
    assert "GB" in result.space_reclaimed_human


def test_pruner_handles_already_gone_image():
    from docker.errors import ImageNotFound
    pruner, mock_client = make_pruner()

    dangling_img = MagicMock()
    dangling_img.id = "sha256:gone"
    dangling_img.attrs = {"Size": 0}

    mock_client.images.list.side_effect = lambda filters=None: (
        [dangling_img] if filters and filters.get("dangling") else []
    )
    mock_client.images.get.return_value = dangling_img
    mock_client.containers.list.return_value = []
    mock_client.images.remove.side_effect = ImageNotFound("already gone")

    # Should not raise
    result = pruner.prune()
    assert result.images_removed == []  # nothing actually removed
    assert result.errors == []  # ImageNotFound is silently skipped


def test_pruner_list_candidates():
    pruner, mock_client = make_pruner()

    dangling_img = MagicMock()
    dangling_img.id = "sha256:dangling"
    dangling_img.attrs = {"Size": 100 * 1024 * 1024}

    mock_client.images.list.side_effect = lambda filters=None: (
        [dangling_img] if filters and filters.get("dangling") else []
    )
    mock_client.images.get.return_value = dangling_img
    mock_client.containers.list.return_value = []

    report = pruner.list_candidates()
    assert "dangling" in report
    assert "total_candidates" in report
    assert "estimated_space_human" in report


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
