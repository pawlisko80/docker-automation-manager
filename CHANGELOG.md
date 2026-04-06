# Changelog

All notable changes to docker-automation-manager are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [0.1.0] — 2026-04-05

### Added

**Core engine**
- `inspector.py` — Docker SDK-based container discovery, full config extraction into `ContainerConfig` dataclass. Filters runtime env vars injected by base images (PATH, S6_*, UV_*, etc.)
- `snapshot.py` — timestamped YAML snapshots with rotation, `latest.yaml` always current, `load_previous()` for drift comparison
- `updater.py` — digest-comparison update cycle: pull → compare → recreate only changed containers. Dry-run mode, per-container version strategy (latest/stable/pinned), progress callback hook
- `pruner.py` — safe image cleanup: never removes images in use, targets dangling + replaced + optionally unreferenced. Dry-run preview with space estimates
- `drift.py` — five-level severity drift detection (CRITICAL/HIGH/MEDIUM/LOW/INFO) across all container config fields: image, network/IP, volumes, env, capabilities, devices, ports, labels

**Platform layer**
- `base.py` — abstract platform adapter interface
- `detector.py` — auto-detects QNAP, Synology, or Generic Linux at runtime via filesystem fingerprints, `/proc/version`, os-release, and Docker network driver signals
- `qnap.py` — QNAP adapter: qnet/macvlan static IP support, `/share/Container` paths, `/etc/config/crontab` with reload
- `synology.py` — Synology adapter stub (community-extendable): `/volume1/docker` paths, systemd/crontab
- `generic.py` — Generic Linux fallback: `/opt/docker`, systemd or `/etc/cron.d`

**Daemon**
- `scheduler.py` — pure stdlib cron expression parser and next-run calculator (no external dependencies). Supports `*`, `*/n`, `a-b`, `a,b,c`, `a-b/n` syntax. Sunday=0 and Sunday=7 both supported
- `service.py` — daemon lifecycle: install (cron or systemd), remove, status query, foreground run loop with graceful SIGTERM shutdown, structured run state persistence

**Interface**
- `tui.py` — Rich terminal UI: header bar, main menu, status table, update results with progress bars, drift diff view, prune preview/result, snapshot browser, platform/settings panels
- `cli.py` — dual-mode Click CLI: no flags = interactive TUI; `--status`, `--update`, `--drift`, `--prune`, `--install-daemon` for headless/automation use. Exit code 2 on drift detected
- `main.py` — `dam` binary entry point

**Project**
- `config/settings.yaml` — per-container version strategy, retention, auto-prune, daemon schedule
- 223 tests across 5 test files, 0 failures
- GitHub Actions CI (Python 3.10/3.11/3.12)
- Issue templates: bug report, feature request, new platform adapter
- `CONTRIBUTING.md` with platform adapter guide

### Platform support

| Platform       | Status    | Networks              | Paths                    | Daemon         |
|----------------|-----------|-----------------------|--------------------------|----------------|
| QNAP NAS       | ✅ Tested  | macvlan, qnet (static)| /share/Container         | crontab        |
| Synology NAS   | 🔶 Stub   | macvlan, bridge       | /volume1/docker          | systemd/cron   |
| Generic Linux  | ✅ Tested  | macvlan, ipvlan       | /opt/docker              | systemd/cron.d |

### Known limitations

- Synology adapter is a stub — needs testing and refinement from a Synology owner
- `--install-daemon` with systemd requires root privileges
- Container health check waiting not yet implemented (containers are assumed healthy after start)
- No notification support yet (email/webhook on update completion)

---

[Unreleased]: https://github.com/pawlisko80/docker-automation-manager/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/pawlisko80/docker-automation-manager/releases/tag/v0.1.0
