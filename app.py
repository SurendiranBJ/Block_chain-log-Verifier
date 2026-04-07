"""
app.py  —  Flask Frontend with AJAX-Powered Live Dashboard
────────────────────────────────────────────────────────────────────
Now launches LogMonitor as a background daemon upon startup.
Serves a dynamic, no-refresh UI that auto-submits and flags tampers
instantaneously utilizing REST APIs and Watchdog.
"""

import hashlib
import json
import os
from flask import Flask, render_template_string, request, jsonify
from web3 import Web3
from merkle import build_merkle_tree
from watcher import LogMonitor

app = Flask(__name__)

# ── Config ────────────────────────────────────────────────────────
CONFIG_PATH         = "/home/sura/logchain/config.json"
RPC_URL             = "http://10.28.109.210:8545"
CONTRACT_ADDRESS_V1 = "0xE89d89d78b1a2BBA11Cb36C0750c28cBbd118862"

# ── Start LogMonitor Daemon ───────────────────────────────────────
print("🚀 Starting Background LogMonitor Daemon...")
monitor = LogMonitor(CONFIG_PATH)
monitor.start()

# ── Legacy V1 setup (for / route only) ────────────────────────────
w3 = Web3(Web3.HTTPProvider(RPC_URL))
ABI_V1_PATH = "/home/sura/logchain/LogIntegrity_abi.json"
if os.path.exists(ABI_V1_PATH):
    with open(ABI_V1_PATH) as f:
        contract_v1 = w3.eth.contract(address=CONTRACT_ADDRESS_V1, abi=json.load(f))

# ── HTML Templates & Styles ───────────────────────────────────────
COMMON_STYLE = """
body { font-family: Arial; background: #1a1a2e; color: #eee; padding: 40px; }
h1 { color: #00d4ff; }
nav a { color: #00d4ff; margin-right: 20px; font-weight: bold; text-decoration: none;
        border: 1px solid #00d4ff; padding: 6px 14px; border-radius: 6px; }
nav a:hover { background: #00d4ff; color: #000; }
nav { margin-bottom: 30px; }
.card { background: #16213e; padding: 20px; border-radius: 10px; margin: 20px 0; }
.verified { color: #00ff88; font-size: 2em; font-weight: bold; }
.tampered-title { color: #ff4444; font-size: 2em; font-weight: bold; }
label { color: #00d4ff; font-weight: bold; display: inline-block; margin-top: 5px; }
input { background: #1a1a2e; color: #eee; border: 1px solid #00d4ff; padding: 8px; border-radius: 4px; box-sizing: border-box; }
button { background: #00d4ff; color: #000; border: none; padding: 10px 20px; border-radius: 4px; font-weight: bold; cursor: pointer; margin-top:10px; }
button:hover { background: #00a0cc; }
table { width: 100%; border-collapse: collapse; margin-top: 10px; }
th { background: #0f3460; padding: 10px; text-align: left; color: #00d4ff; }
td { padding: 10px; border-bottom: 1px solid #0f3460; font-size: 0.85em; }
.mono { font-family: monospace; font-size: 0.8em; }
.row-ok       { background: transparent; }
.row-tampered { background: rgba(255,50,50,0.2);  border-left: 4px solid #ff4444; }
.row-added    { background: rgba(255,165,0,0.2);  border-left: 4px solid orange; }
.row-deleted  { background: rgba(255,50,50,0.1);  border-left: 4px solid #aa0000; }
.row-pending  { background: rgba(100,100,255,0.1); border-left: 4px solid #6666ff; }
.tag-ok       { color: #00ff88; font-weight: bold; }
.tag-tampered { color: #ff4444; font-weight: bold; }
.tag-pending  { color: #8888ff; font-weight: bold; }
.tag-deleted  { color: #aa4444; font-weight: bold; }
.tag-added    { color: orange;  font-weight: bold; }
.badge-v2 { background:#00d4ff; color:#000; border-radius:4px; padding:2px 8px; font-size:0.75em; margin-left:8px; }
"""

HTML_ENTRIES = """
<!DOCTYPE html>
<html>
<head>
    <title>Live Dashboard — Dynamic Monitor</title>
    <style>{{ style }}</style>
</head>
<body>
    <h1>🔢 Live Auto-Monitoring & Hash Verification</h1>
    <nav>
        <a href="/">🌳 Legacy Merkle View</a>
        <a href="/entries">🔢 Live Dashboard</a>
    </nav>
    
    <div class="card" style="border: 1px solid #00d4ff">
        <label>⚙️ Monitoring Configuration</label><br><br>
        <form onsubmit="updateSettings(event)">
            <label>Active Log File:</label>
            <input type="text" id="logFile" style="width:100%" placeholder="/path/to/log.txt" />
            
            <label>Case ID:</label>
            <input type="text" id="caseId" style="width:100%" placeholder="CASE-XXXX-YYY" />
            
            <button type="submit">Update Target & Re-Scan</button>
            <span id="saveStatus" style="margin-left:15px; color:#00ff88; display:none;">Saved!</span>
        </form>
    </div>

    <div class="card">
        <label>Mode: <span class="badge-v2">V2 Background Daemon</span></label><br><br>
        <label>System Status:</label> <span id="sysStatus">Loading...</span><br><br>
        
        <label>File lines:</label> <span id="fileCount">-</span>
        &nbsp;|&nbsp;
        <label>Chain entries:</label> <span id="chainCount">-</span>
    </div>

    <div class="card" id="tableCard" style="display:none">
        <label>Real-Time Blockchain Comparison:</label>
        <table id="entriesTable">
            <tr>
                <th>#</th>
                <th>Status</th>
                <th>Line Content</th>
                <th>File SHA-256</th>
                <th>Chain SHA-256</th>
            </tr>
        </table>
    </div>

    <div class="card">
        <label>Node 1 (10.28.109.210):</label> 
        Conn: <span id="nodeConnected">False</span> | Block: <span id="blockNumber">0</span>
        <br><br>
        <label>Node 2 (10.28.109.234):</label> 
        Conn: <span id="node2Connected" style="color:#aaa">False</span> | Block: <span id="node2BlockNumber" style="color:#aaa">0</span>
    </div>
    <p style="color:#555">⚡ Fetching updates from Background Daemon via AJAX...</p>

    <!-- AJAX CLIENT SCRIPT -->
    <script>
        let isEditing = false;
        
        // Don't overwrite the inputs while the user is typing
        document.getElementById('logFile').addEventListener('focus', () => isEditing = true);
        document.getElementById('logFile').addEventListener('blur', () => isEditing = false);
        document.getElementById('caseId').addEventListener('focus', () => isEditing = true);
        document.getElementById('caseId').addEventListener('blur', () => isEditing = false);

        async function fetchStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                
                if (!isEditing) {
                    document.getElementById('logFile').value = data.config.log_file;
                    document.getElementById('caseId').value = data.config.case_id;
                }
                
                const statusSpan = document.getElementById('sysStatus');
                if (data.results.all_ok && data.results.status !== 'Initializing...') {
                    statusSpan.innerHTML = '<span class="verified">✅ ALL ENTRIES VERIFIED</span>';
                } else if (!data.results.all_ok) {
                    statusSpan.innerHTML = `<span class="tampered-title">🚨 ${data.results.status}</span>`;
                } else {
                    statusSpan.innerHTML = `<span>${data.results.status}</span>`;
                }
                    
                document.getElementById('fileCount').innerText = data.results.file_count;
                document.getElementById('chainCount').innerText = data.results.chain_count;
                
                // Node 1
                document.getElementById('nodeConnected').innerText = data.node.connected;
                document.getElementById('nodeConnected').style.color = data.node.connected ? '#00ff88' : '#ff4444';
                document.getElementById('blockNumber').innerText = data.node.block;
                
                // Node 2
                document.getElementById('node2Connected').innerText = data.node2.connected;
                document.getElementById('node2Connected').style.color = data.node2.connected ? '#00ff88' : '#ff4444';
                document.getElementById('node2BlockNumber').innerText = data.node2.block;
                
                const table = document.getElementById('entriesTable');
                while (table.rows.length > 1) { table.deleteRow(1); } // clear
                
                if (data.results.rows.length > 0) {
                    document.getElementById('tableCard').style.display = 'block';
                    data.results.rows.forEach(row => {
                        const tr = table.insertRow();
                        tr.className = row.row_class;
                        
                        let tag = row.status.includes('TAMPERED') ? 'tag-tampered' : 
                                  row.status.includes('OK') ? 'tag-ok' : 
                                  row.status.includes('PENDING') ? 'tag-pending' : 'tag-deleted';
                                  
                        tr.innerHTML = `
                            <td>${row.index}</td>
                            <td class="${tag}">${row.status}</td>
                            <td>${row.content}</td>
                            <td class="mono">${row.file_hash}</td>
                            <td class="mono">${row.chain_hash}</td>
                        `;
                    });
                } else {
                    document.getElementById('tableCard').style.display = 'none';
                }
            } catch (e) {
                console.error("AJAX Error:", e);
            }
        }
        
        async function updateSettings(e) {
            e.preventDefault();
            const log_file = document.getElementById('logFile').value;
            const case_id = document.getElementById('caseId').value;
            
            await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ LOG_FILE: log_file, CASE_ID: case_id })
            });
            
            const msg = document.getElementById('saveStatus');
            msg.style.display = 'inline-block';
            setTimeout(() => msg.style.display = 'none', 2000);
            
            isEditing = false;
            fetchStatus();
        }
        
        fetchStatus();
        setInterval(fetchStatus, 500);
    </script>
</body>
</html>
"""

HTML_LEGACY = """
<!DOCTYPE html>
<html>
<head>
    <title>Log Integrity Dashboard</title>
    <meta http-equiv="refresh" content="10">
    <style>{{ style }}</style>
</head>
<body>
    <h1>🔐 Legacy Log Integrity Validation</h1>
    <nav>
        <a href="/">🌳 Legacy Merkle View</a>
        <a href="/entries">🔢 Live Dashboard</a>
    </nav>

    <div class="card">
        <label>Active Target:</label> <b>{{ log_file }}</b><br>
        <label>Case ID:</label> <b>{{ case_id }}</b><br><br>
        <label>Status: <span class="badge-v2" style="background:#888;color:#fff">Legacy Merkle Route</span></label><br>
        {% if verified %}
            <span class="verified">✅ VERIFIED — Original Content Matches Base Layer</span>
        {% else %}
            <span class="tampered-title">🚨 TAMPER DETECTED / OUT OF SYNC</span>
        {% endif %}
    </div>
    
    <div class="card">
        <label>Merkle Root (Current CPU compute):</label>
        <p style="font-family:monospace; color:#aaa">{{ current_root }}</p>
        <label>Merkle Root (Blockchain State):</label>
        <p style="font-family:monospace; color:#aaa">{{ blockchain_root }}</p>
    </div>
</body>
</html>
"""

# ── REST Endpoints ────────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    return jsonify({
        "config": {
            "log_file": monitor.log_file,
            "case_id": monitor.case_id
        },
        "results": monitor.results_cache,
        "node": {
            "connected": monitor.w3.is_connected(),
            "block": monitor.w3.eth.block_number if monitor.w3.is_connected() else 0
        },
        "node2": getattr(monitor, 'node2_status', {"connected": False, "block": 0})
    })

@app.route("/api/settings", methods=["POST"])
def api_settings():
    data = request.json
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)
    # Ping the daemon to restart its watchdog and run verify
    monitor.update_target()
    return jsonify({"success": True})


# ── Full Page Routes ──────────────────────────────────────────────

@app.route("/entries")
def entries_view():
    return render_template_string(HTML_ENTRIES, style=COMMON_STYLE)

@app.route("/")
def index():
    # Retains legacy Merkle backward compatibility logic
    try:
        log_file = monitor.log_file
        case_id  = monitor.case_id
        
        if os.path.exists(log_file):
            with open(log_file, "r") as f:
                entries = [line for line in f.readlines() if line.strip()]
        else:
            entries = []

        current_root, _, _ = build_merkle_tree(entries)
        result           = contract_v1.functions.getLog(case_id).call()
        blockchain_root  = result[0]
        verified         = (current_root == blockchain_root)
        
    except Exception as ex:
        current_root, blockchain_root, verified = str(ex), "Errors", False
        log_file, case_id = monitor.log_file, monitor.case_id

    return render_template_string(
        HTML_LEGACY,
        style=COMMON_STYLE,
        log_file=log_file,
        case_id=case_id,
        verified=verified,
        current_root=current_root,
        blockchain_root=blockchain_root
    )

if __name__ == "__main__":
    # Disable auto-reloading to prevent multi-spawning daemon threads
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
