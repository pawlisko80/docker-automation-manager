# Changelog

All notable changes to docker-automation-manager are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [0.6.0] — 2026-04-07

### Added

- **Migration export** — new 🚚 Migration format on the Export page produces `dam-migration.zip` containing:
  - `migrate.sh` — two-phase migration script:
    - `bash migrate.sh source` — stops containers, archives all bind-mount volumes to `volumes.tar.xz` using maximum XZ compression (`XZ_OPT=-9e`), then restarts containers
    - `bash migrate.sh restore` — extracts volumes to original paths, stops/removes old containers, recreates all containers with original config
  - `dam-migrate-config.yaml` — full DAM YAML for re-import via web UI Import page
  - `README.txt` — step-by-step instructions
- **Drift Reset Baseline** button — takes a new snapshot directly from the Drift page to clear stale CLI drift

### Fixed

- ☀/☾ Dark/Light mode toggle now shows sun/moon unicode (was invisible FA icon)
- All remaining Font Awesome icons replaced with unicode — zero font dependency anywhere
- Reload button in dashboard styled consistently with action buttons
- Scheduler Install/Remove/Run Now buttons now visible without FA
- Export download button icon fixed
- Migration script now uses `XZ_OPT="-9e --threads=0"` for best compression ratio

### Changed

- Migration export produces a zip bundle (2 files) instead of a single shell script
- Version bumped to 0.6.0

---

## [0.5.0] — 2026-04-07

### Added

- **Scheduler page** — view daemon status, install/remove cron or systemd, change cron expression, Run Now button with live results table
- **Import from file** — file picker on Import page (`.yaml`/`.yml`), reads file client-side via FileReader API alongside existing paste
- **Session persistence** — sessions saved to `.sessions` file next to `settings.yaml`; survive `docker restart`; fixes login when accessing via hostname vs IP address
- **Static file server** — proper `/static/{filepath:path}` route with `webfonts/` subdirectory support for Font Awesome
- `scripts/fetch-static.sh` — one-shot script to download Alpine.js + Font Awesome CSS + webfonts for restricted/offline networks
- New API endpoints:
  - `GET  /api/daemon` — daemon status (installed, method, schedule, next/last run, last counts)
  - `POST /api/daemon/install` — install daemon (cron or systemd) with optional schedule override
  - `POST /api/daemon/remove` — remove daemon
  - `POST /api/daemon/run-now` — trigger immediate full update run from web UI

### Fixed

- **Dark/light mode toggle** — `:class` binding on `<body>` was lost when moving `x-data` from `<html>` to `<body>` tag; restored
- **Export browser download** — added `expose_headers: [Content-Disposition]` to CORS config; header was previously blocked by browser security
- **Snapshot button feedback** — error/success messages now correctly styled red/green; null API response handled gracefully
- **Action buttons invisible** — buttons now show text labels (`Logs`, `Stop`, `Start`, `↺`) without requiring Font Awesome
- **FA icons 404** — `onerror` CDN fallback on `<link>` tag; static server now properly serves `webfonts/` subdirectory
- **Import file picker** — file input reads YAML client-side and populates textarea, no server upload needed

### Changed

- CORS middleware now exposes `Content-Disposition` and `X-Filename` response headers
- Session cookie uses `samesite=lax`; sessions persisted to disk across container restarts

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
- Port auto-detection — priority: `dam.ports` label → env vars (`WEB_PORT`, `PORT`, etc.) → `ExposedPorts` → well-known image map
- Host-mode container links — use `window.location.hostname` for correct routing
- **Import page** — paste DAM YAML → Preview → Dry Run → live Import
- **Settings page** — platform info, Docker engine info, editable DAM config, change password
- **Take Snapshot button** in Snapshots page — no CLI required
- New API endpoints: `/api/snapshots` POST, `/api/settings` GET+POST, `/api/import/preview`, `/api/import/run`, `/api/auth/change-password`
- `/api/containers/{name}/logs`, `/api/containers/{name}/start|stop|restart`
- `/api/dam/version`, `/api/dam/update`

### Fixed

- **Critical: JS syntax error** — literal newline inside JS string caused `dam()` to never parse (blank screen)
- **Alpine.js initialization** — moved `x-data` from `<html>` to `<body>` tag
- **CDN blocked on QNAP** — Alpine.js and Font Awesome served from `/static/` locally
- **Password format** — `dam --web-passwd` now writes `sha256:salt:hash`; `_verify_password` handles bcrypt legacy + sha256
- TUI export, import, drift prompts now accept `q` to cancel
- All flake8 warnings resolved

### Changed

- `dam --web-passwd` writes flat `web.username` + `web.password_hash` format, removes legacy `web.auth[]` list
- Port links use container IP instead of `localhost`

---

## [0.3.0] — 2026-04-06

### Added

- `dam/web/` — Full web UI (FastAPI + Alpine.js SPA)
- Login with sha256-hashed password
- Dashboard, Update (SSE progress), Drift, EOL Check, Prune, Export, Snapshots pages
- `dam --web`, `dam --web --host 0.0.0.0 --port 8080`, `dam --web-passwd`
- Cookie session auth with configurable TTL

---

## [0.2.0] — 2026-04-06

### Added

- `dam/core/exporter.py` — export as DAM YAML, shell script, docker-compose
- `dam/core/importer.py` — recreate containers from DAM YAML; dry-run + overwrite
- `dam/core/deprecation.py` + `data/eol.yaml` — bundled EOL/deprecation database
- CLI `--export`, `--import-file`, `--eol-check`; TUI options 7/8/9
- Exit code 3 on deprecated images

---

## [0.1.0] — 2026-04-06

### Added

- Platform auto-detection: QNAP, Synology, Generic Linux
- Inspector, Snapshot, Updater, Pruner, Drift, Exporter, Importer, Deprecation modules
- Rich TUI (9 options), Click CLI, Daemon installer
- 281 unit tests, fully mocked
