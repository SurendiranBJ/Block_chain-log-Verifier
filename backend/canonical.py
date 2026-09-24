"""
LogChain - Canonical Serialization
Deterministic, provider-independent canonical JSON for hashing.
Every identical logical event MUST produce identical bytes.
"""
import json
from typing import Any

# Required fields in every normalized event
REQUIRED_FIELDS = [
    "event_id",
    "provider",
    "service",
    "source",
    "case_id",
    "sequence",
    "timestamp",
    "message",
]


def validate_event(event: dict) -> None:
    """
    Validate that an event contains all required fields.
    Raises ValueError with a clear message on failure.
    """
    missing = [f for f in REQUIRED_FIELDS if f not in event]
    if missing:
        raise ValueError(
            f"Event is missing required fields: {missing}. "
            f"Got fields: {list(event.keys())}"
        )
    if not isinstance(event["sequence"], int):
        raise ValueError(
            f"event.sequence must be an integer, got {type(event['sequence'])}"
        )
    if not isinstance(event["event_id"], str) or not event["event_id"]:
        raise ValueError("event.event_id must be a non-empty string")
    if not isinstance(event["timestamp"], str) or not event["timestamp"]:
        raise ValueError("event.timestamp must be a non-empty ISO-8601 string")


def canonicalize_event(event: dict) -> bytes:
    """
    Produce deterministic UTF-8 bytes from a normalized event dict.

    Rules:
    - Only canonical fields are included (extras are ignored).
    - Keys are sorted alphabetically.
    - No extra whitespace (compact separators).
    - Strings are preserved exactly as-is (no case normalization).
    - sequence is stored as integer (not string).
    - Returns bytes (utf-8 encoded).

    Two events that are logically identical MUST produce identical bytes.
    """
    validate_event(event)

    canonical = {
        "case_id":   str(event["case_id"]),
        "event_id":  str(event["event_id"]),
        "message":   str(event["message"]),
        "provider":  str(event["provider"]),
        "sequence":  int(event["sequence"]),
        "service":   str(event["service"]),
        "source":    str(event["source"]),
        "timestamp": str(event["timestamp"]),
    }

    return json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def canonical_repr(event: dict) -> str:
    """Return canonical JSON as string (for debugging/display)."""
    return canonicalize_event(event).decode("utf-8")
