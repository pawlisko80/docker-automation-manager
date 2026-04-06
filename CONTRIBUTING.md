# Contributing to docker-automation-manager

Thank you for your interest in contributing! DAM is designed to be extended
by the community — especially for new platform adapters.

---

## Getting started

```bash
git clone https://github.com/yourusername/docker-automation-manager
cd docker-automation-manager
pip install -r requirements.txt
pip install -e .
```

Run the test suite to confirm everything works:

```bash
python tests/test_inspector_snapshot.py
python tests/test_updater_pruner.py
python tests/test_drift.py
python tests/test_tui.py
python tests/test_daemon.py
```

All 223 tests should pass before you start making changes.

---

## Project structure

```
dam/
├── core/           # Engine: inspect, snapshot, update, prune, drift
├── platform/       # Platform adapters: QNAP, Synology, generic, base
├── daemon/         # Scheduler + service lifecycle
├── tui.py          # Rich terminal UI
├── cli.py          # Click CLI entry point
└── main.py         # Binary entry point
tests/              # One test file per module
config/             # settings.yaml
```

---

## Adding a new platform adapter

This is the most valuable contribution you can make.

### 1. Create `dam/platform/yourplatform.py`

Subclass `BasePlatform` and implement all abstract methods:

```python
from dam.platform.base import BasePlatform

class UnraidPlatform(BasePlatform):
    name = "Unraid"

    def is_static_ip_network(self, network_name: str) -> bool:
        ...

    def get_network_driver(self, network_name: str) -> Optional[str]:
        ...

    def get_default_data_root(self) -> str:
        return "/mnt/user/appdata"

    def get_default_log_root(self) -> str:
        return "/mnt/user/appdata/dam/logs"

    def supports_systemd(self) -> bool:
        return False

    def get_cron_path(self) -> str:
        return "/etc/cron.d/dam"
```

### 2. Add detection logic to `dam/platform/detector.py`

```python
_UNRAID_MARKERS = [
    "/etc/unraid-version",
    "/usr/bin/mdcmd",
]

# In detect_platform():
if _file_exists_any(_UNRAID_MARKERS):
    return UnraidPlatform()
```

### 3. Write tests

Add platform-specific tests to `tests/test_inspector_snapshot.py`
(use the `make_qnap_platform()` pattern as a template).

### 4. Update README

Add your platform to the "Supported Platforms" table in `README.md`.

---

## Code style

- Python 3.10+ — use `from __future__ import annotations` for forward refs
- Type hints on all public functions and method signatures
- Docstrings on all public classes and methods
- Max line length: 120 characters
- No external dependencies beyond what's in `requirements.txt`
  (the codebase must run on minimal NAS Python environments)

---

## Testing guidelines

- Every new function should have at least one test
- Tests must not require a live Docker daemon (mock with `unittest.mock`)
- Tests must not write outside `tempfile.TemporaryDirectory()`
- Test names: `test_<what>_<condition>` e.g. `test_parse_cron_invalid_raises`

---

## Pull request checklist

- [ ] All existing tests pass
- [ ] New tests added for new code
- [ ] Docstrings added/updated
- [ ] README updated if user-facing behaviour changed
- [ ] CHANGELOG.md entry added under `[Unreleased]`
- [ ] Tested on real hardware if possible (especially for platform adapters)

---

## Reporting bugs

Use the [Bug Report](.github/ISSUE_TEMPLATE/bug_report.md) template.
Include your platform, DAM version, and `dam --status` output.

## Requesting features

Use the [Feature Request](.github/ISSUE_TEMPLATE/feature_request.md) template.

## Adding platform support

Use the [New Platform](.github/ISSUE_TEMPLATE/new_platform.md) template
before opening a PR — it helps us understand the platform specifics.

---

## License

By contributing, you agree your contributions will be licensed under the MIT License.
