# LogChain Architecture

## System Overview

**Zero-Trust Cross-Cloud Log Integrity & Tamper Detection System**

> "Cloud providers own the logs. Our system owns the proof of what those logs originally contained."

---

## Core Principles

- **THE BLOCKCHAIN AS COMMITMENT** — "The blockchain protects the cryptographic commitment/proof. It does not magically make the original cloud log immutable."
- **MONGODB AS OPERATIONAL METADATA** — "MongoDB is operational metadata only and is not a trusted cryptographic source."
- **TAMPER-EVIDENT** — not tamper-proof
- **INDEPENDENT VERIFICATION** — separate integrity ledger
- **CRYPTOGRAPHIC COMMITMENT** — SHA-256 + Merkle + blockchain
- **DETECTS POST-COMMITMENT MODIFICATION** — via hash comparison
- **PROVIDER-AGNOSTIC** — adapters isolate cloud-specific logic

---

## Architecture Diagram

```
Cloud Logs / Local Simulator
        │
        ▼
┌─────────────────────┐
│  Log Getter Adapter  │  (AWS / Azure / Local)
│  fetch_events()      │  Returns normalized events only
└─────────┬───────────┘
          │  list[NormalizedEvent]
          ▼
┌─────────────────────┐
│  Normalized Event   │  {event_id, provider, service, source,
│  Schema (canonical) │   case_id, sequence, timestamp, message}
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Canonical          │  Deterministic UTF-8 JSON
│  Serialization      │  Sorted keys, compact separators
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  SHA-256            │  64-char hex per event
│  Hash Engine        │
└─────────┬───────────┘
          │  [hash_1, hash_2, ..., hash_N]
          ▼
┌─────────────────────┐
│  Merkle Batch       │  Binary tree, deterministic ordering
│  Root Computation   │  Duplicate-last for odd counts
└─────────┬───────────┘
          │  (batch_id, merkle_root, event_hashes)
          ▼
┌─────────────────────┐
│  LogIntegrityV3     │  Append-only Solidity contract
│  Blockchain Anchor  │  Duplicate batch protection
└────────┬────────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
Device 1    Device 2
(primary)   (independent validator)
    │         │
    └────┬────┘
         │
         ▼
┌─────────────────────┐
│  Verification       │  Compare current vs committed hashes
│  Engine             │  States: GREEN/MODIFIED/DELETED/
└────────┬────────────┘          UNEXPECTED/REORDERED
         │
    ┌────┴────┐
    │         │
    ▼         ▼
Dashboard  MongoDB Alerts
(Flask)    (tamper evidence)
```

---

## Security Model

A privileged attacker may modify or delete cloud-side logs, but the original
cryptographic commitment remains independently anchored on the separate
integrity ledger, so later verification can detect changes provided the
trusted ledger/proof system itself has not been compromised.

**The blockchain protects the COMMITMENT / PROOF.**  
**It does NOT magically make the cloud log file immutable.**

---

## Two-Node Architecture

| Role | Device 1 | Device 2 |
|------|----------|----------|
| Type | Primary | Independent Validator |
| Geth | Mining validator | Replica |
| RPC Port | 8545 | 8546 |
| P2P Port | 30303 | 30304 |
| Backend | Yes | No |
| Dashboard | Yes | No |
| MongoDB | Yes | No |

---

## V3 Contract Design

**Append-Only**: Once a batch is committed, it cannot be overwritten.

```solidity
function anchorBatch(
    string caseId,
    string batchId,
    string merkleRoot,
    uint256 entryCount,
    string[] eventHashes
) external onlyWriter
```

**Reverts if**:
- batchId already exists (no overwrites)
- merkleRoot or batchId is empty
- caller is not authorized writer

---

## Verification States

| State | Meaning |
|-------|---------|
| `GREEN` | Hash matches blockchain commitment |
| `MODIFIED` | Hash changed since commitment |
| `DELETED` | Event committed but now missing |
| `UNEXPECTED` | Event exists but was never committed |
| `REORDERED` | Event ID is at wrong sequence position |
| `MISSING_COMMITMENT` | No blockchain record found |
| `BLOCKCHAIN_ERROR` | Cannot reach chain |

---

## Adapter Pattern

The integrity pipeline is completely provider-independent.

```
AWS Getter ──────────\
                      \
Azure Getter ──────────▶ Normalized Event ──▶ Integrity Pipeline
                      /
Local Getter ─────────/
```

Cloud adapters implement ONE interface:
```python
class LogGetter(ABC):
    def fetch_events(self, case_id: str) -> list[dict]: ...
    def health_check(self) -> dict: ...
```

---

## File Structure

```
backend/
    app.py          Flask API + dashboard
    config.py       Environment config (no secrets)
    canonical.py    Deterministic serialization
    hashing.py      SHA-256 engine
    merkle.py       Merkle tree
    blockchain.py   Web3 interface
    verifier.py     Verification engine
    alerts.py       MongoDB alert store
    pipeline.py     Core ingestion pipeline

adapters/
    base.py         Abstract interface
    local_getter.py Demo/test adapter
    aws_getter.py   AWS stub (friend implements)
    azure_getter.py Azure stub (friend implements)

contracts/
    LogIntegrityV3.sol  Append-only V3 contract

scripts/
    start_device1.sh    Start primary node
    start_device2.sh    Start validator node
    connect_nodes.sh    Peer the two nodes
    verify_network.sh   Check network status
    deploy_contract.py  Deploy V3 contract
    preflight_check.py  System pre-flight
    run_demo.sh         Full demo flow
    reset_demo.sh       Reset to GREEN
    modify_event.py     Attack: modify
    delete_event.py     Attack: delete

demo/
    generate_logs.py    100 deterministic demo events
    sample_logs/        Case JSON files

tests/
    test_all.py         Full test suite

docs/
    ARCHITECTURE.md     This file
    FRIEND_INTEGRATION.md  For cloud adapter developer
    DEMO_RUNBOOK.md     Step-by-step demo
    SECURITY.md         Security notes
```
