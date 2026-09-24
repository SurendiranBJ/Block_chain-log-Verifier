# LogChain — Zero-Trust Cross-Cloud Log Integrity & Tamper Detection System

> "Cloud providers own the logs. Our system owns the proof of what those logs originally contained."

A **tamper-evident**, **blockchain-anchored** log integrity system for cloud forensics. Built for hackathon demonstration with a clean local-first core and pluggable cloud adapters.

---

## Architecture

```
Cloud Logs / Local Simulator
        |
        v
 Log Getter Adapter (AWS / Azure / Local)
        |
        v
 Normalized Event Schema
        |
        v
 Canonical Serialization (deterministic UTF-8 JSON)
        |
        v
 SHA-256 per Event
        |
        v
 Merkle Batch Root
        |
        v
 LogIntegrityV3 (append-only Solidity contract)
        |
    +---+---+
    |       |
Device 1   Device 2 (independent validator)
    |
    v
 Verification Engine
    |
 +--+--+
 |     |
Dashboard  MongoDB Alerts
```

---

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Generate fresh key: python scripts/preflight_check.py --gen-key
# Fill in: BLOCKCHAIN_PRIVATE_KEY, BLOCKCHAIN_ACCOUNT, FLASK_SECRET_KEY
```

### 3. Start Geth nodes
```bash
./scripts/start_device1.sh   # Device 1 (primary)
./scripts/start_device2.sh   # Device 2 (independent validator)
./scripts/connect_nodes.sh   # Peer them
./scripts/verify_network.sh  # Confirm status
```

### 4. Deploy V3 contract
```bash
python scripts/deploy_contract.py
# Add CONTRACT_ADDRESS= to .env
```

### 5. Run demo
```bash
./scripts/run_demo.sh        # Generate -> Hash -> Merkle -> Anchor -> Verify
python backend/app.py        # Start dashboard: http://localhost:5000
```

### 6. Demo attacks
```bash
python scripts/modify_event.py --case CASE-001 --sequence 51  # RED: MODIFIED
python scripts/delete_event.py --case CASE-001 --sequence 51  # RED: DELETED
./scripts/reset_demo.sh                                        # GREEN: reset
```

---

## Pre-flight Check
```bash
python scripts/preflight_check.py
```

---

## Test Suite
```bash
pytest tests/   # 61 tests: canonical, SHA-256, Merkle, pipeline, verification, adapters
```

---

## Project Structure

```
backend/           Core pipeline (canonical, hashing, merkle, blockchain, verifier, alerts)
adapters/          Log getter adapters (local + AWS/Azure stubs)
contracts/         LogIntegrityV3.sol (append-only, duplicate-protected)
scripts/           Start/connect/deploy/demo/attack scripts
demo/              Event generator + sample_logs/
tests/             61-test pytest suite
docs/              ARCHITECTURE.md, FRIEND_INTEGRATION.md, DEMO_RUNBOOK.md, SECURITY.md
legacy/            Original pre-refactor code (preserved for reference)
.env.example       Configuration template
```

---

## For Cloud Adapter Contributors

See [docs/FRIEND_INTEGRATION.md](docs/FRIEND_INTEGRATION.md).

You only need to implement **two files**:
- `adapters/aws_getter.py`
- `adapters/azure_getter.py`

The integrity pipeline (hashing, Merkle, blockchain, verification) does not need any changes.

---

## Security Model

**TAMPER-EVIDENT** — not tamper-proof.

A privileged attacker may modify or delete cloud-side logs, but the original
cryptographic commitment remains independently anchored on the separate integrity
ledger, so later verification can detect changes.

**Verification States:**
`GREEN` | `MODIFIED` | `DELETED` | `UNEXPECTED` | `REORDERED` | `MISSING_COMMITMENT` | `BLOCKCHAIN_ERROR`

---

## Chain Configuration

- Chain ID: `12345`
- Consensus: Clique (PoA)
- Contract: `LogIntegrityV3` (append-only batch anchoring)
- Genesis: `genesis.json`