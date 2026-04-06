# docker-automation-manager (DAM)

Automated Docker container lifecycle manager with auto platform detection.
Supports QNAP, Synology, and generic Linux Docker hosts.

[![CI](https://github.com/pawlisko80/docker-automation-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/pawlisko80/docker-automation-manager/actions)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Features

- 🔍 **Auto-detects** host platform (QNAP, Synology, Generic Linux) at runtime
- 📸 **Snapshots** full container config to YAML before every update
- 🔄 **Smart updates** — only recreates containers where new images were pulled
- 📊 **Drift detection** — compares live config against last snapshot, flags changes
- 🎨 **Rich TUI** — color-coded tables, progress bars, interactive menus
- ⚙️ **Daemon mode** — install as cron job or systemd unit for automated runs
- 🗑️ **Auto-prune** — cleans up unused images after successful updates
- 📌 **Version pinning** — per-container strategy: `latest`, `stable`, or pinned digest
- 🧪 **223 tests** — full mock-based suite, no live Docker daemon required

---

## Supported platforms

| Platform       | Networks               | Paths                    | Daemon          | Notes                        |
|----------------|------------------------|--------------------------|-----------------|------------------------------|
| QNAP NAS       | macvlan, qnet (static) | /share/Container         | crontab         | Run via Docker — see guide   |
| Synology NAS   | macvlan, bridge        | /volume1/docker          | systemd / cron  | Contributions welcome        |
| Generic Linux  | macvlan, ipvlan        | /opt/docker              | systemd / cron.d| Direct pip install           |
| macOS          | bridge                 | ~/docker                 | launchd / cron  | Development / testing        |

---

## Installation

### Generic Linux (Python 3.9+)

```bash
git clone https://github.com/pawlisko80/docker-automation-manager
cd docker-automation-manager
pip install -r requirements.txt
pip install -e .
dam
```

### macOS

```bash
git clone https://github.com/pawlisko80/docker-automation-manager
cd docker-automation-manager
pip3 install -r requirements.txt
pip3 install -e .
# Add to PATH if needed:
export PATH="$HOME/Library/Python/3.9/bin:$PATH"
dam
```

### QNAP NAS

QNAP ships with Python 2.7 / 3.7 — both too old. DAM runs inside a Docker container instead:

```bash
# Copy DAM to your QNAP
scp docker-automation-manager-v0.1.0.zip admin@YOUR_QNAP_IP:/share/Container/

# SSH in and unzip
ssh admin@YOUR_QNAP_IP
cd /share/Container && unzip docker-automation-manager-v0.1.0.zip

# Run DAM
docker run -it --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /share/Container/docker-automation-manager:/app \
  -w /app python:3.11-slim \
  bash -c "pip install -r requirements.txt -q --root-user-action=ignore \
           --disable-pip-version-check && pip install -e . -q \
           --root-user-action=ignore --disable-pip-version-check && dam"
```

👉 **See [docs/QNAP_DEPLOYMENT.md](docs/QNAP_DEPLOYMENT.md) for the full guide** including alias setup, cron automation, and troubleshooting.

---

## Quick start

```bash
dam                    # Interactive TUI
dam --status           # Container status table
dam --update --dry-run # Show what would update, make no changes
dam --update           # Full update cycle
dam --drift            # Drift check vs last snapshot
dam --prune            # Prune unused images
dam --install-daemon   # Install monthly cron job
```

---

## Configuration

Edit `config/settings.yaml`:

```yaml
dam:
  snapshot_retention: 10
  auto_prune: true
  recreate_delay: 5        # seconds between container recreations

containers:
  homeassistant:
    version_strategy: stable   # latest | stable | pinned
  nut:
    version_strategy: pinned
    pinned_digest: sha256:edadf0d...

daemon:
  schedule: "0 2 1 * *"   # 2 AM on the 1st of every month
```

---

## How updates work

1. Inspect all containers — capture full config (IPs, volumes, env, networks)
2. Save pre-update YAML snapshot
3. Pull latest image per container
4. Compare pre/post digest — skip if unchanged
5. Recreate only containers with new images, preserving all settings
6. Prune old images (if auto_prune enabled)
7. Save post-update snapshot for next drift baseline

---

## Drift detection severity

| Level    | Examples |
|----------|---------|
| 🔴 CRITICAL | Container added or removed |
| 🟠 HIGH     | Image, IP, network, privilege changed |
| 🟡 MEDIUM   | Volumes, ports, restart policy, devices |
| 🔵 LOW      | Env vars, labels, capabilities |
| ⚪ INFO     | Status change only (running→exited) |

---

## Project structure

```
dam/
├── core/           inspector, snapshot, updater, pruner, drift
├── platform/       detector, base, qnap, synology, generic
├── daemon/         scheduler (cron parser), service (lifecycle)
├── tui.py          Rich interactive TUI
├── cli.py          Click CLI
└── main.py         dam binary entry point
docs/               Deployment guides
tests/              223 tests, all mocked (no live Docker required)
config/             settings.yaml
```

---

## Deployment guides

- 📦 [QNAP NAS](docs/QNAP_DEPLOYMENT.md) — Docker-based deployment, alias setup, cron automation
- 📦 Synology — coming soon (contributions welcome)

---

## Help wanted — platform contributors

DAM is designed to be extended by the community. The core engine is platform-agnostic — adding support for a new NAS or Docker host only requires implementing a small adapter class.

We are actively looking for contributors with the following platforms:

| Platform       | Status         | Notes |
|----------------|----------------|-------|
| Unraid         | 🙏 Wanted      | Popular community NAS, Slackware-based |
| TrueNAS Scale  | 🙏 Wanted      | Debian-based, k3s + Docker |
| TrueNAS Core   | 🙏 Wanted      | FreeBSD-based, jails |
| OpenMediaVault | 🙏 Wanted      | Debian-based, popular in homelab |
| Synology DSM   | 🔶 Stub exists | Needs real-hardware testing and refinement |
| Portainer      | 🙏 Wanted      | Remote Docker host management |
| Proxmox LXC    | 🙏 Wanted      | LXC containers running Docker |
| Raspberry Pi   | 🙏 Wanted      | Raspbian / DietPi Docker hosts |

**Adding support takes about 30 minutes** if you know your platform. See [CONTRIBUTING.md](CONTRIBUTING.md) for the step-by-step guide — it's essentially:

1. Create `dam/platform/yourplatform.py` — implement 6 methods (paths, networks, cron)
2. Add 2-3 detection fingerprints to `detector.py`
3. Write a handful of tests

If you run Docker on any platform not listed above and want to help, open an issue using the [New Platform template](.github/ISSUE_TEMPLATE/new_platform.md) and let's make it happen.

---

## Adding a new platform

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full step-by-step guide.
Subclass `BasePlatform`, add detection fingerprints to `detector.py`, write tests.

---

## Running tests

```bash
python tests/test_inspector_snapshot.py  # 33 tests
python tests/test_updater_pruner.py      # 37 tests
python tests/test_drift.py               # 48 tests
python tests/test_tui.py                 # 51 tests
python tests/test_daemon.py              # 54 tests
```

No live Docker daemon required — all Docker calls are mocked.

---

## License

MIT — see [LICENSE](LICENSE).
