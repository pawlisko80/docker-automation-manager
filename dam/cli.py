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
@click.option("--status", is_flag=True, help="Show container status and exit")
@click.option("--update", is_flag=True, help="Run update cycle")
@click.option("--drift", is_flag=True, help="Run drift detection")
@click.option("--prune", is_flag=True, help="Prune unused images")
@click.option("--dry-run", is_flag=True, help="Simulate actions without making changes")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompts")
@click.option("--all", "-a", is_flag=True, help="(--prune) Remove all unreferenced images")
@click.option("--container", default=None, help="Target a single container by name")
@click.option("--export", is_flag=True, help="Export container configs")
@click.option("--migrate", is_flag=True, help="Export migration bundle (migrate.sh + DAM YAML + README)")
@click.option("--import-file", default=None, help="Import containers from a DAM YAML file")
@click.option("--eol-check", is_flag=True, help="Check for deprecated or EOL images")
@click.option("--format", "fmt", default="dam-yaml", help="Export format: dam-yaml | docker-run | compose")
@click.option("--output", "-o", default=None, help="Output directory for exports")
@click.option("--web", is_flag=True, help="Launch web UI")
@click.option("--host", default="127.0.0.1", help="Web UI bind host (use 0.0.0.0 for network access)")
@click.option("--port", default=8080, type=int, help="Web UI port (default: 8080)")
@click.option("--web-passwd", is_flag=True, help="Set web UI username and password")
@click.option("--install-daemon", is_flag=True, help="Install DAM as a scheduled daemon")
@click.option("--backup", is_flag=True, help="Backup all container configs to DAM YAML")
@click.option("--snapshot", is_flag=True, help="Take a snapshot of current container state")
@click.option("--snapshots", is_flag=True, help="List all saved snapshots")
@click.option("--rollback", default=None, type=int, metavar="N", help="Rollback to snapshot N (0=latest)")
@click.option("--images", is_flag=True, help="List all Docker images with status")
@click.option("--clone", default=None, metavar="SRC", help="Clone container SRC")
@click.option("--clone-name", default=None, help="New name for cloned container")
@click.option("--clone-ip", default=None, help="New IP address for cloned container")
@click.option("--clone-mac", default=None, help="New MAC address (or 'auto' to generate)")
@click.option("--history", is_flag=True, help="Show update history")
@click.option("--approvals", is_flag=True, help="List pending update approvals")
@click.option("--approve", default=None, metavar="NAME", help="Approve pending update for container")
@click.option("--reject", default=None, metavar="NAME", help="Reject pending update for container")
@click.option("--network-health", is_flag=True, help="Check for containers with network issues")
@click.option("--network-fix", default=None, metavar="NAME", help="Recreate container with correct network")
@click.option("--notify-test", is_flag=True, help="Send a test notification")
@click.option("--policy", default=None, metavar="NAME:POLICY",
              help="Set update policy: name:auto|notify|approve|hold")
@click.option("--version", is_flag=True, help="Print version and exit")
@click.pass_context
def cli(ctx, config, status, update, drift, prune, dry_run, yes, all,
        container, install_daemon, export, import_file, eol_check,
        fmt, output, migrate, web, host, port, web_passwd,
        backup, snapshot, snapshots, rollback, images, clone, clone_name, clone_ip, clone_mac,
        history, approvals, approve, reject, network_health, network_fix,
        notify_test, policy, version):
    """Docker Automation Manager — container lifecycle management."""

    if version:
        from dam import __version__
        console.print(f"dam v{__version__}")
        return

    # If any action flag is set, run headless
    any_action = web or web_passwd or status or update or drift or prune
    any_action = any_action or install_daemon or export or import_file or eol_check or migrate
    any_action = any_action or backup or snapshot or snapshots or (rollback is not None) or images
    any_action = any_action or clone or history or approvals or approve or reject
    any_action = any_action or network_health or network_fix or notify_test or policy
    if any_action:
        ctx.ensure_object(dict)
        ctx.obj["config"] = config
        ctx.obj["dry_run"] = dry_run
        ctx.obj["yes"] = yes
        ctx.obj["all"] = all
        ctx.obj["container"] = container
        ctx.obj["fmt"] = fmt
        ctx.obj["output"] = output

        if web_passwd:
            _cmd_set_web_passwd(config)
        if migrate:
            _cmd_migrate(config, output=output)
            return
        if web:
            _cmd_web(config, host=host, port=port)
            return
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
        if export:
            _cmd_export(config, fmt=fmt, output=output, container=container, yes=yes)
        if import_file:
            _cmd_import(config, file_path=import_file, dry_run=dry_run, yes=yes)
        if eol_check:
            _cmd_eol_check(config)
        if backup:
            _cmd_backup(config, output=output)
        if snapshot:
            _cmd_snapshot(config)
        if snapshots:
            _cmd_list_snapshots(config)
        if rollback is not None:
            _cmd_rollback(config, index=rollback, yes=yes)
        if images:
            _cmd_images(config)
        if clone:
            _cmd_clone(config, source=clone, new_name=clone_name,
                       new_ip=clone_ip, new_mac=clone_mac, dry_run=dry_run, yes=yes)
        if history:
            _cmd_history(config)
        if approvals:
            _cmd_approvals(config)
        if approve:
            _cmd_approve(config, container_name=approve)
        if reject:
            _cmd_reject(config, container_name=reject)
        if network_health:
            _cmd_network_health(config)
        if network_fix:
            _cmd_network_fix(config, container_name=network_fix, yes=yes)
        if notify_test:
            _cmd_notify_test(config)
        if policy:
            _cmd_set_policy(config, policy_spec=policy)
        if web:
            _cmd_web(config, host=host, port=port)
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


def _cmd_web(config, host: str = "127.0.0.1", port: int = 8080) -> None:
    """Launch the DAM web UI."""
    try:
        from dam.web.server import run_server
        from pathlib import Path
        config_path = Path(config).expanduser() if config else None
        console.print(f"[bold cyan]🐳 DAM Web UI[/bold cyan]  →  http://{host}:{port}")
        console.print("[dim]Press Ctrl+C to stop.[/dim]")
        run_server(host=host, port=port, config_path=config_path)
    except ImportError:
        console.print("[bold red]Error:[/bold red] Web UI requires fastapi and uvicorn.")
        console.print("Install with: [cyan]pip install fastapi uvicorn[/cyan]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)


def _cmd_web_passwd(config) -> None:
    """Interactively set the web UI username and password."""
    import getpass
    from pathlib import Path
    import yaml
    from dam.web.auth import hash_password

    config_path = Path(config).expanduser() if config else Path(__file__).parent.parent / "config" / "settings.yaml"

    # Load existing settings
    settings = {}
    try:
        with open(config_path) as f:
            settings = yaml.safe_load(f) or {}
    except FileNotFoundError:
        pass

    console.print("[bold cyan]Set Web UI Credentials[/bold cyan]")
    console.print(f"[dim]Saving to: {config_path}[/dim]\n")

    username = click.prompt("Username", default=settings.get("web", {}).get("username", "admin"))
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")

    if password != confirm:
        console.print("[bold red]Passwords do not match.[/bold red]")
        sys.exit(1)

    if len(password) < 6:
        console.print("[bold red]Password must be at least 6 characters.[/bold red]")
        sys.exit(1)

    hashed = hash_password(password)

    if "web" not in settings:
        settings["web"] = {}
    settings["web"]["username"] = username
    settings["web"]["password_hash"] = hashed

    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        yaml.dump(settings, f, default_flow_style=False, sort_keys=False)

    console.print("[bold green]✓[/bold green] Credentials saved. Start the web UI with:")
    console.print("  [cyan]dam --web[/cyan]")
    console.print("  [cyan]dam --web --host 0.0.0.0  [/cyan][dim]# accessible from your network[/dim]")


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
    service = """[Unit]
Description=Docker Automation Manager update cycle
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart={dam_path} --update --yes
"""
    timer = """[Unit]
Description=Docker Automation Manager scheduled timer

[Timer]
OnCalendar={schedule}
Persistent=true

[Install]
WantedBy=timers.target
"""
    service_path = Path("/etc/systemd/system/dam.service")
    timer_path = Path("/etc/systemd/system/dam.timer")

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


def _cmd_export(
    config,
    fmt: str = "dam-yaml",
    output=None,
    container=None,
    yes: bool = False,
) -> None:
    """Export container configs to specified format."""
    from dam.core.inspector import Inspector
    from dam.core.exporter import Exporter, FORMATS
    from pathlib import Path

    if fmt not in FORMATS:
        console.print(f"[red]Invalid format '{fmt}'. Choose from: {', '.join(FORMATS)}[/red]")
        sys.exit(1)

    platform, settings, _ = _load_context(config)
    out_dir = Path(output).expanduser() if output else Path.home() / "dam-exports"

    try:
        inspector = Inspector(platform)
        all_configs = inspector.inspect_all(
            settings_containers=settings.get("containers", {}) or {}
        )
        if container:
            all_configs = [c for c in all_configs if c.name == container]
            if not all_configs:
                console.print(f"[yellow]Container '{container}' not found.[/yellow]")
                sys.exit(1)

        exporter = Exporter()
        single = len(all_configs) > 1
        paths = exporter.export(all_configs, fmt, out_dir, single_file=single)
        for p in paths:
            console.print(f"[green]✓[/green] Exported: {p}")

    except Exception as e:
        console.print(f"[bold red]Export failed:[/bold red] {e}")
        sys.exit(1)


def _cmd_migrate(config, output=None) -> None:
    """Export a migration bundle: migrate.sh + dam-migrate-config.yaml + README in a zip."""
    import zipfile
    from dam.core.inspector import Inspector
    from dam.core.exporter import Exporter
    from dam.web.server import _generate_migration_script, _get_migration_binds
    from pathlib import Path

    platform, settings, _ = _load_context(config)
    out_dir = Path(output).expanduser() if output else Path.cwd()

    try:
        inspector = Inspector(platform)
        configs = inspector.inspect_all(
            settings_containers=settings.get("containers", {}) or {}
        )

        # Generate migrate.sh
        script = _generate_migration_script(configs)

        # Generate dam-migrate-config.yaml
        import tempfile
        exporter = Exporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = exporter.export(configs, "dam-yaml", Path(tmpdir), single_file=True)
            yaml_content = paths[0].read_text() if paths else "# export failed"

        readme = (
            "DAM Migration Bundle\n"
            "====================\n\n"
            "Files:\n"
            "  migrate.sh              Run on source then target server\n"
            "  dam-migrate-config.yaml Import via DAM web UI Import page\n"
            "  volumes.tar.xz          Created by: bash migrate.sh source\n\n"
            "Steps:\n"
            "  1. bash migrate.sh source  (on source server)\n"
            "     Stops containers, archives volumes to volumes.tar.xz, restarts\n"
            "  2. Copy migrate.sh + volumes.tar.xz + dam-migrate-config.yaml to target\n"
            "  3. bash migrate.sh restore  (on target server)\n"
            "     Extracts volumes, recreates all containers\n"
        )

        zip_path = out_dir / "dam-migration.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            zf.writestr("migrate.sh", script)
            zf.writestr("dam-migrate-config.yaml", yaml_content)
            zf.writestr("README.txt", readme)

        console.print(f"[green]✓[/green] Migration bundle: {zip_path}")
        console.print()

        all_binds = _get_migration_binds(configs)
        if all_binds:
            console.print("[cyan]Volume paths that will be archived:[/cyan]")
            for path, cname in all_binds.items():
                console.print(f"  {cname}: [dim]{path}[/dim]")
            console.print()

        console.print("[bold]Next steps:[/bold]")
        console.print("  1. [cyan]bash migrate.sh source[/cyan]  — archive volumes")
        console.print("  2. Copy migrate.sh + volumes.tar.xz + dam-migrate-config.yaml to target")
        console.print("  3. [cyan]bash migrate.sh restore[/cyan]  — restore on target")

    except Exception as e:
        console.print(f"[bold red]Migration export failed:[/bold red] {e}")
        sys.exit(1)


def _cmd_import(
    config,
    file_path: str = None,
    dry_run: bool = False,
    yes: bool = False,
) -> None:
    """Import containers from a DAM YAML export file."""
    from dam.core.importer import Importer, load_import_file
    from pathlib import Path

    if not file_path:
        console.print("[red]--import-file requires a file path.[/red]")
        sys.exit(1)

    platform, settings, _ = _load_context(config)
    path = Path(file_path).expanduser()

    try:
        meta, configs = load_import_file(path)
        console.print(f"Found [bold]{len(configs)}[/bold] container(s) in {path.name}")
        for cfg in configs:
            console.print(f"  • {cfg.name}  ({cfg.image})")

        if not yes and not dry_run:
            click.confirm("Proceed with import?", default=True, abort=True)

        importer = Importer(platform, dry_run=dry_run)
        results = importer.import_configs(configs)

        for r in results:
            icon = "✓" if r.success else "✗"
            color = "green" if r.success else "red"
            console.print(f"[{color}]{icon}[/{color}] {r.container_name}: {r.status.value}")
            if r.error:
                console.print(f"   [red]{r.error}[/red]")

        summary = Importer.summarize(results)
        if summary["failed"] > 0:
            sys.exit(1)

    except SystemExit:
        raise
    except Exception as e:
        console.print(f"[bold red]Import failed:[/bold red] {e}")
        sys.exit(1)


def _cmd_eol_check(config) -> None:
    """Check all containers for deprecated or EOL images."""
    from dam.core.inspector import Inspector
    from dam.core.deprecation import DeprecationChecker, DeprecationStatus

    platform, settings, _ = _load_context(config)

    try:
        inspector = Inspector(platform)
        configs = inspector.inspect_all(
            settings_containers=settings.get("containers", {}) or {}
        )
        checker = DeprecationChecker()
        results = checker.check_all(configs)
        warnings = checker.warnings_only(results)
        summary = checker.summary(results)

        console.print(
            f"Checked {summary['total_checked']} containers — "
            f"[green]{summary['ok']} ok[/green]  "
            f"[yellow]{summary['deprecated']} deprecated  "
            f"{summary['archived']} archived[/yellow]  "
            f"[red]{summary['eol']} EOL[/red]"
        )

        if not warnings:
            console.print("[bold green]✓ All images are current and actively maintained.[/bold green]")
        else:
            console.print()
            for r in warnings:
                icons = {
                    DeprecationStatus.DEPRECATED: "⚠",
                    DeprecationStatus.ARCHIVED: "📦",
                    DeprecationStatus.EOL: "☠",
                }
                icon = icons.get(r.status, "?")
                console.print(f"{icon} [bold]{r.container_name}[/bold] ({r.image})")
                console.print(f"   Status: [yellow]{r.status.value}[/yellow]")
                if r.reason:
                    console.print(f"   Reason: {r.reason}")
                if r.alternatives:
                    alts = ", ".join(a.name for a in r.alternatives)
                    console.print(f"   Alternatives: [cyan]{alts}[/cyan]")
                console.print()

            # Exit code 3 signals EOL/deprecated found (useful for monitoring)
            sys.exit(3)

    except SystemExit:
        raise
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)


def _cmd_set_web_passwd(config) -> None:
    """Interactive: set web UI username/password in settings.yaml."""
    import hashlib as _hl
    import secrets as _sec
    from pathlib import Path
    import yaml as _yaml

    console.print("[bold cyan]Set Web UI Password[/bold cyan]")
    console.print()

    username = click.prompt("Username", default="admin")
    password = click.prompt("Password", hide_input=True, confirmation_prompt=True)

    # Always write sha256:salt:hash — works without bcrypt dependency
    salt = _sec.token_hex(16)
    h = _hl.sha256(f"{salt}{password}".encode()).hexdigest()
    hashed = f"sha256:{salt}:{h}"

    cfg_path = Path(config) if config else Path(__file__).parent.parent / "config" / "settings.yaml"
    settings = {}
    if cfg_path.exists():
        with open(cfg_path) as f:
            settings = _yaml.safe_load(f) or {}

    if "web" not in settings:
        settings["web"] = {}

    # Write flat format: web.username + web.password_hash
    settings["web"]["username"] = username
    settings["web"]["password_hash"] = hashed
    # Remove old auth list format if present
    settings["web"].pop("auth", None)

    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cfg_path, "w") as f:
        _yaml.dump(settings, f, default_flow_style=False, sort_keys=False)

    console.print(f"[green]✓[/green] Password set for user [cyan]{username}[/cyan]")
    console.print(f"[dim]Saved to {cfg_path}[/dim]")
    console.print()
    console.print("Start web UI with: [cyan]dam --web[/cyan]")


def _cmd_backup(config, output: str = None) -> None:
    """Backup all container configs to a DAM YAML file."""
    import datetime
    platform, settings, _ = _load_context(config)
    from dam.core.inspector import Inspector
    from dam.core.exporter import Exporter
    inspector = Inspector(platform)
    configs = inspector.inspect_all(settings_containers=settings.get("containers", {}) or {})
    exporter = Exporter(platform)
    out_dir = Path(output) if output else Path(".")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_file = out_dir / f"dam-backup-{ts}.yaml"
    yaml_content = exporter.to_yaml(configs)
    out_file.write_text(yaml_content)
    console.print(f"[green]✓[/green] Backup saved: [bold]{out_file}[/bold]")
    console.print(f"  {len(configs)} container(s) backed up")
    console.print(f"  [dim]Restore with:[/dim] dam --import-file {out_file}")


def _cmd_snapshot(config) -> None:
    """Take a manual snapshot of current container state."""
    platform, settings, _ = _load_context(config)
    from dam.core.inspector import Inspector
    from dam.core.snapshot import SnapshotManager
    inspector = Inspector(platform)
    configs = inspector.inspect_all(settings_containers=settings.get("containers", {}) or {})
    snap_dir = Path(__file__).parent.parent / "snapshots"
    mgr = SnapshotManager(snapshot_dir=snap_dir)
    path = mgr.save(configs, platform, label="cli-manual")
    console.print(f"[green]✓[/green] Snapshot saved: {path.name}")


def _cmd_list_snapshots(config) -> None:
    """List saved snapshots."""
    from dam.core.snapshot import SnapshotManager
    snap_dir = Path(__file__).parent.parent / "snapshots"
    mgr = SnapshotManager(snapshot_dir=snap_dir)
    snaps = mgr.list_snapshots()
    if not snaps:
        console.print("[dim]No snapshots found.[/dim]")
        return
    from rich.table import Table
    t = Table("N", "Filename", "Size", show_header=True, header_style="bold")
    for i, s in enumerate(snaps):
        t.add_row(str(i), s.name, f"{s.stat().st_size // 1024} KB")
    console.print(t)


def _cmd_rollback(config, index: int = 0, yes: bool = False) -> None:
    """Rollback containers to a saved snapshot."""
    platform, settings, _ = _load_context(config)
    from dam.core.snapshot import SnapshotManager
    from dam.core.updater import Updater
    snap_dir = Path(__file__).parent.parent / "snapshots"
    mgr = SnapshotManager(snapshot_dir=snap_dir)
    snaps = mgr.list_snapshots()
    if not snaps or index >= len(snaps):
        console.print(f"[red]Snapshot {index} not found.[/red]")
        return
    snap_name = snaps[index].name
    if not yes:
        console.print(f"[yellow]Roll back ALL containers to snapshot: {snap_name}?[/yellow]")
        if not click.confirm("Proceed?"):
            return
    result = mgr.load(snaps[index])
    if not result:
        console.print("[red]Could not load snapshot.[/red]")
        return
    _, snap_configs = result
    updater = Updater(platform=platform, dry_run=False,
                      recreate_delay=settings.get("dam", {}).get("recreate_delay", 5))
    for cfg in snap_configs:
        try:
            updater._recreate(cfg, cfg.image)
            console.print(f"[green]✓[/green] {cfg.name}")
        except Exception as e:
            console.print(f"[red]✗[/red] {cfg.name}: {e}")


def _cmd_images(config) -> None:
    """List all Docker images with status."""
    platform, _, _ = _load_context(config)
    import docker
    client = docker.from_env()
    in_use_ids = set()
    in_use_tags = set()
    for c in client.containers.list(all=True):
        try:
            in_use_ids.add(c.attrs.get("Image", ""))
            cfg_img = c.attrs.get("Config", {}).get("Image", "")
            if ":" not in cfg_img.split("/")[-1]:
                cfg_img += ":latest"
            in_use_tags.add(cfg_img)
        except Exception:
            pass
    from rich.table import Table
    t = Table("Image", "ID", "Size", "Status", show_header=True, header_style="bold")
    for img in client.images.list(all=False):
        tags = img.tags or ["<none>:<none>"]
        in_use = img.id in in_use_ids or any(tg in in_use_tags for tg in tags)
        dangling = not img.tags
        size = f"{img.attrs.get('Size', 0) // 1024 // 1024} MB"
        status = "in use" if in_use else ("dangling" if dangling else "unused")
        style = "green" if in_use else ("dim" if dangling else "yellow")
        t.add_row(tags[0], img.short_id, size, f"[{style}]{status}[/{style}]")
    console.print(t)


def _cmd_clone(config, source: str, new_name: str = None, new_ip: str = None,
               new_mac: str = None, dry_run: bool = False, yes: bool = False) -> None:
    """Clone a container with optional overrides."""
    platform, settings, _ = _load_context(config)
    if not new_name:
        new_name = click.prompt("New container name")
    from dam.core.inspector import Inspector, generate_mac
    from dam.core.updater import _build_run_kwargs
    import docker
    import copy
    inspector = Inspector(platform)
    all_cfgs = inspector.inspect_all(settings_containers=settings.get("containers", {}) or {})
    src_cfg = next((c for c in all_cfgs if c.name == source), None)
    if not src_cfg:
        console.print(f"[red]Container '{source}' not found.[/red]")
        return
    cfg = copy.deepcopy(src_cfg)
    cfg.name = new_name
    if new_ip and cfg.networks:
        for net in cfg.networks:
            if net.is_static:
                net.ip_address = new_ip
    cfg.mac_address = new_mac if new_mac and new_mac != "auto" else generate_mac()
    console.print(f"Source:   [cyan]{source}[/cyan]")
    console.print(f"Clone:    [cyan]{new_name}[/cyan]")
    console.print(f"MAC:      [dim]{cfg.mac_address}[/dim]")
    if new_ip:
        console.print(f"IP:       [dim]{new_ip}[/dim]")
    if dry_run:
        console.print("[dim]Dry run — no changes made.[/dim]")
        return
    if not yes and not click.confirm("Create clone?"):
        return
    try:
        client = docker.from_env()
        run_kwargs = _build_run_kwargs(cfg)
        run_kwargs["name"] = new_name
        run_kwargs["detach"] = True
        container = client.containers.run(**run_kwargs)
        console.print(f"[green]✓[/green] Clone created: {new_name} ({container.short_id})")
    except Exception as e:
        console.print(f"[red]Clone failed:[/red] {e}")


def _cmd_history(config) -> None:
    """Show update run history."""
    cfg_path = Path(config) if config else Path("config/settings.yaml")
    history_file = cfg_path.parent / ".update_history.json"
    if not history_file.exists():
        console.print("[dim]No update history found.[/dim]")
        return
    import json
    history = json.loads(history_file.read_text())
    for run in history[:10]:
        updated = run.get("updated", 0)
        failed = run.get("failed", 0)
        ts = run.get("timestamp", "")
        color = "green" if failed == 0 else "yellow"
        console.print(
            f"[{color}]{ts}[/{color}] — {updated} updated, {failed} failed, "
            f"{run.get('skipped', 0)} unchanged"
        )
        for r in run.get("results", []):
            if r.get("status") != "skipped":
                status_color = "green" if r["status"] == "updated" else "red"
                console.print(f"  [{status_color}]{r['name']}[/{status_color}]: {r['status']}")


def _cmd_approvals(config) -> None:
    """List pending update approvals."""
    cfg_path = Path(config) if config else Path("config/settings.yaml")
    from dam.core.approval import ApprovalQueue
    queue = ApprovalQueue(cfg_path.parent / ".approval_queue.json")
    pending = queue.get_pending()
    if not pending:
        console.print("[green]✓[/green] No pending approvals.")
        return
    from rich.table import Table
    t = Table("Container", "Image", "Detected", "Status", show_header=True, header_style="bold")
    for item in queue.get_all():
        color = {"pending": "yellow", "approved": "green",
                 "rejected": "red", "applied": "dim"}.get(item.status, "white")
        t.add_row(item.container_name, item.image,
                  item.detected_at[:16], f"[{color}]{item.status}[/{color}]")
    console.print(t)


def _cmd_approve(config, container_name: str) -> None:
    """Approve a pending update."""
    cfg_path = Path(config) if config else Path("config/settings.yaml")
    from dam.core.approval import ApprovalQueue
    queue = ApprovalQueue(cfg_path.parent / ".approval_queue.json")
    item = queue.approve(container_name)
    if item:
        console.print(f"[green]✓[/green] Approved update for {container_name}")
    else:
        console.print(f"[red]No pending update found for '{container_name}'[/red]")


def _cmd_reject(config, container_name: str) -> None:
    """Reject a pending update."""
    cfg_path = Path(config) if config else Path("config/settings.yaml")
    from dam.core.approval import ApprovalQueue
    queue = ApprovalQueue(cfg_path.parent / ".approval_queue.json")
    item = queue.reject(container_name)
    if item:
        console.print(f"[yellow]✗[/yellow] Rejected update for {container_name}")
    else:
        console.print(f"[red]No pending update found for '{container_name}'[/red]")


def _cmd_network_health(config) -> None:
    """Check for containers with network issues."""
    import docker
    client = docker.from_env()
    found = False
    for c in client.containers.list(all=True):
        try:
            hc = c.attrs.get("HostConfig", {})
            nets = c.attrs.get("NetworkSettings", {}).get("Networks", {})
            mode = hc.get("NetworkMode", "")
            real_nets = {k: v for k, v in nets.items() if k != "none"}
            if mode == "none" and real_nets:
                net = next(iter(real_nets))
                ip = (real_nets[net].get("IPAMConfig") or {}).get("IPv4Address", "")
                console.print(
                    f"[yellow]⚠[/yellow] {c.name}: started on 'none', "
                    f"reconnected to {net}" + (f" ({ip})" if ip else "") +
                    " — recreate needed"
                )
                found = True
            elif mode == "none" and not real_nets:
                console.print(f"[red]✗[/red] {c.name}: stuck on 'none' network")
                found = True
        except Exception:
            pass
    if not found:
        console.print("[green]✓[/green] All containers have correct network config.")


def _cmd_network_fix(config, container_name: str, yes: bool = False) -> None:
    """Recreate a container with correct network from startup."""
    platform, settings, _ = _load_context(config)
    from dam.core.inspector import Inspector
    from dam.core.updater import Updater
    inspector = Inspector(platform)
    all_cfgs = inspector.inspect_all(settings_containers=settings.get("containers", {}) or {})
    cfg = next((c for c in all_cfgs if c.name == container_name), None)
    if not cfg:
        console.print(f"[red]Container '{container_name}' not found.[/red]")
        return
    if not yes and not click.confirm(
            f"Recreate {container_name} with network {cfg.network_mode}?"):
        return
    updater = Updater(platform=platform, dry_run=False,
                      recreate_delay=settings.get("dam", {}).get("recreate_delay", 5))
    try:
        updater._recreate(cfg, cfg.image)
        console.print(
            f"[green]✓[/green] {container_name} recreated on {cfg.network_mode}"
            + (f" ({cfg.primary_ip()})" if cfg.primary_ip() else "")
        )
    except Exception as e:
        console.print(f"[red]Fix failed:[/red] {e}")


def _cmd_notify_test(config) -> None:
    """Send a test notification."""
    _, settings, _ = _load_context(config)
    from dam.core.notifier import Notifier, NotificationConfig
    notif = Notifier(NotificationConfig.from_settings(settings))
    if not notif.cfg.enabled:
        console.print("[yellow]Notifications are disabled in settings.[/yellow]")
        return
    ok = notif.test()
    if ok:
        console.print("[green]✓[/green] Test notification sent successfully.")
    else:
        console.print("[red]✗[/red] Test notification failed — check your config.")


def _cmd_set_policy(config, policy_spec: str) -> None:
    """Set update policy for a container. Format: name:policy"""
    from dam.core.approval import POLICIES
    import yaml as _yaml
    if ":" not in policy_spec:
        console.print("[red]Format: --policy container_name:policy[/red]")
        console.print(f"Valid policies: {', '.join(POLICIES)}")
        return
    name, policy = policy_spec.split(":", 1)
    if policy not in POLICIES:
        console.print(f"[red]Invalid policy '{policy}'.[/red] Valid: {', '.join(POLICIES)}")
        return
    cfg_path = Path(config) if config else Path("config/settings.yaml")
    if cfg_path.exists():
        settings = _yaml.safe_load(cfg_path.read_text()) or {}
    else:
        settings = {}
    if "containers" not in settings:
        settings["containers"] = {}
    if name not in settings["containers"]:
        settings["containers"][name] = {}
    settings["containers"][name]["update_policy"] = policy
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(_yaml.dump(settings, default_flow_style=False))
    console.print(f"[green]✓[/green] {name}: update_policy = {policy}")


def main():
    cli(obj={})


if __name__ == "__main__":
    main()
