"""
LogChain - Demo Attack: Reorder Events
Simulates an attacker swapping the order of two events in the local demo source.

Usage:
    python scripts/reorder_events.py --sequence-a 51 --sequence-b 52
    python scripts/reorder_events.py --case CASE-001 --sequence-a 51 --sequence-b 52
"""
import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import get_current_case_id
from adapters.local_getter import LocalLogGetter


def reorder_events(case_id: str, seq_a: int, seq_b: int) -> None:
    getter = LocalLogGetter()
    events = getter.fetch_events(case_id)

    if not events:
        print(f"[ERROR] No events found for case {case_id}")
        sys.exit(1)

    idx_a = None
    idx_b = None
    for i, e in enumerate(events):
        if e.get("sequence") == seq_a:
            idx_a = i
        elif e.get("sequence") == seq_b:
            idx_b = i

    if idx_a is None or idx_b is None:
        print(f"[ERROR] Could not find both events with sequence={seq_a} and sequence={seq_b}")
        sys.exit(1)

    event_a_id = events[idx_a]["event_id"]
    event_b_id = events[idx_b]["event_id"]

    # Swap sequence values and/or positions
    events[idx_a]["sequence"] = seq_b
    events[idx_b]["sequence"] = seq_a
    events[idx_a], events[idx_b] = events[idx_b], events[idx_a]

    getter.write_events(case_id, events)

    print("============================================================")
    print("ATTACK TYPE:     REORDERED")
    print(f"CASE:            {case_id}")
    print(f"EVENT ID:        {event_a_id} <-> {event_b_id}")
    print(f"SEQUENCE:        {seq_a} <-> {seq_b}")
    print("EXPECTED RESULT: RED / REORDERED (Event sequence mismatch detected)")
    print("============================================================")


def main():
    parser = argparse.ArgumentParser(
        description="Demo attack: swap two events to demonstrate reorder detection"
    )
    parser.add_argument("--case", default=None, help="Case ID (defaults to active case)")
    parser.add_argument("--sequence-a", type=int, required=True, help="First event sequence number")
    parser.add_argument("--sequence-b", type=int, required=True, help="Second event sequence number")
    args = parser.parse_args()

    case_id = args.case or get_current_case_id()
    reorder_events(case_id, args.sequence_a, args.sequence_b)


if __name__ == "__main__":
    main()
