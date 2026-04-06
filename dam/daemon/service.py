"""
dam/daemon/service.py

Daemon lifecycle management for Docker Automation Manager.

Responsibilities:
  - Install DAM as a recurring scheduled job (cron or systemd)
  - Remove the scheduled job
  - Query daemon status (installed / next run / last run)
  - Run the background update loop (blocking, for process managers)
  - Write structured run logs

Platform routing:
  - QNAP/Synology without systemd → cron via platform adapter
  - Generic Linux with systemd    → systemd timer unit
  - Any platform                  → fallback to user crontab

The daemon run loop uses the CronExpression.next_run() calculator
to sleep precisely until the next scheduled trigger, then calls
the core update/prune pipeline without spawning subprocesses.
"""

from __future__ import annotations

import json
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from dam.daemon.scheduler import parse_cron, validate_cron
from dam.platform.base import BasePlatform


# ------------------------------------------------------------
# State file — tracks last run metadata
# ------------------------------------------------------------

STATE_FILENAME = ".dam_daemon_state.json"


@dataclass
class DaemonState:
    installed: bool = False
    install_method: str = ""       # "cron" or "systemd"
    schedule: str = ""
    last_run_at: Optional[str] = None
    last_run_status: str = ""      # "success" / "partial" / "failed"
    last_updated_count: int = 0
    last_failed_count: int = 0
    next_run_at: Optional[str] = None

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, path: Path) -> "DaemonState":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text())
            return cls(**{k: v for k, v in data.items()
                          if k in cls.__dataclass_fields__})
        except Exception:
            return cls()


# ------------------------------------------------------------
# Systemd unit templates
# ------------------------------------------------------------

_SYSTEMD_SERVICE = """\
[Unit]
Description=Docker Automation Manager — container update cycle
After=docker.service network-online.target
Requires=docker.service
Wants=network-online.target

[Service]
Type=oneshot
ExecStart={dam_path} --update --yes
StandardOutput=journal
StandardError=journal
"""

_SYSTEMD_TIMER = """\
[Unit]
Description=Docker Automation Manager — scheduled timer
After=docker.service

[Timer]
OnCalendar={schedule}
Persistent=true
RandomizedDelaySec=60

[Install]
WantedBy=timers.target
"""

_SYSTEMD_SERVICE_PATH = Path("/etc/systemd/system/dam.service")
_SYSTEMD_TIMER_PATH   = Path("/etc/systemd/system/dam.timer")


# ------------------------------------------------------------
# Cron entry marker
# ------------------------------------------------------------

_CRON_MARKER = "# dam-managed"


# ------------------------------------------------------------
# DaemonManager
# ------------------------------------------------------------

class DaemonManager:
    """
    Installs, removes, and queries the DAM daemon schedule.
    Runs the background update loop in foreground mode.
    """

    def __init__(
        self,
        platform: BasePlatform,
        schedule: str = "0 2 1 * *",
        state_dir: Optional[Path] = None,
        dam_executable: Optional[str] = None,
    ):
        """
        Args:
            platform:        Active platform adapter
            schedule:        Cron expression for the update schedule
            state_dir:       Directory to write state file (default: config/)
            dam_executable:  Path to the `dam` binary (default: sys.argv[0])
        """
        self.platform = platform
        self.schedule = schedule
        self.state_dir = state_dir or Path(__file__).parent.parent.parent / "config"
        self.state_path = self.state_dir / STATE_FILENAME
        self.dam_executable = dam_executable or sys.argv[0]

        # Validate schedule on init
        valid, msg = validate_cron(schedule)
        if not valid:
            raise ValueError(f"Invalid schedule '{schedule}': {msg}")

        self.cron_expr = parse_cron(schedule)

    # ------------------------------------------------------------
    # Install
    # ------------------------------------------------------------

    def install(self) -> dict:
        """
        Install DAM as a scheduled daemon.
        Returns result dict with keys: success, method, message.
        """
        if self.platform.supports_systemd():
            return self._install_systemd()
        else:
            return self._install_cron()

    def _install_systemd(self) -> dict:
        """Write systemd service + timer units and enable the timer."""
        dam_path = Path(self.dam_executable).resolve()
        service_content = _SYSTEMD_SERVICE.format(dam_path=dam_path)
        timer_content   = _SYSTEMD_TIMER.format(schedule=self.schedule)

        try:
            _SYSTEMD_SERVICE_PATH.write_text(service_content)
            _SYSTEMD_TIMER_PATH.write_text(timer_content)
        except PermissionError:
            return {
                "success": False,
                "method": "systemd",
                "message": "Permission denied writing to /etc/systemd/system/. Run as root.",
            }

        # Reload and enable
        try:
            subprocess.run(["systemctl", "daemon-reload"], check=True, capture_output=True)
            subprocess.run(["systemctl", "enable", "--now", "dam.timer"],
                           check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            return {
                "success": False,
                "method": "systemd",
                "message": f"systemctl failed: {e.stderr.decode().strip()}",
            }
        except FileNotFoundError:
            return {
                "success": False,
                "method": "systemd",
                "message": "systemctl not found despite systemd detection.",
            }

        self._save_state(installed=True, method="systemd")
        return {
            "success": True,
            "method": "systemd",
            "message": f"Timer installed and enabled. Schedule: {self.schedule}",
        }

    def _install_cron(self) -> dict:
        """Write a cron entry using the platform cron path."""
        from dam.platform.qnap import QNAPPlatform

        cron_path_str = self.platform.get_cron_path()
        dam_path = Path(self.dam_executable).resolve()
        cron_line = (
            f"{self.schedule} {dam_path} --update --yes "
            f"{_CRON_MARKER}\n"
        )

        if cron_path_str == "crontab":
            return self._install_user_crontab(cron_line)

        cron_path = Path(cron_path_str)

        try:
            existing = cron_path.read_text() if cron_path.exists() else ""
            # Remove any existing DAM cron entry
            lines = [
                l for l in existing.splitlines()
                if _CRON_MARKER not in l
            ]
            lines.append(cron_line.rstrip())
            cron_path.write_text("\n".join(lines) + "\n")
        except PermissionError:
            return {
                "success": False,
                "method": "cron",
                "message": f"Permission denied writing to {cron_path_str}. Run as root.",
            }

        # QNAP requires crontab reload
        if isinstance(self.platform, QNAPPlatform):
            self.platform.reload_cron()

        self._save_state(installed=True, method="cron")
        return {
            "success": True,
            "method": "cron",
            "message": f"Cron entry written to {cron_path_str}. Schedule: {self.schedule}",
        }

    def _install_user_crontab(self, cron_line: str) -> dict:
        """Install via `crontab -l` / `crontab -` for user-level crontab."""
        try:
            result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True, text=True,
            )
            existing = result.stdout if result.returncode == 0 else ""

            lines = [ln for ln in existing.splitlines() if _CRON_MARKER not in ln]
            lines.append(cron_line.rstrip())
            new_crontab = "\n".join(lines) + "\n"

            proc = subprocess.run(
                ["crontab", "-"],
                input=new_crontab,
                capture_output=True, text=True,
            )
            if proc.returncode != 0:
                return {
                    "success": False,
                    "method": "cron",
                    "message": f"crontab failed: {proc.stderr.strip()}",
                }
        except FileNotFoundError:
            return {
                "success": False,
                "method": "cron",
                "message": "crontab command not found.",
            }

        self._save_state(installed=True, method="cron")
        return {
            "success": True,
            "method": "cron",
            "message": f"User crontab updated. Schedule: {self.schedule}",
        }

    # ------------------------------------------------------------
    # Remove
    # ------------------------------------------------------------

    def remove(self) -> dict:
        """Remove the DAM daemon schedule."""
        state = DaemonState.load(self.state_path)

        if state.install_method == "systemd":
            return self._remove_systemd()
        else:
            return self._remove_cron()

    def _remove_systemd(self) -> dict:
        """Disable and remove systemd timer."""
        try:
            subprocess.run(
                ["systemctl", "disable", "--now", "dam.timer"],
                capture_output=True
            )
            for path in (_SYSTEMD_TIMER_PATH, _SYSTEMD_SERVICE_PATH):
                if path.exists():
                    path.unlink()
            subprocess.run(["systemctl", "daemon-reload"], capture_output=True)
        except Exception as e:
            return {"success": False, "message": str(e)}

        self._save_state(installed=False, method="")
        return {"success": True, "message": "Systemd timer removed."}

    def _remove_cron(self) -> dict:
        """Remove the DAM cron entry."""
        from dam.platform.qnap import QNAPPlatform

        cron_path_str = self.platform.get_cron_path()

        if cron_path_str == "crontab":
            try:
                result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
                lines = [l for l in result.stdout.splitlines()
                         if _CRON_MARKER not in l]
                new_tab = "\n".join(lines) + "\n"
                subprocess.run(["crontab", "-"], input=new_tab, capture_output=True, text=True)
            except Exception as e:
                return {"success": False, "message": str(e)}
        else:
            cron_path = Path(cron_path_str)
            if cron_path.exists():
                try:
                    lines = [ln for ln in cron_path.read_text().splitlines()
                             if _CRON_MARKER not in ln]
                    cron_path.write_text("\n".join(lines) + "\n")
                    if isinstance(self.platform, QNAPPlatform):
                        self.platform.reload_cron()
                except Exception as e:
                    return {"success": False, "message": str(e)}

        self._save_state(installed=False, method="")
        return {"success": True, "message": "Cron entry removed."}

    # ------------------------------------------------------------
    # Status
    # ------------------------------------------------------------

    def status(self) -> dict:
        """Return daemon status information."""
        state = DaemonState.load(self.state_path)
        next_run = None
        try:
            next_run = self.cron_expr.next_run().isoformat(timespec="minutes")
        except Exception:
            pass

        return {
            "installed": state.installed,
            "method": state.install_method,
            "schedule": self.schedule,
            "schedule_description": self.cron_expr.describe(),
            "next_run": next_run,
            "last_run_at": state.last_run_at,
            "last_run_status": state.last_run_status,
            "last_updated_count": state.last_updated_count,
            "last_failed_count": state.last_failed_count,
        }

    # ------------------------------------------------------------
    # Foreground run loop
    # ------------------------------------------------------------

    def run_loop(
        self,
        settings: dict,
        on_tick: Optional[callable] = None,
    ) -> None:
        """
        Run the DAM update loop in the foreground.
        Sleeps until the next scheduled trigger, then executes the
        full update + prune pipeline directly (no subprocess).

        Args:
            settings:  Loaded settings.yaml dict
            on_tick:   Optional callback(next_run_dt) called before each sleep
        """
        from dam.core.inspector import Inspector
        from dam.core.updater import Updater
        from dam.core.pruner import Pruner
        from dam.core.snapshot import SnapshotManager

        dam_cfg = settings.get("dam", {})
        sm = SnapshotManager(retention=dam_cfg.get("snapshot_retention", 10))

        # Graceful shutdown on SIGTERM/SIGINT
        self._running = True

        def _handle_signal(sig, frame):
            self._running = False
        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT,  _handle_signal)

        print(f"[dam daemon] Started. Schedule: {self.schedule} ({self.cron_expr.describe()})")

        while self._running:
            next_run = self.cron_expr.next_run()
            print(f"[dam daemon] Next run: {next_run.isoformat(timespec='minutes')}")

            if on_tick:
                on_tick(next_run)

            # Sleep in 30-second chunks to stay responsive to SIGTERM
            while self._running and datetime.now() < next_run:
                time.sleep(min(30, (next_run - datetime.now()).total_seconds()))

            if not self._running:
                break

            print(f"[dam daemon] Triggering update at {datetime.now().isoformat(timespec='seconds')}")
            try:
                inspector = Inspector(self.platform)
                configs = inspector.inspect_all(
                    settings_containers=settings.get("containers", {}) or {}
                )
                sm.save(configs, self.platform, label="daemon-pre")

                updater = Updater(
                    platform=self.platform,
                    dry_run=False,
                    recreate_delay=dam_cfg.get("recreate_delay", 5),
                )
                results = updater.update_all(configs)
                summary = Updater.summarize(results)

                if dam_cfg.get("auto_prune", True) and summary["updated"] > 0:
                    pruner = Pruner(dry_run=False)
                    pruner.prune(results)

                self._record_run(
                    updated=summary["updated"],
                    failed=summary["failed"],
                )
                print(
                    f"[dam daemon] Done. Updated: {summary['updated']}, "
                    f"Skipped: {summary['skipped']}, "
                    f"Failed: {summary['failed']}"
                )

            except Exception as e:
                print(f"[dam daemon] Error during update: {e}")
                self._record_run(updated=0, failed=-1)

        print("[dam daemon] Stopped.")

    # ------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------

    def _save_state(self, installed: bool, method: str) -> None:
        state = DaemonState.load(self.state_path)
        state.installed = installed
        state.install_method = method
        state.schedule = self.schedule
        try:
            next_run = self.cron_expr.next_run()
            state.next_run_at = next_run.isoformat(timespec="minutes")
        except Exception:
            pass
        self.state_dir.mkdir(parents=True, exist_ok=True)
        state.save(self.state_path)

    def _record_run(self, updated: int, failed: int) -> None:
        state = DaemonState.load(self.state_path)
        state.last_run_at = datetime.now().isoformat(timespec="seconds")
        state.last_updated_count = updated
        state.last_failed_count = failed
        if failed < 0:
            state.last_run_status = "error"
        elif failed > 0:
            state.last_run_status = "partial"
        else:
            state.last_run_status = "success"
        try:
            state.next_run_at = self.cron_expr.next_run().isoformat(timespec="minutes")
        except Exception:
            pass
        state.save(self.state_path)
