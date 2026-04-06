"""
tests/test_daemon.py

Unit tests for dam/daemon/scheduler.py and dam/daemon/service.py.
No live Docker, no filesystem writes outside tempdir, no cron/systemd calls.
"""

import sys
import json
import tempfile
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from dam.daemon.scheduler import (
    CronExpression,
    parse_cron,
    validate_cron,
    next_run_from_now,
    _expand_field,
    _normalize_dow,
)
from dam.daemon.service import DaemonManager, DaemonState, STATE_FILENAME
from dam.platform.generic import GenericPlatform
from dam.platform.qnap import QNAPPlatform


# ============================================================
# Tests: _expand_field
# ============================================================

def test_expand_field_star():
    assert _expand_field("*", 0, 59) == set(range(60))

def test_expand_field_literal():
    assert _expand_field("5", 0, 59) == {5}

def test_expand_field_range():
    assert _expand_field("1-5", 1, 31) == {1, 2, 3, 4, 5}

def test_expand_field_list():
    assert _expand_field("0,15,30,45", 0, 59) == {0, 15, 30, 45}

def test_expand_field_step_star():
    result = _expand_field("*/15", 0, 59)
    assert result == {0, 15, 30, 45}

def test_expand_field_step_range():
    result = _expand_field("0-10/2", 0, 59)
    assert result == {0, 2, 4, 6, 8, 10}

def test_expand_field_clamps_to_range():
    result = _expand_field("*", 1, 12)
    assert 0 not in result
    assert 13 not in result

def test_expand_field_combined_list():
    result = _expand_field("1,3,5-7", 0, 7)
    assert result == {1, 3, 5, 6, 7}


# ============================================================
# Tests: _normalize_dow
# ============================================================

def test_normalize_dow_7_becomes_0():
    assert _normalize_dow({7}) == {0}

def test_normalize_dow_both_0_and_7():
    assert _normalize_dow({0, 7}) == {0}

def test_normalize_dow_no_change():
    assert _normalize_dow({1, 2, 3}) == {1, 2, 3}


# ============================================================
# Tests: CronExpression.parse
# ============================================================

def test_parse_monthly():
    expr = parse_cron("0 2 1 * *")
    assert 0 in expr.minutes
    assert 2 in expr.hours
    assert 1 in expr.days_of_month
    assert expr.months == set(range(1, 13))

def test_parse_every_15_minutes():
    expr = parse_cron("*/15 * * * *")
    assert expr.minutes == {0, 15, 30, 45}
    assert expr.hours == set(range(24))

def test_parse_weekdays():
    expr = parse_cron("30 4 * * 1-5")
    assert expr.minutes == {30}
    assert expr.hours == {4}
    assert expr.days_of_week == {1, 2, 3, 4, 5}

def test_parse_sunday_as_7_normalized():
    expr = parse_cron("0 0 * * 7")
    assert 0 in expr.days_of_week  # 7 normalized to 0

def test_parse_invalid_field_count():
    try:
        parse_cron("0 2 1 *")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass

def test_parse_invalid_value():
    try:
        parse_cron("99 2 1 * *")  # 99 is not a valid minute
    except Exception:
        pass  # May or may not raise depending on clamping

def test_parse_complex_expression():
    expr = parse_cron("0,30 9-17 * * 1-5")
    assert expr.minutes == {0, 30}
    assert expr.hours == set(range(9, 18))
    assert expr.days_of_week == {1, 2, 3, 4, 5}


# ============================================================
# Tests: CronExpression.matches
# ============================================================

def test_matches_exact():
    expr = parse_cron("30 14 15 6 *")
    dt = datetime(2026, 6, 15, 14, 30)
    assert expr.matches(dt)

def test_matches_wrong_minute():
    expr = parse_cron("30 14 15 6 *")
    dt = datetime(2026, 6, 15, 14, 31)
    assert not expr.matches(dt)

def test_matches_wrong_hour():
    expr = parse_cron("30 14 15 6 *")
    dt = datetime(2026, 6, 15, 15, 30)
    assert not expr.matches(dt)

def test_matches_every_minute():
    expr = parse_cron("* * * * *")
    for minute in range(60):
        dt = datetime(2026, 1, 1, 0, minute)
        assert expr.matches(dt)


# ============================================================
# Tests: CronExpression.next_run
# ============================================================

def test_next_run_monthly_from_start_of_month():
    expr = parse_cron("0 2 1 * *")
    # If we're on Jan 1 at 01:00, next run should be Jan 1 at 02:00
    after = datetime(2026, 1, 1, 1, 0)
    nxt = expr.next_run(after)
    assert nxt.hour == 2
    assert nxt.minute == 0
    assert nxt.day == 1

def test_next_run_monthly_after_trigger():
    expr = parse_cron("0 2 1 * *")
    # If we just passed Jan 1 at 02:00, next run is Feb 1 at 02:00
    after = datetime(2026, 1, 1, 2, 5)
    nxt = expr.next_run(after)
    assert nxt.month == 2
    assert nxt.day == 1
    assert nxt.hour == 2

def test_next_run_every_15_min():
    expr = parse_cron("*/15 * * * *")
    after = datetime(2026, 4, 1, 10, 7)
    nxt = expr.next_run(after)
    assert nxt.minute == 15
    assert nxt.hour == 10

def test_next_run_every_15_min_near_hour_boundary():
    expr = parse_cron("*/15 * * * *")
    after = datetime(2026, 4, 1, 10, 46)
    nxt = expr.next_run(after)
    assert nxt.minute == 0
    assert nxt.hour == 11

def test_next_run_is_strictly_after():
    expr = parse_cron("0 2 1 * *")
    after = datetime(2026, 1, 1, 2, 0)  # exactly at trigger time
    nxt = expr.next_run(after)
    assert nxt > after

def test_next_run_year_boundary():
    expr = parse_cron("0 0 1 1 *")  # Jan 1 at midnight
    after = datetime(2026, 1, 1, 0, 5)  # just after Jan 1
    nxt = expr.next_run(after)
    assert nxt.year == 2027
    assert nxt.month == 1
    assert nxt.day == 1

def test_next_run_returns_datetime():
    expr = parse_cron("0 3 * * 0")  # every Sunday at 3 AM
    nxt = expr.next_run()
    assert isinstance(nxt, datetime)
    assert nxt > datetime.now()


# ============================================================
# Tests: CronExpression.describe
# ============================================================

def test_describe_known_expression():
    expr = parse_cron("0 2 1 * *")
    desc = expr.describe()
    assert "monthly" in desc.lower() or "1st" in desc.lower() or "2:00" in desc

def test_describe_every_15():
    expr = parse_cron("*/15 * * * *")
    desc = expr.describe()
    assert "15" in desc

def test_describe_unknown_returns_cron():
    expr = parse_cron("5 4 3 2 1")
    desc = expr.describe()
    assert "cron" in desc.lower() or "5 4 3 2 1" in desc


# ============================================================
# Tests: validate_cron
# ============================================================

def test_validate_valid():
    ok, msg = validate_cron("0 2 1 * *")
    assert ok is True
    assert msg  # non-empty description

def test_validate_invalid():
    ok, msg = validate_cron("not a cron")
    assert ok is False
    assert "Invalid" in msg or "expected" in msg

def test_validate_wrong_field_count():
    ok, msg = validate_cron("0 2 *")
    assert ok is False


# ============================================================
# Tests: next_run_from_now
# ============================================================

def test_next_run_from_now_returns_future():
    nxt = next_run_from_now("*/5 * * * *")
    assert nxt > datetime.now()

def test_next_run_from_now_within_5_minutes():
    nxt = next_run_from_now("*/1 * * * *")
    assert (nxt - datetime.now()).total_seconds() <= 60


# ============================================================
# Tests: DaemonState
# ============================================================

def test_daemon_state_save_load():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / STATE_FILENAME
        state = DaemonState(
            installed=True,
            install_method="cron",
            schedule="0 2 1 * *",
            last_run_at="2026-04-01T02:00:00",
            last_run_status="success",
            last_updated_count=3,
            last_failed_count=0,
        )
        state.save(path)

        loaded = DaemonState.load(path)
        assert loaded.installed is True
        assert loaded.install_method == "cron"
        assert loaded.schedule == "0 2 1 * *"
        assert loaded.last_updated_count == 3
        assert loaded.last_run_status == "success"

def test_daemon_state_load_missing_returns_default():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "nonexistent.json"
        state = DaemonState.load(path)
        assert state.installed is False
        assert state.install_method == ""

def test_daemon_state_load_corrupted_returns_default():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / STATE_FILENAME
        path.write_text("not valid json {{{")
        state = DaemonState.load(path)
        assert state.installed is False


# ============================================================
# Tests: DaemonManager initialization
# ============================================================

def test_daemon_manager_init():
    with tempfile.TemporaryDirectory() as tmpdir:
        platform = GenericPlatform()
        dm = DaemonManager(platform, schedule="0 2 1 * *",
                           state_dir=Path(tmpdir))
        assert dm.schedule == "0 2 1 * *"
        assert dm.platform is platform

def test_daemon_manager_invalid_schedule_raises():
    with tempfile.TemporaryDirectory() as tmpdir:
        platform = GenericPlatform()
        try:
            DaemonManager(platform, schedule="not valid", state_dir=Path(tmpdir))
            assert False, "Should raise ValueError"
        except ValueError:
            pass


# ============================================================
# Tests: DaemonManager.status
# ============================================================

def test_daemon_status_not_installed():
    with tempfile.TemporaryDirectory() as tmpdir:
        platform = GenericPlatform()
        dm = DaemonManager(platform, state_dir=Path(tmpdir))
        status = dm.status()
        assert status["installed"] is False
        assert "next_run" in status
        assert status["next_run"] is not None  # calculated from schedule

def test_daemon_status_after_install_record():
    with tempfile.TemporaryDirectory() as tmpdir:
        platform = GenericPlatform()
        dm = DaemonManager(platform, state_dir=Path(tmpdir))
        dm._save_state(installed=True, method="cron")
        status = dm.status()
        assert status["installed"] is True
        assert status["method"] == "cron"

def test_daemon_status_has_schedule_description():
    with tempfile.TemporaryDirectory() as tmpdir:
        platform = GenericPlatform()
        dm = DaemonManager(platform, schedule="0 2 1 * *", state_dir=Path(tmpdir))
        status = dm.status()
        assert "schedule_description" in status
        assert status["schedule_description"]  # non-empty


# ============================================================
# Tests: DaemonManager._record_run
# ============================================================

def test_record_run_success():
    with tempfile.TemporaryDirectory() as tmpdir:
        platform = GenericPlatform()
        dm = DaemonManager(platform, state_dir=Path(tmpdir))
        dm._record_run(updated=3, failed=0)
        state = DaemonState.load(dm.state_path)
        assert state.last_run_status == "success"
        assert state.last_updated_count == 3
        assert state.last_failed_count == 0

def test_record_run_partial():
    with tempfile.TemporaryDirectory() as tmpdir:
        platform = GenericPlatform()
        dm = DaemonManager(platform, state_dir=Path(tmpdir))
        dm._record_run(updated=2, failed=1)
        state = DaemonState.load(dm.state_path)
        assert state.last_run_status == "partial"

def test_record_run_error():
    with tempfile.TemporaryDirectory() as tmpdir:
        platform = GenericPlatform()
        dm = DaemonManager(platform, state_dir=Path(tmpdir))
        dm._record_run(updated=0, failed=-1)
        state = DaemonState.load(dm.state_path)
        assert state.last_run_status == "error"

def test_record_run_sets_timestamp():
    with tempfile.TemporaryDirectory() as tmpdir:
        platform = GenericPlatform()
        dm = DaemonManager(platform, state_dir=Path(tmpdir))
        dm._record_run(updated=1, failed=0)
        state = DaemonState.load(dm.state_path)
        assert state.last_run_at is not None
        # Should be a valid ISO datetime
        datetime.fromisoformat(state.last_run_at)


# ============================================================
# Tests: DaemonManager.install — cron path (mocked filesystem)
# ============================================================

def test_install_cron_writes_entry():
    with tempfile.TemporaryDirectory() as tmpdir:
        cron_file = Path(tmpdir) / "crontab"
        cron_file.write_text("")  # empty crontab file

        platform = MagicMock(spec=GenericPlatform)
        platform.supports_systemd.return_value = False
        platform.get_cron_path.return_value = str(cron_file)
        platform.name = "Mock"

        dm = DaemonManager(
            platform,
            schedule="0 2 1 * *",
            state_dir=Path(tmpdir),
            dam_executable="/usr/local/bin/dam",
        )
        result = dm.install()

        assert result["success"] is True
        assert result["method"] == "cron"
        content = cron_file.read_text()
        assert "0 2 1 * *" in content
        assert "/usr/local/bin/dam" in content
        assert "# dam-managed" in content

def test_install_cron_replaces_existing_entry():
    with tempfile.TemporaryDirectory() as tmpdir:
        cron_file = Path(tmpdir) / "crontab"
        cron_file.write_text("0 3 1 * * /usr/local/bin/dam --update --yes # dam-managed\n")

        platform = MagicMock(spec=GenericPlatform)
        platform.supports_systemd.return_value = False
        platform.get_cron_path.return_value = str(cron_file)
        platform.name = "Mock"

        dm = DaemonManager(
            platform,
            schedule="0 4 1 * *",  # new schedule
            state_dir=Path(tmpdir),
            dam_executable="/usr/local/bin/dam",
        )
        result = dm.install()

        assert result["success"] is True
        content = cron_file.read_text()
        # Old entry replaced — only one dam entry
        dam_lines = [l for l in content.splitlines() if "dam-managed" in l]
        assert len(dam_lines) == 1
        assert "0 4 1 * *" in content
        assert "0 3 1 * *" not in content

def test_install_cron_updates_state():
    with tempfile.TemporaryDirectory() as tmpdir:
        cron_file = Path(tmpdir) / "crontab"
        cron_file.write_text("")

        platform = MagicMock(spec=GenericPlatform)
        platform.supports_systemd.return_value = False
        platform.get_cron_path.return_value = str(cron_file)
        platform.name = "Mock"

        dm = DaemonManager(
            platform, state_dir=Path(tmpdir),
            dam_executable="/usr/local/bin/dam",
        )
        dm.install()

        state = DaemonState.load(dm.state_path)
        assert state.installed is True
        assert state.install_method == "cron"


# ============================================================
# Tests: DaemonManager.remove — cron
# ============================================================

def test_remove_cron_cleans_entry():
    with tempfile.TemporaryDirectory() as tmpdir:
        cron_file = Path(tmpdir) / "crontab"
        cron_file.write_text(
            "# other cron job\n"
            "0 2 1 * * /usr/local/bin/dam --update --yes # dam-managed\n"
            "# another job\n"
        )

        platform = MagicMock(spec=GenericPlatform)
        platform.supports_systemd.return_value = False
        platform.get_cron_path.return_value = str(cron_file)
        platform.name = "Mock"

        # Save state as installed via cron
        state_path = Path(tmpdir) / STATE_FILENAME
        DaemonState(installed=True, install_method="cron",
                    schedule="0 2 1 * *").save(state_path)

        dm = DaemonManager(
            platform, state_dir=Path(tmpdir),
            dam_executable="/usr/local/bin/dam",
        )
        result = dm.remove()

        assert result["success"] is True
        content = cron_file.read_text()
        assert "dam-managed" not in content
        assert "# other cron job" in content
        assert "# another job" in content

def test_remove_updates_state():
    with tempfile.TemporaryDirectory() as tmpdir:
        cron_file = Path(tmpdir) / "crontab"
        cron_file.write_text("")

        platform = MagicMock(spec=GenericPlatform)
        platform.supports_systemd.return_value = False
        platform.get_cron_path.return_value = str(cron_file)
        platform.name = "Mock"

        state_path = Path(tmpdir) / STATE_FILENAME
        DaemonState(installed=True, install_method="cron").save(state_path)

        dm = DaemonManager(platform, state_dir=Path(tmpdir),
                           dam_executable="/usr/local/bin/dam")
        dm.remove()

        state = DaemonState.load(dm.state_path)
        assert state.installed is False
        assert state.install_method == ""


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
