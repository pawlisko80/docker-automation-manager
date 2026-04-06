---
name: Bug Report
about: Something isn't working as expected
title: '[BUG] '
labels: bug
assignees: ''
---

## Describe the bug
A clear description of what went wrong.

## Environment
- **Platform:** (QNAP / Synology / Generic Linux / other)
- **OS / firmware version:**
- **Docker version:** (run `docker --version`)
- **Python version:** (run `python3 --version`)
- **DAM version:** (run `dam --version`)

## Steps to reproduce
1. Run `dam ...`
2. See error

## Expected behaviour
What you expected to happen.

## Actual behaviour
What actually happened. Please include full error output:

```
paste error output here
```

## Container list
Output of `dam --status` or `docker ps -a`:

```
paste here
```

## Snapshot (if relevant)
Contents of your latest snapshot from `snapshots/latest.yaml` (redact any sensitive values):

```yaml
paste here
```

## Additional context
Any other relevant info — network setup, custom settings.yaml, etc.
