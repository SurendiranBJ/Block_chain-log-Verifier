# LogChain: Two-Laptop Physical Deployment & Demonstration Guide

This guide details the exact procedures for deploying and demonstrating **LogChain** across two physical laptops (e.g. Laptop 1 = Main Forensic System, Laptop 2 = Independent Validator / Friend Cloud Getter) connected to the same Wi-Fi or local area network (LAN).

---

## A. Architecture Diagram

```
                 FRIEND'S LAPTOP (DEVICE 2)
                 ==========================
                 +------------------------+
                 | AWS / Azure Cloud Logs |
                 +------------------------+
                             |
                             v
                 +------------------------+
                 | Cloud Getter Adapter   |
                 | (boto3 / Azure SDK)    |
                 +------------------------+
                             |
                             v
                 +------------------------+
                 | Normalized Event Schema|
                 | (Deterministic JSON)   |
                 +------------------------+
                             |
                             | HTTP POST /api/ingest
                             | Header: X-API-Key: <TOKEN>
                             | (Over Wi-Fi / Local LAN)
                             v
                 PRIMARY LAPTOP (DEVICE 1)
                 =========================
                 +------------------------+
                 | Flask /api/ingest      |
                 +------------------------+
                             |
                             v
                 +------------------------+
                 | SHA-256 Event Hashing  |
                 +------------------------+
                             |
                             v
                 +------------------------+
                 | Merkle Tree Batch Root |
                 +------------------------+
                             |
                             v
                 +------------------------+
                 | LogIntegrityV3 Contract|
                 | (Append-Only Anchor)   |
                 +------------------------+
                             |
                +------------+------------+
                |                         |
                v                         v
     +--------------------+    +--------------------+
     | Device 1 Validator |    | Device 2 Validator |
     | (Port 8545/30303)  |    | (Port 8546/30304)  |
     +--------------------+    +--------------------+
                |                         |
                +------------+------------+
                             | P2P Block Sync
                             v
                 +------------------------+
                 | Independent Verifier   |
                 | (Cryptographic Proof)  |
                 +------------------------+
                             |
              +--------------+--------------+
              |                             |
              v                             v
   +--------------------+        +--------------------+
   | Flask Dashboard    |        | MongoDB Alerts     |
   | (Port 5000 UI)     |        | (Localhost:27017)  |
   +--------------------+        +--------------------+
```

---

## B. Device 1 Responsibilities (Laptop 1: Primary System)

- Runs Flask Web Dashboard & REST API (`http://0.0.0.0:5000`)
- Runs MongoDB Community Server (`localhost:27017` only) for alert audit logs
- Runs Device 1 Geth PoA Validator (`port 8545`, `P2P 30303`)
- Holds Device 1 validator private key (`BLOCKCHAIN_PRIVATE_KEY`)
- Deploys and manages `LogIntegrityV3` Solidity smart contract
- Executes cryptographic verification comparing raw events directly against on-chain batch commitments
- Exposes authenticated `POST /api/ingest` for Friend Laptop events

---

## C. Device 2 Responsibilities (Laptop 2: Independent Validator & Friend System)

- Runs Device 2 Geth PoA Validator (`port 8546`, `P2P 30304`)
- Holds Device 2's **independent** validator key (`DEVICE2_ACCOUNT`)
- Continuously seals and replicates identical blocks from Device 1 via P2P
- **SECURITY GUARANTEE**: Does NOT store, require, or have access to Device 1's private key
- Does NOT require MongoDB or Flask
- Pulls live AWS CloudTrail or Azure Activity logs (or mocks) via `scripts/test_cloud_adapter.py`
- Pushes normalized events over Wi-Fi to Device 1 via `scripts/test_remote_ingest.py`

---

## D. Network Topology

| Device | Role | Hostname / IP | RPC Endpoint | P2P Port |
| :--- | :--- | :--- | :--- | :--- |
| **Laptop 1** | Primary System / Backend | `<DEVICE1_IP>` (e.g. `192.168.1.100`) | `http://127.0.0.1:8545` (Localhost) | `30303 TCP/UDP` |
| **Laptop 2** | Independent Validator | `<DEVICE2_IP>` (e.g. `192.168.1.101`) | `http://127.0.0.1:8546` (Localhost) | `30304 TCP/UDP` |

---

## E. Required Firewall Ports

### Laptop 1 (Device 1) Inbound Rules
- `30303 TCP & UDP` (Geth P2P discovery & block sync from Laptop 2)
- `5000 TCP` (Flask Dashboard & Ingest API from Laptop 2 & judges)
- **DO NOT EXPOSE**: `27017` (MongoDB) or `8545` (Device 1 RPC) to external network.

### Laptop 2 (Device 2) Inbound Rules
- `30304 TCP & UDP` (Geth P2P discovery & block sync from Laptop 1)

---

## F. IP Address Discovery

### Windows (PowerShell)
```powershell
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } | Select-Object -ExpandProperty IPAddress
```

### Linux / Ubuntu / WSL
```bash
hostname -I | awk '{print $1}'
```

### Connectivity Verification
```powershell
# From Laptop 2 to Laptop 1:
Test-NetConnection 192.168.1.100 -Port 5000
Test-NetConnection 192.168.1.100 -Port 30303

# From Laptop 1 to Laptop 2:
Test-NetConnection 192.168.1.101 -Port 30304
```

---

## G. Geth Version Requirement (CRITICAL)

> [!WARNING]
> **Clique PoA Deprecation in Upstream Geth**
> Official go-ethereum (Geth) releases v1.14.0+ removed Clique Proof-of-Authority (PoA) block sealing as part of post-Merge cleanup.
> Running `geth --mine` with a Clique genesis on Geth v1.14+ fails with fatal errors requiring `terminalTotalDifficulty` and PoS consensus clients.
>
> **LogChain strictly pins Geth v1.13.15**.
> Automated download script:
> ```bash
> python scripts/download_geth.py
> ```
> This installs official Geth v1.13.15 into `./bin/` across Windows, Linux, and macOS. All node management scripts prioritize this binary automatically.

---

## H. MongoDB Setup (Device 1 Only)

### Native Windows/Linux Service
Verify service status:
```bash
python -c "from backend.alerts import is_mongodb_available; print('MongoDB Status:', is_mongodb_available())"
```

### Or Via Docker (Fastest for Hackathons)
```bash
docker pull mongodb/mongodb-community-server:latest
docker run --name logchain-mongodb -p 127.0.0.1:27017:27017 -d mongodb/mongodb-community-server:latest
```

---

## I. Device 1 Setup Step-by-Step

### 1. Clone & Dependencies
```bash
git clone https://github.com/SurendiranBJ/Block_chain-log-Verifier.git LogChain
cd LogChain
pip install -r requirements.txt
python scripts/download_geth.py
```

### 2. Configure Environment
```bash
cp .env.device1.example .env
# Generate fresh cryptographic credentials & genesis.json:
python scripts/setup_private_chain.py
# (Ensure BLOCKCHAIN_ACCOUNT, BLOCKCHAIN_PRIVATE_KEY, and BLOCKCHAIN_PASSWORD are set)
```

### 3. Start Geth Validator & Peer
```bash
# Start Node 1:
python scripts/start_nodes.py --clean --node 1

# Obtain Device 1 Enode:
python scripts/connect_nodes.py --show-enode
```

### 4. Deploy Contract
```bash
python scripts/deploy_contract.py
# Copy printed CONTRACT_ADDRESS=0x... into .env
```

### 5. Start Flask Backend
```bash
python backend/app.py
```

---

## J. Device 2 Setup Step-by-Step (Laptop 2)

### 1. Clone & Dependencies
```bash
git clone https://github.com/SurendiranBJ/Block_chain-log-Verifier.git LogChain
cd LogChain
pip install -r requirements.txt
python scripts/download_geth.py
```

### 2. Configure Environment & Genesis
```bash
cp .env.device2.example .env
# Copy the exact matching genesis.json from Laptop 1
# Set DEVICE1_IP=<LAPTOP1_LAN_IP>
# Set DEVICE2_ACCOUNT & DEVICE2_PASSWORD
```

### 3. Start Node 2 & Connect to Laptop 1
```bash
# Start Node 2:
python scripts/start_nodes.py --clean --node 2

# Connect to Laptop 1:
python scripts/connect_nodes.py --enode "<DEVICE1_ENODE_URI>"
```

### 4. Verify Synchronization
```bash
bash scripts/verify_peers.sh
# Both devices should report the same block height and >= 1 peer.
```

---

## K. Friend Cloud Log Ingestion

From Laptop 2, friend can test cloud normalization locally:
```bash
# Test local normalization & schema compliance:
python scripts/test_cloud_adapter.py --provider aws --mock

# Transmit normalized events to Laptop 1 over Wi-Fi:
python scripts/test_remote_ingest.py \
    --url http://<DEVICE1_IP>:5000/api/ingest \
    --token lc-hackathon-token-2026 \
    --case-id CASE-CLOUD-DEMO-01
```

---

## L. Live Hackathon Judge Demonstration Sequence

1. **Clean Baseline (GREEN)**:
   - Run `python scripts/reset_demo.py --count 10`.
   - Open browser at `http://<DEVICE1_IP>:5000`.
   - Show judges:
     - Integrity status: **VERIFIED (GREEN)**
     - Multi-node status: **Device 1 & Device 2 in sync**
     - Contract commitment: **On-chain Merkle root verified**

2. **Cross-Laptop Ingestion**:
   - Have friend on Laptop 2 run:
     `python scripts/test_remote_ingest.py --url http://<DEVICE1_IP>:5000/api/ingest --token lc-hackathon-token-2026`
   - Show dashboard updates in real time with new cloud batch anchored.

3. **Attack: Unauthorized Log Modification (RED)**:
   - Attacker alters log message: `python scripts/modify_event.py --seq 3`.
   - Refresh dashboard.
   - Show judges:
     - Integrity status: **TAMPER DETECTED (RED)**
     - Exact Event ID: `evt-000003` (Sequence 3)
     - Root cause: Cryptographic hash mismatch against on-chain block commitment.

4. **Self-Healing / Recovery (GREEN)**:
   - Run `python scripts/reset_demo.py --count 10`.
   - Dashboard returns immediately to **VERIFIED (GREEN)**.
