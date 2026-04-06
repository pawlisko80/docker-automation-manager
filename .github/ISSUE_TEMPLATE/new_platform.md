---
name: New Platform Adapter
about: Add support for a new NAS or Docker host platform
title: '[PLATFORM] Add support for '
labels: platform, enhancement
assignees: ''
---

## Platform details
- **Name:** (e.g. Unraid, TrueNAS, OpenMediaVault)
- **OS base:** (e.g. Slackware, Debian, FreeBSD)
- **Docker install method:** (built-in / community plugin / manual)
- **Python availability:** (built-in / pip / unavailable)

## Network specifics
- Default Docker network driver:
- Does it support macvlan with static IPs?
- Any proprietary network drivers?

## Path conventions
- Default container data location:
- Where should DAM store logs?

## Daemon / scheduler
- Is systemd available?
- Cron path / method:
- Any special reload steps needed after cron edit?

## Detection fingerprints
What files or markers uniquely identify this platform?
(e.g. `/etc/unraid-version`, `/usr/bin/mdcmd`)

## Are you willing to test a PR?
- [ ] Yes, I can test on real hardware
- [ ] Yes, I can test in a VM
- [ ] No, submitting for community interest only
