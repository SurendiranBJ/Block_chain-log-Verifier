# LogChain Demo Runbook

## Pre-Requisites

```bash
pip install -r requirements.txt
# Install geth: https://geth.ethereum.org/downloads
# Install MongoDB: https://www.mongodb.com/try/download/community
# Copy .env.example → .env and fill in values
```

---

## Full Demo Flow

### Step 1: Start Device 1

```bash
./scripts/start_device1.sh
```

### Step 2: Start Device 2 (separate machine or terminal)

```bash
./scripts/start_device2.sh
```

### Step 3: Connect Peers

```bash
./scripts/connect_nodes.sh
```

### Step 4: Verify Network

```bash
./scripts/verify_network.sh
# Expected: Device 1 PASS, Device 2 PASS or BLOCKED
```

### Step 5: Deploy V3 Contract

```bash
python scripts/deploy_contract.py
# Update .env: CONTRACT_ADDRESS=<output address>
```

### Step 6-13: Run Full Demo

```bash
./scripts/run_demo.sh
```

This:
- Generates 100 events
- Ingests → SHA-256 → Merkle → blockchain
- Verifies → DASHBOARD: GREEN

---

## Attack Demos

### Demo A: Modify Event

```bash
# Show GREEN dashboard
python scripts/modify_event.py --case CASE-001 --sequence 51
# Verify
curl -X POST http://localhost:5000/api/verify -H "Content-Type: application/json" -d "{}"
# Dashboard shows: 🚨 MODIFIED - evt-000051
```

### Demo B: Delete Event

```bash
python scripts/delete_event.py --case CASE-001 --sequence 51
# Verify
# Dashboard shows: 🚨 DELETED - evt-000051
```

### Demo C: Reset to GREEN

```bash
./scripts/reset_demo.sh
# Dashboard shows: ✅ GREEN
```

---

## Starting the Dashboard

```bash
python backend/app.py
# Open: http://localhost:5000
```

---

## Key Commands Reference

| Command | Purpose |
|---------|---------|
| `python scripts/preflight_check.py` | Check all dependencies |
| `python demo/generate_logs.py` | Generate 100 demo events |
| `python scripts/deploy_contract.py` | Deploy V3 contract |
| `python scripts/modify_event.py --sequence 51` | Simulate modify attack |
| `python scripts/delete_event.py --sequence 51` | Simulate delete attack |
| `./scripts/reset_demo.sh` | Reset to GREEN |
| `pytest tests/` | Run all tests |

---

## Threat Model Statement

> A privileged attacker may modify or delete cloud-side logs, but the original
> cryptographic commitment remains independently anchored on the separate
> integrity ledger, so later verification can detect changes provided the
> trusted ledger/proof system itself has not been compromised.

**Correct claims:**
- TAMPER-EVIDENT ✓
- INDEPENDENT VERIFICATION ✓
- CRYPTOGRAPHIC COMMITMENT ✓
- DETECTS POST-COMMITMENT MODIFICATION ✓

**Do NOT claim:**
- "Impossible to tamper" ✗
- "Root access cannot change logs" ✗
- "Blockchain prevents all attacks" ✗
