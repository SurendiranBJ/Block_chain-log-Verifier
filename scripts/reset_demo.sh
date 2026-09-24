#!/usr/bin/env bash
# LogChain - Demo Reset Script
# Resets demo state WITHOUT destroying the blockchain
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
if [ -f ".env" ]; then source ".env"; fi

CASE_ID="${DEMO_CASE_ID:-CASE-001}"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║       LogChain - Demo Reset                                 ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "  This will:"
echo "    [1] Clear MongoDB alerts for $CASE_ID"
echo "    [2] Clear local batch metadata"
echo "    [3] Regenerate 100 clean demo events"
echo "    [4] Re-anchor to blockchain"
echo "    [5] Verify → GREEN"
echo ""
echo "  Blockchain data is PRESERVED."
echo ""
read -p "  Continue? [y/N] " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "  Aborted."
    exit 0
fi

# Step 1: Clear alerts
echo ""
echo "[1] Clearing MongoDB alerts for $CASE_ID..."
python3 - <<PYEOF
import sys; sys.path.insert(0, '.')
from backend import alerts as alert_store
from backend.config import DEMO_CASE_ID
n = alert_store.clear_demo_alerts(DEMO_CASE_ID)
m = alert_store.clear_batch_metadata(DEMO_CASE_ID)
print(f"  Cleared {n} alerts, {m} batch records")
PYEOF

# Step 2: Regenerate events
echo "[2] Regenerating 100 clean demo events..."
python3 demo/generate_logs.py --case-id "$CASE_ID" --count 100
echo "[PASS] Events regenerated"

# Step 3: Re-anchor
echo "[3] Re-anchoring to blockchain..."
python3 - <<PYEOF
import sys; sys.path.insert(0, '.')
from adapters.local_getter import LocalLogGetter
from backend.pipeline import ingest_events
from backend.config import DEMO_CASE_ID
getter = LocalLogGetter()
events = getter.fetch_events(DEMO_CASE_ID)
result = ingest_events(events)
print(f"  Batch: {result['batch_id']}")
print(f"  Tx:    {result['transaction_hash'][:20]}...")
print(f"  Status: {result['status']}")
PYEOF

# Step 4: Verify → GREEN
echo "[4] Verifying..."
python3 - <<PYEOF
import sys; sys.path.insert(0, '.')
from adapters.local_getter import LocalLogGetter
from backend import alerts as alert_store, verifier as ve
from backend.config import DEMO_CASE_ID
getter = LocalLogGetter()
events = getter.fetch_events(DEMO_CASE_ID)
batches = alert_store.get_case_batches_local(DEMO_CASE_ID)
all_green = True
for bm in batches:
    seq_list = bm.get('sequences', [])
    batch_events = [e for e in events if e.get('sequence') in seq_list]
    result = ve.verify_batch(DEMO_CASE_ID, bm['batch_id'], batch_events)
    if result.state.value != 'GREEN':
        all_green = False
if all_green:
    print("  ✅ DASHBOARD: GREEN")
else:
    print("  🚨 WARNING: Not GREEN after reset")
    sys.exit(1)
PYEOF

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Reset complete. Dashboard should show GREEN.               ║"
echo "╚══════════════════════════════════════════════════════════════╝"
