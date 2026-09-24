#!/usr/bin/env bash
# LogChain - Full Demo Run Script
# Steps 1-13 from the demo runbook
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
if [ -f ".env" ]; then source ".env"; fi

CASE_ID="${DEMO_CASE_ID:-CASE-001}"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║       LogChain - Hackathon Demo                             ║"
echo "║       Zero-Trust Cross-Cloud Log Integrity System           ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# STEP 6: Generate 100 demo events
echo "[STEP 6] Generating 100 demo events for $CASE_ID..."
python3 demo/generate_logs.py --case-id "$CASE_ID" --count 100
echo "[PASS] Events generated"
echo ""

# STEP 7-11: Ingest (normalize → hash → Merkle → anchor → verify)
echo "[STEP 7-11] Running ingestion pipeline (normalize → SHA-256 → Merkle → anchor)..."
python3 - <<'PYEOF'
import sys, json
sys.path.insert(0, '.')

from adapters.local_getter import LocalLogGetter
from backend.pipeline import ingest_events
from backend.config import DEMO_CASE_ID

case_id = DEMO_CASE_ID
getter  = LocalLogGetter()
events  = getter.fetch_events(case_id)

print(f"  Loaded {len(events)} events for {case_id}")
print(f"  Running pipeline...")

result = ingest_events(events)

print(f"")
print(f"  Case ID:      {result['case_id']}")
print(f"  Batch ID:     {result['batch_id']}")
print(f"  Entry Count:  {result['entry_count']}")
print(f"  Merkle Root:  {result['merkle_root'][:32]}...")
print(f"  Tx Hash:      {result['transaction_hash'][:20]}...")
print(f"  Status:       {result['status']}")
print(f"  Verification: {result['verification']}")
PYEOF

echo ""
echo "[STEP 12] Device 2 independently receives blockchain state"
echo "          (Check with: ./scripts/verify_network.sh)"
echo ""

# STEP 13: Verify
echo "[STEP 13] Running verification..."
python3 - <<'PYEOF'
import sys
sys.path.insert(0, '.')

from adapters.local_getter import LocalLogGetter
from backend import alerts as alert_store, verifier as ve
from backend.config import DEMO_CASE_ID

case_id = DEMO_CASE_ID
getter  = LocalLogGetter()
events  = getter.fetch_events(case_id)
batches = alert_store.get_case_batches_local(case_id)

if not batches:
    print("  [WARN] No batch metadata. Run ingestion first.")
    sys.exit(0)

all_green = True
for batch_meta in batches:
    batch_id = batch_meta['batch_id']
    seq_list = batch_meta.get('sequences', [])
    batch_events = [e for e in events if e.get('sequence') in seq_list]
    result = ve.verify_batch(case_id, batch_id, batch_events)
    print(f"  Batch {batch_id}: {result.state.value}")
    if result.state.value != 'GREEN':
        all_green = False

print()
if all_green:
    print("  ✅ DASHBOARD: GREEN — All events verified")
else:
    print("  🚨 DASHBOARD: RED — Integrity violation detected")
PYEOF

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Demo running. Open dashboard:                              ║"
echo "║  python3 backend/app.py → http://localhost:5000             ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "  Next demo steps:"
echo "    python scripts/modify_event.py --sequence 51   → RED"
echo "    python scripts/delete_event.py --sequence 51   → RED"
echo "    ./scripts/reset_demo.sh                        → GREEN"
