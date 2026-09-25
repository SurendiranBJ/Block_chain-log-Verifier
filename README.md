# LogChain — Zero-Trust Cross-Cloud Log Integrity & Tamper Detection System

> "Cloud providers own the logs. Our system owns the proof of what those logs originally contained."
> 
> "The blockchain protects the cryptographic commitment/proof. It does not magically make the original cloud log immutable."
> 
> "MongoDB is operational metadata only and is not a trusted cryptographic source."

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

# IMPORTANT: Geth >= 1.14 removed Clique PoA block sealing.
# Install pinned Geth v1.13.15 into ./bin/ (auto-downloads Windows/Linux/macOS binary):
python scripts/download_geth.py
```

### 2. Configure environment & fresh validators
```bash
cp .env.example .env
# Setup fresh validator keys & genesis (no hardcoded credentials):
python scripts/setup_private_chain.py
# Fill in: BLOCKCHAIN_PRIVATE_KEY, BLOCKCHAIN_ACCOUNT, FLASK_SECRET_KEY
```

### 3. Start Geth nodes
```bash
# Via Bash:
./scripts/start_device1.sh   # Device 1 (primary validator)
./scripts/start_device2.sh   # Device 2 (independent validator)
./scripts/connect_nodes.sh   # Peer them
./scripts/verify_network.sh  # Confirm status

# Or cross-platform / Windows:
python scripts/start_nodes.py --all
```

### 4. Deploy V3 contract
```bash
./scripts/deploy_contract.sh
# or: python3 scripts/deploy_contract.py
# Add CONTRACT_ADDRESS= to .env
```

### 5. Run demo
```bash
./scripts/run_demo.sh        # Generate -> Hash -> Merkle -> Anchor -> Verify
python backend/app.py        # Start dashboard: http://localhost:5000
```

### 6. Demo attacks
```bash
# 1. Modify event in the middle:
python scripts/modify_event.py --sequence 51

# 2. Delete event in the middle (exact detection, zero cascading false alarms):
python scripts/delete_event.py --sequence 51

# 3. Reorder events:
python scripts/reorder_events.py --sequence-a 51 --sequence-b 52

# 4. Insert unexpected uncommitted event:
python scripts/insert_event.py --sequence 51

# Reset demo (preserves append-only blockchain, unique run case):
./scripts/reset_demo.sh
```

---

## Pre-flight Check
```bash
python scripts/preflight_check.py
```

---

## Test Suite
```bash
pytest tests/   # 67 unit & integration tests
```

---

## Project Structure

```
backend/           Core pipeline (canonical, hashing, merkle, blockchain, verifier, alerts)
adapters/          Log getter adapters (local + AWS/Azure stubs)
contracts/         LogIntegrityV3.sol (append-only, event identity protected)
scripts/           Start/connect/deploy/demo/attack scripts
demo/              Event generator + sample_logs/
tests/             67-test pytest suite (unit + tests/integration/)
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