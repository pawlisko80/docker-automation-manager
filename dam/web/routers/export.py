"""
dam/web/routers/export.py

POST /api/export   — export containers in chosen format, return as download
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/export", tags=["export"])


class ExportRequest(BaseModel):
    containers: Optional[list[str]] = None   # None = all
    format: str = "dam-yaml"                 # dam-yaml | docker-run | compose
    single_file: bool = True


@router.post("")
async def export_containers(body: ExportRequest):
    """
    Export containers in the specified format.
    Returns the exported file(s) as a downloadable zip if multiple,
    or a single file directly.
    """
    from dam.web.server import _get_inspector, _get_settings
    from dam.core.exporter import Exporter, FORMATS

    if body.format not in FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid format '{body.format}'. Choose from: {', '.join(FORMATS)}"
        )

    inspector = _get_inspector()
    settings = _get_settings()
    configs = inspector.inspect_all(
        settings_containers=settings.get("containers", {}) or {}
    )

    if body.containers:
        configs = [c for c in configs if c.name in body.containers]
        if not configs:
            raise HTTPException(status_code=404, detail="No matching containers found")

    tmpdir = Path(tempfile.mkdtemp())
    exporter = Exporter()
    paths = exporter.export(configs, body.format, tmpdir, single_file=body.single_file)

    if not paths:
        raise HTTPException(status_code=500, detail="Export produced no files")

    if len(paths) == 1:
        path = paths[0]
        media_types = {
            ".yaml": "application/yaml",
            ".sh":   "text/x-shellscript",
            ".yml":  "application/yaml",
        }
        media_type = media_types.get(path.suffix, "application/octet-stream")
        return FileResponse(
            path=str(path),
            filename=path.name,
            media_type=media_type,
        )

    # Multiple files — zip them
    import zipfile
    zip_path = tmpdir / "dam-export.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for p in paths:
            zf.write(p, p.name)

    return FileResponse(
        path=str(zip_path),
        filename="dam-export.zip",
        media_type="application/zip",
    )
