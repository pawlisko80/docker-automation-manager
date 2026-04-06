"""
dam/cli.py

Click-based CLI for Docker Automation Manager.
Supports both interactive TUI mode and headless flag-driven mode
for use in cron jobs, scripts, and automation pipelines.

Usage:
  dam                         # Launch interactive TUI
  dam --status                # Print container status table and exit
  dam --update                # Run update cycle (interactive prompts)
  dam --update --yes          # Run update cycle non-interactively
  dam --update --dry-run      # Show what would change, make no changes
  dam --drift                 # Run drift check against last snapshot
  dam --prune                 # Prune unused images
  dam --prune --all           # Prune all unreferenced images
  dam --install-daemon        # Install as cron job / systemd unit
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import click
import yaml
from rich.console import Console

console = Console()


# ----------------------------------------------------------------
# Shared context loader
# ----------------------------------------------------------------

def _load_context(config: Optional[str]):
    """Load platform, settings, snapshot manager. Returns (platform, settings, sm)."""
    from dam.platform.detector import detect_platform
    from dam.core.snapshot import SnapshotManager

    platform = detect_platform()
    config_path = Path(config) if config else Path(__file__).parent.parent / "config" / "settings.yaml"

    settings = {}
    try:
        with open(config_path) as f:
            settings = yaml.safe_load(f) or {}
    except FileNotFoundError:
        pass

    dam_cfg = settings.get("dam", {})
    sm = SnapshotManager(retention=dam_cfg.get("snapshot_retention", 10))
    return platform, settings, sm


# ----------------------------------------------------------------
# Main CLI group
# ----------------------------------------------------------------

@click.group(invoke_without_command=True)
@click.option("--config", "-c", default=None, help="Path to settings.yaml")
@click.option("--status",       is_flag=True, help="Show container status and exit")
@click.option("--update",       is_flag=True, help="Run update cycle")
@click.option("--drift",        is_flag=True, help="Run drift detection")
@click.option("--prune",        is_flag=True, help="Prune unused images")
@click.option("--dry-run",      is_flag=True, help="Simulate actions without making changes")
@click.option("--yes",  "-y",   is_flag=True, help="Skip confirmation prompts")
@click.option("--all",  "-a",   is_flag=True, help="(--prune) Remove all unreferenced images")
@click.option("--container",    default=None,  help="Target a single container by name")
@click.option("--install-daemon", is_flag=True, help="Install DAM as a scheduled daemon")
@click.option("--version",      is_flag=True, help="Print version and exit")
@click.pass_context
def cli(ctx, config, status, update, drift, prune, dry_run, yes, all,
        container, install_daemon, version):
    """Docker Automation Manager — container lifecycle management."""

    if version:
        from dam import __version__
        console.print(f"dam v{__version__}")
        return

    # If any action flag is set, run headless
    if status or update or drift or prune or install_daemon:
        ctx.ensure_object(dict)
        ctx.obj["config"]     = config
        ctx.obj["dry_run"]    = dry_run
        ctx.obj["yes"]        = yes
        ctx.obj["all"]        = all
        ctx.obj["container"]  = container

        if status:
            _cmd_status(config)
        if update:
            _cmd_update(config, dry_run=dry_run, yes=yes, container=container)
        if drift:
            _cmd_drift(config)
        if prune:
            _cmd_prune(config, remove_all=all, yes=yes)
        if install_daemon:
            _cmd_install_daemon(config)
        return

    # No flags — launch interactive TUI
    if ctx.invoked_subcommand is None:
        _launch_tui(config)


# ----------------------------------------------------------------
# Headless commands
# ----------------------------------------------------------------

def _launch_tui(config: Optional[str]) -> None:
    """Launch the interactive Rich TUI."""
    try:
        from dam.tui import DAMTui
        config_path = Path(config) if config else None
        tui = DAMTui(config_path=config_path)
        tui.run()
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]")
    except Exception as e:
        console.print(f"[bold red]Fatal error:[/bold red] {e}")
        sys.exit(1)


def _cmd_status(config: Optional[str]) -> None:
    """Print container status table."""
    from dam.tui import render_status_table
    from dam.core.inspector import Inspector

    platform, settings, _ = _load_context(config)
    try:
        inspector = Inspector(platform)
        configs = inspector.inspect_all(
            settings_containers=settings.get("containers", {}) or {}
        )
        console.print(render_status_table(configs))
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)


def _cmd_update(
    config: Optional[str],
    dry_run: bool = False,
    yes: bool = False,
    container: Optional[str] = None,
) -> None:
    """Run update cycle non-interactively."""
    from dam.core.inspector import Inspector
    from dam.core.updater import Updater
    from dam.tui import render_update_results, render_update_summary

    platform, settings, sm = _load_context(config)
    dam_cfg = settings.get("dam", {})

    try:
        inspector = Inspector(platform)
        all_configs = inspector.inspect_all(
            settings_containers=settings.get("containers", {}) or {}
        )

        # Filter to single container if specified
        configs = all_configs
        if container:
            configs = [c for c in all_configs if c.name == container]
            if not configs:
                console.print(f"[yellow]Container '{container}' not found.[/yellow]")
                sys.exit(1)

        if not yes:
            click.confirm(
                f"Update {len(configs)} container(s)?",
                default=True, abort=True
            )

        # Snapshot before
        sm.save(all_configs, platform, label="pre-update")

        def on_progress(name: str, msg: str) -> None:
            console.print(f"[dim]{name}[/dim] {msg}")

        updater = Updater(
            platform=platform,
            dry_run=dry_run,
            recreate_delay=dam_cfg.get("recreate_delay", 5),
            progress_callback=on_progress,
        )

        results = updater.update_all(configs)

        console.print()
        console.print(render_update_results(results))
        console.print()
        summary = Updater.summarize(results)
        console.print(render_update_summary(summary))

        # Auto-prune
        if not dry_run and summary["updated"] > 0 and dam_cfg.get("auto_prune", True):
            _cmd_prune(config, remove_all=False, yes=True, update_results=results)

        if summary["failed"] > 0:
            sys.exit(1)

    except SystemExit:
        raise
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)


def _cmd_drift(config: Optional[str]) -> None:
    """Run drift detection and print report."""
    from dam.core.inspector import Inspector
    from dam.core.drift import DriftDetector
    from dam.tui import render_drift_report, render_drift_summary

    platform, settings, sm = _load_context(config)

    try:
        result = sm.load_latest()
        if not result:
            console.print("[yellow]No snapshot found. Run --update first.[/yellow]")
            sys.exit(1)

        snap_meta, snap_configs = result
        inspector = Inspector(platform)
        live_configs = inspector.inspect_all(
            settings_containers=settings.get("containers", {}) or {}
        )

        detector = DriftDetector()
        report = detector.compare(
            snap_configs, live_configs,
            label_a=f"snapshot ({snap_meta['captured_at']})",
            label_b="live",
        )

        if not report.has_drift:
            console.print("[bold green]✓ No drift detected.[/bold green]")
        else:
            console.print(render_drift_summary(report))
            console.print()
            console.print(render_drift_report(report))
            # Exit code 2 signals drift found (useful for monitoring scripts)
            sys.exit(2)

    except SystemExit:
        raise
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)


def _cmd_prune(
    config: Optional[str],
    remove_all: bool = False,
    yes: bool = False,
    update_results=None,
) -> None:
    """Prune unused images."""
    from dam.core.pruner import Pruner
    from dam.tui import render_prune_candidates, render_prune_result

    platform, settings, _ = _load_context(config)

    try:
        preview_pruner = Pruner(dry_run=True, remove_unreferenced=remove_all)
        candidates = preview_pruner.list_candidates(update_results)

        if candidates["total_candidates"] == 0:
            console.print("[green]✓ Nothing to prune.[/green]")
            return

        console.print(render_prune_candidates(candidates))

        if not yes:
            click.confirm("Proceed with prune?", default=True, abort=True)

        pruner = Pruner(dry_run=False, remove_unreferenced=remove_all)
        result = pruner.prune(update_results)
        console.print(render_prune_result(result))

    except SystemExit:
        raise
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)


def _cmd_install_daemon(config: Optional[str]) -> None:
    """Install DAM as a scheduled cron job or systemd unit."""
    platform, settings, _ = _load_context(config)
    daemon_cfg = settings.get("daemon", {})
    schedule = daemon_cfg.get("schedule", "0 2 1 * *")

    console.print("[bold cyan]Installing DAM daemon[/bold cyan]")
    console.print(f"Platform:  [cyan]{platform.name}[/cyan]")
    console.print(f"Schedule:  [cyan]{schedule}[/cyan]")
    console.print()

    dam_path = Path(sys.argv[0]).resolve()
    cron_line = f"{schedule} {dam_path} --update --yes\n"

    if platform.supports_systemd():
        _install_systemd(dam_path, schedule)
    else:
        _install_cron(platform, cron_line)


def _install_cron(platform, cron_line: str) -> None:
    """Write cron entry to platform cron path."""
    from dam.platform.qnap import QNAPPlatform

    cron_path = platform.get_cron_path()
    console.print(f"Writing cron entry to: [cyan]{cron_path}[/cyan]")
    console.print(f"Entry: [dim]{cron_line.strip()}[/dim]")

    try:
        # Check for existing DAM entry
        existing = ""
        try:
            with open(cron_path) as f:
                existing = f.read()
        except FileNotFoundError:
            pass

        if "dam" in existing and "--update" in existing:
            console.print("[yellow]Existing DAM cron entry found — replacing.[/yellow]")
            lines = [ln for ln in existing.splitlines()
                     if not ("dam" in ln and "--update" in ln)]
            existing = "\n".join(lines) + "\n"

        with open(cron_path, "a") as f:
            f.write(cron_line)

        # QNAP needs a reload after crontab edit
        if isinstance(platform, QNAPPlatform):
            if platform.reload_cron():
                console.print("[green]✓ Crontab reloaded.[/green]")
            else:
                console.print("[yellow]Warning: crontab reload failed — reload manually.[/yellow]")

        console.print("[bold green]✓ Daemon installed.[/bold green]")

    except PermissionError:
        console.print(f"[bold red]Permission denied writing to {cron_path}.[/bold red]")
        console.print("[dim]Try running as root or with sudo.[/dim]")
        sys.exit(1)


def _install_systemd(dam_path: Path, schedule: str) -> None:
    """Create systemd timer unit for DAM."""
    service = f"""[Unit]
Description=Docker Automation Manager update cycle
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart={dam_path} --update --yes
"""
    timer = f"""[Unit]
Description=Docker Automation Manager scheduled timer

[Timer]
OnCalendar={schedule}
Persistent=true

[Install]
WantedBy=timers.target
"""
    service_path = Path("/etc/systemd/system/dam.service")
    timer_path   = Path("/etc/systemd/system/dam.timer")

    try:
        service_path.write_text(service)
        timer_path.write_text(timer)
        console.print(f"[green]✓[/green] Written: {service_path}")
        console.print(f"[green]✓[/green] Written: {timer_path}")
        console.print("\nEnable with:")
        console.print("  [cyan]systemctl daemon-reload[/cyan]")
        console.print("  [cyan]systemctl enable --now dam.timer[/cyan]")
    except PermissionError:
        console.print("[bold red]Permission denied — run as root.[/bold red]")
        sys.exit(1)


# ----------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------

def main():
    cli(obj={})


if __name__ == "__main__":
    main()
