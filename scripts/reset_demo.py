"""
LogChain - Append-Only Blockchain-Safe Demo Reset
Preserves the blockchain, generates a fresh unique demo case ID and batch,
anchors to the append-only blockchain, and resets verification to GREEN.

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

    # 1. Preserve blockchain: Generate a NEW unique demo case ID
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    new_case_id = f"CASE-RUN-{now_str}"
    print(f"\n[1] Generated fresh active case ID: {new_case_id}")
    set_current_case_id(new_case_id)

    # 2. Clear MongoDB demo alerts
    print("\n[2] Clearing previous demo MongoDB alerts...")
    cleared_alerts = alert_store.clear_demo_alerts()
    print(f"    [PASS] Cleared {cleared_alerts} historical alerts")

    # 3. Generate fresh clean events
    print(f"\n[3] Generating {count} clean events for {new_case_id}...")
    events = generate_events(case_id=new_case_id, count=count)
    getter = LocalLogGetter()
    getter.write_events(new_case_id, events)
    print(f"    [PASS] Generated and saved {len(events)} events")

    # 4. Ingest and Anchor to blockchain (if contract deployed and node online)
    print("\n[4] Ingesting and anchoring to blockchain...")
    try:
        result = ingest_events(events)
        print(f"    [PASS] Batch anchored: {result['batch_id']}")
        print(f"    Tx Hash:  {result.get('transaction_hash', 'N/A')}")
        print(f"    Status:   {result.get('status', 'ANCHORED')}")
    except Exception as e:
        print(f"    [WARN] Ingestion/anchoring warning: {e}")
        print("    If running without live Geth node, local metadata is ready.")

    # 5. Verify clean state
    print("\n[5] Running verification...")
    batches = alert_store.get_case_batches_local(new_case_id)
    if not batches:
        onchain_batch_ids = blockchain.get_case_batches(new_case_id)
        batches = [{"batch_id": bid} for bid in onchain_batch_ids]

    all_green = True
    if batches:
        for bm in batches:
            seq_list = bm.get("sequences", [])
            batch_events = [e for e in events if e.get("sequence") in seq_list] if seq_list else events
            vres = ve.verify_batch(new_case_id, bm["batch_id"], batch_events)
            if vres.state != ve.VerificationState.GREEN:
                all_green = False
                print(f"    [FAIL] Batch {bm['batch_id']} verification state: {vres.state}")
            else:
                print(f"    [PASS] Batch {bm['batch_id']} verification: GREEN")

    print("\n============================================================")
    if all_green:
        print(" DEMO RESET SUCCESSFUL: DASHBOARD GREEN")
    else:
        print(" DEMO RESET COMPLETED WITH WARNINGS")
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
