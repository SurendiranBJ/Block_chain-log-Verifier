"""
LogChain - Append-Only Blockchain-Safe Demo Reset
Preserves the blockchain, generates a fresh unique demo case ID and batch,
anchors to the append-only blockchain, and resets verification to GREEN.
Fails with non-zero exit code if any stage fails.

Usage:
    python scripts/reset_demo.py
    python scripts/reset_demo.py --count 100
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from backend.config import set_current_case_id, DEMO_EVENT_COUNT, CONTRACT_ADDRESS
from backend import alerts as alert_store, verifier as ve, blockchain
from backend.pipeline import ingest_events
from adapters.local_getter import LocalLogGetter
from demo.generate_logs import generate_events


def reset_demo(count: int = 100) -> str:
    print("============================================================")
    print(" LogChain - Append-Only Demo Reset")
    print("============================================================")

    # Stage 1: Generate case
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    new_case_id = f"CASE-RUN-{now_str}"
    print(f"\n[1] Generated fresh active case ID: {new_case_id}")
    set_current_case_id(new_case_id)

    # Stage 2: Clear MongoDB demo alerts & metadata
    print("\n[2] Clearing previous demo MongoDB alerts & metadata...")
    cleared_alerts = alert_store.clear_demo_alerts()
    alert_store.clear_batch_metadata()
    print(f"    [PASS] Cleared {cleared_alerts} historical alerts")

    # Stage 3: Generate clean events
    print(f"\n[3] Generating {count} clean events for {new_case_id}...")
    events = generate_events(case_id=new_case_id, count=count)
    getter = LocalLogGetter()
    getter.write_events(new_case_id, events)
    print(f"    [PASS] Generated and saved {len(events)} events")

    # Stage 4: Check blockchain connection
    print("\n[4] Checking blockchain connection...")
    try:
        w3 = blockchain.get_w3(1)
        if not w3.is_connected():
            print(f"    [FAIL] Blockchain connection: Cannot connect to Device 1 at {blockchain.DEVICE1_RPC}")
            sys.exit(1)
    except Exception as e:
        print(f"    [FAIL] Blockchain connection: {e}")
        sys.exit(1)
    print("    [PASS] Blockchain connection: Device 1 online")

    # Stage 5: Anchor
    print("\n[5] Anchoring batch to blockchain...")
    try:
        ingest_res = ingest_events(events)
        batch_id = ingest_res["batch_id"]
        tx_hash = ingest_res.get("transaction_hash", "N/A")
        print(f"    [PASS] Anchor transaction: Batch {batch_id} confirmed (tx: {tx_hash})")
    except Exception as e:
        print(f"    [FAIL] Anchor transaction: {e}")
        sys.exit(1)

    # Stage 6: Batch retrieval from blockchain
    print("\n[6] Retrieving batch directly from blockchain...")
    try:
        on_chain = blockchain.get_batch_on_chain(new_case_id, batch_id)
        if not on_chain or not on_chain.get("exists", True):
            print(f"    [FAIL] Batch retrieval: Batch {batch_id} not found on chain")
            sys.exit(1)
    except Exception as e:
        print(f"    [FAIL] Batch retrieval: {e}")
        sys.exit(1)
    print(f"    [PASS] Batch retrieval: Confirmed Merkle root on chain: {on_chain['merkle_root'][:16]}...")

    # Stage 7: Verify current events against blockchain
    print("\n[7] Verifying current events against blockchain...")
    vres = ve.verify_batch(new_case_id, batch_id, events)
    if vres.state != ve.VerificationState.GREEN:
        print(f"    [FAIL] Verification: Expected GREEN but got {vres.state.value}")
        sys.exit(1)
    print(f"    [PASS] Verification: All {len(events)} events match blockchain commitment (GREEN)")

    # Stage 8: Success
    print("\n============================================================")
    print(" DEMO RESET SUCCESSFUL: DASHBOARD GREEN")
    print(f" Active Case: {new_case_id}")
    print("============================================================")
    return new_case_id


def main():
    parser = argparse.ArgumentParser(description="LogChain Demo Reset")
    parser.add_argument("--count", type=int, default=DEMO_EVENT_COUNT, help="Number of demo events to generate")
    args = parser.parse_args()

    reset_demo(count=args.count)


if __name__ == "__main__":
    main()
