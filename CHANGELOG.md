# Changelog

All notable changes to docker-automation-manager are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [0.4.0] — 2026-04-06

### Added

- **Web UI v0.4.0** — complete DockPeek feature parity + DAM-exclusive features
- Live container log viewer — real-time SSE stream, follow toggle, last N lines
- Start / Stop / Restart buttons per container in the dashboard
- Search / filter bar — searches name, image, IP, network, ports, tags
- Auto-refresh toggle — refreshes container list every 60 seconds
- Dark / light mode toggle — persisted to localStorage
- Clickable port links — http/https auto-detected (443/8443/9443 = HTTPS)
- Container tag pills — reads `dockpeek.tags` / `dam.tags` labels
- Clickable container names — reads `dockpeek.link` / `dam.link` labels
- Extra ports display — reads `dockpeek.ports` / `dam.ports` labels
- DAM self-update panel — checks GitHub releases API, shows version badge in sidebar
  - git pull (if .git dir present) with zip download fallback
  - Update available badge appears automatically in sidebar
- `dam/web/dam_updater.py` — self-update module (git pull → zip fallback)
- New API endpoints:
  - `GET  /api/containers/{name}/logs?tail=N&follow=bool` — SSE log stream
  - `POST /api/containers/{name}/start|stop|restart` — container lifecycle
  - `GET  /api/dam/version` — check GitHub releases for latest version
  - `POST /api/dam/update` — trigger self-update

### Changed

- Version bumped to 0.4.0
- `server.py` fully rewritten with all new endpoints
- `index.html` fully rewritten (721 lines, 20 features)

---

## [0.3.0] — 2026-04-06

### Added

- `dam/web/` — Full web UI (FastAPI + Alpine.js single-file SPA)
  - Login with hashed password (sha256 fallback for QNAP)
  - Dashboard: container table with status, IPs, EOL warnings
  - Update: 3-step flow — select → dry run → confirm → live progress stream (SSE)
  - Drift: visual diff table with severity color coding
  - EOL Check: deprecated/archived/EOL image warnings with alternatives
  - Prune: preview + confirm before removing images
  - Export: checkbox picker + 3 format options + browser download
  - Snapshots: list + view detail
- `dam --web` — launch web UI (default: http://localhost:8080)
- `dam --web --host 0.0.0.0 --port 8080` — bind to network (QNAP access from browser)
- `dam --web-passwd` — interactive password setup, saves sha256 hash to settings.yaml
- Web dependencies added to requirements.txt: fastapi, uvicorn, python-multipart, passlib

### Changed

- Version bumped to 0.3.0

---

## [0.2.0] — 2026-04-06

### Added

- `core/exporter.py` — export containers to 3 formats:
  - `dam-yaml` — full config snapshot, re-importable by DAM on any host
  - `docker-run` — executable `.sh` script, works anywhere without DAM
  - `compose` — valid `docker-compose.yml`, single or full stack
- `core/importer.py` — import from DAM YAML, recreate containers with dry-run and overwrite options
- `core/deprecation.py` — checks containers against EOL/archived image database
- `data/eol.yaml` — bundled community-maintained deprecated image database
  - Includes: containrrr/watchtower (archived Dec 2025), portainer/portainer, ouroboros, linuxserver/letsencrypt, and more
  - GitHub API support for detecting archived repositories (opt-in)
- 58 new tests — total now 281/281

### Changed

- Version bumped to 0.2.0

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

[Unreleased]: https://github.com/yourusername/docker-automation-manager/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/yourusername/docker-automation-manager/releases/tag/v0.1.0
