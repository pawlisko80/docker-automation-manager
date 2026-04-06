"""
dam/web/routers/containers.py

REST endpoints for container status, updates, and EOL checks.

GET  /api/containers              — list all containers with full config
POST /api/containers/update       — dry-run update (returns plan)
POST /api/containers/update/apply — apply update (confirmed)
GET  /api/containers/eol          — EOL/deprecation check
POST /api/containers/prune        — prune unused images
GET  /api/containers/update/stream — SSE live progress stream
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/containers", tags=["containers"])


# ------------------------------------------------------------
# Request / Response models
# ------------------------------------------------------------

class UpdateRequest(BaseModel):
    containers: Optional[list[str]] = None   # None = all
    dry_run: bool = True


class PruneRequest(BaseModel):
    remove_all: bool = False


# ------------------------------------------------------------
# Helper: get shared app state
# ------------------------------------------------------------

def get_state(request):
    return request.app.state


# ------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------

@router.get("")
async def list_containers(request_obj=None):
    """Return all containers with their current config."""
    from fastapi import Request
    return _list_containers_impl()


def _list_containers_impl():
    """Shared implementation callable from both HTTP and SSE."""
    from dam.web.server import _get_inspector, _get_settings
    inspector = _get_inspector()
    settings = _get_settings()
    configs = inspector.inspect_all(
        settings_containers=settings.get("containers", {}) or {}
    )
    return [_serialize_config(c) for c in configs]


def _serialize_config(cfg) -> dict:
    """Serialize a ContainerConfig to a JSON-safe dict."""
    return {
        "name": cfg.name,
        "image": cfg.image,
        "image_id": cfg.image_id[:19] if cfg.image_id else "",
        "status": cfg.status,
        "restart_policy": cfg.restart_policy,
        "network_mode": cfg.network_mode,
        "ip": cfg.primary_ip(),
        "network": cfg.primary_network(),
        "binds": cfg.binds,
        "env": cfg.env,
        "privileged": cfg.privileged,
        "version_strategy": cfg.version_strategy,
        "ports": [
            {"container": p.container_port, "host": p.host_port}
            for p in cfg.ports
        ],
        "volume_count": len(cfg.binds),
    }


@router.post("/update")
async def plan_update(body: UpdateRequest):
    """
    Dry-run update — pull images and compare digests.
    Returns what would change without making any modifications.
    Always dry_run=True here; use /update/apply to execute.
    """
    from dam.web.server import _get_inspector, _get_settings, _get_platform
    from dam.core.updater import Updater

    inspector = _get_inspector()
    settings = _get_settings()
    platform = _get_platform()

    configs = inspector.inspect_all(
        settings_containers=settings.get("containers", {}) or {}
    )
    if body.containers:
        configs = [c for c in configs if c.name in body.containers]

    updater = Updater(platform=platform, dry_run=True, recreate_delay=0)
    results = updater.update_all(configs)
    summary = Updater.summarize(results)

    return {
        "dry_run": True,
        "summary": summary,
        "results": [
            {
                "name": r.container_name,
                "status": r.status.value,
                "old_image_id": r.old_image_id[:19] if r.old_image_id else None,
                "new_image_id": r.new_image_id[:19] if r.new_image_id else None,
                "duration": round(r.duration_seconds, 1),
                "error": r.error,
            }
            for r in results
        ],
    }


@router.post("/update/apply")
async def apply_update(body: UpdateRequest):
    """
    Execute update — only call after dry-run confirmation.
    Pulls new images, recreates changed containers.
    """
    from dam.web.server import _get_inspector, _get_settings, _get_platform
    from dam.core.updater import Updater
    from dam.core.snapshot import SnapshotManager

    inspector = _get_inspector()
    settings = _get_settings()
    platform = _get_platform()
    dam_cfg = settings.get("dam", {})

    configs = inspector.inspect_all(
        settings_containers=settings.get("containers", {}) or {}
    )
    if body.containers:
        configs = [c for c in configs if c.name in body.containers]

    # Snapshot before
    sm = SnapshotManager(retention=dam_cfg.get("snapshot_retention", 10))
    sm.save(configs, platform, label="web-pre-update")

    updater = Updater(
        platform=platform,
        dry_run=False,
        recreate_delay=dam_cfg.get("recreate_delay", 5),
    )
    results = updater.update_all(configs)
    summary = Updater.summarize(results)

    # Auto-prune if configured
    if dam_cfg.get("auto_prune", True) and summary["updated"] > 0:
        from dam.core.pruner import Pruner
        pruner = Pruner(dry_run=False)
        pruner.prune(results)

    # Post-update snapshot
    try:
        post_configs = inspector.inspect_all(
            settings_containers=settings.get("containers", {}) or {}
        )
        sm.save(post_configs, platform, label="web-post-update")
    except Exception:
        pass

    return {
        "dry_run": False,
        "summary": summary,
        "results": [
            {
                "name": r.container_name,
                "status": r.status.value,
                "old_image_id": r.old_image_id[:19] if r.old_image_id else None,
                "new_image_id": r.new_image_id[:19] if r.new_image_id else None,
                "duration": round(r.duration_seconds, 1),
                "error": r.error,
            }
            for r in results
        ],
    }


@router.get("/eol")
async def check_eol():
    """Check all containers for deprecated or EOL images."""
    from dam.web.server import _get_inspector, _get_settings
    from dam.core.deprecation import DeprecationChecker

    inspector = _get_inspector()
    settings = _get_settings()
    configs = inspector.inspect_all(
        settings_containers=settings.get("containers", {}) or {}
    )
    checker = DeprecationChecker()
    results = checker.check_all(configs)
    summary = checker.summary(results)

    return {
        "summary": summary,
        "results": [
            {
                "container_name": r.container_name,
                "image": r.image,
                "status": r.status.value,
                "severity": r.severity.value,
                "reason": r.reason,
                "deprecated_date": r.deprecated_date,
                "alternatives": [
                    {"name": a.name, "url": a.url, "note": a.note}
                    for a in r.alternatives
                ],
            }
            for r in results
        ],
    }


@router.post("/prune")
async def prune_images(body: PruneRequest):
    """Remove unused Docker images."""
    from dam.core.pruner import Pruner

    pruner = Pruner(dry_run=False, remove_unreferenced=body.remove_all)
    result = pruner.prune()

    return {
        "images_removed": len(result.images_removed),
        "space_reclaimed": result.space_reclaimed_human,
        "errors": result.errors,
    }
