"""
LogChain - Demo Attack: Insert Event
Simulates an attacker injecting an uncommitted event into the local demo source.

Usage:
    python scripts/insert_event.py --sequence 51
    python scripts/insert_event.py --case CASE-001 --sequence 51
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import get_current_case_id
from adapters.local_getter import LocalLogGetter


def insert_event(case_id: str, sequence: int) -> None:
    getter = LocalLogGetter()
    events = getter.fetch_events(case_id)

    if not events:
        print(f"[ERROR] No events found for case {case_id}")
        sys.exit(1)

    event_id = f"attacker-injected-{sequence:04d}"
    fake_event = {
        "event_id":     event_id,
        "case_id":      case_id,
        "sequence":     sequence,
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        "source":       "cloudtrail",
        "provider":     "aws",
        "service":      "iam",
        "action":       "UnauthorizedAccess",
        "message":      "Attacker inserted backdoor credentials",
        "severity":     "CRITICAL",
    }

    # Insert into position
    insert_idx = len(events)
    for i, e in enumerate(events):
        if e.get("sequence", 0) >= sequence:
            insert_idx = i
            break

    events.insert(insert_idx, fake_event)
    getter.write_events(case_id, events)

    print("============================================================")
    print("ATTACK TYPE:     UNEXPECTED")
    print(f"CASE:            {case_id}")
    print(f"EVENT ID:        {event_id}")
    print(f"SEQUENCE:        {sequence}")
    print("EXPECTED RESULT: RED / UNEXPECTED (Uncommitted injected event detected)")
    print("============================================================")


def main():
    parser = argparse.ArgumentParser(
        description="Demo attack: insert an uncommitted log event to demonstrate unexpected insertion detection"
    )
    parser.add_argument("--case", default=None, help="Case ID (defaults to active case)")
    parser.add_argument("--sequence", type=int, required=True, help="Sequence number position to insert event at")
    args = parser.parse_args()

    case_id = args.case or get_current_case_id()
    insert_event(case_id, args.sequence)


if __name__ == "__main__":
    main()
