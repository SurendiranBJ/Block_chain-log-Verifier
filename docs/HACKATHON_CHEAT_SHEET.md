# LogChain - Hackathon One-Page Cheat Sheet

```
============================================================
QUICK REFERENCE CARD
============================================================
DEVICE 1 IP:   ______________________ (e.g. 192.168.1.100)
DEVICE 2 IP:   ______________________ (e.g. 192.168.1.101)
CHAIN ID:      12345
DEVICE 1 P2P:  30303 (TCP/UDP)
DEVICE 2 P2P:  30304 (TCP/UDP)
DEVICE 1 RPC:  8545 (localhost only)
DEVICE 2 RPC:  8546 (restricted)
DASHBOARD:     5000 (http://<DEVICE1_IP>:5000)
MONGO:         27017 (localhost only)
API TOKEN:     lc-hackathon-token-2026
============================================================
```

---

## 1. Laptop 1 (Device 1 Main System) Commands

```bash
# 1. Install & Pin Geth 1.13.15
pip install -r requirements.txt
python scripts/download_geth.py

# 2. Setup Validator Keys & Genesis
cp .env.device1.example .env
python scripts/setup_private_chain.py
# (Edit .env with generated BLOCKCHAIN_ACCOUNT & BLOCKCHAIN_PASSWORD)

# 3. Start Node 1
python scripts/start_nodes.py --clean --node 1

# 4. Deploy Contract
python scripts/deploy_contract.py
# (Add output CONTRACT_ADDRESS=0x... to .env)

# 5. Start Flask Dashboard
python backend/app.py

# 6. Pre-Flight Verification
python scripts/hackathon_preflight.py

# 7. Reset to Clean State (GREEN)
python scripts/reset_demo.py --count 10
```

---

## 2. Laptop 2 (Device 2 / Friend System) Commands

```bash
# 1. Install & Pin Geth 1.13.15
pip install -r requirements.txt
python scripts/download_geth.py

# 2. Configure Environment & Copy genesis.json from Laptop 1
cp .env.device2.example .env
# (Set DEVICE1_IP=<LAPTOP1_IP>, set DEVICE2_ACCOUNT & DEVICE2_PASSWORD)

# 3. Start Node 2
python scripts/start_nodes.py --clean --node 2

# 4. Connect to Laptop 1
python scripts/connect_nodes.py --enode "<DEVICE1_ENODE>"

# 5. Friend Cloud Test (No Blockchain Keys Needed!)
python scripts/test_cloud_adapter.py --provider aws --mock

# 6. Transmit Cloud Logs to Laptop 1 Over Wi-Fi
python scripts/test_remote_ingest.py \
    --url http://<DEVICE1_IP>:5000/api/ingest \
    --token lc-hackathon-token-2026 \
    --case-id CASE-CLOUD-01
```

---

## 3. Attack & Tamper Demo Commands (Run on Laptop 1)

| Demo Action | Command | Expected Dashboard Result |
| :--- | :--- | :--- |
| **Clean State** | `python scripts/reset_demo.py --count 10` | **VERIFIED (GREEN)** |
| **Ingest Cloud Batch** | `python scripts/test_remote_ingest.py --token lc-hackathon-token-2026` | **ANCHORED (GREEN)** |
| **Attack: Modify Event** | `python scripts/modify_event.py --seq 3` | **TAMPER DETECTED (RED)** - Hash mismatch |
| **Attack: Delete Event** | `python scripts/delete_event.py --seq 2` | **TAMPER DETECTED (RED)** - Missing event |
| **Attack: Reorder Events**| `python scripts/reorder_events.py --seq1 4 --seq2 5`| **TAMPER DETECTED (RED)** - Sequence violation |
| **Attack: Insert Rogue** | `python scripts/insert_event.py --after 1` | **TAMPER DETECTED (RED)** - Unexpected event |
| **Self-Healing Recovery**| `python scripts/reset_demo.py --count 10` | **RESTORED (GREEN)** |

---

## 4. Emergency Troubleshooting

- **Node 1 or Node 2 won't start:**
  `python scripts/start_nodes.py --stop`
  `python scripts/start_nodes.py --clean --all`
- **Peer count is 0:**
  Check Windows Firewall on Laptop 1 allows port 30303 TCP/UDP.
  Check Windows Firewall on Laptop 2 allows port 30304 TCP/UDP.
- **Port 5000 unreachable from Laptop 2:**
  Check Windows Firewall allows inbound TCP 5000 on Laptop 1.
