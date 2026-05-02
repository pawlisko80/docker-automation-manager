# docker-automation-manager (DAM)

Automated Docker container lifecycle manager for QNAP, Synology, and generic Linux hosts.
Includes a Rich terminal TUI, headless CLI, and a full web UI — no font dependencies, works on restricted networks.

[![CI](https://github.com/pawlisko80/docker-automation-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/pawlisko80/docker-automation-manager/actions)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.9.0-green)](CHANGELOG.md)

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

All web UI features are available from the command line:

```bash
# ── Container management ──────────────────────────────────────────
dam --status                          # list all containers with status/IPs
dam --update                          # pull + recreate changed containers
dam --update --dry-run                # preview what would change
dam --update --container homeassistant  # update a single container
dam --drift                           # detect config drift vs last snapshot
dam --eol-check                       # check for deprecated/EOL images

# ── Backup & restore ──────────────────────────────────────────────
dam --backup                          # backup ALL containers to dam-backup-<timestamp>.yaml
dam --backup -o /mnt/backups          # save to specific directory
dam --import-file dam-backup.yaml     # restore from backup
dam --import-file dam-backup.yaml --dry-run  # preview restore

# ── Snapshots ─────────────────────────────────────────────────────
dam --snapshot                        # take a manual snapshot
dam --snapshots                       # list all snapshots (with index)
dam --rollback 0                      # rollback ALL containers to latest snapshot
dam --rollback 2                      # rollback to snapshot index 2

# ── Images ────────────────────────────────────────────────────────
dam --images                          # list all images with in-use/unused/dangling status
dam --prune                           # remove unused images (preview first)
dam --prune --yes                     # remove unused images without confirmation
dam --prune --all                     # remove ALL unreferenced images

# ── Clone ─────────────────────────────────────────────────────────
dam --clone homeassistant --clone-name ha-test --clone-ip 10.20.30.50
dam --clone homeassistant --clone-name ha2 --clone-mac auto  # generate new MAC
dam --clone homeassistant --clone-name ha-test --dry-run     # preview only

# ── History & approvals ───────────────────────────────────────────
dam --history                         # show last 10 update runs
dam --approvals                       # list pending update approvals
dam --approve homeassistant           # approve pending update
dam --reject homeassistant            # reject pending update
dam --policy homeassistant:approve    # set update policy (auto/notify/approve/hold)
dam --policy qbittorrent:hold         # never auto-update this container

# ── Network ───────────────────────────────────────────────────────
dam --network-health                  # check for containers on wrong network
dam --network-fix qbittorrent         # recreate with correct network

# ── Export ────────────────────────────────────────────────────────
dam --export --format dam-yaml        # export all configs as DAM YAML
dam --export --format docker-run      # export as shell script (no DAM needed)
dam --export --format compose         # export as docker-compose.yml
dam --migrate                         # full migration bundle (config + volume backup)
dam --export --container homeassistant --format dam-yaml  # single container

# ── Notifications & scheduler ─────────────────────────────────────
dam --notify-test                     # send test notification
dam --install-daemon                  # install as cron job (QNAP) or systemd timer

# ── Web UI ────────────────────────────────────────────────────────
dam --web                             # launch web UI on localhost:8080
dam --web --host 0.0.0.0 --port 8090 # bind to all interfaces
dam --web-passwd                      # change web UI username/password
```

---

## Web UI Pages

| Page | Description |
|------|-------------|
| Dashboard | Container table with status, IPs, MACs, ports; start/stop/restart/logs per container; network health warnings with one-click fix |
| Update | Select containers → dry run → apply with live progress; stale container detection; dam-web self-update |
| Drift | Compare live state vs last snapshot; severity levels; Reset Baseline button |
| EOL Check | Deprecated/archived image warnings with version details |
| Prune | Preview + remove unused images |
| **Backup** | **One-click full backup of all container configs to DAM YAML; restore instructions; migration link** |
| Export | DAM YAML / Shell Script / Compose / Migration zip with volume data |
| Snapshots | List snapshots, view config detail, take snapshot, rollback to any snapshot |
| Images | Full image inventory with in-use/unused/dangling/old-version status; pull, remove, remove all dangling |
| Import | Paste YAML or upload `.yaml`/`.zip`; editable preview (change IPs, networks, MACs, ports, env before importing); MAC conflict resolution (Options A/B/C) |
| Clone | Copy a container with new name, IP, MAC, and env overrides |
| History | Update run log with per-container results; persisted across restarts |
| Approvals | Pending updates awaiting approval; approve/reject/apply; badge shows count |
| Scheduler | Configure cron schedule, install daemon, Run Now |
| Settings | Email SMTP config, maintenance window with day toggles, per-container policies, platform/Docker info, change password |

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
