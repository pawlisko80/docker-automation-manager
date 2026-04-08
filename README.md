# docker-automation-manager (DAM)

Automated Docker container lifecycle manager for QNAP, Synology, and generic Linux hosts.
Includes a Rich terminal TUI, headless CLI, and a full web UI.

[![CI](https://github.com/pawlisko80/docker-automation-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/pawlisko80/docker-automation-manager/actions)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.6.0-green)](CHANGELOG.md)

---

## Features

- 🔍 **Platform auto-detection** — QNAP, Synology, Generic Linux at runtime
- 📸 **Snapshots** — full container config saved to YAML before every update
- 🔄 **Smart updates** — digest compare, only recreates containers that actually changed
- 🌐 **Static IP preservation** — macvlan / qnet networks survive container recreation
- 📊 **Drift detection** — 5-level severity diff between live state and last snapshot
- 📦 **Export** — container configs as DAM YAML, shell script, or docker-compose
- 📥 **Import** — recreate containers from a DAM YAML export on any host
- ⚠️  **EOL detection** — warns when images are deprecated, archived, or end-of-life
- 🌐 **Web UI** — full dashboard with port links, log viewer, import, settings
- 🖥️  **Rich TUI** — color-coded tables, progress bars, 9-option interactive menu
- ⚙️  **Daemon mode** — cron job or systemd unit for automated runs
- 🗑️  **Auto-prune** — removes unused images after successful updates
- 📌 **Version pinning** — per-container: `latest`, `stable`, or pinned digest
- 🔁 **Self-updater** — web UI can update DAM itself via git pull or zip download
- 🧪 **281 tests** — fully mocked, no live Docker daemon required

---

## Quick Start

### Install

```bash
pip install -e .
```

### Terminal TUI

```bash
dam
```

### Web UI

```bash
dam --web-passwd              # set username + password (first time)
dam --web                     # http://localhost:8080
dam --web --host 0.0.0.0      # accessible from your network
dam --web --host 0.0.0.0 --port 8090
```

### CLI (headless / scripting)

```bash
dam --status                  # show all containers
dam --update                  # pull + recreate changed containers
dam --update --dry-run        # preview only
dam --drift                   # compare live vs last snapshot
dam --export --format dam-yaml
dam --eol-check               # exits 3 if deprecated images found
```

---

## Web UI (v0.6.0)

### Dashboard

| Column | Source |
|--------|--------|
| Container name | Clickable → service web UI (auto-resolved IP + port) |
| Image | Full image reference |
| Status | running / exited / paused |
| IP / Network | Static IP for macvlan containers, network name |
| Ports | Published ports (clickable) + auto-detected service ports |
| Tags | `dam.tags` / `dockpeek.tags` container labels |
| Actions | Logs · Start · Stop · Restart |

### Port auto-detection (for macvlan/host containers without published ports)

DAM resolves service ports in priority order:

1. `dam.ports` or `dockpeek.ports` label on the container
2. Environment variable — `WEB_PORT`, `HTTP_PORT`, `PORT`, `APP_PORT`, etc.
3. `ExposedPorts` from the Docker image config
4. Well-known image name map (homeassistant → 8123, grafana → 3000, etc.)

### Container labels

```bash
# Custom link (overrides auto-link)
--label dam.link=https://myapp.local

# Port hint (when auto-detection isn't enough)
--label dam.ports=8080

# Tag pills shown in dashboard
--label dam.tags=media,arr

# All dockpeek.* labels also supported
--label dockpeek.link=http://10.0.0.5:8096
--label dockpeek.tags=media
--label dockpeek.ports=8096
```

### Pages

| Page | Description |
|------|-------------|
| Dashboard | Container table, search/filter, start/stop/restart, log viewer |
| Update | Select containers → dry run → live update with SSE progress |
| Drift | Compare live state vs last snapshot |
| EOL Check | Deprecated/archived image warnings |
| Prune | Preview + remove unused images |
| Export | Select containers + format → download file (DAM YAML / Shell Script / Compose / **Migration zip**) |
| Snapshots | List snapshots, view detail, **take snapshot** |
| Import | Paste DAM YAML → preview → dry run → live import |
| Settings | Platform info, Docker info, DAM config, change password |

---

## QNAP Deployment

Run DAM as a persistent Docker container on QNAP:

```bash
docker run -d --name dam-web \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /share/Container/docker-automation-manager:/app \
  -p 8090:8090 -w /app python:3.11-slim \
  bash -c "pip install -r requirements.txt -q --root-user-action=ignore \
  --disable-pip-version-check && pip install -e . -q \
  --root-user-action=ignore --disable-pip-version-check \
  && dam --web --host 0.0.0.0 --port 8090"
```

**First-time password setup** (run once after container starts):

```bash
docker exec -it dam-web dam --web-passwd
```

**Updating DAM on QNAP:**

```bash
cd /share/Container
wget -q -O dam.zip https://github.com/pawlisko80/docker-automation-manager/archive/refs/tags/v0.6.0.zip
cp docker-automation-manager/config/settings.yaml /tmp/settings.yaml.bak
unzip -o dam.zip
cp -r docker-automation-manager-0.6.0/. docker-automation-manager/
cp /tmp/settings.yaml.bak docker-automation-manager/config/settings.yaml
rm -rf docker-automation-manager-0.6.0 dam.zip
docker restart dam-web
```

### Static files for restricted networks

If your QNAP blocks CDN access, serve Alpine.js and Font Awesome locally:

```bash
# Download once
wget -q -O /share/Container/docker-automation-manager/dam/web/static/alpine.min.js \
  https://cdnjs.cloudflare.com/ajax/libs/alpinejs/3.13.5/cdn.min.js
wget -q -O /share/Container/docker-automation-manager/dam/web/static/fa.min.css \
  "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css"
```

DAM's web server automatically serves these from `/static/` if present.

---

## Configuration

`config/settings.yaml`:

```yaml
web:
  username: admin
  password_hash: sha256:SALT:HASH   # set via dam --web-passwd or Settings page

dam:
  snapshot_retention: 10     # keep last N snapshots
  log_retention_days: 30
  auto_prune: true           # prune unused images after update
  recreate_delay: 5          # seconds between stop and start on recreate

daemon:
  schedule: "0 2 1 * *"     # cron schedule for automated runs

containers:
  my-container:
    version_strategy: pinned
    pinned_digest: sha256:abc123...
```

---

## Password Management

**From CLI:**
```bash
dam --web-passwd              # interactive prompt, writes sha256:salt:hash
```

**From web UI:**  
Settings → Change Password section

**Manual reset** (if locked out):
```bash
docker exec dam-web python3 -c "
import hashlib, secrets
pwd = 'newpassword'
salt = secrets.token_hex(16)
h = hashlib.sha256((salt+pwd).encode()).hexdigest()
open('/app/config/settings.yaml','w').write(
  'web:\n  username: admin\n  password_hash: sha256:'+salt+':'+h+'\n')
print('Done')
"
docker restart dam-web
```

---

## Architecture

```
dam/
├── cli.py              Click CLI entry point
├── main.py             Package entry point
├── tui.py              Rich TUI (9-option interactive menu)
├── core/
│   ├── inspector.py    Docker SDK container inspection → ContainerConfig
│   ├── snapshot.py     YAML snapshot save/load/list
│   ├── updater.py      Digest-compare update + static IP preservation
│   ├── pruner.py       Unused image removal
│   ├── drift.py        5-level severity diff engine
│   ├── exporter.py     Export to DAM YAML / shell script / compose
│   ├── importer.py     Recreate containers from DAM YAML
│   └── deprecation.py  EOL/deprecation checker + bundled eol.yaml
├── platform/
│   ├── detector.py     Auto-detect QNAP / Synology / Generic
│   ├── qnap.py         QNAP-specific: qnet static IP networks
│   ├── synology.py     Synology-specific paths
│   └── generic.py      Generic Linux
├── daemon/
│   ├── scheduler.py    Cron job installer
│   └── service.py      Systemd unit installer
└── web/
    ├── server.py       FastAPI app + all endpoints
    ├── auth.py         Password hashing (legacy)
    ├── dam_updater.py  Self-update (git pull → zip fallback)
    ├── write_html.py   Generates static/index.html
    └── static/
        ├── index.html  Alpine.js SPA (single file, ~750 lines)
        ├── alpine.min.js  (optional local copy)
        └── fa.min.css     (optional local copy)
```

---

## Development

```bash
pip install -e ".[dev]"

# Run tests (no Docker daemon required)
pytest tests/ -v

# Lint
flake8 dam/ --max-line-length=120

# Regenerate index.html from write_html.py template
python dam/web/write_html.py
```

---

## Server Migration

DAM can export a complete migration bundle to move containers between servers:

```bash
# In web UI: Export → select containers → Migration → Download
# This downloads dam-migration.zip containing:
#   migrate.sh              — two-phase migration script
#   dam-migrate-config.yaml — DAM YAML for re-import
#   README.txt              — step-by-step instructions
```

**On source server:**
```bash
unzip dam-migration.zip
bash migrate.sh source
# Stops containers, archives all bind-mount volumes to volumes.tar.xz
# using maximum XZ compression (XZ_OPT=-9e), then restarts containers
```

**Transfer files to target server:**
```
migrate.sh
volumes.tar.xz
dam-migrate-config.yaml
```

**On target server:**
```bash
bash migrate.sh restore
# Extracts volumes to original paths, recreates all containers
```

**Optional:** import `dam-migrate-config.yaml` via the DAM web UI Import page to verify config.

---

## Known Limitations

- Export downloads work via browser — direct file download from web UI (file-picker upload for import coming)
- Font Awesome icons require `fa.min.css` to be present locally on CDN-restricted networks
- Self-update requires either a `.git` directory or network access to GitHub

---

## License

MIT
