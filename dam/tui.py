"""
dam/tui.py

Rich terminal UI for Docker Automation Manager.
Provides an interactive menu-driven interface over all core modules.

Layout:
  - Header bar: platform info, Docker version, snapshot count
  - Main menu: Status / Update / Drift / Prune / Settings / Quit
  - Each action renders its own panel with live progress or tables

Dependencies: rich, prompt_toolkit
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from rich.align import Align
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich import box

from dam import __version__
from dam.core.deprecation import DeprecationChecker, DeprecationStatus, DeprecationSeverity
from dam.core.drift import DriftDetector, DriftReport
from dam.core.exporter import Exporter, FORMATS
from dam.core.importer import Importer, ImportStatus
from dam.core.inspector import ContainerConfig, Inspector
from dam.core.pruner import Pruner
from dam.core.snapshot import SnapshotManager
from dam.core.updater import Updater, UpdateResult, UpdateStatus
from dam.platform.base import BasePlatform
from dam.platform.detector import detect_platform


# ------------------------------------------------------------
# Console singleton — used throughout
# ------------------------------------------------------------

console = Console()


# ------------------------------------------------------------
# Color / style constants
# ------------------------------------------------------------

SEVERITY_COLORS = {
    "critical": "bold red",
    "high":     "red",
    "medium":   "yellow",
    "low":      "cyan",
    "info":     "dim",
}

STATUS_COLORS = {
    "running":     "bold green",
    "healthy":     "bold green",
    "exited":      "red",
    "paused":      "yellow",
    "restarting":  "yellow",
    "dead":        "bold red",
    "unknown":     "dim",
}

UPDATE_STATUS_COLORS = {
    UpdateStatus.UPDATED:  "bold green",
    UpdateStatus.SKIPPED:  "dim",
    UpdateStatus.PINNED:   "cyan",
    UpdateStatus.FAILED:   "bold red",
    UpdateStatus.DRY_RUN:  "yellow",
}

UPDATE_STATUS_ICONS = {
    UpdateStatus.UPDATED:  "✓",
    UpdateStatus.SKIPPED:  "–",
    UpdateStatus.PINNED:   "📌",
    UpdateStatus.FAILED:   "✗",
    UpdateStatus.DRY_RUN:  "◎",
}


# ------------------------------------------------------------
# Header
# ------------------------------------------------------------

def render_header(platform: BasePlatform, snapshot_count: int) -> Panel:
    """Render the top header bar."""
    grid = Table.grid(expand=True)
    grid.add_column(justify="left")
    grid.add_column(justify="center")
    grid.add_column(justify="right")

    grid.add_row(
        Text(f"  🐳 Docker Automation Manager v{__version__}", style="bold cyan"),
        Text(f"Platform: {platform.name}", style="bold white"),
        Text(f"Snapshots: {snapshot_count}  ", style="dim"),
    )
    return Panel(grid, style="on grey11", padding=(0, 0))


# ------------------------------------------------------------
# Main menu
# ------------------------------------------------------------

MENU_OPTIONS = [
    ("1", "Status",   "Show all containers with current state"),
    ("2", "Update",   "Pull latest images and recreate changed containers"),
    ("3", "Drift",    "Compare current state against last snapshot"),
    ("4", "Prune",    "Remove unused images"),
    ("5", "Snapshots","Browse and manage saved snapshots"),
    ("6", "Settings", "View platform info and configuration"),
    ("7", "Export",   "Export container configs (dam-yaml / docker-run / compose)"),
    ("8", "Import",   "Import and recreate containers from a DAM YAML file"),
    ("9", "EOL Check","Check for deprecated or archived images"),
    ("q", "Quit",     "Exit DAM"),
]


def render_menu() -> Panel:
    """Render the main navigation menu."""
    table = Table(
        box=box.SIMPLE,
        show_header=False,
        padding=(0, 2),
        expand=False,
    )
    table.add_column(style="bold cyan", width=4)
    table.add_column(style="bold white", width=12)
    table.add_column(style="dim")

    for key, label, desc in MENU_OPTIONS:
        table.add_row(Text(f"[{key}]", no_wrap=True), label, desc)

    return Panel(
        Align.center(table),
        title="[bold cyan]Main Menu[/bold cyan]",
        border_style="cyan",
        padding=(1, 4),
    )


# ------------------------------------------------------------
# Status view
# ------------------------------------------------------------

def render_status_table(configs: list[ContainerConfig]) -> Table:
    """Render a rich table of all containers and their current config."""
    table = Table(
        title="Container Status",
        box=box.ROUNDED,
        show_lines=False,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("Container",      style="bold white",  min_width=16)
    table.add_column("Image",          style="cyan",        min_width=30, overflow="fold")
    table.add_column("Status",         min_width=10)
    table.add_column("IP / Network",   min_width=22)
    table.add_column("Restart",        min_width=14)
    table.add_column("Strategy",       min_width=8)
    table.add_column("Volumes",        min_width=8)

    for cfg in sorted(configs, key=lambda c: c.name):
        status_color = STATUS_COLORS.get(cfg.status, "white")
        status_text  = Text(cfg.status, style=status_color)

        ip = cfg.primary_ip()
        net = cfg.primary_network() or cfg.network_mode
        if ip:
            net_text = Text(f"{ip}\n", style="green") + Text(net, style="dim")
        else:
            net_text = Text(net, style="dim")

        strategy_color = {
            "latest": "green", "stable": "cyan", "pinned": "yellow"
        }.get(cfg.version_strategy, "white")

        table.add_row(
            cfg.name,
            cfg.image,
            status_text,
            net_text,
            cfg.restart_policy,
            Text(cfg.version_strategy, style=strategy_color),
            str(len(cfg.binds)),
        )

    return table


# ------------------------------------------------------------
# Update view
# ------------------------------------------------------------

def render_update_results(results: list[UpdateResult]) -> Table:
    """Render a summary table after an update cycle."""
    table = Table(
        title="Update Results",
        box=box.ROUNDED,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("Container",  style="bold white", min_width=16)
    table.add_column("Result",     min_width=10)
    table.add_column("Old Image",  style="dim",  min_width=19, overflow="fold")
    table.add_column("New Image",  style="cyan", min_width=19, overflow="fold")
    table.add_column("Duration",   min_width=8)
    table.add_column("Error",      style="red",  min_width=20, overflow="fold")

    for r in results:
        color = UPDATE_STATUS_COLORS.get(r.status, "white")
        icon  = UPDATE_STATUS_ICONS.get(r.status, "?")
        status_text = Text(f"{icon} {r.status.value}", style=color)

        old_id = r.old_image_id[:19] if r.old_image_id else "—"
        new_id = r.new_image_id[:19] if r.new_image_id else "—"
        duration = f"{r.duration_seconds:.1f}s"

        table.add_row(
            r.container_name,
            status_text,
            old_id,
            new_id,
            duration,
            r.error or "",
        )

    return table


def render_update_summary(summary: dict) -> Panel:
    """Render a compact summary panel after updates."""
    grid = Table.grid(padding=(0, 3))
    grid.add_column(justify="center")
    grid.add_column(justify="center")
    grid.add_column(justify="center")
    grid.add_column(justify="center")
    grid.add_column(justify="center")

    grid.add_row(
        Text(f"✓ {summary['updated']} updated",  style="bold green"),
        Text(f"– {summary['skipped']} skipped",  style="dim"),
        Text(f"📌 {summary['pinned']} pinned",    style="cyan"),
        Text(f"◎ {summary['dry_run']} dry-run",  style="yellow"),
        Text(f"✗ {summary['failed']} failed",    style="bold red"),
    )

    return Panel(grid, title="Summary", border_style="green" if summary["failed"] == 0 else "red")


# ------------------------------------------------------------
# Drift view
# ------------------------------------------------------------

def render_drift_report(report: DriftReport) -> Table:
    """Render drift items as a rich table."""
    if not report.has_drift:
        return Table()  # empty — caller handles the no-drift case

    table = Table(
        title=f"Drift: {report.snapshot_a_label} → {report.snapshot_b_label}",
        box=box.ROUNDED,
        header_style="bold cyan",
        expand=True,
        show_lines=True,
    )
    table.add_column("Severity",   min_width=10)
    table.add_column("Container",  style="bold white", min_width=16)
    table.add_column("Field",      style="cyan",       min_width=24)
    table.add_column("Description",                    min_width=30)
    table.add_column("Was",        style="dim red",    min_width=20, overflow="fold")
    table.add_column("Now",        style="green",      min_width=20, overflow="fold")

    for item in report.sorted_by_severity():
        sev_color = SEVERITY_COLORS.get(item.severity.value, "white")
        table.add_row(
            Text(item.severity.value.upper(), style=sev_color),
            item.container_name,
            item.field,
            item.description,
            item.old_value or "—",
            item.new_value or "—",
        )

    return table


def render_drift_summary(report: DriftReport) -> Panel:
    """Compact drift summary panel."""
    summary = report.summary()
    grid = Table.grid(padding=(0, 3))
    grid.add_column(justify="center")
    grid.add_column(justify="center")
    grid.add_column(justify="center")
    grid.add_column(justify="center")
    grid.add_column(justify="center")
    grid.add_column(justify="center")

    grid.add_row(
        Text(f"Containers affected: {summary['containers_affected']}", style="bold white"),
        Text(f"🔴 {summary['critical']} critical", style="bold red"),
        Text(f"🟠 {summary['high']} high",         style="red"),
        Text(f"🟡 {summary['medium']} medium",      style="yellow"),
        Text(f"🔵 {summary['low']} low",            style="cyan"),
        Text(f"⚪ {summary['info']} info",          style="dim"),
    )

    border = "red" if summary["critical"] or summary["high"] else \
             "yellow" if summary["medium"] else "cyan"
    return Panel(grid, title="Drift Summary", border_style=border)


# ------------------------------------------------------------
# Prune view
# ------------------------------------------------------------

def render_prune_candidates(candidates: dict) -> Panel:
    """Show prune preview before confirming."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(justify="left", style="dim")
    grid.add_column(justify="right")

    grid.add_row("Dangling images:",    str(len(candidates.get("dangling", []))))
    grid.add_row("Replaced images:",    str(len(candidates.get("replaced", []))))
    grid.add_row("Unreferenced images:",str(len(candidates.get("unreferenced", []))))
    grid.add_row(Rule(), Rule())
    grid.add_row(
        Text("Total candidates:", style="bold"),
        Text(str(candidates.get("total_candidates", 0)), style="bold yellow"),
    )
    grid.add_row(
        Text("Estimated space freed:", style="bold"),
        Text(candidates.get("estimated_space_human", "0 MB"), style="bold green"),
    )

    return Panel(grid, title="Prune Preview", border_style="yellow")


def render_prune_result(result) -> Panel:
    """Show result after prune."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(justify="left", style="dim")
    grid.add_column(justify="right")

    grid.add_row("Images removed:", Text(str(len(result.images_removed)), style="bold green"))
    grid.add_row("Space reclaimed:", Text(result.space_reclaimed_human, style="bold green"))

    if result.errors:
        grid.add_row("Errors:", Text(str(len(result.errors)), style="bold red"))

    border = "red" if result.errors else "green"
    return Panel(grid, title="Prune Complete", border_style=border)


# ------------------------------------------------------------
# Snapshots view
# ------------------------------------------------------------

def render_snapshots_table(snapshot_manager: SnapshotManager) -> Table:
    """List all saved snapshots."""
    snapshots = snapshot_manager.list_snapshots()

    table = Table(
        title=f"Saved Snapshots ({len(snapshots)})",
        box=box.ROUNDED,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("#",          style="dim",         width=4)
    table.add_column("Filename",   style="cyan",        min_width=30)
    table.add_column("Size",       justify="right",     min_width=8)
    table.add_column("Label",      style="dim",         min_width=12)

    for i, path in enumerate(snapshots, 1):
        size_kb = path.stat().st_size / 1024
        # Extract label from filename if present (YYYY-MM-DD_HH-MM-SS_label.yaml)
        parts = path.stem.split("_", 3)
        label = parts[3] if len(parts) > 3 else ""
        table.add_row(
            str(i),
            path.name,
            f"{size_kb:.1f} KB",
            label,
        )

    return table


# ------------------------------------------------------------
# Platform / settings view
# ------------------------------------------------------------

def render_platform_info(platform: BasePlatform) -> Panel:
    """Render platform detection results."""
    info = platform.describe()

    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", justify="right")
    table.add_column(style="white")

    table.add_row("Platform:",        info["platform"])
    table.add_row("Data root:",       info["data_root"])
    table.add_row("Log root:",        info["log_root"])
    table.add_row("Systemd:",         "yes" if info["systemd"] else "no")
    table.add_row("Cron path:",       info["cron_path"])

    return Panel(table, title="Platform Info", border_style="cyan")


def render_settings(settings: dict) -> Panel:
    """Render current settings.yaml content."""
    dam_cfg = settings.get("dam", {})
    daemon_cfg = settings.get("daemon", {})
    containers_cfg = settings.get("containers", {}) or {}

    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", justify="right")
    table.add_column(style="white")

    table.add_row("Snapshot retention:", str(dam_cfg.get("snapshot_retention", 10)))
    table.add_row("Log retention:",      f"{dam_cfg.get('log_retention_days', 30)} days")
    table.add_row("Auto prune:",         "yes" if dam_cfg.get("auto_prune", True) else "no")
    table.add_row("Recreate delay:",     f"{dam_cfg.get('recreate_delay', 5)}s")
    table.add_row("Daemon schedule:",    daemon_cfg.get("schedule", "0 2 1 * *"))
    table.add_row("Pinned containers:",  str(len(containers_cfg)))

    return Panel(table, title="Settings (config/settings.yaml)", border_style="cyan")


# ------------------------------------------------------------
# Progress helpers
# ------------------------------------------------------------

def make_update_progress() -> Progress:
    """Create a progress bar configured for update operations."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    )


def make_pull_progress() -> Progress:
    """Simpler spinner progress for pull operations."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[cyan]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    )


# ------------------------------------------------------------
# Main TUI class
# ------------------------------------------------------------

class DAMTui:
    """
    Interactive terminal UI for Docker Automation Manager.
    Orchestrates all core modules and renders results with Rich.
    """

    def __init__(self, config_path: Optional[Path] = None):
        self.platform = detect_platform()
        self.config_path = config_path or Path(__file__).parent.parent / "config" / "settings.yaml"
        self.settings = self._load_settings()

        dam_cfg = self.settings.get("dam", {})
        self.snapshot_manager = SnapshotManager(
            retention=dam_cfg.get("snapshot_retention", 10)
        )

        self._last_update_results: list[UpdateResult] = []
        self._last_configs: list[ContainerConfig] = []

    # ------------------------------------------------------------
    # Settings loader
    # ------------------------------------------------------------

    def _load_settings(self) -> dict:
        try:
            with open(self.config_path) as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            return {}
        except Exception as e:
            console.print(f"[yellow]Warning: Could not load settings: {e}[/yellow]")
            return {}

    # ------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------

    def run(self) -> None:
        """Main event loop."""
        console.clear()
        self._print_header()

        while True:
            console.print()
            console.print(render_menu())
            console.print()

            choice = Prompt.ask(
                "[bold cyan]Select action[/bold cyan]",
                choices=["1", "2", "3", "4", "5", "6", "7", "8", "9", "q"],
                default="1",
            ).strip().lower()

            console.print()

            if choice == "1":
                self._action_status()
            elif choice == "2":
                self._action_update()
            elif choice == "3":
                self._action_drift()
            elif choice == "4":
                self._action_prune()
            elif choice == "5":
                self._action_snapshots()
            elif choice == "6":
                self._action_settings()
            elif choice == "7":
                self._action_export()
            elif choice == "8":
                self._action_import()
            elif choice == "9":
                self._action_eol_check()
            elif choice == "q":
                console.print("[bold cyan]Goodbye.[/bold cyan]")
                break

    # ------------------------------------------------------------
    # Header
    # ------------------------------------------------------------

    def _print_header(self) -> None:
        count = self.snapshot_manager.snapshot_count()
        console.print(render_header(self.platform, count))
        console.print()

    # ------------------------------------------------------------
    # Action: Status
    # ------------------------------------------------------------

    def _action_status(self) -> None:
        console.print(Rule("[bold cyan]Container Status[/bold cyan]"))

        with console.status("[cyan]Inspecting containers...[/cyan]"):
            try:
                inspector = self._make_inspector()
                configs = inspector.inspect_all(
                    include_stopped=True,
                    settings_containers=self.settings.get("containers", {}) or {},
                )
                self._last_configs = configs
            except RuntimeError as e:
                console.print(f"[bold red]Error:[/bold red] {e}")
                return

        if not configs:
            console.print("[yellow]No containers found.[/yellow]")
            return

        console.print(render_status_table(configs))
        console.print(f"\n[dim]Total: {len(configs)} containers[/dim]")

        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="")

    # ------------------------------------------------------------
    # Action: Update
    # ------------------------------------------------------------

    def _action_update(self) -> None:
        console.print(Rule("[bold cyan]Update Containers[/bold cyan]"))

        # --- Options ---
        dry_run = Confirm.ask("Dry run? (no changes will be made)", default=False)
        console.print()

        # --- Inspect ---
        with console.status("[cyan]Inspecting containers...[/cyan]"):
            try:
                inspector = self._make_inspector()
                configs = inspector.inspect_all(
                    settings_containers=self.settings.get("containers", {}) or {}
                )
                self._last_configs = configs
            except RuntimeError as e:
                console.print(f"[bold red]Error:[/bold red] {e}")
                return

        if not configs:
            console.print("[yellow]No containers found.[/yellow]")
            return

        # --- Snapshot before update ---
        console.print("[dim]Taking pre-update snapshot...[/dim]")
        self.snapshot_manager.save(configs, self.platform, label="pre-update")

        # --- Confirm ---
        console.print(f"\nFound [bold]{len(configs)}[/bold] containers to check:")
        for cfg in sorted(configs, key=lambda c: c.name):
            pin_marker = " [yellow]📌 pinned[/yellow]" if cfg.version_strategy == "pinned" else ""
            console.print(f"  [cyan]•[/cyan] {cfg.name}  [dim]({cfg.image})[/dim]{pin_marker}")

        console.print()
        if not Confirm.ask("Proceed with update check?", default=True):
            console.print("[dim]Update cancelled.[/dim]")
            return

        # --- Run update with live progress ---
        dam_cfg = self.settings.get("dam", {})
        delay = dam_cfg.get("recreate_delay", 5)
        results: list[UpdateResult] = []
        log_lines: list[str] = []

        with make_update_progress() as progress:
            task = progress.add_task("Updating containers...", total=len(configs))

            def on_progress(name: str, msg: str) -> None:
                progress.update(task, description=f"[cyan]{name}[/cyan]: {msg}")
                log_lines.append(msg)

            updater = Updater(
                platform=self.platform,
                dry_run=dry_run,
                recreate_delay=delay,
                progress_callback=on_progress,
            )

            for cfg in configs:
                result = updater.update_one(cfg)
                results.append(result)
                progress.advance(task)

        self._last_update_results = results

        # --- Results table ---
        console.print()
        console.print(render_update_results(results))
        console.print()
        summary = Updater.summarize(results)
        console.print(render_update_summary(summary))

        # --- Post-update snapshot ---
        if not dry_run and summary["updated"] > 0:
            console.print("\n[dim]Taking post-update snapshot...[/dim]")
            try:
                post_configs = inspector.inspect_all(
                    settings_containers=self.settings.get("containers", {}) or {}
                )
                self.snapshot_manager.save(post_configs, self.platform, label="post-update")
            except Exception:
                pass

        # --- Auto-prune prompt ---
        auto_prune = dam_cfg.get("auto_prune", True)
        if not dry_run and summary["updated"] > 0:
            if auto_prune or Confirm.ask("\nPrune unused images?", default=True):
                self._run_prune(update_results=results)

        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="")

    # ------------------------------------------------------------
    # Action: Drift
    # ------------------------------------------------------------

    def _action_drift(self) -> None:
        console.print(Rule("[bold cyan]Drift Detection[/bold cyan]"))

        # Check snapshots available
        snapshots = self.snapshot_manager.list_snapshots()
        if not snapshots:
            console.print("[yellow]No snapshots found. Run an update first to create a baseline.[/yellow]")
            Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="")
            return

        # --- Choose comparison mode ---
        console.print("Compare against:")
        console.print("  [cyan][1][/cyan] Last snapshot vs live containers")
        console.print("  [cyan][2][/cyan] Last snapshot vs previous snapshot")
        console.print()

        mode = Prompt.ask("Select", choices=["1", "2"], default="1")
        console.print()

        with console.status("[cyan]Running drift analysis...[/cyan]"):
            try:
                # Load last snapshot
                result = self.snapshot_manager.load_latest()
                if not result:
                    console.print("[red]Could not load latest snapshot.[/red]")
                    return
                snap_meta, snap_configs = result

                if mode == "1":
                    # Live comparison
                    inspector = self._make_inspector()
                    live_configs = inspector.inspect_all(
                        settings_containers=self.settings.get("containers", {}) or {}
                    )
                    label_a = f"snapshot ({snap_meta['captured_at']})"
                    label_b = "live"
                    configs_b = live_configs

                else:
                    # Snapshot vs previous snapshot
                    prev = self.snapshot_manager.load_previous(skip=1)
                    if not prev:
                        console.print("[yellow]Only one snapshot exists. Need at least two for comparison.[/yellow]")
                        return
                    prev_meta, prev_configs = prev
                    label_a = f"snapshot ({prev_meta['captured_at']})"
                    label_b = f"snapshot ({snap_meta['captured_at']})"
                    snap_configs, configs_b = prev_configs, snap_configs

                detector = DriftDetector()
                report = detector.compare(snap_configs, configs_b, label_a, label_b)

            except Exception as e:
                console.print(f"[bold red]Error during drift analysis:[/bold red] {e}")
                return

        # --- Render ---
        if not report.has_drift:
            console.print(Panel(
                Align.center(Text("✓ No drift detected — configurations match", style="bold green")),
                border_style="green",
                padding=(1, 4),
            ))
        else:
            console.print(render_drift_summary(report))
            console.print()
            console.print(render_drift_report(report))

        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="")

    # ------------------------------------------------------------
    # Action: Prune
    # ------------------------------------------------------------

    def _action_prune(self) -> None:
        console.print(Rule("[bold cyan]Prune Unused Images[/bold cyan]"))
        self._run_prune()
        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="")

    def _run_prune(self, update_results: Optional[list[UpdateResult]] = None) -> None:
        """Run prune cycle — shared between manual prune and post-update auto-prune."""
        remove_all = Confirm.ask(
            "Remove all unreferenced images? (equivalent to `docker image prune -a`)",
            default=False,
        )
        console.print()

        with console.status("[cyan]Scanning images...[/cyan]"):
            try:
                pruner = Pruner(dry_run=True, remove_unreferenced=remove_all)
                candidates = pruner.list_candidates(update_results)
            except RuntimeError as e:
                console.print(f"[bold red]Error:[/bold red] {e}")
                return

        if candidates["total_candidates"] == 0:
            console.print(Panel(
                Align.center(Text("✓ Nothing to prune", style="bold green")),
                border_style="green",
            ))
            return

        console.print(render_prune_candidates(candidates))
        console.print()

        if not Confirm.ask("Proceed with prune?", default=True):
            console.print("[dim]Prune cancelled.[/dim]")
            return

        with console.status("[cyan]Pruning images...[/cyan]"):
            try:
                pruner = Pruner(dry_run=False, remove_unreferenced=remove_all)
                result = pruner.prune(update_results)
            except RuntimeError as e:
                console.print(f"[bold red]Error:[/bold red] {e}")
                return

        console.print()
        console.print(render_prune_result(result))

        if result.errors:
            console.print("\n[bold red]Errors:[/bold red]")
            for err in result.errors:
                console.print(f"  [red]•[/red] {err}")

    # ------------------------------------------------------------
    # Action: Snapshots
    # ------------------------------------------------------------

    def _action_snapshots(self) -> None:
        console.print(Rule("[bold cyan]Snapshot Manager[/bold cyan]"))

        snapshots = self.snapshot_manager.list_snapshots()
        if not snapshots:
            console.print("[yellow]No snapshots found.[/yellow]")
            Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="")
            return

        console.print(render_snapshots_table(self.snapshot_manager))
        console.print()

        # --- Show detail of a snapshot ---
        view = Confirm.ask("View a snapshot's container list?", default=False)
        if view:
            idx_str = Prompt.ask(
                f"Enter snapshot number [1-{len(snapshots)}]",
                default="1",
            )
            try:
                idx = int(idx_str) - 1
                path = snapshots[idx]
                result = self.snapshot_manager.load(path)
                if result:
                    meta, cfgs = result
                    console.print(f"\n[bold cyan]Snapshot:[/bold cyan] {path.name}")
                    console.print(f"[dim]Captured: {meta['captured_at']}  Platform: {meta['platform']}[/dim]\n")
                    console.print(render_status_table(cfgs))
            except (ValueError, IndexError):
                console.print("[yellow]Invalid selection.[/yellow]")

        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="")

    # ------------------------------------------------------------
    # Action: Settings
    # ------------------------------------------------------------

    def _action_settings(self) -> None:
        console.print(Rule("[bold cyan]Platform & Settings[/bold cyan]"))
        console.print()

        # Platform side by side with settings
        plat_panel = render_platform_info(self.platform)
        sett_panel = render_settings(self.settings)
        console.print(Columns([plat_panel, sett_panel], equal=True))

        console.print()
        # Docker version info
        try:
            inspector = self._make_inspector()
            ver = inspector.docker_version()
            docker_ver = ver.get("Version", "unknown")
            api_ver    = ver.get("ApiVersion", "unknown")
            console.print(Panel(
                f"Docker Engine: [cyan]{docker_ver}[/cyan]   API: [dim]{api_ver}[/dim]",
                title="Docker Info",
                border_style="dim",
            ))
        except Exception:
            pass

        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="")


    # ------------------------------------------------------------
    # Action: Export
    # ------------------------------------------------------------

    def _action_export(self) -> None:
        console.print(Rule("[bold cyan]Export Containers[/bold cyan]"))

        # Inspect containers
        with console.status("[cyan]Inspecting containers...[/cyan]"):
            try:
                inspector = self._make_inspector()
                configs = inspector.inspect_all(
                    settings_containers=self.settings.get("containers", {}) or {}
                )
            except RuntimeError as e:
                console.print(f"[bold red]Error:[/bold red] {e}")
                return

        if not configs:
            console.print("[yellow]No containers found.[/yellow]")
            Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="")
            return

        # --- Select containers ---
        console.print("\nAvailable containers:")
        for i, cfg in enumerate(sorted(configs, key=lambda c: c.name), 1):
            console.print(f"  [cyan]{i}[/cyan]. {cfg.name}  [dim]({cfg.image})[/dim]")

        console.print()
        selection = Prompt.ask(
            "Select containers [all / comma-separated numbers e.g. 1,3]",
            default="all"
        )

        sorted_configs = sorted(configs, key=lambda c: c.name)
        if selection.strip().lower() == "all":
            selected = sorted_configs
        else:
            try:
                indices = [int(x.strip()) - 1 for x in selection.split(",")]
                selected = [sorted_configs[i] for i in indices if 0 <= i < len(sorted_configs)]
            except (ValueError, IndexError):
                console.print("[red]Invalid selection.[/red]")
                Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="")
                return

        if not selected:
            console.print("[yellow]No containers selected.[/yellow]")
            Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="")
            return

        # --- Select format ---
        console.print()
        console.print("Export format:")
        console.print("  [cyan][1][/cyan] dam-yaml    — DAM import file (recommended for backup/migration)")
        console.print("  [cyan][2][/cyan] docker-run  — Executable shell script (works anywhere without DAM)")
        console.print("  [cyan][3][/cyan] compose     — docker-compose.yml")
        console.print("  [cyan][4][/cyan] All formats")
        console.print()

        fmt_choice = Prompt.ask("Select format", choices=["1", "2", "3", "4"], default="1")
        fmt_map = {"1": "dam-yaml", "2": "docker-run", "3": "compose"}

        # --- Output directory ---
        default_out = str(Path.home() / "dam-exports")
        out_dir_str = Prompt.ask("Output directory", default=default_out)
        out_dir = Path(out_dir_str).expanduser()

        # --- Export ---
        console.print()
        exporter = Exporter()
        try:
            if fmt_choice == "4":
                results = exporter.export_all_formats(selected, out_dir)
                console.print(Panel(
                    "\n".join(
                        f"[cyan]{fmt}[/cyan]  →  {paths[0]}"
                        for fmt, paths in results.items()
                    ),
                    title="[bold green]✓ Exported — All Formats[/bold green]",
                    border_style="green",
                ))
            else:
                fmt = fmt_map[fmt_choice]
                single = len(selected) > 1
                paths = exporter.export(selected, fmt, out_dir, single_file=single)
                console.print(Panel(
                    "\n".join(str(p) for p in paths),
                    title=f"[bold green]✓ Exported — {fmt}[/bold green]",
                    border_style="green",
                ))
        except Exception as e:
            console.print(f"[bold red]Export failed:[/bold red] {e}")

        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="")

    # ------------------------------------------------------------
    # Action: Import
    # ------------------------------------------------------------

    def _action_import(self) -> None:
        console.print(Rule("[bold cyan]Import Containers[/bold cyan]"))

        file_path_str = Prompt.ask("Path to DAM YAML export file")
        file_path = Path(file_path_str).expanduser()

        if not file_path.exists():
            console.print(f"[red]File not found: {file_path}[/red]")
            Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="")
            return

        # Load and preview
        try:
            from dam.core.importer import load_import_file
            meta, configs = load_import_file(file_path)
        except Exception as e:
            console.print(f"[bold red]Error reading file:[/bold red] {e}")
            Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="")
            return

        console.print(f"\n[dim]Exported: {meta.get('exported_at', 'unknown')}  "
                     f"DAM version: {meta.get('dam_version', 'unknown')}[/dim]\n")
        console.print(f"Found [bold]{len(configs)}[/bold] container(s) to import:")
        for cfg in configs:
            console.print(f"  [cyan]•[/cyan] {cfg.name}  [dim]({cfg.image})[/dim]")

        console.print()
        dry_run = Confirm.ask("Dry run first? (recommended)", default=True)
        overwrite = Confirm.ask("Overwrite existing containers with same name?", default=False)
        console.print()

        importer = Importer(self.platform, dry_run=dry_run, overwrite=overwrite)
        results = importer.import_configs(configs)

        # Results table
        table = Table(
            title="Import Results",
            box=box.ROUNDED,
            header_style="bold cyan",
            expand=True,
        )
        table.add_column("Container", style="bold white", min_width=16)
        table.add_column("Result", min_width=10)
        table.add_column("Image", style="dim", min_width=30, overflow="fold")
        table.add_column("Error", style="red", min_width=20, overflow="fold")

        status_colors = {
            ImportStatus.CREATED:  "bold green",
            ImportStatus.SKIPPED:  "dim",
            ImportStatus.DRY_RUN:  "yellow",
            ImportStatus.FAILED:   "bold red",
        }
        status_icons = {
            ImportStatus.CREATED:  "✓",
            ImportStatus.SKIPPED:  "–",
            ImportStatus.DRY_RUN:  "◎",
            ImportStatus.FAILED:   "✗",
        }

        for r in results:
            color = status_colors.get(r.status, "white")
            icon = status_icons.get(r.status, "?")
            table.add_row(
                r.container_name,
                Text(f"{icon} {r.status.value}", style=color),
                r.image,
                r.error or "",
            )

        console.print(table)

        summary = Importer.summarize(results)
        if dry_run and summary["dry_run"] > 0:
            console.print()
            console.print("[yellow]Dry run complete — no containers were created.[/yellow]")
            if Confirm.ask("Run actual import now?", default=False):
                importer2 = Importer(self.platform, dry_run=False, overwrite=overwrite)
                importer2.import_configs(configs)
                console.print("[bold green]✓ Import complete.[/bold green]")

        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="")

    # ------------------------------------------------------------
    # Action: EOL Check
    # ------------------------------------------------------------

    def _action_eol_check(self) -> None:
        console.print(Rule("[bold cyan]Deprecated / EOL Image Check[/bold cyan]"))

        with console.status("[cyan]Inspecting containers...[/cyan]"):
            try:
                inspector = self._make_inspector()
                configs = inspector.inspect_all(
                    settings_containers=self.settings.get("containers", {}) or {}
                )
            except RuntimeError as e:
                console.print(f"[bold red]Error:[/bold red] {e}")
                return

        with console.status("[cyan]Checking deprecation database...[/cyan]"):
            checker = DeprecationChecker()
            results = checker.check_all(configs)

        summary = checker.summary(results)
        warnings = checker.warnings_only(results)

        # Summary panel
        grid = Table.grid(padding=(0, 3))
        grid.add_column(justify="center")
        grid.add_column(justify="center")
        grid.add_column(justify="center")
        grid.add_column(justify="center")
        grid.add_column(justify="center")
        grid.add_row(
            Text(f"✓ {summary['ok']} ok",             style="bold green"),
            Text(f"⚠ {summary['deprecated']} deprecated", style="yellow"),
            Text(f"📦 {summary['archived']} archived",  style="yellow"),
            Text(f"☠ {summary['eol']} EOL",            style="bold red"),
            Text(f"{summary['total_checked']} checked", style="dim"),
        )
        border = "red" if summary["eol"] > 0 else                  "yellow" if (summary["deprecated"] + summary["archived"]) > 0 else "green"
        console.print(Panel(grid, title="Deprecation Check Summary", border_style=border))
        console.print()

        if not warnings:
            console.print(Panel(
                Align.center(Text("✓ All images are current and actively maintained", style="bold green")),
                border_style="green", padding=(1, 4),
            ))
        else:
            # Warnings table
            table = Table(
                title="Deprecated / EOL Images Found",
                box=box.ROUNDED,
                header_style="bold cyan",
                expand=True,
                show_lines=True,
            )
            table.add_column("Container",   style="bold white", min_width=16)
            table.add_column("Image",       style="dim",        min_width=28, overflow="fold")
            table.add_column("Status",      min_width=12)
            table.add_column("Reason",      min_width=30, overflow="fold")
            table.add_column("Alternatives",min_width=24, overflow="fold")

            status_colors = {
                DeprecationStatus.DEPRECATED: "yellow",
                DeprecationStatus.ARCHIVED:   "yellow",
                DeprecationStatus.EOL:        "bold red",
            }
            status_icons = {
                DeprecationStatus.DEPRECATED: "⚠",
                DeprecationStatus.ARCHIVED:   "📦",
                DeprecationStatus.EOL:        "☠",
            }

            for r in warnings:
                color = status_colors.get(r.status, "white")
                icon = status_icons.get(r.status, "?")
                alts = ", ".join(a.name for a in r.alternatives) if r.alternatives else "—"
                table.add_row(
                    r.container_name,
                    r.image,
                    Text(f"{icon} {r.status.value}", style=color),
                    r.reason or "—",
                    alts,
                )

            console.print(table)

        Prompt.ask("\n[dim]Press Enter to continue[/dim]", default="")

    # ------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------

    def _make_inspector(self) -> Inspector:
        return Inspector(self.platform)
