# LogChain Friend Integration Guide
## Zero-Trust Cross-Cloud Log Integrity System

---

## 🎯 Your Job Is Simple

You only need to implement **two files**:

```
adapters/aws_getter.py       ← Replace the TODOs
adapters/azure_getter.py     ← Replace the TODOs
```

**That's it.** You do NOT touch anything else.

---

## Files You Are Allowed To Modify

| File | Action |
|------|--------|
| `adapters/aws_getter.py` | ✅ Implement |
| `adapters/azure_getter.py` | ✅ Implement |
| `.env` | ✅ Add your cloud credentials |

## Files You Must NOT Modify

| File | Reason |
|------|--------|
| `backend/canonical.py` | Core hash engine |
| `backend/hashing.py` | SHA-256 implementation |
| `backend/merkle.py` | Merkle tree |
| `backend/blockchain.py` | Blockchain interface |
| `backend/verifier.py` | Verification engine |
| `backend/pipeline.py` | Ingestion pipeline |
| `backend/alerts.py` | MongoDB store |
| `backend/app.py` | Flask dashboard |
| `adapters/base.py` | Abstract interface |
| `contracts/` | Smart contracts |
| `tests/` | Test suite |

---

## The Interface You Must Implement

```python
from adapters.base import LogGetter

class AWSLogGetter(LogGetter):

    def fetch_events(self, case_id: str) -> list[dict]:
        """
        Fetch events from AWS CloudTrail for case_id.
        Return a list of normalized event dicts.
        """
        ...

    def health_check(self) -> dict:
        """
        Return {"status": "ok", "provider": "aws", "message": "..."}
        """
        ...
```

---

## Required Event Schema

Every event you return MUST have these exact fields:

```python
{
    "event_id":  "aws-abc123",         # str, unique
    "provider":  "aws",                # str
    "service":   "cloudtrail",         # str, e.g. "iam", "s3", "ec2"
    "source":    "cloudtrail",         # str
    "case_id":   "CASE-001",           # str (from parameter)
    "sequence":  1,                    # int, 1-based ordering
    "timestamp": "2026-09-25T03:20:00Z",  # str, ISO-8601 UTC
    "message":   "CreateUser by admin",   # str
}
```

### Field Rules
- `sequence` must be an **integer** (not a string)
- `timestamp` must be a **string** in ISO-8601 format
- `event_id` must be **unique** within the provider
- All fields are **required**
- Extra fields are silently ignored (not hashed)

---

## AWS CloudTrail → Normalized Event

```python
# Raw CloudTrail event from AWS SDK
raw_event = {
    "eventID":     "abc-123-def-456",
    "eventTime":   "2026-09-25T03:20:00Z",
    "eventSource": "s3.amazonaws.com",
    "eventName":   "PutObject",
    "userIdentity": {
        "type": "IAMUser",
        "arn":  "arn:aws:iam::123456789:user/admin"
    },
    "sourceIPAddress": "10.0.1.5",
    # ... many more fields
}

# Convert to normalized event
normalized = {
    "event_id":  raw_event["eventID"],
    "provider":  "aws",
    "service":   raw_event["eventSource"].split(".")[0],   # "s3"
    "source":    "cloudtrail",
    "case_id":   case_id,
    "sequence":  index + 1,                                # 1-based
    "timestamp": raw_event["eventTime"],
    "message":   f"{raw_event['eventName']} by {raw_event['userIdentity']['arn']}",
}
```

---

## Azure Activity Log → Normalized Event

```python
# Raw Azure Activity Log event
raw_event = {
    "id":            "/subscriptions/xxx/.../events/yyy",
    "eventTimestamp": "2026-09-25T03:20:00.000Z",
    "operationName": {"value": "Microsoft.Storage/storageAccounts/write"},
    "resourceType":  {"value": "Microsoft.Storage/storageAccounts"},
    "caller":        "admin@example.com",
    "status":        {"value": "Succeeded"},
}

# Convert to normalized event
normalized = {
    "event_id":  raw_event["id"].split("/")[-1],
    "provider":  "azure",
    "service":   raw_event["operationName"]["value"].split("/")[1].lower(),
    "source":    "activitylog",
    "case_id":   case_id,
    "sequence":  index + 1,
    "timestamp": raw_event["eventTimestamp"],
    "message":   f"{raw_event['operationName']['value']} by {raw_event.get('caller', 'unknown')}",
}
```

---

## How Your Adapter Calls the Core

You have **two options**:

### Option 1: Direct Python Call (recommended for hackathon)

```python
from adapters.aws_getter import AWSLogGetter
from backend.pipeline import ingest_events

# Your adapter
getter = AWSLogGetter(region="us-east-1")
events = getter.fetch_events("CASE-001")

# Pipeline handles EVERYTHING else:
# → canonicalize → SHA-256 → Merkle → blockchain anchor → verify → alerts
result = ingest_events(events)

print(result)
# {
#     "case_id": "CASE-001",
#     "batch_id": "batch-CASE-001-000001",
#     "entry_count": 150,
#     "merkle_root": "abc123...",
#     "transaction_hash": "0x...",
#     "status": "ANCHORED",
#     "verification": "PASS"
# }
```

### Option 2: HTTP API Call

```bash
curl -X POST http://DEVICE1_IP:5000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "case_id": "CASE-001",
    "events": [
        {
            "event_id": "aws-abc123",
            "provider": "aws",
            "service": "cloudtrail",
            "source": "cloudtrail",
            "case_id": "CASE-001",
            "sequence": 1,
            "timestamp": "2026-09-25T03:20:00Z",
            "message": "CreateUser by admin"
        }
    ]
}'
```

---

## How to Test Without Real Cloud Credentials

```python
# Test your normalization logic without real AWS/Azure
def test_my_adapter():
    from adapters.aws_getter import AWSLogGetter
    from backend.canonical import canonicalize_event, validate_event

    getter = AWSLogGetter()

    # Simulate what fetch_events returns by constructing manually
    mock_events = [
        {
            "event_id":  "evt-001",
            "provider":  "aws",
            "service":   "iam",
            "source":    "cloudtrail",
            "case_id":   "CASE-001",
            "sequence":  1,
            "timestamp": "2026-09-25T03:20:00Z",
            "message":   "CreateUser by admin",
        }
    ]

    # Validate schema
    for e in mock_events:
        validate_event(e)  # Raises ValueError if schema is wrong

    print("Schema OK")

    # Test canonicalization is deterministic
    from backend.hashing import hash_event
    h1 = hash_event(mock_events[0])
    h2 = hash_event(mock_events[0])
    assert h1 == h2, "Hashing not deterministic!"
    print(f"Hash: {h1}")
```

---

## How to Connect to Device 1

1. Get Device 1's IP from the team (stored in `.env` as `DEVICE1_IP`)
2. The pipeline endpoint is at `http://DEVICE1_IP:5000/api/ingest`
3. OR import `pipeline.py` directly if you're on the same machine

```bash
# From your machine:
curl http://DEVICE1_IP:5000/api/status
```

---

## Your Adapter Must NEVER

- ❌ Import anything from `backend/blockchain.py` directly
- ❌ Call Web3 or smart contracts
- ❌ Write to MongoDB
- ❌ Know what a Merkle tree is
- ❌ Handle SHA-256 hashing
- ❌ Store state on-chain

**Your only job is: raw cloud event → normalized event dict**

---

## Quick Implementation Checklist

```
[ ] Implement AWSLogGetter.__init__ with boto3 client setup
[ ] Implement AWSLogGetter.fetch_events to call CloudTrail
[ ] Sort events by timestamp (ascending)
[ ] Assign 1-based sequence numbers
[ ] Return list of normalized event dicts
[ ] Implement AWSLogGetter.health_check
[ ] Test: python -c "from adapters.aws_getter import AWSLogGetter; print(AWSLogGetter().health_check())"
[ ] Test schema: from backend.canonical import validate_event; validate_event(your_event)
[ ] Test pipeline: python -c "from backend.pipeline import ingest_events; ..."
```

---

## Need Help?

- Event schema: `adapters/base.py` → `NORMALIZED_EVENT_SCHEMA`
- Pipeline entry point: `backend/pipeline.py` → `ingest_events(events)`
- HTTP API: `POST /api/ingest` with `{"case_id": "...", "events": [...]}`
- Dashboard: `http://DEVICE1_IP:5000` to see results
- Tests: `pytest tests/` to validate core logic
