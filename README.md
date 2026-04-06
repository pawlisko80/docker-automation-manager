# docker-automation-manager (DAM)

Automated Docker container lifecycle manager with auto platform detection.
Supports QNAP, Synology, and generic Linux Docker hosts.

[![CI](https://github.com/pawlisko80/docker-automation-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/pawlisko80/docker-automation-manager/actions)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org)
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

| Platform       | Networks               | Paths                    | Daemon          |
|----------------|------------------------|--------------------------|-----------------|
| QNAP NAS       | macvlan, qnet (static) | /share/Container         | crontab         |
| Synology NAS   | macvlan, bridge        | /volume1/docker          | systemd / cron  |
| Generic Linux  | macvlan, ipvlan        | /opt/docker              | systemd / cron.d|

---

## Installation

```bash
git clone https://github.com/pawlisko80/docker-automation-manager
cd docker-automation-manager
pip install -r requirements.txt
pip install -e .
```

**QNAP / Synology** (no pip available):

```bash
curl https://bootstrap.pypa.io/get-pip.py | python3
pip3 install -r requirements.txt --break-system-packages
pip3 install -e . --break-system-packages
```

---

## Quick start

```bash
dam                    # Interactive TUI
dam --status           # Container status table
dam --update --dry-run # Show what would update
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
  recreate_delay: 5

containers:
  homeassistant:
    version_strategy: stable
  nut:
    version_strategy: pinned
    pinned_digest: sha256:edadf0d...

daemon:
  schedule: "0 2 1 * *"   # 2 AM on the 1st of every month
```

---

## How updates work

1. Inspect all containers — capture full config
2. Save pre-update YAML snapshot
3. Pull latest image per container
4. Compare pre/post digest — skip if unchanged
5. Recreate only containers with new images
6. Prune old images (if auto_prune)
7. Save post-update snapshot for drift baseline

---

## Drift detection severity

| Level    | Examples |
|----------|---------|
| CRITICAL | Container added or removed |
| HIGH     | Image, IP, network, privilege changed |
| MEDIUM   | Volumes, ports, restart policy, devices |
| LOW      | Env vars, labels, capabilities |
| INFO     | Status change only |

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
tests/              223 tests, all mocked (no live Docker)
config/             settings.yaml
```

---

## Deployment guides

- [QNAP NAS](docs/QNAP_DEPLOYMENT.md) — Docker-based deployment, alias setup, cron automation
- Synology — coming soon (contributions welcome)

---

## Adding a new platform

See [CONTRIBUTING.md](CONTRIBUTING.md).
Subclass `BasePlatform`, add detection to `detector.py`, write tests.

---

## Running tests

```bash
python tests/test_inspector_snapshot.py  # 33
python tests/test_updater_pruner.py      # 37
python tests/test_drift.py               # 48
python tests/test_tui.py                 # 51
python tests/test_daemon.py              # 54
```

## License

MIT — see [LICENSE](LICENSE).
