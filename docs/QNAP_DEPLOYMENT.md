# Deploying DAM on QNAP NAS

QNAP ships with Python 2.7 as default and an optional Python 3.7 package — both too old or too broken to run DAM directly. The solution is to run DAM inside a Docker container on the QNAP itself, mounting the Docker socket so DAM can manage your other containers.

---

## Prerequisites

- QNAP NAS with Docker (Container Station) installed and running
- SSH access to your QNAP
- DAM source files copied to `/share/Container/docker-automation-manager/`

---

## Step 1 — Copy DAM to your QNAP

**From your Mac or PC:**

```bash
scp ~/Downloads/docker-automation-manager-v0.1.0.zip admin@YOUR_QNAP_IP:/share/Container/
```

**On QNAP (via SSH):**

```bash
cd /share/Container
unzip docker-automation-manager-v0.1.0.zip
```

Alternatively, if you want to stay up to date with the latest version, install Git via QNAP App Center (search "Git") and clone directly:

```bash
cd /share/Container
git clone https://github.com/pawlisko80/docker-automation-manager.git
```

---

## Step 2 — Run DAM

DAM runs inside a `python:3.11-slim` container with two mounts:
- `/var/run/docker.sock` — gives DAM access to the Docker daemon
- `/share/Container/docker-automation-manager` — the DAM source directory

```bash
docker run -it --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /share/Container/docker-automation-manager:/app \
  -w /app \
  python:3.11-slim \
  bash -c "pip install -r requirements.txt -q --root-user-action=ignore --disable-pip-version-check && pip install -e . -q --root-user-action=ignore --disable-pip-version-check && dam"
```

On first run this pulls the `python:3.11-slim` image (~50MB). Subsequent runs reuse the cached image and start in a few seconds.

---

## Step 3 — Create a `dam` alias (recommended)

Add a permanent alias so you can just type `dam`:

```bash
echo "alias dam='docker run -it --rm -v /var/run/docker.sock:/var/run/docker.sock -v /share/Container/docker-automation-manager:/app -w /app python:3.11-slim bash -c \"pip install -r requirements.txt -q --root-user-action=ignore --disable-pip-version-check && pip install -e . -q --root-user-action=ignore --disable-pip-version-check && dam\"'" >> ~/.profile
source ~/.profile
```

Now just run:

```bash
dam
```

---

## Step 4 — Verify it works

On first launch you should see:

```
╭──────────────────────────────────────────────────────────────╮
│  🐳 Docker Automation Manager v0.1.0    Platform: QNAP  ...  │
╰──────────────────────────────────────────────────────────────╯
```

Note **Platform: QNAP** — DAM auto-detects the QNAP environment and applies the correct network driver handling for `macvlan` and `qnet` static IP networks.

Select **[1] Status** to confirm all your containers are visible with correct IPs.

---

## Monthly update workflow

```bash
# SSH into QNAP
ssh admin@YOUR_QNAP_IP

# Launch DAM
dam

# Select [2] Update → Dry run: n → Proceed: y
# DAM will pull images, compare digests, and recreate only changed containers
# All static IPs and settings are preserved automatically
```

---

## Automating monthly updates (optional)

To run DAM automatically on a schedule, add a cron entry to QNAP's persistent crontab:

```bash
# Edit crontab
vi /etc/config/crontab

# Add this line (runs at 2 AM on the 1st of every month):
0 2 1 * * docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v /share/Container/docker-automation-manager:/app -w /app python:3.11-slim bash -c "pip install -r requirements.txt -q --root-user-action=ignore --disable-pip-version-check && pip install -e . -q --root-user-action=ignore --disable-pip-version-check && dam --update --yes" >> /share/Container/docker-automation-manager/logs/dam-cron.log 2>&1

# Reload crontab (required on QNAP)
crontab /etc/config/crontab
```

---

## Updating DAM itself

When a new version of DAM is released:

```bash
cd /share/Container/docker-automation-manager

# If installed via git clone:
git pull

# If installed via zip: download new zip, unzip, replace folder
```

The `python:3.11-slim` container always installs the latest dependencies from `requirements.txt` on each run, so no further steps are needed.

---

## Troubleshooting

**`python3: command not found`**
QNAP's built-in Python 3.7 is at `/usr/local/Python3/bin/python3` but is missing `runpy` and other standard modules. Always use the Docker-based approach above — do not try to run DAM with QNAP's native Python.

**`git: command not found`**
Install Git from QNAP App Center, or use the scp/zip approach instead.

**`pip3: command not found`**
Same issue — use the Docker-based approach. Do not try to install pip into QNAP's Python environment.

**DAM shows a container named `recursing_xxxxx` (or similar)**
That's the DAM container itself. It appears in the status list but is excluded from updates automatically (it has restart policy `no` and will be skipped).

**Permission denied on `/var/run/docker.sock`**
Make sure you are running the docker command as the `admin` user or a user in the `docker` group on your QNAP.
