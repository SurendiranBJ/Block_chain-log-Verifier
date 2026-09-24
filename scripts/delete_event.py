"""
LogChain - Demo Attack: Delete Event
Simulates an attacker deleting an event from the local demo source.

Usage:
    python scripts/delete_event.py --sequence 51
    python scripts/delete_event.py --case CASE-001 --sequence 51
"""
import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import get_current_case_id
from adapters.local_getter import LocalLogGetter


def delete_event(case_id: str, sequence: int) -> None:
    getter = LocalLogGetter()
    events = getter.fetch_events(case_id)

    if not events:
        print(f"[ERROR] No events found for case {case_id}")
        sys.exit(1)

    target = None
    for i, e in enumerate(events):
        if e.get("sequence") == sequence:
            target = (i, e)
            break

    if target is None:
        print(f"[ERROR] Event with sequence={sequence} not found in case {case_id}")
        sys.exit(1)

    idx, event = target
    event_id = event["event_id"]

    events.pop(idx)
    getter.write_events(case_id, events)

    print("============================================================")
    print("ATTACK TYPE:     DELETED")
    print(f"CASE:            {case_id}")
    print(f"EVENT ID:        {event_id}")
    print(f"SEQUENCE:        {sequence}")
    print("EXPECTED RESULT: RED / DELETED (Missing event detected without cascading false alarms)")
    print("============================================================")


def main():
    parser = argparse.ArgumentParser(
        description="Demo attack: delete a log event to demonstrate deletion detection"
    )
    parser.add_argument("--case", default=None, help="Case ID (defaults to active case)")
    parser.add_argument("--sequence", type=int, required=True, help="Event sequence number to delete")
    args = parser.parse_args()

    case_id = args.case or get_current_case_id()
    delete_event(case_id, args.sequence)


if __name__ == "__main__":
    main()
