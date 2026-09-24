"""
LogChain - Demo Attack: Delete Event
Simulates an attacker deleting a specific event from the local demo source.
After running this, verification should show DELETED.

Usage:
    python scripts/delete_event.py --case CASE-001 --sequence 51
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import DEMO_CASE_ID, DEMO_LOG_DIR
from adapters.local_getter import LocalLogGetter


def delete_event(case_id: str, sequence: int) -> None:
    getter = LocalLogGetter()
    events = getter.fetch_events(case_id)

    if not events:
        print(f"[!] No events found for case {case_id}")
        sys.exit(1)

    target = None
    for i, e in enumerate(events):
        if e["sequence"] == sequence:
            target = (i, e)
            break

    if target is None:
        print(f"[!] Event with sequence={sequence} not found in {case_id}")
        sys.exit(1)

    idx, event = target
    original_event_id = event["event_id"]
    original_message  = event["message"]

    print(f"\n[*] ATTACK: Deleting event from {case_id}")
    print(f"    Event ID:  {original_event_id}")
    print(f"    Sequence:  {sequence}")
    print(f"    Message:   {original_message}")

    events.pop(idx)
    # Note: we do NOT renumber sequences - that would be additional evidence of tampering
    getter.write_events(case_id, events)

    print(f"\n[!] Event {original_event_id} (seq={sequence}) has been DELETED.")
    print(f"    Remaining events: {len(events)}")
    print(f"    Run verification to detect the deletion.")
    print(f"    Expected result: DELETED / RED")


def main():
    parser = argparse.ArgumentParser(
        description="Demo attack: delete a log event to demonstrate deletion detection"
    )
    parser.add_argument("--case",     default=DEMO_CASE_ID, help="Case ID")
    parser.add_argument("--sequence", type=int, required=True, help="Event sequence number to delete")
    args = parser.parse_args()

    delete_event(args.case, args.sequence)


if __name__ == "__main__":
    main()
