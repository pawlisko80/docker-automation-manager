# Changelog

All notable changes to docker-automation-manager are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [0.7.0] — 2026-04-09

### Added

- **Clone Container page** — duplicate any container with overrides: new name, new static IP, env var overrides; dry-run preview shows the `docker run` command before creating
- **Update History page** — full log of every update run: timestamp, container results, updated/skipped/failed counts; persisted in memory across restarts
- **Image Management page** — list all images with size, creation date, in-use status; pull new images by name; remove unused images with one click
- **Rollback from snapshot** — Rollback button on Snapshots page recreates containers from any saved snapshot
- **Drift ignore/dismiss** — Ignore button per container row in Drift; ignored containers excluded from future drift comparisons; unignore anytime; list shown below drift results
- **Notifications** (`dam/core/notifier.py`) — ntfy.sh and generic webhook support; configurable in Settings; send test notification; fires on update success and failure
  - `POST /api/notifications/test` — send test notification
- New API endpoints:
  - `GET  /api/images` — list all Docker images with in-use status
  - `POST /api/images/pull` — pull image by name
  - `DELETE /api/images/{id}` — remove image
  - `GET  /api/update/history` — update run history
  - `POST /api/containers/clone` — clone container with overrides (dry-run supported)
  - `POST /api/snapshots/{id}/rollback` — recreate containers from snapshot
  - `POST/DELETE /api/drift/ignore/{name}` — add/remove container from drift ignore list
  - `GET  /api/drift/ignore` — list ignored containers

### Fixed

- Take Snapshot — added null guard for `_snapshot_manager` and `_platform`; surfaces proper 503 error if server not fully initialized
- Notification settings — saved to `config/settings.yaml` and reloaded on next update run

### Changed

- 294 tests (was 281) — +13 notifier tests
- Settings page now includes Notifications section (ntfy URL, provider, enable/disable, test button)
- Drift page shows ignored container list with unignore buttons

---

## [0.6.0] — 2026-04-08

### Added

- **Migration export** — new 🚚 Migration format on Export page produces `dam-migration.zip` containing:
  - `migrate.sh` — two-phase migration script:
    - `bash migrate.sh source` — stops containers, archives all bind-mount volumes to `volumes.tar.xz` with maximum XZ compression (`XZ_OPT=-9e`), restarts containers
    - `bash migrate.sh restore` — extracts volumes to original paths, removes old containers, recreates all
  - `dam-migrate-config.yaml` — full DAM YAML for re-import via web UI Import page
  - `README.txt` — step-by-step transfer instructions
- **`dam --migrate` CLI** — generate `dam-migration.zip` from the terminal with volume path preview
- **Drift Reset Baseline** button — takes a fresh snapshot from the Drift page to clear stale CLI-era drift without leaving the UI
- **Snapshots UTC/local toggle** — checkbox on Snapshots page to display filenames and detail timestamps in local time or UTC
- **Import accepts migration zip** — file picker on Import page now accepts `.zip` files and auto-extracts `dam-migrate-config.yaml` via JSZip
- **Scheduler UX rewrite** — preset schedule buttons (Daily at 2am, Weekly, Every 6h, Every 12h), plain-English description, clear Install/Run Now buttons
- **Scheduler Docker awareness** — when running inside a Docker container, Install Daemon detects it cannot write the host crontab and instead shows the exact cron line + QNAP Task Scheduler instructions
- **Run Now spinner** — progress message and spinner shown while update is in progress
- **Settings password section** — clear instructions showing current username, explains username-only vs password-only changes, lockout recovery tip (`dam --web-passwd`)
- **Import migration tip** — info box on Import page explains how to load a migration zip directly

### Fixed

- ☀/☾ Dark/Light mode toggle — unicode sun/moon, always visible
- All Font Awesome icon dependencies removed — zero font dependency anywhere in the UI
- `Restart` action button — replaced `↺` (U+21BA, not universally supported) with text label
- `Reload` dashboard button — text only, consistent style with other page buttons
- Scheduler `Install Daemon` / `Run Now` buttons greyed — fixed `:disabled="ld.daemonact===true"` (was matching `undefined`)
- `UpdateResult.container_name` — `run-now` endpoint was accessing non-existent `.name` attribute
- `DaemonService` → `DaemonManager` — correct class name in all daemon API endpoints
- Take Snapshot — uses raw `fetch()` to properly surface HTTP error codes; success message persists until navigation
- Drift Reset Baseline — uses own `ld.driftReset` flag, no longer shares state with Take Snapshot
- Session persistence — sessions survive `docker restart`; fixes hostname vs IP login mismatch
- Export CORS — `Content-Disposition` header exposed so browser download works correctly
- `changePwd` — now allows username-only or password-only change (previously required both)
- Self-update guard — null check on `dv` prevents crash when version data not yet loaded
- CI workflow — updated to `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24`, simplified lint command to use `.flake8` config

### Changed

- Migration export produces a zip bundle (`migrate.sh` + `dam-migrate-config.yaml` + `README.txt`) instead of a bare shell script
- Scheduler page explains what the daemon does before showing controls
- Settings password card shows current username and explains each field

---

## [0.5.0] — 2026-04-07

### Added

- **Scheduler page** — view daemon status, install/remove cron or systemd, change schedule, Run Now
- **Import from file** — `.yaml`/`.yml` file picker on Import page via FileReader API
- **Session persistence** — sessions saved to `.sessions` file; survive `docker restart`; fixes hostname vs IP login
- **Static file server** — `/static/{filepath:path}` route with `webfonts/` subdirectory support
- `scripts/fetch-static.sh` — downloads Alpine.js + Font Awesome + webfonts for offline/restricted networks
- `GET /api/daemon`, `POST /api/daemon/install|remove|run-now`

### Fixed

- Dark/light mode `:class` binding restored on `<body>` tag
- Export browser download — `expose_headers: [Content-Disposition]` added to CORS
- Snapshot button feedback — error/success message styled correctly
- Action buttons — text labels without Font Awesome dependency

---

## [0.4.0] — 2026-04-06

### Added

- Full web UI (FastAPI + Alpine.js SPA) — Dashboard, Update, Drift, EOL Check, Prune, Export, Snapshots, Import, Settings
- Live log viewer (SSE), start/stop/restart per container, search/filter, auto-refresh, dark/light mode
- Port auto-detection (label → env vars → ExposedPorts → well-known map)
- Clickable container names and port links
- DAM self-update panel
- `POST /api/snapshots`, `GET|POST /api/settings`, `POST /api/import/preview|run`, `POST /api/auth/change-password`

### Fixed

- JS syntax error (literal newline in string) — blank screen on all browsers
- Alpine.js initialization — `x-data` moved from `<html>` to `<body>`
- CDN blocked on QNAP — Alpine.js and Font Awesome served locally
- Password format unified to `sha256:salt:hash`

---

## [0.3.0] — 2026-04-06

### Added

- `dam/web/` — FastAPI + Alpine.js web UI with login, dashboard, update SSE stream, drift, EOL, prune, export, snapshots
- `dam --web`, `dam --web --host 0.0.0.0 --port 8080`, `dam --web-passwd`

---

## [0.2.0] — 2026-04-06

### Added

- Export (DAM YAML / shell script / docker-compose), Import (DAM YAML), EOL/deprecation checker
- CLI `--export`, `--import-file`, `--eol-check`; TUI options 7/8/9

---

## [0.1.0] — 2026-04-06

### Added

- Platform auto-detection (QNAP, Synology, Generic Linux)
- Inspector, Snapshot, Updater, Pruner, Drift, Exporter, Importer, Deprecation modules
- Rich TUI (9 options), Click CLI, Daemon installer
- 281 unit tests, fully mocked
