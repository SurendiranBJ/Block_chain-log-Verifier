"""
LogChain - Core Ingestion Pipeline
Provider-independent integrity pipeline.
Adapters feed events in → pipeline handles everything else.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from backend.canonical import validate_event
from backend.hashing import hash_event
from backend.merkle import build_merkle_tree, make_batch_id
from backend import blockchain
from backend import alerts as alert_store
from backend import verifier as verify_engine

logger = logging.getLogger(__name__)


class PipelineError(Exception):
    """Raised when the pipeline cannot continue."""
    pass


def _validate_events(events: list[dict]) -> list[dict]:
    """Validate and clean event list. Raises on invalid events."""
    validated = []
    for i, event in enumerate(events):
        try:
            validate_event(event)
            validated.append(event)
        except ValueError as e:
            raise PipelineError(f"Event at index {i} is invalid: {e}")
    return validated


def ingest_events(events: list[dict]) -> dict:
    """
    Main ingestion pipeline.

    Flow:
        events
         → validate schema
         → canonicalize + SHA-256 hash
         → build Merkle batch
         → anchor to blockchain
         → persist metadata
         → verify
         → return result

    Args:
        events: List of normalized event dicts (from any adapter)

    Returns:
        {
            "case_id": "CASE-001",
            "batch_id": "batch-CASE-001-000001",
            "entry_count": 100,
            "merkle_root": "...",
            "transaction_hash": "...",
            "status": "ANCHORED",
            "verification": "PASS" | "FAIL",
            "event_hashes": [...],
        }
    """
    if not events:
        raise PipelineError("No events provided")

    # Step 1: Validate schema
    logger.info(f"Ingesting {len(events)} events")
    events = _validate_events(events)

    # Extract case_id from first event (all events in batch must share case_id)
    case_id = events[0]["case_id"]
    for e in events:
        if e["case_id"] != case_id:
            raise PipelineError(
                f"Mixed case_ids in batch: {case_id!r} vs {e['case_id']!r}. "
                "Each batch must contain events for exactly one case."
            )

    # Sort events by sequence to ensure deterministic ordering
    events_sorted = sorted(events, key=lambda e: e["sequence"])

    # Step 2: Compute SHA-256 per event
    event_hashes = [hash_event(e) for e in events_sorted]
    event_ids    = [e["event_id"] for e in events_sorted]
    sequences    = [e["sequence"] for e in events_sorted]

    logger.info(f"Hashed {len(event_hashes)} events")

    # Step 3: Build Merkle tree
    merkle_result = build_merkle_tree(event_hashes)
    merkle_root   = merkle_result["root"]
    seq_start     = sequences[0] if sequences else 1
    batch_id      = make_batch_id(case_id, seq_start)

    logger.info(f"Merkle root: {merkle_root[:16]}... batch_id: {batch_id}")

    # Step 4: Check for duplicate batch
    if blockchain.batch_exists(case_id, batch_id):
        raise PipelineError(
            f"Batch {batch_id} already anchored. "
            "Use a different sequence range or reset the demo."
        )

    # Step 5: Anchor to blockchain
    try:
        anchor_result = blockchain.anchor_batch(
            case_id=case_id,
            batch_id=batch_id,
            merkle_root=merkle_root,
            entry_count=len(event_hashes),
            event_hashes=event_hashes,
        )
        tx_hash = anchor_result["tx_hash"]
        logger.info(f"Anchored at tx: {tx_hash}")
    except Exception as e:
        raise PipelineError(f"Blockchain anchor failed: {e}")

    # Step 6: Persist local metadata
    alert_store.save_batch_metadata(
        case_id=case_id,
        batch_id=batch_id,
        merkle_root=merkle_root,
        entry_count=len(event_hashes),
        tx_hash=tx_hash,
        event_hashes=event_hashes,
        event_ids=event_ids,
        sequences=sequences,
    )

    # Step 7: Immediate verification
    try:
        batch_result = verify_engine.verify_batch(
            case_id=case_id,
            batch_id=batch_id,
            current_events=events_sorted,
        )
        verification_status = "PASS" if batch_result.state == verify_engine.VerificationState.GREEN else "FAIL"
    except Exception as e:
        logger.warning(f"Post-anchor verification failed: {e}")
        verification_status = "UNKNOWN"

    return {
        "case_id":         case_id,
        "batch_id":        batch_id,
        "entry_count":     len(event_hashes),
        "merkle_root":     merkle_root,
        "transaction_hash": tx_hash,
        "block_number":    anchor_result.get("block_number"),
        "status":          "ANCHORED",
        "verification":    verification_status,
        "event_hashes":    event_hashes,
    }
