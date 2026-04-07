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
- Clickable container names — auto-link to service web UI (IP + resolved port)
- Port auto-detection — priority order: `dam.ports` label → env vars (`WEB_PORT`, `PORT`, etc.) → `ExposedPorts` → well-known image map
- Host-mode container links — use `window.location.hostname` for correct routing
- Extra ports display — reads `dockpeek.ports` / `dam.ports` labels
- DAM self-update panel — checks GitHub releases API, shows version badge in sidebar
  - git pull (if .git dir present) with zip download fallback
- **Import page** — paste DAM YAML → Preview → Dry Run → live Import
- **Settings page** — platform info, Docker engine info, editable DAM config (retention, delay, schedule, auto-prune), change password
- **Take Snapshot button** in web UI Snapshots page — no CLI required
- `POST /api/snapshots` — take snapshot from web UI
- `GET/POST /api/settings` — read and update DAM configuration
- `POST /api/import/preview` — parse and validate YAML without creating containers
- `POST /api/import/run` — recreate containers from DAM YAML (dry-run or live)
- `POST /api/auth/change-password` — change web UI password from browser
- New API endpoints:
  - `GET  /api/containers/{name}/logs?tail=N&follow=bool` — SSE log stream
  - `POST /api/containers/{name}/start|stop|restart` — container lifecycle
  - `GET  /api/dam/version` — check GitHub releases for latest version
  - `POST /api/dam/update` — trigger self-update

### Fixed

- **Critical: JS syntax error** — literal newline inside JS string in `write_html.py` caused `dam()` function to never parse (blank screen on all browsers)
- **Alpine.js initialization** — moved `x-data="dam()"` from `<html>` to `<body>` tag; Alpine v3 does not reliably initialize on `<html>`
- **CDN blocked on restricted networks** — Alpine.js and Font Awesome now served locally from `/static/` instead of cdnjs.cloudflare.com
- **Password format unification** — `dam --web-passwd` now writes `sha256:salt:hash` format; old bcrypt and `auth[]` list formats caused persistent login failures
- `_verify_password` now handles all three formats: `sha256:salt:hash`, `$2b$` bcrypt (legacy), plain sha256
- **Port detection for macvlan/host containers** — env var ports (`WEB_PORT=80`) take exclusive priority over `ExposedPorts`; well-known image map as final fallback
- TUI export, import, and drift prompts now accept `q` to cancel — previously trapped the user with no escape
- Removed stale `determined_mestorf` debug container from inspection results
- All flake8 warnings resolved — unused imports, F541, F841, E704, E303, E301, E271, E128

### Changed

- `dam --web-passwd` rewrites settings in flat `web.username` + `web.password_hash` format, removes legacy `web.auth[]` list
- Port links for published-port containers now use container IP instead of `localhost`
- Snapshot empty-state message updated to prompt user to take a snapshot
- Version bumped to 0.4.0

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
- `dam --web-passwd` — interactive password setup
- Cookie session auth with configurable TTL
- FastAPI with SSE streaming for update progress
- `dam/web/auth.py` — password hashing and session management
- `dam/web/server.py` — FastAPI application with all endpoints

---

## [0.2.0] — 2026-04-06

### Added

- `dam/core/exporter.py` — export container configs as DAM YAML, shell script (`docker run`), or `docker-compose.yml`
- `dam/core/importer.py` — recreate containers from DAM YAML export; dry-run mode; overwrite flag
- `dam/core/deprecation.py` + `data/eol.yaml` — bundled EOL/deprecation database
  - watchtower (archived Dec 2025), portainer CE, ouroboros, letsencrypt→swag migration, postgres EOL versions
- CLI flags: `--export`, `--import-file`, `--eol-check`
- TUI menu options 7 (Export), 8 (Import), 9 (EOL Check)
- Exit code 3 when `--eol-check` finds deprecated images

---

## [0.1.0] — 2026-04-06

### Added

- Platform auto-detection: QNAP, Synology, Generic Linux
- `dam/core/inspector.py` — reads full container config via Docker SDK (no shell parsing)
- `dam/core/snapshot.py` — save/load/list YAML snapshots with configurable retention
- `dam/core/updater.py` — digest-compare update with static IP preservation
- `dam/core/pruner.py` — remove dangling/unused images, dry-run mode
- `dam/core/drift.py` — 5-level severity diff (critical/high/medium/low/info)
- Rich TUI with 9-option interactive menu, progress bars, color-coded tables
- Click CLI with full flag coverage
- `dam/daemon/` — cron and systemd daemon installer
- 281 unit tests, fully mocked (no live Docker daemon required)
