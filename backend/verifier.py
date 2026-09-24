"""
LogChain - Verification Engine
Compares current events against blockchain commitments.
Detects: MODIFIED, DELETED, UNEXPECTED, REORDERED events.
"""
import logging
from enum import Enum
from typing import Optional
from dataclasses import dataclass, field

from backend.hashing import hash_event
from backend.merkle import compute_merkle_root, verify_root
from backend import blockchain, alerts as alert_store

logger = logging.getLogger(__name__)


class VerificationState(str, Enum):
    GREEN              = "GREEN"
    MODIFIED           = "MODIFIED"
    DELETED            = "DELETED"
    UNEXPECTED         = "UNEXPECTED"
    REORDERED          = "REORDERED"
    MISSING_COMMITMENT = "MISSING_COMMITMENT"
    BLOCKCHAIN_ERROR   = "BLOCKCHAIN_ERROR"


@dataclass
class EventVerificationResult:
    event_id:       str
    sequence:       int
    state:          VerificationState
    expected_hash:  str = ""
    actual_hash:    str = ""
    batch_id:       str = ""
    merkle_root:    str = ""
    tx_hash:        str = ""
    message:        str = ""


@dataclass
class BatchVerificationResult:
    case_id:       str
    batch_id:      str
    state:         VerificationState
    merkle_root:   str          = ""
    entry_count:   int          = 0
    tx_hash:       str          = ""
    message:       str          = ""
    event_results: list         = field(default_factory=list)
    summary:       dict         = field(default_factory=dict)


@dataclass
class CaseVerificationResult:
    case_id:       str
    overall_state: VerificationState
    batch_results: list         = field(default_factory=list)
    summary:       dict         = field(default_factory=dict)


def _overall_state(event_results: list[EventVerificationResult]) -> VerificationState:
    """Compute overall state from individual event results."""
    if not event_results:
        return VerificationState.MISSING_COMMITMENT
    states = {r.state for r in event_results}
    if states == {VerificationState.GREEN}:
        return VerificationState.GREEN
    # Priority order
    for bad in [
        VerificationState.BLOCKCHAIN_ERROR,
        VerificationState.DELETED,
        VerificationState.UNEXPECTED,
        VerificationState.MODIFIED,
        VerificationState.REORDERED,
        VerificationState.MISSING_COMMITMENT,
    ]:
        if bad in states:
            return bad
    return VerificationState.GREEN


def verify_batch(
    case_id: str,
    batch_id: str,
    current_events: list[dict],
) -> BatchVerificationResult:
    """
    Verify a batch of events against the blockchain commitment.

    Args:
        case_id:        Case identifier
        batch_id:       Batch identifier
        current_events: Current normalized events (from adapter/local store)

    Returns:
        BatchVerificationResult with per-event states
    """
    # 1. Get on-chain commitment
    try:
        on_chain = blockchain.get_batch_on_chain(case_id, batch_id)
    except Exception as e:
        logger.error(f"Blockchain error fetching {batch_id}: {e}")
        return BatchVerificationResult(
            case_id=case_id,
            batch_id=batch_id,
            state=VerificationState.BLOCKCHAIN_ERROR,
            message=str(e),
        )

    if on_chain is None:
        return BatchVerificationResult(
            case_id=case_id,
            batch_id=batch_id,
            state=VerificationState.MISSING_COMMITMENT,
        )

    committed_hashes: list[str] = on_chain["event_hashes"]
    committed_root:   str       = on_chain["merkle_root"]
    committed_count:  int       = on_chain["entry_count"]
    tx_hash = ""

    # 2. Also get local metadata for tx_hash
    local_meta = alert_store.get_batch_metadata(case_id, batch_id)
    if local_meta:
        tx_hash = local_meta.get("tx_hash", "")

    # 3. Hash current events in order
    current_hashes = [hash_event(e) for e in current_events]
    current_id_map  = {e["event_id"]: (i, e, h) for i, (e, h) in enumerate(zip(current_events, current_hashes))}

    event_results: list[EventVerificationResult] = []
    seen_committed = set()

    # 4. For each committed hash position, check if current matches
    for idx, committed_hash in enumerate(committed_hashes):
        # Find what event_id corresponds to position idx
        # We use local metadata for the event_id↔index mapping
        expected_event_id = None
        expected_sequence  = idx + 1  # fallback

        if local_meta and "event_ids" in local_meta:
            event_ids_list = local_meta["event_ids"]
            if idx < len(event_ids_list):
                expected_event_id = event_ids_list[idx]
                expected_sequence = local_meta.get("sequences", [])[idx] if idx < len(local_meta.get("sequences", [])) else idx + 1

        # Check if current events have this position
        if idx < len(current_hashes):
            actual_hash = current_hashes[idx]
            actual_event = current_events[idx]
            actual_event_id = actual_event.get("event_id", f"pos-{idx}")

            seen_committed.add(idx)

            if actual_hash == committed_hash:
                # Check for reordering: event_id should match expected position
                if expected_event_id and actual_event_id != expected_event_id:
                    state = VerificationState.REORDERED
                    msg = f"Expected {expected_event_id} at position {idx}, got {actual_event_id}"
                else:
                    state = VerificationState.GREEN
                    msg = "OK"
            else:
                state = VerificationState.MODIFIED
                msg = f"Hash mismatch at position {idx}"

            er = EventVerificationResult(
                event_id=actual_event_id,
                sequence=actual_event.get("sequence", expected_sequence),
                state=state,
                expected_hash=committed_hash,
                actual_hash=actual_hash,
                batch_id=batch_id,
                merkle_root=committed_root,
                tx_hash=tx_hash,
                message=msg,
            )
        else:
            # Event was committed but is now missing → DELETED
            er = EventVerificationResult(
                event_id=expected_event_id or f"pos-{idx}",
                sequence=expected_sequence,
                state=VerificationState.DELETED,
                expected_hash=committed_hash,
                actual_hash="",
                batch_id=batch_id,
                merkle_root=committed_root,
                tx_hash=tx_hash,
                message=f"Event at position {idx} is missing",
            )

        event_results.append(er)

        # Store alert for non-green states
        if er.state != VerificationState.GREEN:
            severity = "CRITICAL" if er.state in [
                VerificationState.MODIFIED, VerificationState.DELETED
            ] else "HIGH"
            alert_store.save_alert(
                case_id=case_id,
                batch_id=batch_id,
                event_id=er.event_id,
                sequence=er.sequence,
                alert_type=er.state.value,
                severity=severity,
                expected_hash=er.expected_hash,
                actual_hash=er.actual_hash,
                merkle_root=committed_root,
                tx_hash=tx_hash,
            )

    # 5. Check for UNEXPECTED events (current has more than committed)
    if len(current_events) > len(committed_hashes):
        for idx in range(len(committed_hashes), len(current_events)):
            extra_event = current_events[idx]
            extra_hash  = current_hashes[idx]
            er = EventVerificationResult(
                event_id=extra_event.get("event_id", f"extra-{idx}"),
                sequence=extra_event.get("sequence", idx + 1),
                state=VerificationState.UNEXPECTED,
                expected_hash="",
                actual_hash=extra_hash,
                batch_id=batch_id,
                merkle_root=committed_root,
                tx_hash=tx_hash,
                message=f"Unexpected event at position {idx} (not in committed batch)",
            )
            event_results.append(er)
            alert_store.save_alert(
                case_id=case_id,
                batch_id=batch_id,
                event_id=er.event_id,
                sequence=er.sequence,
                alert_type="UNEXPECTED",
                severity="HIGH",
                expected_hash="",
                actual_hash=extra_hash,
                merkle_root=committed_root,
                tx_hash=tx_hash,
            )

    # 6. Recompute Merkle root from committed hashes to verify chain integrity
    recomputed_root = compute_merkle_root(committed_hashes)
    root_valid = (recomputed_root == committed_root)
    if not root_valid:
        logger.error(f"Merkle root mismatch for batch {batch_id}!")

    overall = _overall_state(event_results)

    summary = {
        "total":      len(event_results),
        "green":      sum(1 for r in event_results if r.state == VerificationState.GREEN),
        "modified":   sum(1 for r in event_results if r.state == VerificationState.MODIFIED),
        "deleted":    sum(1 for r in event_results if r.state == VerificationState.DELETED),
        "unexpected": sum(1 for r in event_results if r.state == VerificationState.UNEXPECTED),
        "reordered":  sum(1 for r in event_results if r.state == VerificationState.REORDERED),
        "merkle_root_valid": root_valid,
    }

    return BatchVerificationResult(
        case_id=case_id,
        batch_id=batch_id,
        state=overall,
        merkle_root=committed_root,
        entry_count=committed_count,
        tx_hash=tx_hash,
        event_results=event_results,
        summary=summary,
    )


def verify_case(
    case_id: str,
    current_events_by_batch: dict[str, list[dict]],
) -> CaseVerificationResult:
    """
    Verify all batches for a case.

    Args:
        case_id: Case identifier
        current_events_by_batch: {batch_id: [events]} mapping
    """
    batch_ids = blockchain.get_case_batches(case_id)
    if not batch_ids:
        return CaseVerificationResult(
            case_id=case_id,
            overall_state=VerificationState.MISSING_COMMITMENT,
            summary={"error": "No batches found on blockchain"},
        )

    batch_results = []
    for batch_id in batch_ids:
        current_events = current_events_by_batch.get(batch_id, [])
        result = verify_batch(case_id, batch_id, current_events)
        batch_results.append(result)

    # Overall state across all batches
    all_states = {r.state for r in batch_results}
    if all_states == {VerificationState.GREEN}:
        overall = VerificationState.GREEN
    else:
        # Use same priority as batch-level
        overall = _overall_state([
            EventVerificationResult(
                event_id="batch", sequence=0, state=r.state
            ) for r in batch_results
        ])

    total_summary = {
        "batch_count": len(batch_results),
        "green_batches": sum(1 for r in batch_results if r.state == VerificationState.GREEN),
    }

    return CaseVerificationResult(
        case_id=case_id,
        overall_state=overall,
        batch_results=batch_results,
        summary=total_summary,
    )


def verify_event(
    case_id: str,
    event_id: str,
    current_event: dict,
) -> EventVerificationResult:
    """
    Verify a single event against all batches for the case.
    Searches through batches to find where this event_id was committed.
    """
    batch_ids = blockchain.get_case_batches(case_id)
    for batch_id in batch_ids:
        local_meta = alert_store.get_batch_metadata(case_id, batch_id)
        if not local_meta:
            continue
        event_ids_list = local_meta.get("event_ids", [])
        if event_id not in event_ids_list:
            continue
        idx = event_ids_list.index(event_id)
        committed_hashes = local_meta.get("event_hashes", [])
        if idx >= len(committed_hashes):
            continue
        committed_hash = committed_hashes[idx]
        actual_hash    = hash_event(current_event)
        tx_hash        = local_meta.get("tx_hash", "")
        merkle_root    = local_meta.get("merkle_root", "")

        if actual_hash == committed_hash:
            return EventVerificationResult(
                event_id=event_id,
                sequence=current_event.get("sequence", idx + 1),
                state=VerificationState.GREEN,
                expected_hash=committed_hash,
                actual_hash=actual_hash,
                batch_id=batch_id,
                merkle_root=merkle_root,
                tx_hash=tx_hash,
                message="OK",
            )
        else:
            return EventVerificationResult(
                event_id=event_id,
                sequence=current_event.get("sequence", idx + 1),
                state=VerificationState.MODIFIED,
                expected_hash=committed_hash,
                actual_hash=actual_hash,
                batch_id=batch_id,
                merkle_root=merkle_root,
                tx_hash=tx_hash,
                message="Hash mismatch",
            )

    return EventVerificationResult(
        event_id=event_id,
        sequence=current_event.get("sequence", 0),
        state=VerificationState.MISSING_COMMITMENT,
        message=f"Event {event_id} not found in any batch for case {case_id}",
    )
