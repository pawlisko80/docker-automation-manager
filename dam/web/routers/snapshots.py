"""
dam/web/routers/snapshots.py

GET /api/snapshots           — list all snapshots
GET /api/snapshots/latest    — latest snapshot container list
GET /api/snapshots/{index}   — specific snapshot by index
GET /api/drift               — drift: latest snapshot vs live containers
GET /api/drift/snapshots     — drift: last snapshot vs previous snapshot
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["snapshots"])


@router.get("/api/snapshots")
async def list_snapshots():
    """List all saved snapshots."""
    from dam.web.server import _get_snapshot_manager

    sm = _get_snapshot_manager()
    snapshots = sm.list_snapshots()

    return [
        {
            "index": i,
            "filename": p.name,
            "size_kb": round(p.stat().st_size / 1024, 1),
            "label": p.stem.split("_", 3)[3] if len(p.stem.split("_")) > 3 else "",
        }
        for i, p in enumerate(snapshots)
    ]


@router.get("/api/snapshots/latest")
async def get_latest_snapshot():
    """Return containers from the latest snapshot."""
    from dam.web.server import _get_snapshot_manager
    from dam.web.routers.containers import _serialize_config

    sm = _get_snapshot_manager()
    result = sm.load_latest()
    if not result:
        raise HTTPException(status_code=404, detail="No snapshots found")

    meta, configs = result
    return {
        "metadata": meta,
        "containers": [_serialize_config(c) for c in configs],
    }


@router.get("/api/snapshots/{index}")
async def get_snapshot(index: int):
    """Return a specific snapshot by index (0 = newest)."""
    from dam.web.server import _get_snapshot_manager
    from dam.web.routers.containers import _serialize_config

    sm = _get_snapshot_manager()
    snapshots = sm.list_snapshots()

    if index < 0 or index >= len(snapshots):
        raise HTTPException(status_code=404, detail=f"Snapshot index {index} not found")

    result = sm.load(snapshots[index])
    if not result:
        raise HTTPException(status_code=500, detail="Failed to load snapshot")

    meta, configs = result
    return {
        "metadata": meta,
        "containers": [_serialize_config(c) for c in configs],
    }


@router.get("/api/drift")
async def drift_vs_live():
    """Compare latest snapshot against live container state."""
    from dam.web.server import _get_inspector, _get_settings, _get_snapshot_manager
    from dam.core.drift import DriftDetector

    sm = _get_snapshot_manager()
    result = sm.load_latest()
    if not result:
        raise HTTPException(status_code=404, detail="No snapshots found — run an update first")

    snap_meta, snap_configs = result

    inspector = _get_inspector()
    settings = _get_settings()
    live_configs = inspector.inspect_all(
        settings_containers=settings.get("containers", {}) or {}
    )

    detector = DriftDetector()
    report = detector.compare(
        snap_configs, live_configs,
        label_a=f"snapshot ({snap_meta['captured_at']})",
        label_b="live",
    )

    return _serialize_drift_report(report)


@router.get("/api/drift/snapshots")
async def drift_between_snapshots():
    """Compare last snapshot against the previous one."""
    from dam.web.server import _get_snapshot_manager
    from dam.core.drift import DriftDetector

    sm = _get_snapshot_manager()
    latest = sm.load_latest()
    previous = sm.load_previous(skip=1)

    if not latest:
        raise HTTPException(status_code=404, detail="No snapshots found")
    if not previous:
        raise HTTPException(status_code=404, detail="Only one snapshot — need at least two to compare")

    prev_meta, prev_configs = previous
    snap_meta, snap_configs = latest

    detector = DriftDetector()
    report = detector.compare(
        prev_configs, snap_configs,
        label_a=f"snapshot ({prev_meta['captured_at']})",
        label_b=f"snapshot ({snap_meta['captured_at']})",
    )

    return _serialize_drift_report(report)


def _serialize_drift_report(report) -> dict:
    """Serialize a DriftReport to a JSON-safe dict."""
    return {
        "has_drift": report.has_drift,
        "label_a": report.snapshot_a_label,
        "label_b": report.snapshot_b_label,
        "summary": report.summary(),
        "items": [
            {
                "container_name": item.container_name,
                "field": item.field,
                "severity": item.severity.value,
                "description": item.description,
                "old_value": item.old_value,
                "new_value": item.new_value,
            }
            for item in report.sorted_by_severity()
        ],
    }
