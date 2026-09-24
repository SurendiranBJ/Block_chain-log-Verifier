# LogChain Demo Runbook

## Pre-Requisites

```bash
pip install -r requirements.txt
# Install geth: https://geth.ethereum.org/downloads
# Install MongoDB: https://www.mongodb.com/try/download/community
```

---

## 1. Private Blockchain Setup (Fresh Credentials)

```bash
# Generate fresh validator accounts and genesis with 2 Clique signers
python scripts/setup_private_chain.py
# Copy generated credentials into .env on Device 1 & Device 2
```

---

## 2. Starting the Network

### Step 1: Start Device 1 (Primary Validator)

```bash
./scripts/start_device1.sh
```

### Step 2: Start Device 2 (Independent Validator)

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
# Expected: Device 1 PASS, Device 2 PASS (or BLOCKED if second physical device offline)
```

### Step 5: Deploy LogIntegrityV3 Contract

```bash
# Either wrapper or python script:
./scripts/deploy_contract.sh
# or: python3 scripts/deploy_contract.py

# Update .env with the output address:
# CONTRACT_ADDRESS=0x...
```

---

## 3. Running the Live Demo

### Step 1: Start Dashboard

```bash
python backend/app.py
# Open http://localhost:5000 in your browser
```

### Step 2: Initialize Clean State

```bash
./scripts/reset_demo.sh
# Dashboard displays: ✅ ALL VERIFIED (GREEN)
```

---

## 4. Attack Demonstrations (All 4 Attacks)

### Attack 1: Middle-Event Modification

```bash
python scripts/modify_event.py --sequence 51
# Verify: click 'Verify' in dashboard or run:
curl -X POST http://localhost:5000/api/verify -H "Content-Type: application/json" -d "{}"
# Dashboard displays: 🚨 INTEGRITY VIOLATION (RED)
# Attack panel shows: MODIFIED | Event ID: evt-000051 | Sequence: 51 | Expected Hash vs Actual Hash
```

### Reset Demo (Append-Only Safe)

```bash
./scripts/reset_demo.sh
# Dashboard displays: ✅ ALL VERIFIED (GREEN) with new unique Case ID
```

### Attack 2: Middle-Event Deletion

```bash
python scripts/delete_event.py --sequence 51
# Verify
# Dashboard displays: 🚨 INTEGRITY VIOLATION (RED)
# Attack panel shows: DELETED | Event ID: evt-000051 | Sequence: 51 | Actual: MISSING
# Notice: ONLY event 51 is flagged DELETED. Later events 52-100 remain GREEN!
```

### Reset Demo

```bash
./scripts/reset_demo.sh
# Dashboard displays: ✅ ALL VERIFIED (GREEN)
```

### Attack 3: Event Reordering

```bash
python scripts/reorder_events.py --sequence-a 51 --sequence-b 52
# Verify
# Dashboard displays: 🚨 INTEGRITY VIOLATION (RED)
# Attack panel shows: REORDERED | Sequences 51 <-> 52
# Content intact, sequence mismatch explicitly flagged as REORDERED (not MODIFIED)
```

### Reset Demo

```bash
./scripts/reset_demo.sh
# Dashboard displays: ✅ ALL VERIFIED (GREEN)
```

### Attack 4: Unexpected Event Insertion

```bash
python scripts/insert_event.py --sequence 51
# Verify
# Dashboard displays: 🚨 INTEGRITY VIOLATION (RED)
# Attack panel shows: UNEXPECTED | Event ID: attacker-injected-0051 | Uncommitted event detected
```

### Reset Demo

```bash
./scripts/reset_demo.sh
# Dashboard displays: ✅ ALL VERIFIED (GREEN)
```

---

## Key Commands Reference

| Command | Purpose |
|---------|---------|
| `python scripts/preflight_check.py` | Check system dependencies and environment |
| `python scripts/setup_private_chain.py` | Generate fresh validator keys and genesis |
| `./scripts/deploy_contract.sh` | Deploy V3 contract via safe wrapper |
| `python backend/app.py` | Launch dashboard at `http://localhost:5000` |
| `./scripts/reset_demo.sh` | Reset demo state (append-only safe) |
| `python scripts/modify_event.py --sequence 51` | Simulate middle-event modification |
| `python scripts/delete_event.py --sequence 51` | Simulate middle-event deletion |
| `python scripts/reorder_events.py --sequence-a 51 --sequence-b 52` | Simulate event reordering |
| `python scripts/insert_event.py --sequence 51` | Simulate unexpected event insertion |
| `pytest tests/` | Run all 67 unit & integration tests |

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
- DETECTS POST-COMMITMENT MODIFICATION, DELETION, REORDERING, INSERTION ✓

**Do NOT claim:**
- "Impossible to tamper" ✗
- "Root access cannot change logs" ✗
- "Blockchain prevents all attacks" ✗
