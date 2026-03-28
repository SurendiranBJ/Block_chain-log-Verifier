#!/usr/bin/env python3
"""
Real-Time Activity Dashboard
Flask + Flask-SocketIO server
Tails SAMPLELOG and pushes every new event to browser in real-time
Run: python3 dashboard_app.py
Visit: http://10.27.17.210:5001
"""

import json
import os
import threading
import time
from datetime import datetime
from flask import Flask, render_template_string, jsonify
from flask_socketio import SocketIO

# ── Config ─────────────────────────────────────────────────────────────────────
LOG_DIR = os.path.expanduser("~/logchain/SAMPLELOG")
PORT    = 5001
HOST    = "0.0.0.0"

os.makedirs(LOG_DIR, exist_ok=True)

app      = Flask(__name__)
app.config["SECRET_KEY"] = "logchain-secret-2024"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ── Log tailer ─────────────────────────────────────────────────────────────────

def get_today_log():
    date_str = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(LOG_DIR, f"activity_{date_str}.log")

def tail_log():
    current_path = None
    f = None
    while True:
        today = get_today_log()
        if today != current_path:
            if f:
                f.close()
            current_path = today
            if not os.path.exists(current_path):
                open(current_path, "a").close()
            f = open(current_path, "r")
            f.seek(0, 2)   # seek to end — only stream new lines
            print(f"[tailer] Watching: {current_path}")

        line = f.readline()
        if line:
            line = line.strip()
            if line:
                try:
                    event = json.loads(line)
                    socketio.emit("activity", event)
                except json.JSONDecodeError:
                    pass
        else:
            time.sleep(0.05)

def get_recent_events(n=200):
    path = get_today_log()
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        lines = f.readlines()
    events = []
    for line in lines[-n:]:
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except Exception:
                pass
    return events

# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/api/recent")
def recent():
    return jsonify(get_recent_events(200))

@app.route("/api/stats")
def stats():
    events = get_recent_events(10000)
    counts = {"mouse_move": 0, "mouse_click": 0, "mouse_scroll": 0,
              "key_press": 0, "key_release": 0}
    for e in events:
        t = e.get("type", "")
        if t in counts:
            counts[t] += 1
    return jsonify({"counts": counts, "total": len(events)})

@app.route("/api/logpath")
def logpath():
    return jsonify({"path": get_today_log(), "dir": LOG_DIR})

# ── SocketIO ───────────────────────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    print("[ws] Client connected")

@socketio.on("disconnect")
def on_disconnect():
    print("[ws] Client disconnected")

# ── HTML ───────────────────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>LOGCHAIN // Activity Monitor</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@300;500;700&display=swap" rel="stylesheet"/>
<style>
  :root {
    --bg:      #030b0f;
    --panel:   #071318;
    --border:  #0d3a4a;
    --accent:  #00ffe7;
    --accent2: #ff3e6c;
    --accent3: #f5c400;
    --dim:     #1a4a5a;
    --text:    #c8f0f5;
    --mono:    'Share Tech Mono', monospace;
    --sans:    'Rajdhani', sans-serif;
  }
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; background: var(--bg); color: var(--text); font-family: var(--sans); overflow: hidden; }

  body::after {
    content: ''; position: fixed; inset: 0; pointer-events: none; z-index: 9999;
    background: repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,.12) 2px, rgba(0,0,0,.12) 4px);
  }

  .shell {
    display: grid;
    grid-template-rows: 56px 1fr;
    grid-template-columns: 260px 1fr 220px;
    height: 100vh; gap: 1px; background: var(--border);
  }

  header {
    grid-column: 1 / -1; background: var(--panel);
    display: flex; align-items: center; gap: 20px;
    padding: 0 24px; border-bottom: 1px solid var(--border);
  }
  .logo { font-family: var(--mono); font-size: 1.1rem; color: var(--accent); letter-spacing: 4px; }
  .logo span { color: var(--accent2); }
  .logpath { font-family: var(--mono); font-size: .6rem; color: var(--dim); letter-spacing: 1px; }
  .live-badge { display: flex; align-items: center; gap: 6px; font-size: .72rem; letter-spacing: 2px; color: var(--accent); font-family: var(--mono); }
  .live-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); animation: pulse 1.2s ease-in-out infinite; }
  @keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.4;transform:scale(.7)} }
  .header-time { margin-left: auto; font-family: var(--mono); font-size: .8rem; color: var(--dim); letter-spacing: 2px; }

  .panel { background: var(--panel); display: flex; flex-direction: column; overflow: hidden; }

  /* Left stats */
  .sidebar-left { padding: 16px; gap: 12px; }
  .stat-block { border: 1px solid var(--border); padding: 12px 14px; position: relative; overflow: hidden; }
  .stat-block::before { content: ''; position: absolute; top: 0; left: 0; width: 3px; height: 100%; background: var(--accent); }
  .stat-label { font-family: var(--mono); font-size: .65rem; color: var(--dim); letter-spacing: 2px; text-transform: uppercase; margin-bottom: 4px; }
  .stat-val { font-family: var(--mono); font-size: 1.6rem; color: var(--accent); line-height: 1; }
  .stat-block.click::before  { background: var(--accent2); } .stat-block.click .stat-val  { color: var(--accent2); }
  .stat-block.key::before    { background: var(--accent3); } .stat-block.key .stat-val    { color: var(--accent3); }
  .stat-block.scroll::before { background: #a78bfa; }        .stat-block.scroll .stat-val { color: #a78bfa; }
  .section-title { font-family: var(--mono); font-size: .65rem; letter-spacing: 3px; color: var(--dim); text-transform: uppercase; border-bottom: 1px solid var(--border); padding-bottom: 8px; margin-bottom: 10px; }

  /* Center feed */
  .feed-panel { flex: 1; }
  .feed-header { padding: 12px 18px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; }
  .feed-title  { font-family: var(--mono); font-size: .7rem; letter-spacing: 3px; color: var(--dim); }
  .feed-count  { font-family: var(--mono); font-size: .7rem; color: var(--accent); }
  .feed-list   { flex: 1; overflow-y: auto; padding: 8px 0; display: flex; flex-direction: column-reverse; }
  .feed-list::-webkit-scrollbar { width: 4px; }
  .feed-list::-webkit-scrollbar-track { background: var(--bg); }
  .feed-list::-webkit-scrollbar-thumb { background: var(--dim); }

  .entry {
    display: grid; grid-template-columns: 160px 90px 1fr;
    gap: 0 12px; padding: 5px 18px;
    font-family: var(--mono); font-size: .72rem;
    border-left: 2px solid transparent; animation: slideIn .15s ease;
  }
  @keyframes slideIn { from{opacity:0;transform:translateY(-5px)} to{opacity:1;transform:none} }
  .entry:hover { background: rgba(0,255,231,.04); }
  .entry.mouse_move   { border-color: var(--accent); }
  .entry.mouse_click  { border-color: var(--accent2); background: rgba(255,62,108,.05); }
  .entry.mouse_scroll { border-color: #a78bfa; }
  .entry.key_press    { border-color: var(--accent3); background: rgba(245,196,0,.04); }
  .entry.key_release  { border-color: #333; }
  .entry.system       { border-color: #4ade80; background: rgba(74,222,128,.05); }
  .e-time   { color: #2a7a8a; }
  .e-type   { }
  .entry.mouse_move   .e-type { color: var(--accent); }
  .entry.mouse_click  .e-type { color: var(--accent2); }
  .entry.mouse_scroll .e-type { color: #a78bfa; }
  .entry.key_press    .e-type { color: var(--accent3); }
  .entry.key_release  .e-type { color: #555; }
  .entry.system       .e-type { color: #4ade80; }
  .e-detail { color: #5a9aaa; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  /* Right sidebar */
  .sidebar-right { padding: 16px; gap: 14px; }
  .crosshair-wrap { border: 1px solid var(--border); aspect-ratio: 1; position: relative; overflow: hidden; background: #040e14; }
  #crosshair-canvas { width: 100%; height: 100%; display: block; }
  .coord-display { font-family: var(--mono); font-size: .8rem; color: var(--accent); text-align: center; padding: 8px; border: 1px solid var(--border); letter-spacing: 2px; }

  .key-last { border: 1px solid var(--border); padding: 12px; text-align: center; }
  .key-last-label { font-family: var(--mono); font-size: .6rem; color: var(--dim); letter-spacing: 2px; margin-bottom: 6px; }
  .key-last-val { font-family: var(--mono); font-size: 1.4rem; color: var(--accent3); min-height: 2rem; display: flex; align-items: center; justify-content: center; }

  .click-flash { border: 1px solid var(--border); padding: 10px 12px; font-family: var(--mono); font-size: .7rem; display: flex; flex-direction: column; gap: 4px; }
  .click-flash-label { color: var(--dim); letter-spacing: 2px; font-size: .6rem; }
  .click-row { display: flex; justify-content: space-between; }
  .click-btn { color: #555; transition: color .1s; }
  .click-btn.active-left  { color: var(--accent2); }
  .click-btn.active-right { color: var(--accent3); }

  .auto-scroll-btn { margin-top: auto; background: none; border: 1px solid var(--dim); color: var(--dim); font-family: var(--mono); font-size: .65rem; letter-spacing: 2px; padding: 7px; cursor: pointer; transition: all .2s; text-transform: uppercase; }
  .auto-scroll-btn:hover, .auto-scroll-btn.on { border-color: var(--accent); color: var(--accent); }
</style>
</head>
<body>
<div class="shell">
  <header>
    <div class="logo">LOG<span>CHAIN</span> // MONITOR</div>
    <div class="live-badge"><div class="live-dot"></div>LIVE</div>
    <div class="logpath" id="logpath-display">📁 ~/logchain/SAMPLELOG/activity_*.log</div>
    <div class="header-time" id="htime">--:--:--</div>
  </header>

  <!-- Left Stats -->
  <div class="panel sidebar-left">
    <div class="section-title">Session Stats</div>
    <div class="stat-block">
      <div class="stat-label">Mouse Moves</div>
      <div class="stat-val" id="s-move">0</div>
    </div>
    <div class="stat-block click">
      <div class="stat-label">Mouse Clicks</div>
      <div class="stat-val" id="s-click">0</div>
    </div>
    <div class="stat-block scroll">
      <div class="stat-label">Scroll Events</div>
      <div class="stat-val" id="s-scroll">0</div>
    </div>
    <div class="stat-block key">
      <div class="stat-label">Keystrokes</div>
      <div class="stat-val" id="s-key">0</div>
    </div>
    <div class="stat-block" style="margin-top:auto">
      <div class="stat-label">Total Events</div>
      <div class="stat-val" id="s-total">0</div>
    </div>
  </div>

  <!-- Center Feed -->
  <div class="panel feed-panel">
    <div class="feed-header">
      <div class="feed-title">ACTIVITY FEED — SAMPLELOG</div>
      <div class="feed-count" id="feed-count">0 events</div>
    </div>
    <div class="feed-list" id="feed"></div>
    <button class="auto-scroll-btn on" id="autoscroll-btn" onclick="toggleAutoScroll()">⬇ AUTO-SCROLL ON</button>
  </div>

  <!-- Right: Pointer -->
  <div class="panel sidebar-right">
    <div class="section-title">Pointer</div>
    <div class="crosshair-wrap">
      <canvas id="crosshair-canvas"></canvas>
    </div>
    <div class="coord-display" id="coords">X: --- &nbsp; Y: ---</div>
    <div class="section-title" style="margin-top:8px">Last Key</div>
    <div class="key-last">
      <div class="key-last-label">KEYSTROKE</div>
      <div class="key-last-val" id="last-key">—</div>
    </div>
    <div class="section-title" style="margin-top:8px">Buttons</div>
    <div class="click-flash">
      <div class="click-flash-label">MOUSE BUTTONS</div>
      <div class="click-row">
        <span class="click-btn" id="btn-left">● LEFT</span>
        <span class="click-btn" id="btn-right">RIGHT ●</span>
      </div>
    </div>
  </div>
</div>

<script>
const socket = io();
let stats = {mouse_move:0, mouse_click:0, mouse_scroll:0, key_press:0, key_release:0};
let totalEvents = 0, feedCount = 0, autoScroll = true;
const MAX_ENTRIES = 500;

// Clock
setInterval(() => {
  document.getElementById('htime').textContent = new Date().toLocaleTimeString('en-US',{hour12:false});
}, 500);

// Log path display
fetch('/api/logpath').then(r=>r.json()).then(d=>{
  document.getElementById('logpath-display').textContent = '📁 ' + d.path;
});

// Canvas crosshair
const canvas = document.getElementById('crosshair-canvas');
const ctx    = canvas.getContext('2d');
let screenW = 1920, screenH = 1080;
function resizeCanvas() { canvas.width = canvas.offsetWidth; canvas.height = canvas.offsetHeight; }
resizeCanvas(); window.addEventListener('resize', resizeCanvas);

function drawCrosshair(rx, ry) {
  const w = canvas.width, h = canvas.height;
  const cx = rx*w, cy = ry*h;
  ctx.clearRect(0,0,w,h);
  ctx.strokeStyle='#00ffe7'; ctx.lineWidth=1; ctx.globalAlpha=.3;
  ctx.beginPath(); ctx.moveTo(cx,0); ctx.lineTo(cx,h); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(0,cy); ctx.lineTo(w,cy); ctx.stroke();
  ctx.globalAlpha=1;
  ctx.beginPath(); ctx.arc(cx,cy,5,0,Math.PI*2); ctx.stroke();
  const g = ctx.createRadialGradient(cx,cy,0,cx,cy,18);
  g.addColorStop(0,'rgba(0,255,231,.5)'); g.addColorStop(1,'transparent');
  ctx.fillStyle=g; ctx.beginPath(); ctx.arc(cx,cy,18,0,Math.PI*2); ctx.fill();
}
drawCrosshair(.5,.5);

function formatEvent(ev) {
  let typeStr='', detail='';
  switch(ev.type) {
    case 'mouse_move':   typeStr='MOVE';   detail=`x:${ev.x}  y:${ev.y}`; break;
    case 'mouse_click':  typeStr='CLICK';  detail=`${(ev.button||'').toUpperCase()} ${ev.action}  @(${ev.x},${ev.y})`; break;
    case 'mouse_scroll': typeStr='SCROLL'; detail=`dx:${ev.dx}  dy:${ev.dy}  @(${ev.x},${ev.y})`; break;
    case 'key_press':    typeStr='KEY↓';   detail=ev.key; break;
    case 'key_release':  typeStr='KEY↑';   detail=ev.key; break;
    case 'system':       typeStr='SYS';    detail=ev.message||''; break;
    default:             typeStr=ev.type;  detail=JSON.stringify(ev);
  }
  return {typeStr, detail};
}

function addEntry(ev) {
  const feed = document.getElementById('feed');
  const {typeStr, detail} = formatEvent(ev);
  const div = document.createElement('div');
  div.className = `entry ${ev.type}`;
  div.innerHTML = `<span class="e-time">${ev.timestamp||''}</span><span class="e-type">${typeStr}</span><span class="e-detail">${detail}</span>`;
  feed.insertBefore(div, feed.firstChild);
  feedCount++;
  while(feed.children.length > MAX_ENTRIES) feed.removeChild(feed.lastChild);
  document.getElementById('feed-count').textContent = `${feedCount} events`;
}

function updateStats(type) {
  if(type in stats) stats[type]++;
  totalEvents++;
  document.getElementById('s-move').textContent   = stats.mouse_move;
  document.getElementById('s-click').textContent  = stats.mouse_click;
  document.getElementById('s-scroll').textContent = stats.mouse_scroll;
  document.getElementById('s-key').textContent    = stats.key_press;
  document.getElementById('s-total').textContent  = totalEvents;
}

socket.on('activity', (ev) => {
  addEntry(ev);
  updateStats(ev.type);
  if(ev.type==='mouse_move'||ev.type==='mouse_click') {
    if(ev.x>screenW) screenW=ev.x+100;
    if(ev.y>screenH) screenH=ev.y+100;
    drawCrosshair(ev.x/screenW, ev.y/screenH);
    document.getElementById('coords').textContent=`X: ${ev.x}   Y: ${ev.y}`;
  }
  if(ev.type==='key_press') {
    const el=document.getElementById('last-key');
    el.textContent=ev.key; el.style.color='#f5c400';
    setTimeout(()=>{el.style.color='';},200);
  }
  if(ev.type==='mouse_click') {
    const id=ev.button==='right'?'btn-right':'btn-left';
    const cls=ev.button==='right'?'active-right':'active-left';
    const el=document.getElementById(id);
    if(ev.action==='pressed') el.classList.add(cls);
    else setTimeout(()=>el.classList.remove(cls),150);
  }
});

// Load recent events on page load
fetch('/api/recent').then(r=>r.json()).then(events=>{
  [...events].reverse().forEach(ev=>{ addEntry(ev); updateStats(ev.type); });
});

function toggleAutoScroll() {
  autoScroll=!autoScroll;
  const btn=document.getElementById('autoscroll-btn');
  btn.textContent=autoScroll?'⬇ AUTO-SCROLL ON':'⏸ AUTO-SCROLL OFF';
  btn.classList.toggle('on',autoScroll);
}
</script>
</body>
</html>
"""

# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    t = threading.Thread(target=tail_log, daemon=True)
    t.start()
    print(f"[dashboard] Log dir : {LOG_DIR}")
    print(f"[dashboard] Starting: http://{HOST}:{PORT}")
    socketio.run(app, host=HOST, port=PORT, debug=False)
