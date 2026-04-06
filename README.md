# docker-automation-manager (DAM)

Automated Docker container lifecycle manager for QNAP, Synology, and generic Linux hosts.
Includes a Rich terminal TUI, headless CLI, and a full web UI.

[![CI](https://github.com/pawlisko80/docker-automation-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/pawlisko80/docker-automation-manager/actions)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.4.0-green)](CHANGELOG.md)

---

## Features

- 🔍 **Auto-detects** host platform (QNAP, Synology, Generic Linux) at runtime
- 📸 **Snapshots** full container config to YAML before every update — rollback-ready
- 🔄 **Smart updates** — digest compare, only recreates containers that actually changed
- 📊 **Drift detection** — 5-level severity diff between live state and last snapshot
- 📦 **Export** — container configs as DAM YAML, shell script, or docker-compose
- 📥 **Import** — recreate containers from a DAM YAML export on any host
- ⚠️  **EOL detection** — warns when images are deprecated, archived, or end-of-life
- 🌐 **Web UI** — full dashboard with logs, start/stop/restart, search, dark/light mode
- 🖥️  **Rich TUI** — color-coded tables, progress bars, 9-option interactive menu
- ⚙️  **Daemon mode** — install as cron job or systemd unit for automated runs
- 🗑️  **Auto-prune** — removes unused images after successful updates
- 📌 **Version pinning** — per-container strategy: `latest`, `stable`, or pinned digest
- 🔁 **Self-updater** — web UI can update DAM itself via git pull or GitHub zip download
- 🧪 **281 tests** — fully mocked, no live Docker daemon required

---

## Web UI (v0.3.0+)

Start the web UI with one command:

```bash
dam --web-passwd          # set username + password once
dam --web                 # launch at http://localhost:8080
dam --web --host 0.0.0.0  # bind to all interfaces (network access)
```

### Web UI features (v0.4.0)

| Feature | Description |
|---------|-------------|
| Dashboard | Container table with status, IPs, port links, tag pills |
| Clickable ports | Auto-detects http/https — 443/8443/9443 → HTTPS |
| Clickable names | Via `dam.link` / `dockpeek.link` container labels |
| Tag pills | Via `dam.tags` / `dockpeek.tags` labels |
| Log viewer | Real-time SSE stream per container, live follow toggle |
| Start/Stop/Restart | Per-container action buttons in dashboard |
| Search/filter | Searches name, image, IP, network, tags, ports |
| Auto-refresh | Refreshes container list every 60 seconds |
| Dark / Light mode | Toggle persisted to localStorage |
| Update flow | Select → dry run → confirm → live progress stream |
| Drift detection | Visual diff table with severity color coding |
| EOL check | Deprecated/archived/EOL warnings with alternatives |
| Export | Format picker + browser file download |
| Snapshots | List and view saved snapshots |
| DAM self-update | Version badge in sidebar, git pull → zip fallback |

### DockPeek label compatibility

DAM reads the same labels as DockPeek — no migration needed:

```yaml
labels:
  - "dockpeek.tags=homeautomation,iot"
  - "dockpeek.link=http://homeassistant.local:8123"
  - "dockpeek.ports=8123,9090"
  # DAM-native aliases also work:
  - "dam.tags=homeautomation,iot"
  - "dam.link=http://homeassistant.local:8123"
```

---

## Supported platforms

| Platform       | Networks               | Paths                    | Daemon          |
|----------------|------------------------|--------------------------|-----------------|
| QNAP NAS       | macvlan, qnet (static) | /share/Container         | crontab         |
| Synology NAS   | macvlan, bridge        | /volume1/docker          | systemd / cron  |
| Generic Linux  | macvlan, ipvlan        | /opt/docker              | systemd / cron.d|
| macOS          | bridge                 | ~/docker                 | launchd / cron  |

---

## Installation

### Generic Linux / macOS (Python 3.9+)

```bash
git clone https://github.com/pawlisko80/docker-automation-manager
cd docker-automation-manager
pip install -r requirements.txt
pip install -e .
dam
```

### QNAP NAS

QNAP ships with Python 2.7/3.7 — both too old. DAM runs inside Docker instead:

```bash
# Copy DAM to your QNAP
scp docker-automation-manager-v0.4.0.zip admin@YOUR_QNAP_IP:/share/Container/

# SSH in, unzip
ssh admin@YOUR_QNAP_IP
cd /share/Container && unzip docker-automation-manager-v0.4.0.zip

# Run TUI (interactive terminal)
docker run -it --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /share/Container/docker-automation-manager:/app \
  -w /app python:3.11-slim \
  bash -c "pip install -r requirements.txt -q --root-user-action=ignore \
           --disable-pip-version-check && pip install -e . -q \
           --root-user-action=ignore --disable-pip-version-check && dam"

# Run Web UI (persistent, accessible from browser)
docker run -d --name dam-web \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /share/Container/docker-automation-manager:/app \
  -p 8080:8080 -w /app python:3.11-slim \
  bash -c "pip install -r requirements.txt -q --root-user-action=ignore \
           --disable-pip-version-check && pip install -e . -q \
           --root-user-action=ignore --disable-pip-version-check \
           && dam --web --host 0.0.0.0"

# Then open: http://YOUR_QNAP_IP:8080
```

> See [docs/QNAP_DEPLOYMENT.md](docs/QNAP_DEPLOYMENT.md) for the full guide including alias setup and cron automation.

---

## Quick start

```bash
# Interactive TUI
dam

# Headless CLI
dam --status                                    # container status table
dam --update --dry-run                          # preview updates, no changes
dam --update                                    # full update cycle
dam --drift                                     # drift check vs last snapshot
dam --prune                                     # prune unused images

# Export / Import
dam --export                                    # interactive picker
dam --export --format docker-run --container homeassistant
dam --export --all --format compose --output ~/backups/
dam --import-file homeassistant.dam.yaml --dry-run

# EOL check (exits 3 if any deprecated/archived/EOL found)
dam --eol-check

# Web UI
dam --web-passwd                                # set password (first time)
dam --web                                       # http://localhost:8080
dam --web --host 0.0.0.0 --port 8080           # network-accessible

# Daemon
dam --install-daemon                            # monthly cron job
```

---

## TUI Menu

```
[1]  Status      Show all containers with current state
[2]  Update      Pull latest images and recreate changed containers
[3]  Drift       Compare current state against last snapshot
[4]  Prune       Remove unused images
[5]  Snapshots   Browse and manage saved snapshots
[6]  Settings    View platform info and configuration
[7]  Export      Export configs (dam-yaml / docker-run / compose)
[8]  Import      Recreate containers from a DAM YAML file
[9]  EOL Check   Check for deprecated or archived images
[q]  Quit
```

---

## Export formats

| Format       | File                  | Use case                                |
|--------------|-----------------------|-----------------------------------------|
| `dam-yaml`   | `<name>.dam.yaml`     | Backup + re-import on any DAM host      |
| `docker-run` | `<name>.sh`           | Executable script — works without DAM  |
| `compose`    | `<name>.compose.yml`  | Migrate to Docker Compose               |

---

## EOL / Deprecation detection

DAM ships a bundled `data/eol.yaml` database. Community PRs welcome.

```bash
dam --eol-check          # CLI
# Or use the EOL Check page in the web UI
```

Current entries: `containrrr/watchtower` (archived Dec 2025), `portainer/portainer`,
`pyouroboros/ouroboros`, `linuxserver/letsencrypt` → swag, postgres EOL versions, and more.

---

## Configuration

`config/settings.yaml`:

```yaml
dam:
  snapshot_retention: 10
  auto_prune: true
  recreate_delay: 5

containers:
  homeassistant:
    version_strategy: stable    # latest | stable | pinned
  nut:
    version_strategy: pinned
    pinned_digest: sha256:edadf0d...

# Web UI (set with: dam --web-passwd)
web:
  username: admin
  password_hash: sha256:SALT:HASH

daemon:
  schedule: "0 2 1 * *"        # 2 AM on the 1st of every month
```

---

## How updates work

1. Inspect all containers — capture full config (IPs, volumes, env, networks, labels)
2. Save pre-update YAML snapshot
3. Pull latest image per container
4. Compare digests — skip if unchanged
5. Recreate only changed containers, preserving static IPs and all settings
6. Prune old images (if `auto_prune` enabled)
7. Save post-update snapshot as next drift baseline

---

## Drift detection severity

| Level       | Examples |
|-------------|---------|
| 🔴 CRITICAL | Container added or removed |
| 🟠 HIGH     | Image, IP, network, privilege changed |
| 🟡 MEDIUM   | Volumes, ports, restart policy, devices |
| 🔵 LOW      | Env vars, labels, capabilities |
| ⚪ INFO     | Status change only (running→exited) |

---

## Project structure

```
dam/
├── core/
│   ├── inspector.py      Container discovery + full config extraction
│   ├── snapshot.py       YAML snapshot save/load with rotation
│   ├── updater.py        Pull, digest compare, recreate
│   ├── pruner.py         Safe image cleanup
│   ├── drift.py          Config drift detection (5 severity levels)
│   ├── exporter.py       Export to dam-yaml / docker-run / compose
│   ├── importer.py       Import from DAM YAML, recreate containers
│   └── deprecation.py    EOL / deprecated image detection
├── platform/
│   ├── detector.py       Auto-detect platform at runtime
│   ├── base.py           Abstract adapter interface
│   ├── qnap.py           QNAP adapter (macvlan + qnet static IPs)
│   ├── synology.py       Synology adapter
│   └── generic.py        Generic Linux fallback
├── daemon/
│   ├── scheduler.py      Cron expression parser
│   └── service.py        Install/remove/status/run loop
├── web/
│   ├── server.py         FastAPI backend (all API endpoints)
│   ├── auth.py           Session auth + bcrypt/sha256 password hashing
│   ├── dam_updater.py    Self-update logic (git pull → zip fallback)
│   └── static/
│       └── index.html    Single-file Alpine.js SPA (no build step)
├── tui.py                Rich interactive TUI (9 menu options)
├── cli.py                Click CLI entry point
└── main.py               dam binary
data/
└── eol.yaml              Community-maintained deprecated image database
tests/                    281 tests, all mocked (no live Docker required)
docs/                     Deployment guides
config/                   settings.yaml
```

---

## DAM vs DockPeek

Both are complementary tools. DAM focuses on lifecycle management; DockPeek focuses on dashboard access.

| Feature | DAM | DockPeek |
|---------|-----|----------|
| Web dashboard | ✅ | ✅ |
| Live log viewer | ✅ | ✅ |
| Start/Stop/Restart | ✅ | ✅ |
| Port links (http/https) | ✅ | ✅ |
| Container tags + labels | ✅ (dockpeek-compatible) | ✅ |
| Image updates | ✅ Dry-run + confirm | ✅ One-click |
| YAML snapshots | ✅ | ❌ |
| Drift detection | ✅ 5-level severity | ❌ |
| Export (yaml/sh/compose) | ✅ | ❌ |
| Import / migrate | ✅ | ❌ |
| EOL image database | ✅ | ❌ |
| Static IP preservation | ✅ QNAP qnet/macvlan | ❌ |
| CLI / TUI interface | ✅ | ❌ |
| Self-updater | ✅ git pull + zip | ❌ |
| Multi-host | ❌ | ✅ |

> Note: `containrrr/watchtower` — the most common alternative — was archived in December 2025 and is no longer maintained.

---

## Help wanted — platform contributors

| Platform       | Status         |
|----------------|----------------|
| Unraid         | 🙏 Wanted      |
| TrueNAS Scale  | 🙏 Wanted      |
| TrueNAS Core   | 🙏 Wanted      |
| OpenMediaVault | 🙏 Wanted      |
| Synology DSM   | 🔶 Stub exists |
| Proxmox LXC    | 🙏 Wanted      |
| Raspberry Pi   | 🙏 Wanted      |

See [CONTRIBUTING.md](CONTRIBUTING.md) for the step-by-step guide.

---

## Running tests

```bash
python tests/test_inspector_snapshot.py   # 33 tests
python tests/test_updater_pruner.py       # 37 tests
python tests/test_drift.py                # 48 tests
python tests/test_tui.py                  # 51 tests
python tests/test_daemon.py               # 54 tests
python tests/test_exporter_importer_deprecation.py  # 58 tests
# Total: 281 tests — no live Docker daemon required
```

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for full version history.

- **v0.4.0** — Web UI: log viewer, start/stop/restart, search, dark mode, DAM self-updater
- **v0.3.0** — Web UI launched (FastAPI + Alpine.js SPA, cookie auth)
- **v0.2.0** — Export/import, EOL/deprecation detection, bundled eol.yaml
- **v0.1.0** — Core engine: inspect, snapshot, update, drift, prune, TUI, CLI, daemon

---

## License

MIT — see [LICENSE](LICENSE).
