"""
Writes the complete v0.4.0 index.html for DAM web UI.
Run: python3 dam/web/write_html.py
"""
from pathlib import Path

HTML = """\
<!DOCTYPE html>
<html lang="en" x-data="dam()" x-init="init()" :class="darkMode?'':'light'">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Docker Automation Manager</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/alpinejs/3.13.5/cdn.min.js" defer></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
<style>
:root{--bg:#0f1117;--bg2:#1a1d2e;--bg3:#242842;--border:#2e3256;--accent:#4f8ef7;--accent2:#7c5cfc;--green:#22c55e;--yellow:#f59e0b;--red:#ef4444;--dim:#6b7280;--text:#e2e8f0;--text2:#94a3b8}
.light{--bg:#f8fafc;--bg2:#fff;--bg3:#f1f5f9;--border:#e2e8f0;--accent:#2563eb;--accent2:#7c3aed;--green:#16a34a;--yellow:#d97706;--red:#dc2626;--dim:#94a3b8;--text:#1e293b;--text2:#64748b}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;font-size:14px}
a{color:var(--accent);text-decoration:none}
.app{display:flex;height:100vh;overflow:hidden}
.sidebar{width:220px;background:var(--bg2);border-right:1px solid var(--border);display:flex;flex-direction:column;flex-shrink:0}
.main{flex:1;overflow-y:auto;padding:24px}
.logo{padding:20px 16px 16px;border-bottom:1px solid var(--border)}
.logo h1{font-size:15px;font-weight:700;color:var(--accent)}
.logo p{font-size:11px;color:var(--dim);margin-top:2px}
.nav{padding:8px 0;flex:1}
.nav-item{display:flex;align-items:center;gap:10px;padding:10px 16px;cursor:pointer;color:var(--text2);transition:all .15s}
.nav-item:hover{background:var(--bg3);color:var(--text)}
.nav-item.active{background:var(--bg3);color:var(--accent);border-left:3px solid var(--accent);padding-left:13px}
.nav-item i{width:16px;text-align:center}
.nbadge{margin-left:auto;background:var(--red);color:white;font-size:10px;padding:1px 6px;border-radius:99px}
.sidebar-footer{padding:12px 16px;border-top:1px solid var(--border)}
.platform-tag{font-size:11px;color:var(--dim)}
.upd-badge{font-size:11px;padding:3px 8px;border-radius:4px;margin-top:6px;cursor:pointer}
.upd-badge.avail{background:rgba(245,158,11,.15);color:var(--yellow);border:1px solid rgba(245,158,11,.3)}
.upd-badge.ok{background:rgba(34,197,94,.1);color:var(--green)}
.card{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:20px;margin-bottom:16px}
.card-title{font-size:13px;font-weight:600;color:var(--text2);text-transform:uppercase;letter-spacing:.05em;margin-bottom:16px}
.page-title{font-size:20px;font-weight:700;margin-bottom:20px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;margin-bottom:20px}
.stat{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:16px;text-align:center}
.stat-val{font-size:28px;font-weight:700}
.stat-label{font-size:11px;color:var(--dim);margin-top:2px}
.stat.green .stat-val{color:var(--green)}.stat.yellow .stat-val{color:var(--yellow)}.stat.red .stat-val{color:var(--red)}.stat.blue .stat-val{color:var(--accent)}
table{width:100%;border-collapse:collapse}
th{text-align:left;padding:8px 12px;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--dim);border-bottom:1px solid var(--border)}
td{padding:10px 12px;border-bottom:1px solid var(--border);vertical-align:middle}
tr:last-child td{border-bottom:none}
tr:hover td{background:var(--bg3)}
.bs{display:inline-flex;align-items:center;gap:4px;font-size:11px;padding:2px 8px;border-radius:99px;font-weight:500}
.bs-running{background:rgba(34,197,94,.15);color:var(--green)}.bs-exited{background:rgba(239,68,68,.15);color:var(--red)}.bs-paused{background:rgba(245,158,11,.15);color:var(--yellow)}
.bs-ok{background:rgba(34,197,94,.15);color:var(--green)}.bs-archived,.bs-deprecated{background:rgba(245,158,11,.15);color:var(--yellow)}.bs-eol{background:rgba(239,68,68,.15);color:var(--red)}
.bs-critical{background:rgba(239,68,68,.2);color:var(--red)}.bs-high{background:rgba(239,68,68,.15);color:#f87171}.bs-medium{background:rgba(245,158,11,.15);color:var(--yellow)}.bs-low{background:rgba(79,142,247,.15);color:var(--accent)}.bs-info{background:rgba(107,114,128,.15);color:var(--dim)}
.bs-updated{background:rgba(34,197,94,.15);color:var(--green)}.bs-skipped{background:rgba(107,114,128,.15);color:var(--dim)}.bs-dry_run{background:rgba(245,158,11,.15);color:var(--yellow)}.bs-failed{background:rgba(239,68,68,.15);color:var(--red)}.bs-pinned{background:rgba(124,92,252,.15);color:var(--accent2)}
.btn{display:inline-flex;align-items:center;gap:6px;padding:8px 16px;border-radius:6px;font-size:13px;font-weight:500;cursor:pointer;border:none;transition:all .15s}
.btn-p{background:var(--accent);color:white}.btn-p:hover{opacity:.9}
.btn-s{background:var(--bg3);color:var(--text);border:1px solid var(--border)}.btn-s:hover{background:var(--border)}
.btn-d{background:rgba(239,68,68,.15);color:var(--red);border:1px solid rgba(239,68,68,.3)}.btn-d:hover{background:rgba(239,68,68,.25)}
.btn-ok{background:rgba(34,197,94,.15);color:var(--green);border:1px solid rgba(34,197,94,.3)}.btn-ok:hover{background:rgba(34,197,94,.25)}
.btn-w{background:rgba(245,158,11,.15);color:var(--yellow);border:1px solid rgba(245,158,11,.3)}
.btn:disabled{opacity:.4;cursor:not-allowed}.btn-sm{padding:4px 10px;font-size:12px}
.bti{padding:5px 8px;border-radius:5px;background:transparent;border:1px solid var(--border);color:var(--text2);cursor:pointer;font-size:12px}.bti:hover{background:var(--bg3);color:var(--text)}
input[type=text],input[type=password],input[type=search],select{background:var(--bg3);border:1px solid var(--border);color:var(--text);padding:8px 12px;border-radius:6px;font-size:13px;width:100%}
input:focus,select:focus{outline:none;border-color:var(--accent)}
label{font-size:12px;color:var(--text2);margin-bottom:4px;display:block}.fg{margin-bottom:12px}
input[type=checkbox]{width:auto;accent-color:var(--accent)}
.lw{display:flex;align-items:center;justify-content:center;height:100vh}
.lb{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:40px;width:340px}
.lb h1{font-size:22px;font-weight:700;color:var(--accent);margin-bottom:6px}
.lb p{color:var(--dim);margin-bottom:24px;font-size:13px}
.logbox{background:#0d0f1a;border:1px solid var(--border);border-radius:6px;padding:12px;font-family:monospace;font-size:12px;overflow-y:auto;color:#a3e635}
.light .logbox{background:#1e293b;color:#86efac}
.ll{margin-bottom:2px;white-space:pre-wrap;word-break:break-all}.ll.err{color:var(--red)}.ll.done{color:var(--green)}
.alert{padding:12px 16px;border-radius:6px;font-size:13px;margin-bottom:16px}
.ai{background:rgba(79,142,247,.1);border:1px solid rgba(79,142,247,.3);color:var(--accent)}
.as{background:rgba(34,197,94,.1);border:1px solid rgba(34,197,94,.3);color:var(--green)}
.aw{background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.3);color:var(--yellow)}
.ad{background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.3);color:var(--red)}
.mono{font-family:monospace;font-size:12px}.dim{color:var(--dim)}.flex{display:flex}.gap{gap:8px}.mla{margin-left:auto}.mb16{margin-bottom:16px}.mt8{margin-top:8px}
.spin{display:inline-block;width:14px;height:14px;border:2px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:sp .6s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
.iptag{font-size:11px;color:var(--green);font-family:monospace}.nettag{font-size:11px;color:var(--dim)}
.crow{display:flex;align-items:center;gap:8px;padding:4px 0;cursor:pointer}
.tag-pill{display:inline-block;font-size:10px;padding:1px 7px;border-radius:99px;background:rgba(79,142,247,.15);color:var(--accent);border:1px solid rgba(79,142,247,.3);margin-right:3px}
.ov{color:var(--red);text-decoration:line-through;font-size:12px;font-family:monospace}.nv{color:var(--green);font-size:12px;font-family:monospace}
.sb{position:relative;margin-bottom:16px}.sb i{position:absolute;left:10px;top:50%;transform:translateY(-50%);color:var(--dim)}.sb input{padding-left:32px}
.plink{font-size:11px;font-family:monospace;padding:1px 6px;border-radius:3px;background:var(--bg3);border:1px solid var(--border);color:var(--accent);text-decoration:none;display:inline-block;margin-right:3px}.plink:hover{background:var(--border)}
.mov{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:100;display:flex;align-items:center;justify-content:center}
.modal{background:var(--bg2);border:1px solid var(--border);border-radius:12px;width:min(900px,95vw);max-height:90vh;display:flex;flex-direction:column;overflow:hidden}
.mh{padding:16px 20px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:12px}
.mb2{flex:1;overflow-y:auto}
.abtns{display:flex;gap:4px}
[x-cloak]{display:none!important}
</style>
</head>
<body>

<!-- LOGIN -->
<div class="lw" x-show="!auth" x-cloak>
  <div class="lb">
    <h1>🐳 DAM</h1>
    <p>Docker Automation Manager</p>
    <div class="fg"><label>Username</label><input type="text" x-model="lf.u" @keyup.enter="login()" placeholder="admin"></div>
    <div class="fg"><label>Password</label><input type="password" x-model="lf.p" @keyup.enter="login()" placeholder="••••••••"></div>
    <div x-show="le" class="alert ad" x-text="le"></div>
    <button class="btn btn-p" style="width:100%" @click="login()" :disabled="ll">
      <span x-show="ll" class="spin"></span>
      <span x-text="ll?'Signing in...':'Sign In'"></span>
    </button>
  </div>
</div>

<!-- APP -->
<div class="app" x-show="auth" x-cloak>
  <div class="sidebar">
    <div class="logo"><h1>🐳 DAM</h1><p>v<span x-text="ver"></span></p></div>
    <nav class="nav">
      <div class="nav-item" :class="{active:pg==='dash'}" @click="go('dash')"><i class="fa fa-gauge"></i> Dashboard</div>
      <div class="nav-item" :class="{active:pg==='update'}" @click="go('update')"><i class="fa fa-arrows-rotate"></i> Update</div>
      <div class="nav-item" :class="{active:pg==='drift'}" @click="go('drift')"><i class="fa fa-code-compare"></i> Drift</div>
      <div class="nav-item" :class="{active:pg==='eol'}" @click="go('eol')">
        <i class="fa fa-triangle-exclamation"></i> EOL Check
        <span class="nbadge" x-show="eolW>0" x-text="eolW"></span>
      </div>
      <div class="nav-item" :class="{active:pg==='prune'}" @click="go('prune')"><i class="fa fa-trash-can"></i> Prune</div>
      <div class="nav-item" :class="{active:pg==='export'}" @click="go('export')"><i class="fa fa-file-export"></i> Export</div>
      <div class="nav-item" :class="{active:pg==='snaps'}" @click="go('snaps')"><i class="fa fa-camera"></i> Snapshots</div>
    </nav>
    <div class="sidebar-footer">
      <div class="platform-tag" x-text="'Platform: '+plat"></div>
      <div x-show="dv.upd" class="upd-badge avail mt8" @click="go('selfupd')" title="Update available">
        <i class="fa fa-download"></i> v<span x-text="dv.latest"></span> available
      </div>
      <div x-show="dv.latest&&!dv.upd&&!dv.err" class="upd-badge ok mt8">
        <i class="fa fa-check"></i> DAM up to date
      </div>
      <div class="flex gap mt8" style="align-items:center">
        <button class="btn btn-s btn-sm" @click="dark=!dark;sp()" style="flex:1">
          <i :class="dark?'fa fa-sun':'fa fa-moon'"></i>
          <span x-text="dark?'Light':'Dark'"></span>
        </button>
        <button class="btn btn-s btn-sm" @click="logout()"><i class="fa fa-right-from-bracket"></i></button>
      </div>
    </div>
  </div>

  <div class="main">
    <!-- auto-refresh indicator -->
    <div x-show="ar" style="position:fixed;top:8px;right:16px;z-index:50;font-size:11px;color:var(--dim)">
      <span class="spin" style="width:10px;height:10px;margin-right:4px"></span>Auto-refresh
    </div>

    <!-- DASHBOARD -->
    <div x-show="pg==='dash'">
      <div class="flex gap mb16" style="align-items:center">
        <div class="page-title">Containers</div>
        <div class="flex gap mla" style="align-items:center">
          <label style="margin:0;color:var(--dim);font-size:12px">
            <input type="checkbox" x-model="ar" @change="togAR()"> Auto-refresh
          </label>
          <button class="btn btn-s btn-sm" @click="loadC()"><i class="fa fa-refresh"></i> Refresh</button>
        </div>
      </div>
      <div class="stats" x-show="cs.length>0">
        <div class="stat blue"><div class="stat-val" x-text="cs.length"></div><div class="stat-label">Total</div></div>
        <div class="stat green"><div class="stat-val" x-text="cs.filter(c=>c.status==='running').length"></div><div class="stat-label">Running</div></div>
        <div class="stat red"><div class="stat-val" x-text="cs.filter(c=>c.status==='exited').length"></div><div class="stat-label">Stopped</div></div>
        <div class="stat yellow"><div class="stat-val" x-text="eolW"></div><div class="stat-label">EOL Warnings</div></div>
      </div>
      <div class="sb" x-show="cs.length>0">
        <i class="fa fa-search"></i>
        <input type="search" x-model="q" placeholder="Search containers, images, IPs, tags, ports...">
      </div>
      <div class="card" x-show="ld.cs"><div class="spin"></div> Loading...</div>
      <div class="card" x-show="!ld.cs&&cs.length===0"><div class="dim">No containers found.</div></div>
      <div class="card" style="padding:0;overflow:hidden" x-show="!ld.cs&&fcs.length>0">
        <table>
          <thead><tr><th>Container</th><th>Image</th><th>Status</th><th>IP / Network</th><th>Ports</th><th>Tags</th><th>Actions</th></tr></thead>
          <tbody>
            <template x-for="c in fcs" :key="c.name">
              <tr>
                <td>
                  <a x-show="c.custom_link" :href="c.custom_link" target="_blank" style="font-weight:600" x-text="c.name"></a>
                  <strong x-show="!c.custom_link" x-text="c.name"></strong>
                </td>
                <td><span class="mono dim" x-text="c.image" style="font-size:11px"></span></td>
                <td><span class="bs" :class="'bs-'+c.status" x-text="c.status"></span></td>
                <td>
                  <div class="iptag" x-text="c.ip||'—'"></div>
                  <div class="nettag" x-text="c.network||c.network_mode"></div>
                </td>
                <td>
                  <template x-for="p in c.ports" :key="p.container">
                    <a x-show="p.host" :href="p.link" target="_blank" class="plink" :title="'Open '+p.container">
                      <i x-show="p.https" class="fa fa-lock" style="font-size:9px"></i>
                      <span x-text="p.host"></span>
                    </a>
                  </template>
                  <template x-for="ep in c.extra_ports" :key="ep">
                    <a :href="'http://localhost:'+ep" target="_blank" class="plink" x-text="ep"></a>
                  </template>
                </td>
                <td>
                  <template x-for="t in c.tags" :key="t"><span class="tag-pill" x-text="t"></span></template>
                </td>
                <td>
                  <div class="abtns">
                    <button class="bti" title="Logs" @click="openLog(c.name)"><i class="fa fa-file-lines"></i></button>
                    <button class="bti" title="Start" @click="cact(c.name,'start')" x-show="c.status!=='running'"><i class="fa fa-play" style="color:var(--green)"></i></button>
                    <button class="bti" title="Stop" @click="cact(c.name,'stop')" x-show="c.status==='running'"><i class="fa fa-stop" style="color:var(--yellow)"></i></button>
                    <button class="bti" title="Restart" @click="cact(c.name,'restart')"><i class="fa fa-rotate-right" style="color:var(--accent)"></i></button>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
        <div x-show="fcs.length===0&&q" style="padding:16px;color:var(--dim);text-align:center">No containers match "<span x-text="q"></span>"</div>
      </div>
    </div>

    <!-- LOG MODAL -->
    <div class="mov" x-show="lm.open" x-cloak @click.self="closeLog()">
      <div class="modal">
        <div class="mh">
          <i class="fa fa-file-lines" style="color:var(--accent)"></i>
          <strong x-text="lm.name"></strong>
          <span class="dim" style="font-size:12px">— last <span x-text="lm.tail"></span> lines</span>
          <div class="mla flex gap" style="align-items:center">
            <label style="margin:0;font-size:12px;color:var(--dim)"><input type="checkbox" x-model="lm.follow" @change="reloadLog()"> Live</label>
            <button class="btn btn-s btn-sm" @click="reloadLog()"><i class="fa fa-refresh"></i></button>
            <button class="btn btn-s btn-sm" @click="closeLog()">✕</button>
          </div>
        </div>
        <div class="mb2" style="padding:0">
          <div class="logbox" id="logv" style="height:500px;border-radius:0;border:none">
            <div x-show="lm.loading" style="padding:8px"><span class="spin"></span> Loading...</div>
            <template x-for="(ln,i) in lm.lines" :key="i"><div class="ll" x-text="ln"></div></template>
          </div>
        </div>
      </div>
    </div>

    <!-- UPDATE -->
    <div x-show="pg==='update'">
      <div class="page-title">Update Containers</div>
      <div x-show="us===1">
        <div class="card">
          <div class="card-title">Select Containers</div>
          <div class="crow mb16"><input type="checkbox" id="ca" @change="togAll($event)"><label for="ca" style="cursor:pointer;margin:0">Select all</label></div>
          <template x-for="c in cs" :key="c.name">
            <div class="crow">
              <input type="checkbox" :id="'ck-'+c.name" :value="c.name" x-model="sel">
              <label :for="'ck-'+c.name" style="cursor:pointer;margin:0">
                <strong x-text="c.name"></strong>
                <span class="dim mono" style="margin-left:8px;font-size:11px" x-text="c.image"></span>
              </label>
            </div>
          </template>
        </div>
        <button class="btn btn-p" @click="dryRun()" :disabled="ld.dr||sel.length===0">
          <span x-show="ld.dr" class="spin"></span>
          <i x-show="!ld.dr" class="fa fa-magnifying-glass"></i> Check for Updates (Dry Run)
        </button>
      </div>
      <div x-show="us===2">
        <div class="card">
          <div class="card-title">Dry Run Results</div>
          <table>
            <thead><tr><th>Container</th><th>Result</th><th>Old Digest</th><th>New Digest</th></tr></thead>
            <tbody>
              <template x-for="r in drr" :key="r.container_name">
                <tr>
                  <td><strong x-text="r.container_name"></strong></td>
                  <td><span class="bs" :class="r.would_update?'bs-dry_run':'bs-skipped'" x-text="r.would_update?'⬆ would update':'– unchanged'"></span></td>
                  <td><span class="mono dim" x-text="r.old_image_id||'—'"></span></td>
                  <td><span class="mono" :style="r.would_update?'color:var(--green)':''" x-text="r.new_image_id||'—'"></span></td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
        <div class="alert aw" x-show="drs.dry_run===0">✓ All images up to date.</div>
        <div class="alert ai" x-show="drs.dry_run>0"><strong x-text="drs.dry_run"></strong> container(s) have new images.</div>
        <div class="flex gap">
          <button class="btn btn-s" @click="us=1">← Back</button>
          <button class="btn btn-ok" @click="doUpdate()" :disabled="drs.dry_run===0||ld.upd">
            <i class="fa fa-rocket"></i> Apply Updates
          </button>
        </div>
      </div>
      <div x-show="us===3">
        <div class="card">
          <div class="card-title">
            <span x-show="ld.upd"><span class="spin"></span> Updating...</span>
            <span x-show="!ld.upd">Update Complete</span>
          </div>
          <div class="logbox" id="ulg" style="height:300px">
            <template x-for="(ln,i) in ulog" :key="i"><div class="ll" :class="ln.c" x-text="ln.t"></div></template>
          </div>
        </div>
        <div x-show="!ld.upd">
          <div class="alert" :class="usum.failed>0?'ad':'as'">
            ✓ <strong x-text="usum.updated"></strong> updated &nbsp;
            – <strong x-text="usum.skipped"></strong> skipped &nbsp;
            ✗ <strong x-text="usum.failed"></strong> failed
          </div>
          <button class="btn btn-s" @click="resetUpd()">← Dashboard</button>
        </div>
      </div>
    </div>

    <!-- DRIFT -->
    <div x-show="pg==='drift'">
      <div class="flex gap mb16" style="align-items:center">
        <div class="page-title">Drift Detection</div>
        <button class="btn btn-s btn-sm mla" @click="loadDrift()"><i class="fa fa-refresh"></i> Refresh</button>
      </div>
      <div class="card" x-show="ld.drift"><div class="spin"></div> Analyzing...</div>
      <div class="alert ai" x-show="!ld.drift&&drift.message"><i class="fa fa-info-circle"></i> <span x-text="drift.message"></span></div>
      <div class="alert as" x-show="!ld.drift&&!drift.has_drift&&!drift.message">✓ No drift detected (<span x-text="drift.snapshot_label"></span>).</div>
      <div x-show="!ld.drift&&drift.has_drift">
        <div class="stats mb16">
          <div class="stat red"><div class="stat-val" x-text="drift.summary?.critical||0"></div><div class="stat-label">Critical</div></div>
          <div class="stat red"><div class="stat-val" x-text="drift.summary?.high||0"></div><div class="stat-label">High</div></div>
          <div class="stat yellow"><div class="stat-val" x-text="drift.summary?.medium||0"></div><div class="stat-label">Medium</div></div>
          <div class="stat blue"><div class="stat-val" x-text="drift.summary?.low||0"></div><div class="stat-label">Low</div></div>
        </div>
        <div class="card" style="padding:0;overflow:hidden">
          <table>
            <thead><tr><th>Severity</th><th>Container</th><th>Field</th><th>Was</th><th>Now</th></tr></thead>
            <tbody>
              <template x-for="(it,i) in drift.items" :key="i">
                <tr>
                  <td><span class="bs" :class="'bs-'+it.severity" x-text="it.severity.toUpperCase()"></span></td>
                  <td><strong x-text="it.container_name"></strong></td>
                  <td><span class="mono" x-text="it.field"></span></td>
                  <td><span class="ov" x-text="it.old_value||'—'"></span></td>
                  <td><span class="nv" x-text="it.new_value||'—'"></span></td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- EOL -->
    <div x-show="pg==='eol'">
      <div class="flex gap mb16" style="align-items:center">
        <div class="page-title">EOL / Deprecation Check</div>
        <button class="btn btn-s btn-sm mla" @click="loadEol()"><i class="fa fa-refresh"></i> Refresh</button>
      </div>
      <div class="card" x-show="ld.eol"><div class="spin"></div> Checking...</div>
      <div x-show="!ld.eol&&eolR.length>0">
        <div class="stats mb16">
          <div class="stat green"><div class="stat-val" x-text="eolS.ok||0"></div><div class="stat-label">OK</div></div>
          <div class="stat yellow"><div class="stat-val" x-text="(eolS.deprecated||0)+(eolS.archived||0)"></div><div class="stat-label">Deprecated</div></div>
          <div class="stat red"><div class="stat-val" x-text="eolS.eol||0"></div><div class="stat-label">EOL</div></div>
        </div>
        <div class="card" style="padding:0;overflow:hidden">
          <table>
            <thead><tr><th>Container</th><th>Image</th><th>Status</th><th>Reason</th><th>Alternatives</th></tr></thead>
            <tbody>
              <template x-for="r in eolR" :key="r.container_name">
                <tr>
                  <td><strong x-text="r.container_name"></strong></td>
                  <td><span class="mono dim" x-text="r.image"></span></td>
                  <td><span class="bs" :class="'bs-'+r.status" x-text="r.status"></span></td>
                  <td><span class="dim" x-text="r.reason||'—'"></span></td>
                  <td>
                    <template x-for="a in r.alternatives" :key="a.name">
                      <span><a x-show="a.url" :href="a.url" target="_blank" x-text="a.name"></a><span x-show="!a.url" x-text="a.name"></span> </span>
                    </template>
                    <span x-show="r.alternatives.length===0" class="dim">—</span>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- PRUNE -->
    <div x-show="pg==='prune'">
      <div class="page-title">Prune Unused Images</div>
      <div class="card" x-show="!pc">
        <p class="dim mb16">Preview images to remove before committing.</p>
        <button class="btn btn-s" @click="loadPrune()" :disabled="ld.prune">
          <span x-show="ld.prune" class="spin"></span>
          <i x-show="!ld.prune" class="fa fa-eye"></i> Preview
        </button>
      </div>
      <div x-show="pc">
        <div class="stats mb16">
          <div class="stat yellow"><div class="stat-val" x-text="pc?.total_candidates||0"></div><div class="stat-label">To Remove</div></div>
          <div class="stat green"><div class="stat-val" x-text="pc?.estimated_space_human||'0 MB'"></div><div class="stat-label">Space Freed</div></div>
        </div>
        <div class="alert as" x-show="pc?.total_candidates===0">✓ Nothing to prune.</div>
        <div class="flex gap" x-show="pc?.total_candidates>0">
          <button class="btn btn-d" @click="doPrune()" :disabled="ld.prune">
            <span x-show="ld.prune" class="spin"></span>
            <i x-show="!ld.prune" class="fa fa-trash-can"></i>
            Remove <span x-text="pc?.total_candidates"></span> image(s)
          </button>
          <button class="btn btn-s" @click="pc=null">Cancel</button>
        </div>
        <div class="alert as" x-show="pr" style="margin-top:16px">
          ✓ Removed <strong x-text="pr?.images_removed"></strong> image(s), freed <strong x-text="pr?.space_reclaimed_human"></strong>.
        </div>
      </div>
    </div>

    <!-- EXPORT -->
    <div x-show="pg==='export'">
      <div class="page-title">Export Containers</div>
      <div class="card">
        <div class="card-title">Select Containers</div>
        <div class="crow mb16"><input type="checkbox" id="ea" @change="togExp($event)"><label for="ea" style="cursor:pointer;margin:0">Export all</label></div>
        <template x-for="c in cs" :key="c.name">
          <div class="crow">
            <input type="checkbox" :id="'ex-'+c.name" :value="c.name" x-model="expSel">
            <label :for="'ex-'+c.name" style="cursor:pointer;margin:0" x-text="c.name"></label>
          </div>
        </template>
      </div>
      <div class="card">
        <div class="card-title">Format</div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px">
          <div @click="expFmt='dam-yaml'" class="card" style="cursor:pointer;padding:16px;text-align:center" :style="expFmt==='dam-yaml'?'border-color:var(--accent)':''">
            <i class="fa fa-database fa-lg" style="color:var(--accent);display:block;margin-bottom:8px"></i>
            <div style="font-weight:600">DAM YAML</div><div class="dim" style="font-size:11px;margin-top:4px">Re-import on any host</div>
          </div>
          <div @click="expFmt='docker-run'" class="card" style="cursor:pointer;padding:16px;text-align:center" :style="expFmt==='docker-run'?'border-color:var(--accent)':''">
            <i class="fa fa-terminal fa-lg" style="color:var(--green);display:block;margin-bottom:8px"></i>
            <div style="font-weight:600">Shell Script</div><div class="dim" style="font-size:11px;margin-top:4px">Works without DAM</div>
          </div>
          <div @click="expFmt='compose'" class="card" style="cursor:pointer;padding:16px;text-align:center" :style="expFmt==='compose'?'border-color:var(--accent)':''">
            <i class="fa fa-layer-group fa-lg" style="color:var(--accent2);display:block;margin-bottom:8px"></i>
            <div style="font-weight:600">Compose</div><div class="dim" style="font-size:11px;margin-top:4px">docker-compose.yml</div>
          </div>
        </div>
      </div>
      <button class="btn btn-p" @click="doExp()" :disabled="ld.exp||expSel.length===0">
        <span x-show="ld.exp" class="spin"></span>
        <i x-show="!ld.exp" class="fa fa-download"></i> Download Export
      </button>
    </div>

    <!-- SNAPSHOTS -->
    <div x-show="pg==='snaps'">
      <div class="flex gap mb16" style="align-items:center">
        <div class="page-title">Snapshots</div>
        <button class="btn btn-s btn-sm mla" @click="loadSnaps()"><i class="fa fa-refresh"></i> Refresh</button>
      </div>
      <div class="card" x-show="ld.snaps"><div class="spin"></div> Loading...</div>
      <div class="alert ai" x-show="!ld.snaps&&snaps.length===0">No snapshots yet. Run an update to create a baseline.</div>
      <div class="card" style="padding:0;overflow:hidden" x-show="!ld.snaps&&snaps.length>0">
        <table>
          <thead><tr><th>#</th><th>Filename</th><th>Size</th><th></th></tr></thead>
          <tbody>
            <template x-for="s in snaps" :key="s.id">
              <tr>
                <td class="dim" x-text="s.id+1"></td>
                <td class="mono" x-text="s.filename"></td>
                <td class="dim" x-text="s.size_kb+' KB'"></td>
                <td><button class="btn btn-s btn-sm" @click="viewSnap(s.id)"><i class="fa fa-eye"></i> View</button></td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
      <div x-show="snapD" style="margin-top:16px">
        <div class="card">
          <div class="card-title">Snapshot Detail <button class="btn btn-s btn-sm" @click="snapD=null" style="float:right">✕</button></div>
          <div class="dim" style="margin-bottom:12px;font-size:12px" x-text="snapD?.meta?.captured_at"></div>
          <table>
            <thead><tr><th>Container</th><th>Image</th><th>Status</th><th>IP</th></tr></thead>
            <tbody>
              <template x-for="c in snapD?.containers" :key="c.name">
                <tr>
                  <td x-text="c.name"></td><td class="mono dim" x-text="c.image"></td>
                  <td><span class="bs" :class="'bs-'+c.status" x-text="c.status"></span></td>
                  <td class="iptag" x-text="c.ip||'—'"></td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- DAM SELF-UPDATE -->
    <div x-show="pg==='selfupd'">
      <div class="page-title">DAM Self-Update</div>
      <div class="card">
        <div class="flex gap mb16" style="align-items:center;flex-wrap:wrap">
          <div>
            <div style="font-size:16px;font-weight:600">Current: v<span x-text="dv.current"></span></div>
            <div class="dim mt8" x-show="dv.latest">Latest: v<span x-text="dv.latest"></span></div>
            <div class="alert aw mt8" x-show="dv.upd"><i class="fa fa-arrow-up"></i> v<span x-text="dv.latest"></span> available</div>
            <div class="alert as mt8" x-show="!dv.upd&&dv.latest">✓ Running latest version</div>
            <div class="alert ai mt8" x-show="dv.err"><i class="fa fa-warning"></i> <span x-text="dv.err"></span></div>
          </div>
          <div class="mla flex gap" style="flex-direction:column;align-items:flex-end">
            <button class="btn btn-s btn-sm" @click="chkDv()"><i class="fa fa-refresh"></i> Check</button>
            <a x-show="dv.release_url" :href="dv.release_url" target="_blank" class="btn btn-s btn-sm"><i class="fa fa-external-link"></i> Release Notes</a>
          </div>
        </div>
        <div x-show="dv.release_notes&&dv.upd">
          <div class="card-title">Release Notes</div>
          <pre class="mono" style="white-space:pre-wrap;color:var(--text2);font-size:12px" x-text="dv.release_notes"></pre>
        </div>
      </div>
      <div class="alert aw">
        <i class="fa fa-triangle-exclamation"></i>
        <strong> Update replaces DAM source files.</strong>
        Tries git pull first, falls back to GitHub zip download. Restart server after updating.
      </div>
      <button class="btn btn-w" @click="doSelfUpd()" :disabled="ld.su||!dv.upd">
        <span x-show="ld.su" class="spin"></span>
        <i x-show="!ld.su" class="fa fa-download"></i>
        Update to v<span x-text="dv.latest||'latest'"></span>
      </button>
      <div x-show="sur" class="alert mt8" :class="sur?.success?'as':'ad'" style="margin-top:16px">
        <span x-show="sur?.success">✓ Updated via <strong x-text="sur?.method"></strong> to v<span x-text="sur?.new_version"></span>. Restart server to apply.</span>
        <span x-show="!sur?.success">✗ Failed (<span x-text="sur?.method"></span>): <span x-text="sur?.message"></span></span>
      </div>
    </div>

  </div>
</div>

<script>
function dam(){return{
auth:false,lf:{u:'',p:''},le:'',ll:false,
pg:'dash',ver:'',plat:'',dark:true,q:'',ar:false,_art:null,
cs:[],ld:{},
eolR:[],eolS:{},eolW:0,
drift:{},snaps:[],snapD:null,
us:1,sel:[],drr:[],drs:{},ulog:[],usum:{},sid:null,
pc:null,pr:null,
expSel:[],expFmt:'dam-yaml',
lm:{open:false,name:'',lines:[],loading:false,follow:false,tail:200,_es:null},
dv:{current:'',latest:null,upd:false,release_url:null,release_notes:null,err:null},
sur:null,

get fcs(){
  if(!this.q)return this.cs;
  const q=this.q.toLowerCase();
  return this.cs.filter(c=>
    c.name.toLowerCase().includes(q)||c.image.toLowerCase().includes(q)||
    (c.ip||'').includes(q)||(c.network||'').toLowerCase().includes(q)||
    c.ports.some(p=>(p.host||'').includes(q))||
    c.tags.some(t=>t.toLowerCase().includes(q))
  );
},

async init(){
  this.dark=localStorage.getItem('dam_dark')!=='false';
  const r=await fetch('/auth/status').then(r=>r.json()).catch(()=>({}));
  this.auth=r.authenticated||false;
  if(this.auth)await this.loadAll();
},
sp(){localStorage.setItem('dam_dark',this.dark);},

async loadAll(){
  const h=await fetch('/health').then(r=>r.json()).catch(()=>({}));
  this.ver=h.version||'';this.plat=h.platform||'';
  await Promise.all([this.loadC(),this.loadEol()]);
  this.chkDv();
},

async api(url,opts={}){
  const r=await fetch(url,{credentials:'include',headers:{'Content-Type':'application/json'},...opts});
  if(r.status===401){this.auth=false;return null;}
  if(!r.ok){const e=await r.json().catch(()=>({}));throw new Error(e.detail||r.statusText);}
  return r.json().catch(()=>null);
},

async login(){
  this.ll=true;this.le='';
  try{
    const r=await fetch('/auth/login',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:this.lf.u,password:this.lf.p})});
    if(!r.ok){this.le='Invalid username or password.';return;}
    this.auth=true;await this.loadAll();
  }catch(e){this.le=e.message;}finally{this.ll=false;}
},
async logout(){
  await fetch('/auth/logout',{method:'POST',credentials:'include'});
  this.auth=false;this.clearAR();
},

go(p){
  this.pg=p;
  if(p==='drift')this.loadDrift();
  if(p==='snaps')this.loadSnaps();
  if(p==='update'){this.us=1;this.loadC();}
  if(p==='prune'){this.pc=null;this.pr=null;}
  if(p==='export')this.loadC();
  if(p==='selfupd')this.chkDv();
},

async loadC(){
  this.ld.cs=true;
  try{const d=await this.api('/api/containers');if(d)this.cs=d.containers;}
  catch(e){console.error(e);}finally{this.ld.cs=false;}
},
async loadEol(){
  this.ld.eol=true;
  try{const d=await this.api('/api/eol');if(d){this.eolR=d.results;this.eolS=d.summary;this.eolW=d.results.filter(r=>r.status!=='ok').length;}}
  catch(e){}finally{this.ld.eol=false;}
},
async loadDrift(){
  this.ld.drift=true;
  try{const d=await this.api('/api/drift');if(d)this.drift=d;}
  catch(e){}finally{this.ld.drift=false;}
},
async loadSnaps(){
  this.ld.snaps=true;
  try{const d=await this.api('/api/snapshots');if(d)this.snaps=d.snapshots;}
  catch(e){}finally{this.ld.snaps=false;}
},
async viewSnap(id){const d=await this.api('/api/snapshots/'+id);if(d)this.snapD=d;},

async cact(name,act){
  try{await this.api('/api/containers/'+name+'/'+act,{method:'POST'});await this.loadC();}
  catch(e){alert(act+' failed: '+e.message);}
},

openLog(name){
  this.lm={open:true,name,lines:[],loading:true,follow:false,tail:200,_es:null};
  this.reloadLog();
},
closeLog(){if(this.lm._es)this.lm._es.close();this.lm.open=false;},
reloadLog(){
  if(this.lm._es){this.lm._es.close();this.lm._es=null;}
  this.lm.lines=[];this.lm.loading=true;
  const {name,tail,follow}=this.lm;
  const es=new EventSource('/api/containers/'+name+'/logs?tail='+tail+'&follow='+(follow?1:0));
  this.lm._es=es;
  es.onmessage=(e)=>{
    const msg=JSON.parse(e.data);
    if(msg.line){this.lm.lines.push(msg.line);this.lm.loading=false;this.$nextTick(()=>{const el=document.getElementById('logv');if(el)el.scrollTop=el.scrollHeight;});}
    if(msg.done||msg.error){this.lm.loading=false;if(!follow)es.close();}
  };
  es.onerror=()=>{this.lm.loading=false;};
},

togAR(){if(this.ar){this._art=setInterval(()=>this.loadC(),60000);}else{this.clearAR();}},
clearAR(){if(this._art){clearInterval(this._art);this._art=null;}this.ar=false;},

togAll(e){this.sel=e.target.checked?this.cs.map(c=>c.name):[];},
togExp(e){this.expSel=e.target.checked?this.cs.map(c=>c.name):[];},

async dryRun(){
  this.ld.dr=true;
  try{const d=await this.api('/api/update/dry-run',{method:'POST',body:JSON.stringify({containers:this.sel})});if(d){this.drr=d.results;this.drs=d.summary;this.us=2;}}
  catch(e){alert('Error: '+e.message);}finally{this.ld.dr=false;}
},
async doUpdate(){
  this.us=3;this.ld.upd=true;this.ulog=[];this.usum={};
  try{
    const d=await this.api('/api/update/run',{method:'POST',body:JSON.stringify({containers:this.sel})});
    if(!d)return;
    this.sid=d.session_id;
    const es=new EventSource('/api/update/stream/'+this.sid);
    es.onmessage=(e)=>{
      const msg=JSON.parse(e.data);
      if(msg.type==='ping')return;
      if(msg.type==='progress'&&msg.message)this.ulog.push({t:'['+( msg.container||'...')+'] '+msg.message,c:''});
      else if(msg.type==='result'){
        const ok=msg.status==='updated';
        this.ulog.push({t:(ok?'✓':'–')+' '+msg.container+': '+msg.status+(msg.error?' — '+msg.error:''),c:ok?'done':(msg.status==='failed'?'err':'')});
      }else if(msg.type==='done'){
        this.usum=msg.summary;
        this.ulog.push({t:'\n✓ Done — '+msg.summary.updated+' updated, '+msg.summary.skipped+' skipped, '+msg.summary.failed+' failed',c:'done'});
        this.ld.upd=false;es.close();this.loadC();
      }else if(msg.type==='error'){this.ulog.push({t:'✗ Error: '+msg.message,c:'err'});this.ld.upd=false;es.close();}
      const lg=document.getElementById('ulg');if(lg)lg.scrollTop=lg.scrollHeight;
    };
    es.onerror=()=>{this.ld.upd=false;es.close();};
  }catch(e){this.ld.upd=false;alert('Error: '+e.message);}
},
resetUpd(){this.us=1;this.sel=[];this.drr=[];this.ulog=[];this.go('dash');},

async loadPrune(){
  this.ld.prune=true;
  try{const d=await this.api('/api/prune/dry-run',{method:'POST'});if(d)this.pc=d;}
  catch(e){alert(e.message);}finally{this.ld.prune=false;}
},
async doPrune(){
  if(!confirm('Remove unused images? Cannot be undone.'))return;
  this.ld.prune=true;
  try{const d=await this.api('/api/prune/run',{method:'POST'});if(d){this.pr=d;this.pc=null;}}
  catch(e){alert(e.message);}finally{this.ld.prune=false;}
},

async doExp(){
  this.ld.exp=true;
  try{
    const r=await fetch('/api/export',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify({containers:this.expSel,fmt:this.expFmt})});
    if(!r.ok){alert('Export failed');return;}
    const blob=await r.blob();
    const cd=r.headers.get('content-disposition')||'';
    const fn=(cd.match(/filename="([^"]+)"/)|| [])[1]||'export.yaml';
    const url=URL.createObjectURL(blob);const a=document.createElement('a');
    a.href=url;a.download=fn;a.click();URL.revokeObjectURL(url);
  }catch(e){alert(e.message);}finally{this.ld.exp=false;}
},

async chkDv(){
  try{const d=await this.api('/api/dam/version');if(d)this.dv=d;}catch(e){}
},
async doSelfUpd(){
  if(!confirm('Update DAM? Source files will be replaced and server restart required.'))return;
  this.ld.su=true;this.sur=null;
  try{const d=await this.api('/api/dam/update',{method:'POST'});if(d)this.sur=d;}
  catch(e){this.sur={success:false,method:'unknown',message:e.message};}
  finally{this.ld.su=false;}
},
};}
</script>
</body>
</html>"""

out = Path("/home/claude/docker-automation-manager/dam/web/static/index.html")
out.write_text(HTML)
print(f"Written: {out} ({len(HTML)} chars, {HTML.count(chr(10))} lines)")
