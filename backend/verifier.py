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
    MERKLE_MISMATCH    = "MERKLE_MISMATCH"
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
        VerificationState.MERKLE_MISMATCH,
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
    Verify a batch of events against the blockchain commitment using EVENT IDENTITY.

    Algorithm:
      STEP 1: Load immutable committed data (event IDs, sequences, hashes, Merkle root)
      STEP 2: Load current normalized events
      STEP 3: Build identity maps current_by_id and committed_by_id
      STEP 4: Detect DELETED (committed event ID missing in current)
      STEP 5: Detect UNEXPECTED (current event ID not in committed)
      STEP 6: Detect MODIFIED (content hash mismatch for same event ID)
      STEP 7: Detect REORDERED (sequence shift or relative ordering mismatch)
      STEP 8: Recompute Merkle root and summarize
    """
    # 1. STEP 1: Load immutable committed data
    try:
        on_chain = blockchain.get_batch_on_chain(case_id, batch_id)
    except Exception as e:
        logger.error(f"Blockchain error fetching {batch_id}: {e}")
        return BatchVerificationResult(
            case_id=case_id,
            batch_id=batch_id,
            state=VerificationState.BLOCKCHAIN_ERROR,
            message=f"Blockchain verification unavailable: {e}",
        )

    if on_chain is None:
        return BatchVerificationResult(
            case_id=case_id,
            batch_id=batch_id,
            state=VerificationState.MISSING_COMMITMENT,
            message=f"No blockchain commitment found for batch {batch_id}",
        )

    # Optional UI metadata (tx_hash only, not cryptographic truth)
    local_meta = alert_store.get_batch_metadata(case_id, batch_id) or {}
    tx_hash = local_meta.get("tx_hash", "")

    committed_hashes: list[str] = on_chain.get("event_hashes", [])
    committed_root: str = on_chain.get("merkle_root", "")
    committed_count: int = on_chain.get("entry_count", len(committed_hashes))
    committed_event_ids: list[str] = on_chain.get("event_ids", [])
    committed_sequences: list[int] = on_chain.get("event_sequences", [])

    # Strict check: LogIntegrityV3 requires event IDs, sequences, hashes, and Merkle root on-chain
    if not committed_hashes or not committed_root or not committed_event_ids or not committed_sequences:
        logger.error(f"Batch {batch_id} on-chain commitment is missing required fields (ids={len(committed_event_ids)}, seqs={len(committed_sequences)}, hashes={len(committed_hashes)}, root={bool(committed_root)})")
        return BatchVerificationResult(
            case_id=case_id,
            batch_id=batch_id,
            state=VerificationState.BLOCKCHAIN_ERROR,
            merkle_root=committed_root,
            entry_count=committed_count,
            message=f"On-chain batch {batch_id} commitment is malformed or missing V3 identity fields",
        )

    if not (len(committed_event_ids) == len(committed_sequences) == len(committed_hashes)):
        logger.error(f"Batch {batch_id} on-chain commitment field count mismatch")
        return BatchVerificationResult(
            case_id=case_id,
            batch_id=batch_id,
            state=VerificationState.BLOCKCHAIN_ERROR,
            merkle_root=committed_root,
            entry_count=committed_count,
            message=f"On-chain batch {batch_id} commitment field count mismatch",
        )

    # STEP 3: Build maps
    committed_by_id = {}
    for i, (eid, seq, h) in enumerate(zip(committed_event_ids, committed_sequences, committed_hashes)):
        committed_by_id[eid] = {
            "index": i,
            "sequence": seq,
            "hash": h,
            "event_id": eid,
        }

    current_hashes = []
    for e in current_events:
        try:
            current_hashes.append(hash_event(e))
        except Exception:
            current_hashes.append("INVALID_SCHEMA_HASH")

    current_by_id = {}
    for j, (e, h) in enumerate(zip(current_events, current_hashes)):
        eid = e.get("event_id", f"unknown-{j}")
        current_by_id[eid] = {
            "index": j,
            "event": e,
            "sequence": e.get("sequence", j + 1),
            "hash": h,
            "event_id": eid,
        }

    event_results: list[EventVerificationResult] = []

    # Map of ordered events present in both for relative reordering checks
    current_ids_in_both = [e.get("event_id") for e in current_events if e.get("event_id") in committed_by_id]
    committed_ids_in_both = [eid for eid in committed_event_ids if eid in current_by_id]

    # STEP 4: Detect DELETED, STEP 6: Detect MODIFIED, STEP 7: Detect REORDERED
    for idx, eid in enumerate(committed_event_ids):
        c_info = committed_by_id[eid]
        expected_seq = c_info["sequence"]
        expected_hash = c_info["hash"]

        if eid not in current_by_id:
            # STEP 4: DELETED
            er = EventVerificationResult(
                event_id=eid,
                sequence=expected_seq,
                state=VerificationState.DELETED,
                expected_hash=expected_hash,
                actual_hash="MISSING",
                batch_id=batch_id,
                merkle_root=committed_root,
                tx_hash=tx_hash,
                message=f"Event ID: {eid} | Sequence: {expected_seq} is DELETED (missing from current case events)",
            )
            event_results.append(er)
            alert_store.save_alert(
                case_id=case_id,
                batch_id=batch_id,
                event_id=er.event_id,
                sequence=er.sequence,
                alert_type="DELETED",
                severity="CRITICAL",
                expected_hash=er.expected_hash,
                actual_hash="MISSING",
                merkle_root=committed_root,
                tx_hash=tx_hash,
                extra={"message": er.message},
            )
        else:
            cur_info = current_by_id[eid]
            cur_seq = cur_info["sequence"]
            actual_hash = cur_info["hash"]

            # Check for reordering
            cur_pos_in_both = current_ids_in_both.index(eid) if eid in current_ids_in_both else -1
            com_pos_in_both = committed_ids_in_both.index(eid) if eid in committed_ids_in_both else -1
            is_reordered = (cur_seq != expected_seq) or (cur_pos_in_both != com_pos_in_both)

            # Check if event content (excluding sequence change) matches expected
            test_event = cur_info["event"].copy()
            test_event["sequence"] = expected_seq
            content_matches = (hash_event(test_event) == expected_hash)

            if is_reordered and content_matches:
                # Content intact, but sequence/position reordered
                er = EventVerificationResult(
                    event_id=eid,
                    sequence=cur_seq,
                    state=VerificationState.REORDERED,
                    expected_hash=expected_hash,
                    actual_hash=actual_hash,
                    batch_id=batch_id,
                    merkle_root=committed_root,
                    tx_hash=tx_hash,
                    message=f"Event ID: {eid} REORDERED (expected sequence: {expected_seq}, current sequence: {cur_seq})",
                )
                event_results.append(er)
                alert_store.save_alert(
                    case_id=case_id,
                    batch_id=batch_id,
                    event_id=er.event_id,
                    sequence=er.sequence,
                    alert_type="REORDERED",
                    severity="HIGH",
                    expected_hash=er.expected_hash,
                    actual_hash=er.actual_hash,
                    merkle_root=committed_root,
                    tx_hash=tx_hash,
                    extra={"message": er.message},
                )
            elif not content_matches:
                # STEP 6: Detect MODIFIED
                er = EventVerificationResult(
                    event_id=eid,
                    sequence=cur_seq,
                    state=VerificationState.MODIFIED,
                    expected_hash=expected_hash,
                    actual_hash=actual_hash,
                    batch_id=batch_id,
                    merkle_root=committed_root,
                    tx_hash=tx_hash,
                    message=f"Event ID: {eid} | Sequence: {cur_seq} MODIFIED (expected hash: {expected_hash[:16]}..., actual hash: {actual_hash[:16]}...)",
                )
                event_results.append(er)
                alert_store.save_alert(
                    case_id=case_id,
                    batch_id=batch_id,
                    event_id=er.event_id,
                    sequence=er.sequence,
                    alert_type="MODIFIED",
                    severity="CRITICAL",
                    expected_hash=er.expected_hash,
                    actual_hash=er.actual_hash,
                    merkle_root=committed_root,
                    tx_hash=tx_hash,
                    extra={"message": er.message},
                )
            else:
                # Clean event - GREEN
                er = EventVerificationResult(
                    event_id=eid,
                    sequence=cur_seq,
                    state=VerificationState.GREEN,
                    expected_hash=expected_hash,
                    actual_hash=actual_hash,
                    batch_id=batch_id,
                    merkle_root=committed_root,
                    tx_hash=tx_hash,
                    message="Event content and sequence verified successfully against blockchain commitment",
                )
                event_results.append(er)
                alert_store.resolve_event_alerts(case_id, batch_id, eid)

    # STEP 5: Detect UNEXPECTED (current event ID not in committed)
    for j, e in enumerate(current_events):
        eid = e.get("event_id", f"unknown-{j}")
        if eid not in committed_by_id:
            cur_seq = e.get("sequence", j + 1)
            actual_h = current_hashes[j]
            er = EventVerificationResult(
                event_id=eid,
                sequence=cur_seq,
                state=VerificationState.UNEXPECTED,
                expected_hash="",
                actual_hash=actual_h,
                batch_id=batch_id,
                merkle_root=committed_root,
                tx_hash=tx_hash,
                message=f"Event ID: {eid} | Sequence: {cur_seq} is UNEXPECTED (not found in blockchain commitment)",
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
                actual_hash=actual_h,
                merkle_root=committed_root,
                tx_hash=tx_hash,
                extra={"message": er.message},
            )

    # STEP 8: Merkle root check
    recomputed_root = compute_merkle_root(committed_hashes)
    root_valid = bool(committed_root and recomputed_root.lower() == committed_root.lower())
    if not root_valid:
        logger.error(f"Merkle root mismatch for batch {batch_id}! Committed: {committed_root}, Recomputed: {recomputed_root}")

    overall = _overall_state(event_results)
    if not root_valid:
        # Merkle failure must NEVER be GREEN
        overall = VerificationState.MERKLE_MISMATCH

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
    try:
        batch_ids = blockchain.get_case_batches(case_id)
    except Exception as e:
        logger.error(f"Blockchain error fetching case batches for {case_id}: {e}")
        return CaseVerificationResult(
            case_id=case_id,
            overall_state=VerificationState.BLOCKCHAIN_ERROR,
            summary={"error": f"Blockchain connection error: {e}"},
        )
    if not batch_ids:
        return CaseVerificationResult(
            case_id=case_id,
            overall_state=VerificationState.MISSING_COMMITMENT,
            summary={"error": f"No batches found on blockchain for case {case_id}"},
        )

    # If a list of events was passed, automatically partition by on-chain batch commitments
    if isinstance(current_events_by_batch, list):
        raw_events = current_events_by_batch
        current_events_by_batch = {}
        for b_id in batch_ids:
            try:
                on_chain = blockchain.get_batch_on_chain(case_id, b_id)
            except Exception:
                on_chain = None
            if on_chain:
                committed_ids = set(on_chain.get("event_ids", []))
                committed_seqs = set(on_chain.get("event_sequences", []))
                current_events_by_batch[b_id] = [
                    e for e in raw_events
                    if e.get("event_id") in committed_ids or e.get("sequence") in committed_seqs
                ]
            else:
                current_events_by_batch[b_id] = []

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
    Searches through on-chain batches to find where this event_id was committed.
    """
    try:
        batch_ids = blockchain.get_case_batches(case_id)
    except Exception as e:
        return EventVerificationResult(
            event_id=event_id,
            sequence=current_event.get("sequence", 0),
            state=VerificationState.BLOCKCHAIN_ERROR,
            message=f"Blockchain connection error: {e}",
        )

    for batch_id in batch_ids:
        try:
            on_chain = blockchain.get_batch_on_chain(case_id, batch_id)
        except Exception:
            continue
        if not on_chain:
            continue
        event_ids_list = on_chain.get("event_ids", [])
        if event_id not in event_ids_list:
            continue
        idx = event_ids_list.index(event_id)
        committed_hashes = on_chain.get("event_hashes", [])
        if idx >= len(committed_hashes):
            continue
        committed_hash = committed_hashes[idx]
        actual_hash    = hash_event(current_event)
        local_meta     = alert_store.get_batch_metadata(case_id, batch_id) or {}
        tx_hash        = local_meta.get("tx_hash", "")
        merkle_root    = on_chain.get("merkle_root", "")

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
        message=f"Event {event_id} has no commitment in any blockchain batch for {case_id}",
    )
