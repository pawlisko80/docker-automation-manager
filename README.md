# docker-automation-manager (DAM)

Automated Docker container lifecycle manager for QNAP, Synology, and generic Linux hosts.
Includes a Rich terminal TUI, headless CLI, and a full web UI — no font dependencies, works on restricted networks.

[![CI](https://github.com/pawlisko80/docker-automation-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/pawlisko80/docker-automation-manager/actions)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.6.0-green)](CHANGELOG.md)

---

## Features

- 🔍 **Platform auto-detection** — QNAP, Synology, Generic Linux at runtime
- 📸 **Snapshots** — full container config saved to YAML before every update; UTC/local time toggle
- 🔄 **Smart updates** — digest compare, only recreates containers that actually changed
- 🌐 **Static IP preservation** — macvlan / qnet networks survive container recreation
- 📊 **Drift detection** — 5-level severity diff between live state and last snapshot; Reset Baseline button
- 📦 **Export** — DAM YAML, shell script, docker-compose, or full **Migration zip**
- 📥 **Import** — recreate containers from DAM YAML or migration zip on any host
- ⚠️  **EOL detection** — warns when images are deprecated, archived, or end-of-life
- 🌐 **Web UI** — full dashboard, zero font dependencies, works behind CDN-blocked networks
- 🖥️  **Rich TUI** — color-coded tables, progress bars, 9-option interactive menu
- ⚙️  **Scheduler** — configure cron/systemd from the web UI; Docker-aware install instructions
- 🗑️  **Auto-prune** — removes unused images after successful updates
- 🚚 **Server migration** — export full migration bundle (containers + volumes) as a zip
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
dam --migrate                 # export full migration bundle
dam --eol-check               # exits 3 if deprecated images found
```

---

## Web UI Pages

| Page | Description |
|------|-------------|
| Dashboard | Container table, status, IPs, ports, start/stop/restart/logs per container |
| Update | Select containers → dry run → apply updates with live SSE progress |
| Drift | Compare live state vs last snapshot; Reset Baseline button |
| EOL Check | Deprecated/archived image warnings |
| Prune | Preview + remove unused images |
| Export | DAM YAML / Shell Script / Compose / **Migration zip** |
| Snapshots | List snapshots, view detail, take snapshot; UTC/local time toggle |
| Import | Paste YAML or upload `.yaml` / `.zip` migration bundle |
| Scheduler | Configure schedule, install cron/systemd daemon, Run Now |
| Settings | Platform info, Docker info, DAM config, change username/password |

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

**First-time password setup:**

```bash
docker exec -it dam-web dam --web-passwd
```

**Updating DAM on QNAP:**

```bash
cd /share/Container/docker-automation-manager
for f in dam/__init__.py dam/web/server.py dam/web/static/index.html; do
  wget -q -O $f https://raw.githubusercontent.com/pawlisko80/docker-automation-manager/main/$f
done
docker restart dam-web
```

### Scheduler on QNAP (Docker-hosted)

Because DAM runs inside Docker, it cannot write to the host crontab directly.
Click **Install Daemon** on the Scheduler page — DAM will detect this and show you the exact cron line to add:

```bash
# Add to /etc/config/crontab on your QNAP host:
0 2 * * * docker exec dam-web dam --update --yes # DAM auto-update

# Then reload:
crontab /etc/config/crontab
```

Alternatively use QNAP **Control Panel → Task Scheduler**.

### Font Awesome / Static Assets (restricted networks)

QNAP may block CDN access. The web UI has zero font dependencies — all icons are unicode text.
If you want Font Awesome icons, download assets locally:

```bash
bash scripts/fetch-static.sh
```

---

## Server Migration

Move all containers and their data to a new server in 3 steps.

**Step 1 — Export migration bundle:**

```bash
# Web UI: Export → select containers → Migration → Download
# Or CLI:
dam --migrate
```

Downloads `dam-migration.zip` containing `migrate.sh`, `dam-migrate-config.yaml`, `README.txt`.

**Step 2 — Archive volumes on source server:**

```bash
unzip dam-migration.zip
bash migrate.sh source
# Stops containers, archives bind-mount volumes to volumes.tar.xz (XZ max compression)
# Restarts containers when done
```

**Step 3 — Restore on target server:**

```bash
# Copy migrate.sh + volumes.tar.xz + dam-migrate-config.yaml to target
bash migrate.sh restore
# Extracts volumes, recreates all containers
```

**Optional:** Import `dam-migrate-config.yaml` (or the full zip) via the DAM web UI Import page to verify config.

---

## Configuration

`config/settings.yaml`:

```yaml
web:
  username: admin
  password_hash: sha256:SALT:HASH   # set via dam --web-passwd or Settings page

dam:
  snapshot_retention: 10
  log_retention_days: 30
  auto_prune: true
  recreate_delay: 5

daemon:
  schedule: "0 2 * * *"

containers:
  my-container:
    version_strategy: pinned
    pinned_digest: sha256:abc123...
```

---

## Password Management

**From CLI:**
```bash
dam --web-passwd              # interactive prompt
```

**From web UI:**
Settings → Change Username & Password — enter current password to change username, password, or both.

**Emergency reset (if locked out):**
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

## Container Labels

```bash
--label dam.link=https://myapp.local    # custom link for container name
--label dam.ports=8080                  # port hint for auto-detection
--label dam.tags=media,arr              # tag pills shown in dashboard
# dockpeek.* labels also supported
```

---

## Architecture

```
dam/
├── cli.py              Click CLI (--status, --update, --drift, --export, --migrate, --web, ...)
├── tui.py              Rich TUI (9-option interactive menu)
├── core/               inspector, snapshot, updater, pruner, drift, exporter, importer, deprecation
├── platform/           detector, qnap, synology, generic
├── daemon/             scheduler (cron parser), service (install/remove/run)
└── web/
    ├── server.py       FastAPI app + all API endpoints
    ├── dam_updater.py  Self-update (git pull → zip fallback)
    └── static/
        └── index.html  Alpine.js SPA (~900 lines, zero font dependencies)
```

---

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v              # 281 tests, no live Docker required
flake8 dam/ --max-line-length=120
```

---

## License

MIT
