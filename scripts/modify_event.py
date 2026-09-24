"""
LogChain - Demo Attack: Modify Event
Simulates an attacker modifying a specific event in the local demo source.
After running this, verification should show MODIFIED.

Usage:
    python scripts/modify_event.py --case CASE-001 --sequence 51
    python scripts/modify_event.py --case CASE-001 --sequence 51 --new-message "ATTACKER INJECTED"
"""
import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import DEMO_CASE_ID, DEMO_LOG_DIR
from adapters.local_getter import LocalLogGetter


def modify_event(case_id: str, sequence: int, new_message: str = None) -> None:
    getter = LocalLogGetter()
    events = getter.fetch_events(case_id)

    if not events:
        print(f"[!] No events found for case {case_id}")
        sys.exit(1)

    # Find event by sequence
    target = None
    for i, e in enumerate(events):
        if e["sequence"] == sequence:
            target = (i, e)
            break

    if target is None:
        print(f"[!] Event with sequence={sequence} not found in {case_id}")
        print(f"    Available sequences: {[e['sequence'] for e in events[:5]]}...")
        sys.exit(1)

    idx, event = target
    original_message = event["message"]
    original_event_id = event["event_id"]

    # Modify the message
    if new_message is None:
        new_message = f"[TAMPERED] {original_message} [MODIFIED BY ATTACKER]"

    print(f"\n[*] ATTACK: Modifying event in {case_id}")
    print(f"    Event ID:        {original_event_id}")
    print(f"    Sequence:        {sequence}")
    print(f"    Original:        {original_message}")
    print(f"    Tampered:        {new_message}")

    events[idx]["message"] = new_message

    getter.write_events(case_id, events)
    print(f"\n[!] Event {original_event_id} (seq={sequence}) has been MODIFIED.")
    print(f"    Run verification to detect tampering.")
    print(f"    Expected result: MODIFIED / RED")


def main():
    parser = argparse.ArgumentParser(
        description="Demo attack: modify a log event to demonstrate tamper detection"
    )
    parser.add_argument("--case",    default=DEMO_CASE_ID, help="Case ID")
    parser.add_argument("--sequence",type=int, required=True, help="Event sequence number to modify")
    parser.add_argument("--new-message", default=None, help="Replacement message (default: append tamper marker)")
    args = parser.parse_args()

    modify_event(args.case, args.sequence, args.new_message)


if __name__ == "__main__":
    main()
