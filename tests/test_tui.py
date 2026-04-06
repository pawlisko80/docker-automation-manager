"""
tests/test_tui.py

Tests for dam/tui.py rendering functions and dam/cli.py logic.
All tests are pure render/logic tests — no Docker daemon, no TTY required.
Rich output is captured to a string buffer for assertion.
"""

import sys
from copy import deepcopy
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch
import tempfile

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table

from dam.core.inspector import ContainerConfig, NetworkConfig, PortBinding, DeviceMapping
from dam.core.updater import UpdateResult, UpdateStatus
from dam.core.drift import DriftDetector, DriftItem, DriftSeverity, DriftReport
from dam.core.pruner import PruneResult
from dam.platform.qnap import QNAPPlatform
from dam.platform.generic import GenericPlatform

import dam.tui as tui_module
from dam.tui import (
    render_status_table,
    render_update_results,
    render_update_summary,
    render_drift_report,
    render_drift_summary,
    render_prune_candidates,
    render_prune_result,
    render_header,
    render_menu,
    render_platform_info,
    render_settings,
    render_snapshots_table,
    SEVERITY_COLORS,
    UPDATE_STATUS_COLORS,
    UPDATE_STATUS_ICONS,
)


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def render_to_str(renderable) -> str:
    """Render a Rich renderable to a plain string for assertions."""
    buf = StringIO()
    c = Console(file=buf, width=200, highlight=False, markup=False)
    c.print(renderable)
    return buf.getvalue()


def make_cfg(
    name="homeassistant",
    image="ghcr.io/home-assistant/home-assistant:stable",
    image_id="sha256:abc123",
    status="running",
    ip="10.20.30.33",
    network="macvlan_network",
    restart_policy="unless-stopped",
    privileged=True,
    env=None,
    binds=None,
    version_strategy="latest",
) -> ContainerConfig:
    return ContainerConfig(
        name=name,
        image=image,
        image_id=image_id,
        status=status,
        restart_policy=restart_policy,
        network_mode=network,
        networks=[NetworkConfig(
            name=network,
            driver="macvlan",
            ip_address=ip,
            mac_address="02:42:0a:14:1e:21",
            is_static=True,
        )],
        ports=[],
        binds=binds or ["/share/Container/ha/config:/config"],
        env=env or {"TZ": "America/New_York"},
        privileged=privileged,
        cap_add=[],
        cap_drop=[],
        devices=[],
        extra_hosts=[],
        labels={},
        version_strategy=version_strategy,
    )


def make_update_result(
    name="homeassistant",
    status=UpdateStatus.UPDATED,
    old_id="sha256:old000000000000000",
    new_id="sha256:new000000000000000",
    error=None,
    duration=2.5,
) -> UpdateResult:
    return UpdateResult(
        container_name=name,
        status=status,
        old_image_id=old_id,
        new_image_id=new_id,
        error=error,
        duration_seconds=duration,
    )


# ============================================================
# Tests: render_header
# ============================================================

def test_header_contains_version():
    from dam import __version__
    platform = GenericPlatform()
    panel = render_header(platform, snapshot_count=3)
    output = render_to_str(panel)
    assert __version__ in output

def test_header_contains_platform_name():
    platform = QNAPPlatform()
    panel = render_header(platform, snapshot_count=5)
    output = render_to_str(panel)
    assert "QNAP" in output

def test_header_contains_snapshot_count():
    platform = GenericPlatform()
    panel = render_header(platform, snapshot_count=7)
    output = render_to_str(panel)
    assert "7" in output


# ============================================================
# Tests: render_menu
# ============================================================

def test_menu_contains_all_options():
    panel = render_menu()
    output = render_to_str(panel)
    assert "Status" in output
    assert "Update" in output
    assert "Drift" in output
    assert "Prune" in output
    assert "Snapshots" in output
    assert "Settings" in output
    assert "Quit" in output

def test_menu_contains_key_bindings():
    panel = render_menu()
    output = render_to_str(panel)
    for key in ["1", "2", "3", "4", "5", "6", "q"]:
        assert key in output


# ============================================================
# Tests: render_status_table
# ============================================================

def test_status_table_contains_container_names():
    configs = [make_cfg("homeassistant"), make_cfg("esphome", ip="192.168.1.10")]
    table = render_status_table(configs)
    output = render_to_str(table)
    assert "homeassistant" in output
    assert "esphome" in output

def test_status_table_contains_images():
    configs = [make_cfg(image="ghcr.io/home-assistant/home-assistant:stable")]
    output = render_to_str(render_status_table(configs))
    assert "home-assistant" in output

def test_status_table_contains_ips():
    configs = [make_cfg(ip="10.20.30.33")]
    output = render_to_str(render_status_table(configs))
    assert "10.20.30.33" in output

def test_status_table_contains_restart_policy():
    configs = [make_cfg(restart_policy="unless-stopped")]
    output = render_to_str(render_status_table(configs))
    assert "unless-stopped" in output

def test_status_table_contains_version_strategy():
    configs = [make_cfg(version_strategy="stable")]
    output = render_to_str(render_status_table(configs))
    assert "stable" in output

def test_status_table_shows_volume_count():
    configs = [make_cfg(binds=["/a:/a", "/b:/b", "/c:/c"])]
    output = render_to_str(render_status_table(configs))
    assert "3" in output

def test_status_table_empty_list():
    # Should not crash on empty list
    table = render_status_table([])
    output = render_to_str(table)
    assert isinstance(output, str)

def test_status_table_sorted_by_name():
    configs = [make_cfg("zzz"), make_cfg("aaa"), make_cfg("mmm")]
    output = render_to_str(render_status_table(configs))
    pos_aaa = output.find("aaa")
    pos_mmm = output.find("mmm")
    pos_zzz = output.find("zzz")
    assert pos_aaa < pos_mmm < pos_zzz

def test_status_table_host_network_no_ip():
    cfg = make_cfg(ip=None, network="host")
    cfg.networks = [NetworkConfig("host", None, None, None, False)]
    output = render_to_str(render_status_table([cfg]))
    assert "host" in output


# ============================================================
# Tests: render_update_results
# ============================================================

def test_update_results_table_shows_all_containers():
    results = [
        make_update_result("ha",      UpdateStatus.UPDATED),
        make_update_result("esphome", UpdateStatus.SKIPPED),
        make_update_result("nut",     UpdateStatus.PINNED),
        make_update_result("peanut",  UpdateStatus.FAILED, error="network error"),
    ]
    output = render_to_str(render_update_results(results))
    assert "ha" in output
    assert "esphome" in output
    assert "nut" in output
    assert "peanut" in output

def test_update_results_shows_status_values():
    results = [make_update_result(status=UpdateStatus.UPDATED)]
    output = render_to_str(render_update_results(results))
    assert "updated" in output.lower()

def test_update_results_shows_error():
    results = [make_update_result(status=UpdateStatus.FAILED, error="pull timeout")]
    output = render_to_str(render_update_results(results))
    assert "pull timeout" in output

def test_update_results_shows_duration():
    results = [make_update_result(duration=12.3)]
    output = render_to_str(render_update_results(results))
    assert "12.3" in output

def test_update_results_truncates_image_ids():
    results = [make_update_result(
        old_id="sha256:" + "a" * 64,
        new_id="sha256:" + "b" * 64,
    )]
    output = render_to_str(render_update_results(results))
    # Should show truncated IDs not full 64-char hashes
    assert "sha256:aaaaaaaaaaaa" in output


# ============================================================
# Tests: render_update_summary
# ============================================================

def test_update_summary_shows_all_counts():
    summary = {
        "total": 5, "updated": 2, "skipped": 1,
        "pinned": 1, "dry_run": 0, "failed": 1, "failures": [],
    }
    output = render_to_str(render_update_summary(summary))
    assert "2" in output   # updated
    assert "1" in output   # skipped / pinned / failed

def test_update_summary_green_border_on_no_failures():
    summary = {
        "total": 3, "updated": 2, "skipped": 1,
        "pinned": 0, "dry_run": 0, "failed": 0, "failures": [],
    }
    panel = render_update_summary(summary)
    # Check border style is green
    assert panel.border_style == "green"

def test_update_summary_red_border_on_failures():
    summary = {
        "total": 3, "updated": 1, "skipped": 1,
        "pinned": 0, "dry_run": 0, "failed": 1, "failures": [],
    }
    panel = render_update_summary(summary)
    assert panel.border_style == "red"


# ============================================================
# Tests: render_drift_report
# ============================================================

def make_drift_report_with_items() -> DriftReport:
    report = DriftReport(snapshot_a_label="prev", snapshot_b_label="curr")
    report.add(DriftItem("ha", "image_id", DriftSeverity.HIGH,
                         "Image updated", "sha256:old", "sha256:new"))
    report.add(DriftItem("ha", "env.TZ", DriftSeverity.LOW,
                         "Env var changed", "UTC", "America/New_York"))
    report.add(DriftItem("nut", "existence", DriftSeverity.CRITICAL,
                         "Container removed", "nut:latest", None))
    return report

def test_drift_report_shows_container_names():
    report = make_drift_report_with_items()
    output = render_to_str(render_drift_report(report))
    assert "ha" in output
    assert "nut" in output

def test_drift_report_shows_severity_labels():
    report = make_drift_report_with_items()
    output = render_to_str(render_drift_report(report))
    assert "HIGH" in output
    assert "LOW" in output
    assert "CRITICAL" in output

def test_drift_report_shows_old_new_values():
    report = make_drift_report_with_items()
    output = render_to_str(render_drift_report(report))
    assert "sha256:old" in output
    assert "sha256:new" in output

def test_drift_report_shows_field_names():
    report = make_drift_report_with_items()
    output = render_to_str(render_drift_report(report))
    assert "image_id" in output
    assert "env.TZ" in output

def test_drift_report_shows_labels():
    report = make_drift_report_with_items()
    output = render_to_str(render_drift_report(report))
    assert "prev" in output
    assert "curr" in output

def test_drift_report_empty_returns_table():
    report = DriftReport()
    result = render_drift_report(report)
    assert isinstance(result, Table)


# ============================================================
# Tests: render_drift_summary
# ============================================================

def test_drift_summary_shows_counts():
    report = make_drift_report_with_items()
    output = render_to_str(render_drift_summary(report))
    assert "1" in output   # 1 critical, 1 high, 1 low

def test_drift_summary_shows_affected_count():
    report = make_drift_report_with_items()
    output = render_to_str(render_drift_summary(report))
    assert "2" in output   # 2 containers affected (ha, nut)

def test_drift_summary_red_border_on_critical():
    report = DriftReport()
    report.add(DriftItem("x", "existence", DriftSeverity.CRITICAL, "missing"))
    panel = render_drift_summary(report)
    assert panel.border_style == "red"

def test_drift_summary_yellow_border_on_medium():
    report = DriftReport()
    report.add(DriftItem("x", "volumes", DriftSeverity.MEDIUM, "vol changed"))
    panel = render_drift_summary(report)
    assert panel.border_style == "yellow"

def test_drift_summary_cyan_border_on_low_only():
    report = DriftReport()
    report.add(DriftItem("x", "env.TZ", DriftSeverity.LOW, "tz changed"))
    panel = render_drift_summary(report)
    assert panel.border_style == "cyan"


# ============================================================
# Tests: render_prune_candidates
# ============================================================

def test_prune_candidates_shows_counts():
    candidates = {
        "dangling": ["sha256:a", "sha256:b"],
        "replaced": ["sha256:c"],
        "unreferenced": [],
        "total_candidates": 3,
        "estimated_space_bytes": 500 * 1024 * 1024,
        "estimated_space_human": "500.0 MB",
    }
    output = render_to_str(render_prune_candidates(candidates))
    assert "3" in output
    assert "500" in output

def test_prune_candidates_shows_space():
    candidates = {
        "dangling": [], "replaced": [], "unreferenced": [],
        "total_candidates": 0,
        "estimated_space_bytes": 0,
        "estimated_space_human": "0.0 MB",
    }
    output = render_to_str(render_prune_candidates(candidates))
    assert "MB" in output


# ============================================================
# Tests: render_prune_result
# ============================================================

def test_prune_result_shows_removed_count():
    result = PruneResult(
        images_removed=["sha256:a", "sha256:b", "sha256:c"],
        space_reclaimed_bytes=3 * 1024 * 1024 * 1024,
        errors=[],
        dry_run=False,
    )
    output = render_to_str(render_prune_result(result))
    assert "3" in output
    assert "GB" in output

def test_prune_result_green_border_on_success():
    result = PruneResult(["sha256:a"], 100, [], False)
    panel = render_prune_result(result)
    assert panel.border_style == "green"

def test_prune_result_red_border_on_errors():
    result = PruneResult([], 0, ["could not remove sha256:x"], False)
    panel = render_prune_result(result)
    assert panel.border_style == "red"


# ============================================================
# Tests: render_platform_info
# ============================================================

def test_platform_info_shows_platform_name():
    platform = QNAPPlatform()
    output = render_to_str(render_platform_info(platform))
    assert "QNAP" in output

def test_platform_info_shows_data_root():
    platform = QNAPPlatform()
    output = render_to_str(render_platform_info(platform))
    assert "/share/Container" in output

def test_platform_info_generic():
    platform = GenericPlatform()
    output = render_to_str(render_platform_info(platform))
    assert "Generic" in output
    assert "/opt/docker" in output


# ============================================================
# Tests: render_settings
# ============================================================

def test_settings_shows_retention():
    settings = {"dam": {"snapshot_retention": 15, "log_retention_days": 30,
                        "auto_prune": True, "recreate_delay": 5},
                "daemon": {"schedule": "0 2 1 * *"},
                "containers": {}}
    output = render_to_str(render_settings(settings))
    assert "15" in output

def test_settings_shows_schedule():
    settings = {"dam": {}, "daemon": {"schedule": "0 3 * * 0"}, "containers": {}}
    output = render_to_str(render_settings(settings))
    assert "0 3 * * 0" in output

def test_settings_empty_dict_no_crash():
    output = render_to_str(render_settings({}))
    assert isinstance(output, str)


# ============================================================
# Tests: render_snapshots_table
# ============================================================

def test_snapshots_table_empty():
    with tempfile.TemporaryDirectory() as tmpdir:
        from dam.core.snapshot import SnapshotManager
        sm = SnapshotManager(snapshot_dir=Path(tmpdir))
        table = render_snapshots_table(sm)
        output = render_to_str(table)
        assert "0" in output

def test_snapshots_table_with_snapshots():
    with tempfile.TemporaryDirectory() as tmpdir:
        from dam.core.snapshot import SnapshotManager
        sm = SnapshotManager(snapshot_dir=Path(tmpdir))
        platform = QNAPPlatform()
        cfg = make_cfg()
        import time
        sm.save([cfg], platform, label="run1")
        time.sleep(0.05)
        sm.save([cfg], platform, label="run2")

        table = render_snapshots_table(sm)
        output = render_to_str(table)
        assert "run1" in output
        assert "run2" in output
        assert "2" in output


# ============================================================
# Tests: Color / style constants completeness
# ============================================================

def test_severity_colors_cover_all_severities():
    for sev in DriftSeverity:
        assert sev.value in SEVERITY_COLORS

def test_update_status_colors_cover_all_statuses():
    for status in UpdateStatus:
        assert status in UPDATE_STATUS_COLORS

def test_update_status_icons_cover_all_statuses():
    for status in UpdateStatus:
        assert status in UPDATE_STATUS_ICONS


# ============================================================
# Tests: DAMTui initialization (no Docker daemon)
# ============================================================

def test_tui_initializes_with_missing_settings():
    with tempfile.TemporaryDirectory() as tmpdir:
        from dam.tui import DAMTui
        # Point to non-existent config — should not crash
        tui = DAMTui(config_path=Path(tmpdir) / "nonexistent.yaml")
        assert tui.settings == {}
        assert tui.platform is not None
        assert tui.snapshot_manager is not None

def test_tui_initializes_with_valid_settings():
    with tempfile.TemporaryDirectory() as tmpdir:
        import yaml
        config_path = Path(tmpdir) / "settings.yaml"
        config_path.write_text(yaml.dump({
            "dam": {"snapshot_retention": 5, "auto_prune": False},
            "daemon": {"schedule": "0 1 * * 0"},
        }))
        from dam.tui import DAMTui
        tui = DAMTui(config_path=config_path)
        assert tui.settings["dam"]["snapshot_retention"] == 5
        assert tui.settings["daemon"]["schedule"] == "0 1 * * 0"


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
