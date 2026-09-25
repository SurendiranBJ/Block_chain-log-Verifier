"""
LogChain - Live Geth Integration Tests
Tests real blockchain interaction against a local private Geth testnet.
Gracefully skips/blocks when Geth or Device 2 is unavailable.
"""
import uuid
import pytest
from web3 import Web3

from backend.config import (
    DEVICE1_RPC, DEVICE2_RPC, CHAIN_ID,
    BLOCKCHAIN_PRIVATE_KEY, BLOCKCHAIN_ACCOUNT,
    CONTRACT_ADDRESS,
)
from backend import blockchain
from backend.merkle import compute_merkle_root, make_batch_id
from backend.hashing import hash_event
from backend import verifier as verify_engine
from demo.generate_logs import generate_events


def _is_device1_available() -> bool:
    try:
        w3 = blockchain.get_w3(1)
        return w3.is_connected()
    except Exception:
        return False


def _is_device2_available() -> bool:
    try:
        w3 = blockchain.get_w3(2)
        return w3.is_connected()
    except Exception:
        return False


@pytest.mark.integration
class TestGethIntegration:

    @pytest.fixture(autouse=True)
    def check_geth(self):
        if not _is_device1_available():
            pytest.skip(f"Device 1 Geth not running at {DEVICE1_RPC}")

    def test_connect_to_geth_and_chain_id(self):
        """1 & 2: Connect to Geth and verify chain ID."""
        w3 = blockchain.get_w3(1)
        assert w3.is_connected() is True
        assert w3.eth.chain_id == CHAIN_ID

    def test_anchor_and_retrieve_batch(self):
        """3, 4, 5, 6: Anchor real batch with event IDs and sequences, then retrieve and verify."""
        case_id = f"CASE-INTEG-{uuid.uuid4().hex[:6]}"
        events = generate_events(case_id=case_id, count=10)
        event_hashes = [hash_event(e) for e in events]
        event_ids = [e["event_id"] for e in events]
        sequences = [e["sequence"] for e in events]
        root = compute_merkle_root(event_hashes)
        batch_id = make_batch_id(case_id, 1, run_id="INTG")

        # Anchor
        res = blockchain.anchor_batch(
            case_id=case_id,
            batch_id=batch_id,
            merkle_root=root,
            entry_count=len(events),
            event_ids=event_ids,
            event_sequences=sequences,
            event_hashes=event_hashes,
        )
        assert res["status"] == "ANCHORED"

        # Retrieve
        on_chain = blockchain.get_batch_on_chain(case_id, batch_id)
        assert on_chain is not None
        assert on_chain["merkle_root"] == root
        assert on_chain["entry_count"] == 10
        assert on_chain["event_ids"] == event_ids
        assert on_chain["event_sequences"] == sequences
        assert on_chain["event_hashes"] == event_hashes

        # Verify clean events
        vres = verify_engine.verify_batch(case_id, batch_id, events)
        assert vres.state == verify_engine.VerificationState.GREEN

    def test_modify_event_detected(self):
        """7 & 8: Tamper content -> detect MODIFIED."""
        case_id = f"CASE-INTEG-MOD-{uuid.uuid4().hex[:6]}"
        events = generate_events(case_id=case_id, count=10)
        event_hashes = [hash_event(e) for e in events]
        event_ids = [e["event_id"] for e in events]
        sequences = [e["sequence"] for e in events]
        root = compute_merkle_root(event_hashes)
        batch_id = make_batch_id(case_id, 1, run_id="MOD")

        blockchain.anchor_batch(
            case_id=case_id,
            batch_id=batch_id,
            merkle_root=root,
            entry_count=len(events),
            event_ids=event_ids,
            event_sequences=sequences,
            event_hashes=event_hashes,
        )

        tampered = [e.copy() for e in events]
        tampered[5]["message"] = "ATTACKER INJECTED MODIFICATION"

        vres = verify_engine.verify_batch(case_id, batch_id, tampered)
        assert vres.state == verify_engine.VerificationState.MODIFIED
        assert vres.summary["modified"] == 1
        assert vres.summary["deleted"] == 0

    def test_delete_middle_event_detected(self):
        """9 & 10: Delete middle event -> detect DELETED exactly (no cascading false modified alerts)."""
        case_id = f"CASE-INTEG-DEL-{uuid.uuid4().hex[:6]}"
        events = generate_events(case_id=case_id, count=10)
        event_hashes = [hash_event(e) for e in events]
        event_ids = [e["event_id"] for e in events]
        sequences = [e["sequence"] for e in events]
        root = compute_merkle_root(event_hashes)
        batch_id = make_batch_id(case_id, 1, run_id="DEL")

        blockchain.anchor_batch(
            case_id=case_id,
            batch_id=batch_id,
            merkle_root=root,
            entry_count=len(events),
            event_ids=event_ids,
            event_sequences=sequences,
            event_hashes=event_hashes,
        )

        # Delete middle event (index 5)
        tampered = events[:5] + events[6:]
        vres = verify_engine.verify_batch(case_id, batch_id, tampered)
        assert vres.state == verify_engine.VerificationState.DELETED
        assert vres.summary["deleted"] == 1
        assert vres.summary["modified"] == 0

    def test_reorder_events_detected(self):
        """11 & 12: Swap events -> detect REORDERED."""
        case_id = f"CASE-INTEG-REO-{uuid.uuid4().hex[:6]}"
        events = generate_events(case_id=case_id, count=10)
        event_hashes = [hash_event(e) for e in events]
        event_ids = [e["event_id"] for e in events]
        sequences = [e["sequence"] for e in events]
        root = compute_merkle_root(event_hashes)
        batch_id = make_batch_id(case_id, 1, run_id="REORD")

        blockchain.anchor_batch(
            case_id=case_id,
            batch_id=batch_id,
            merkle_root=root,
            entry_count=len(events),
            event_ids=event_ids,
            event_sequences=sequences,
            event_hashes=event_hashes,
        )

        tampered = [e.copy() for e in events]
        tampered[5]["sequence"] = 7
        tampered[6]["sequence"] = 6
        tampered[5], tampered[6] = tampered[6], tampered[5]

        vres = verify_engine.verify_batch(case_id, batch_id, tampered)
        assert vres.state == verify_engine.VerificationState.REORDERED
        assert vres.summary["reordered"] >= 1
        assert vres.summary["modified"] == 0

    def test_insert_event_detected(self):
        """13 & 14: Insert unexpected uncommitted event -> detect UNEXPECTED."""
        case_id = f"CASE-INTEG-INS-{uuid.uuid4().hex[:6]}"
        events = generate_events(case_id=case_id, count=10)
        event_hashes = [hash_event(e) for e in events]
        event_ids = [e["event_id"] for e in events]
        sequences = [e["sequence"] for e in events]
        root = compute_merkle_root(event_hashes)
        batch_id = make_batch_id(case_id, 1, run_id="INS")

        blockchain.anchor_batch(
            case_id=case_id,
            batch_id=batch_id,
            merkle_root=root,
            entry_count=len(events),
            event_ids=event_ids,
            event_sequences=sequences,
            event_hashes=event_hashes,
        )

        tampered = events + [{
            "event_id": "attacker-injected",
            "case_id": case_id,
            "sequence": 99,
            "timestamp": "2026-09-25T00:00:00Z",
            "source": "cloudtrail",
            "provider": "aws",
            "action": "Backdoor",
            "message": "Injected uncommitted log",
            "severity": "CRITICAL",
        }]

        vres = verify_engine.verify_batch(case_id, batch_id, tampered)
        assert vres.state == verify_engine.VerificationState.UNEXPECTED
        assert vres.summary["unexpected"] == 1

    def test_device2_replicates_state(self):
        """15: Verify Device 2 sees the same blockchain state."""
        if not _is_device2_available():
            pytest.skip("BLOCKED — Device 2 unavailable")

        w3_dev2 = blockchain.get_w3(2)
        w3_dev1 = blockchain.get_w3(1)

        block1 = w3_dev1.eth.block_number
        block2 = w3_dev2.eth.block_number
        assert abs(block1 - block2) <= 2, f"Device 2 out of sync: dev1={block1}, dev2={block2}"
