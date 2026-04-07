"""
dam/web/server.py - FastAPI web server for Docker Automation Manager v0.4.0
"""
from __future__ import annotations
import asyncio, hashlib, json, secrets, time
from pathlib import Path
from typing import Optional, AsyncGenerator
import yaml
from fastapi import FastAPI, HTTPException, Depends, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from dam import __version__
from dam.core.deprecation import DeprecationChecker
from dam.core.drift import DriftDetector
from dam.core.exporter import Exporter, FORMATS
from dam.core.inspector import Inspector, ContainerConfig
from dam.core.pruner import Pruner
from dam.core.snapshot import SnapshotManager
from dam.core.updater import Updater
from dam.platform.detector import detect_platform

app = FastAPI(title="Docker Automation Manager", version=__version__, docs_url="/api/docs")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

_platform = None
_snapshot_manager = None
_settings = {}
_config_path = None
_sse_queues: dict[str, asyncio.Queue] = {}
_sessions: dict[str, float] = {}
SESSION_TTL = 3600 * 8

@app.on_event("startup")
async def startup():
    global _platform, _snapshot_manager, _settings
    _platform = detect_platform()
    cfg_path = _config_path or Path(__file__).parent.parent.parent / "config" / "settings.yaml"
    try:
        with open(cfg_path) as f:
            _settings = yaml.safe_load(f) or {}
    except FileNotFoundError:
        _settings = {}
    _snapshot_manager = SnapshotManager(retention=_settings.get("dam", {}).get("snapshot_retention", 10))

def _hash_password(p): return hashlib.sha256(p.encode()).hexdigest()

def _check_credentials(username, password):
    w = _settings.get("web", {})
    cfg_user = w.get("username", "admin")
    cfg_hash = w.get("password_hash", "")
    if not cfg_hash: return username == cfg_user
    if cfg_hash.startswith("sha256:"):
        parts = cfg_hash.split(":", 2)
        if len(parts) == 3:
            import hashlib as _hl
            _, salt, h = parts
            return username == cfg_user and secrets.compare_digest(_hl.sha256(f"{salt}{password}".encode()).hexdigest(), h)
    return username == cfg_user and _hash_password(password) == cfg_hash

def _is_authenticated(request: Request):
    token = request.cookies.get("dam_session")
    if not token: return False
    expiry = _sessions.get(token, 0)
    if time.time() > expiry:
        _sessions.pop(token, None); return False
    _sessions[token] = time.time() + SESSION_TTL
    return True

def require_auth(request: Request):
    if not _is_authenticated(request):
        raise HTTPException(status_code=401, detail="Not authenticated")

def _cfg_to_dict(cfg: ContainerConfig) -> dict:
    ports = []
    for p in cfg.ports:
        hp = p.host_port
        https = hp in ("443","8443","9443") or p.container_port.startswith("443")
        scheme = "https" if https else "http"
        ip = cfg.primary_ip() or "localhost"
        ports.append({"container": p.container_port, "host": hp, "host_ip": p.host_ip,
                      "link": f"{scheme}://{ip}:{hp}" if hp else None, "https": https})
    labels = cfg.labels or {}
    tags = [t.strip() for t in labels.get("dockpeek.tags","").split(",") if t.strip()]
    tags += [t.strip() for t in labels.get("dam.tags","").split(",") if t.strip()]

    # Extra ports: label-defined > ExposedPorts > well-known port map
    label_ports = [p.strip() for p in (labels.get("dockpeek.ports") or labels.get("dam.ports","")).split(",") if p.strip()]
    _WELL_KNOWN = {
        "home-assistant": "8123", "homeassistant": "8123",
        "portainer": "9000", "grafana": "3000", "prometheus": "9090",
        "node-red": "1880", "nodered": "1880", "mosquitto": "1883",
        "pihole": "80", "adguardhome": "3000", "nextcloud": "80",
        "jellyfin": "8096", "plex": "32400", "emby": "8096",
        "sonarr": "8989", "radarr": "7878", "lidarr": "8686",
        "prowlarr": "9696", "bazarr": "6767", "readarr": "8787",
        "overseerr": "5055", "transmission": "9091", "deluge": "8112",
        "nzbget": "6789", "sabnzbd": "8080",
        "uptime-kuma": "3001", "vaultwarden": "80", "gitea": "3000",
    }
    # Check well-known port env vars before anything else
    _PORT_ENV_KEYS = ["WEB_PORT", "HTTP_PORT", "PORT", "APP_PORT", "SERVER_PORT",
                      "WEBUI_PORT", "UI_PORT", "DASHBOARD_PORT"]
    env_port = None
    for key in _PORT_ENV_KEYS:
        val = (cfg.env or {}).get(key, "").strip()
        if val and val.isdigit():
            env_port = val
            break

    exposed_ports = []
    if not cfg.ports and not label_ports:
        _SKIP = {"6881", "6882", "1900", "5353", "51820"}
        _UI_PORTS = {"80","443","3000","3001","4000","5000","6052","8000","8008",
                     "8080","8081","8096","8123","8443","8888","9000","9090","9091","9443"}
        _raw = []
        for ep in (cfg.exposed_ports or []):
            port_num = ep.split("/")[0]
            if port_num and port_num not in _SKIP:
                _raw.append(port_num)
        # env var port wins, then UI ports first
        if env_port:
            exposed_ports.append(env_port)
        seen = {env_port} if env_port else set()
        for p in sorted(_raw, key=lambda x: (0 if x in _UI_PORTS else 1, int(x) if x.isdigit() else 0)):
            if p not in seen:
                seen.add(p)
                exposed_ports.append(p)
        if not exposed_ports:
            image_lower = cfg.image.lower().split(":")[0].split("/")[-1]
            for key, port in _WELL_KNOWN.items():
                if key in image_lower:
                    exposed_ports.append(port)
                    break

    container_ip = cfg.primary_ip() or ("__host__" if cfg.network_mode == "host" else None)

    # Build auto_link from resolved IP + first available port
    def _make_auto_link(ip, port_list, extra_list):
        port = (port_list[0]["host"] if port_list else None) or (extra_list[0] if extra_list else None)
        if not port:
            return None
        host = ip if ip and ip != "__host__" else None
        # host_mode: link built in frontend using window.location.hostname
        if not host and cfg.network_mode != "host":
            return None
        if cfg.network_mode == "host":
            return f"__host__:{port}"
        https = port in ("443", "8443", "9443")
        scheme = "https" if https else "http"
        return f"{scheme}://{host}:{port}"
    return {"name": cfg.name, "image": cfg.image, "image_id": cfg.image_id[:19] if cfg.image_id else "",
            "status": cfg.status, "restart_policy": cfg.restart_policy, "network_mode": cfg.network_mode,
            "ip": cfg.primary_ip(), "host_mode": cfg.network_mode == "host", "network": cfg.primary_network(), "binds": cfg.binds,
            "env": cfg.env, "privileged": cfg.privileged, "version_strategy": cfg.version_strategy,
            "ports": ports, "tags": tags,
            "custom_link": labels.get("dockpeek.link") or labels.get("dam.link"),
            "auto_link": _make_auto_link(container_ip, ports, label_ports or exposed_ports),
            "extra_ports": label_ports or exposed_ports,
            "labels": labels}

class LoginRequest(BaseModel):
    username: str; password: str

class UpdateRequest(BaseModel):
    containers: list[str] = []

class ExportRequest(BaseModel):
    containers: list[str] = []; fmt: str = "dam-yaml"

@app.post("/auth/login")
async def login(req: LoginRequest, response: Response):
    if not _check_credentials(req.username, req.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = secrets.token_hex(32)
    _sessions[token] = time.time() + SESSION_TTL
    response.set_cookie(key="dam_session", value=token, httponly=True, max_age=SESSION_TTL, samesite="lax")
    return {"status": "ok"}

@app.post("/auth/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("dam_session")
    if token: _sessions.pop(token, None)
    response.delete_cookie("dam_session")
    return {"status": "ok"}

@app.get("/auth/status")
async def auth_status(request: Request):
    return {"authenticated": _is_authenticated(request)}

@app.get("/health")
async def health():
    return {"status": "ok", "version": __version__, "platform": _platform.name if _platform else "unknown"}

@app.get("/api/containers")
async def get_containers(request: Request, _=Depends(require_auth)):
    try:
        inspector = Inspector(_platform)
        configs = inspector.inspect_all(settings_containers=_settings.get("containers", {}) or {})
        return {"containers": [_cfg_to_dict(c) for c in configs]}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

def _container_action(name: str, action: str) -> dict:
    try:
        import docker
        from docker.errors import NotFound
        client = docker.from_env()
        try: container = client.containers.get(name)
        except NotFound: raise HTTPException(status_code=404, detail=f"Container not found: {name}")
        getattr(container, action)()
        container.reload()
        return {"name": name, "action": action, "status": container.status}
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/containers/{name}/start")
async def container_start(name: str, _=Depends(require_auth)):
    return _container_action(name, "start")

@app.post("/api/containers/{name}/stop")
async def container_stop(name: str, _=Depends(require_auth)):
    return _container_action(name, "stop")

@app.post("/api/containers/{name}/restart")
async def container_restart(name: str, _=Depends(require_auth)):
    return _container_action(name, "restart")

@app.get("/api/containers/{name}/logs")
async def container_logs(name: str, tail: int = 200, follow: bool = False,
                         request: Request = None, _=Depends(require_auth)):
    import docker
    from docker.errors import NotFound
    try:
        client = docker.from_env()
        client.containers.get(name)
    except NotFound:
        raise HTTPException(status_code=404, detail=f"Container not found: {name}")
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

    async def log_generator() -> AsyncGenerator[str, None]:
        import docker
        client = docker.from_env()
        try:
            container = client.containers.get(name)
            log_stream = container.logs(stream=follow, follow=follow, tail=tail, timestamps=True)
            if follow:
                for chunk in log_stream:
                    if request and await request.is_disconnected(): break
                    line = chunk.decode("utf-8", errors="replace").rstrip()
                    yield "data: " + json.dumps({"line": line}) + "\n\n"

                    await asyncio.sleep(0)
            else:
                lines = log_stream.decode("utf-8", errors="replace").splitlines()
                for line in lines[-tail:]:
                    yield "data: " + json.dumps({"line": line}) + "\n\n"

                yield "data: " + json.dumps({"done": True}) + "\n\n"
        except Exception as e:
            yield "data: " + json.dumps({"error": str(e)}) + "\n\n"

    return StreamingResponse(log_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.get("/api/eol")
async def get_eol(request: Request, _=Depends(require_auth)):
    try:
        inspector = Inspector(_platform)
        configs = inspector.inspect_all(settings_containers=_settings.get("containers", {}) or {})
        checker = DeprecationChecker()
        results = checker.check_all(configs)
        return {"results": [{"container_name": r.container_name, "image": r.image,
            "status": r.status.value, "severity": r.severity.value, "reason": r.reason,
            "alternatives": [{"name": a.name, "url": a.url, "note": a.note} for a in r.alternatives]}
            for r in results], "summary": checker.summary(results)}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

@app.get("/api/snapshots")
async def get_snapshots(_=Depends(require_auth)):
    return {"snapshots": [{"id": i, "filename": p.name, "size_kb": round(p.stat().st_size/1024, 1)}
        for i, p in enumerate(_snapshot_manager.list_snapshots())]}

@app.get("/api/snapshots/{snapshot_id}")
async def get_snapshot(snapshot_id: int, _=Depends(require_auth)):
    snaps = _snapshot_manager.list_snapshots()
    if snapshot_id >= len(snaps): raise HTTPException(status_code=404, detail="Not found")
    meta, configs = _snapshot_manager.load(snaps[snapshot_id])
    return {"meta": meta, "containers": [_cfg_to_dict(c) for c in configs]}

@app.get("/api/drift")
async def get_drift(_=Depends(require_auth)):
    result = _snapshot_manager.load_latest()
    if not result: return {"has_drift": False, "items": [], "summary": {}, "message": "No snapshots yet"}
    snap_meta, snap_configs = result
    try:
        inspector = Inspector(_platform)
        live = inspector.inspect_all(settings_containers=_settings.get("containers", {}) or {})
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    report = DriftDetector().compare(snap_configs, live, f"snapshot ({snap_meta['captured_at']})", "live")
    return {"has_drift": report.has_drift, "summary": report.summary(),
        "snapshot_label": snap_meta.get("captured_at", "unknown"),
        "items": [{"container_name": i.container_name, "field": i.field, "severity": i.severity.value,
            "description": i.description, "old_value": i.old_value, "new_value": i.new_value}
            for i in report.sorted_by_severity()]}

@app.post("/api/update/dry-run")
async def update_dry_run(req: UpdateRequest, _=Depends(require_auth)):
    try:
        inspector = Inspector(_platform)
        all_cfgs = inspector.inspect_all(settings_containers=_settings.get("containers", {}) or {})
        configs = [c for c in all_cfgs if not req.containers or c.name in req.containers]
        results = Updater(platform=_platform, dry_run=True, recreate_delay=0).update_all(configs)
        return {"results": [{"container_name": r.container_name, "status": r.status.value,
            "old_image_id": r.old_image_id[:19] if r.old_image_id else None,
            "new_image_id": r.new_image_id[:19] if r.new_image_id else None,
            "would_update": r.status.value == "dry_run", "error": r.error} for r in results],
            "summary": Updater.summarize(results)}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

@app.post("/api/update/run")
async def update_run(req: UpdateRequest, _=Depends(require_auth)):
    session_id = secrets.token_hex(16)
    queue: asyncio.Queue = asyncio.Queue()
    _sse_queues[session_id] = queue
    async def run():
        try:
            inspector = Inspector(_platform)
            all_cfgs = inspector.inspect_all(settings_containers=_settings.get("containers", {}) or {})
            configs = [c for c in all_cfgs if not req.containers or c.name in req.containers]
            _snapshot_manager.save(configs, _platform, label="pre-update-web")
            dam_cfg = _settings.get("dam", {})
            def on_progress(name, msg):
                asyncio.get_event_loop().call_soon_threadsafe(queue.put_nowait,
                    json.dumps({"type": "progress", "container": name, "message": msg}))
            updater = Updater(platform=_platform, dry_run=False,
                recreate_delay=dam_cfg.get("recreate_delay", 5), progress_callback=on_progress)
            results = []
            for cfg in configs:
                r = updater.update_one(cfg)
                results.append(r)
                await queue.put(json.dumps({"type": "result", "container": r.container_name,
                    "status": r.status.value, "error": r.error}))
            summary = Updater.summarize(results)
            if dam_cfg.get("auto_prune", True) and summary["updated"] > 0:
                await queue.put(json.dumps({"type": "progress", "container": "", "message": "Pruning old images..."}))
                Pruner(dry_run=False).prune(results)
            await queue.put(json.dumps({"type": "done", "summary": summary}))
        except Exception as e:
            await queue.put(json.dumps({"type": "error", "message": str(e)}))
        finally:
            await asyncio.sleep(30)
            _sse_queues.pop(session_id, None)
    asyncio.create_task(run())
    return {"session_id": session_id}

@app.get("/api/update/stream/{session_id}")
async def update_stream(session_id: str, request: Request, _=Depends(require_auth)):
    queue = _sse_queues.get(session_id)
    if not queue: raise HTTPException(status_code=404, detail="Session not found")
    async def gen() -> AsyncGenerator[str, None]:
        while True:
            if await request.is_disconnected(): break
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=30)
                yield f"data: {msg}\n\n"
                if json.loads(msg).get("type") in ("done", "error"): break
            except asyncio.TimeoutError:
                yield 'data: {"type":"ping"}\n\n'
    return StreamingResponse(gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.post("/api/prune/dry-run")
async def prune_dry_run(_=Depends(require_auth)):
    return Pruner(dry_run=True).list_candidates()

@app.post("/api/prune/run")
async def prune_run(_=Depends(require_auth)):
    result = Pruner(dry_run=False).prune()
    return {"images_removed": len(result.images_removed),
        "space_reclaimed_human": result.space_reclaimed_human, "errors": result.errors}

@app.post("/api/export")
async def export_containers(req: ExportRequest, _=Depends(require_auth)):
    if req.fmt not in FORMATS: raise HTTPException(status_code=400, detail="Invalid format")
    try:
        inspector = Inspector(_platform)
        all_cfgs = inspector.inspect_all(settings_containers=_settings.get("containers", {}) or {})
        configs = [c for c in all_cfgs if not req.containers or c.name in req.containers]
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = Exporter().export(configs, req.fmt, Path(tmpdir), single_file=True)
            if not paths: raise HTTPException(status_code=500, detail="Export failed")
            content = paths[0].read_text()
            filename = paths[0].name
        return Response(content=content, media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

@app.get("/api/dam/version")
async def dam_version_check(_=Depends(require_auth)):
    from dam.web.dam_updater import check_latest_version
    info = check_latest_version(timeout=5)
    return {"current": info.current, "latest": info.latest,
            "update_available": info.update_available,
            "release_url": info.release_url, "release_notes": info.release_notes, "error": info.error}

@app.post("/api/dam/update")
async def dam_self_update(_=Depends(require_auth)):
    from dam.web.dam_updater import perform_update
    result = perform_update()
    return {"success": result.success, "method": result.method, "new_version": result.new_version,
            "message": result.message, "restart_required": result.restart_required}

_static_dir = Path(__file__).parent / "static"

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    index = _static_dir / "index.html"
    if index.exists(): return HTMLResponse(content=index.read_text())
    return HTMLResponse("<h1>DAM Web UI</h1>", status_code=404)

def create_app(config_path=None):
    global _config_path; _config_path = config_path; return app

def run_server(host="127.0.0.1", port=8080, config_path=None):
    import uvicorn
    global _config_path; _config_path = config_path
    uvicorn.run(app, host=host, port=port, log_level="warning")
