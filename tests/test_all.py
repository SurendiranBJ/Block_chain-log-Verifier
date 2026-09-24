"""
LogChain - Comprehensive Test Suite
Tests: canonicalization, hashing, Merkle, pipeline, verification, attacks.
All tests run without blockchain (mocked where needed).
"""
import json
import pytest
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.canonical import canonicalize_event, validate_event, REQUIRED_FIELDS
from backend.hashing import hash_event, hash_pair, hash_bytes
from backend.merkle import build_merkle_tree, compute_merkle_root, make_batch_id, verify_root


# ══════════════════════════════════════════════════════════════════════════
# Test Fixtures
# ══════════════════════════════════════════════════════════════════════════

def make_event(seq=1, msg="Test event", event_id=None, case_id="CASE-001"):
    return {
        "event_id":  event_id or f"evt-{seq:06d}",
        "provider":  "local",
        "service":   "iam",
        "source":    "cloudtrail",
        "case_id":   case_id,
        "sequence":  seq,
        "timestamp": "2026-09-25T03:20:00Z",
        "message":   msg,
    }


# ══════════════════════════════════════════════════════════════════════════
# Canonicalization Tests
# ══════════════════════════════════════════════════════════════════════════

class TestCanonicalization:

    def test_same_event_same_bytes(self):
        """Same logical event must produce identical bytes every time."""
        e = make_event(1, "Login event")
        b1 = canonicalize_event(e)
        b2 = canonicalize_event(e)
        assert b1 == b2

    def test_returns_bytes(self):
        e = make_event(1)
        result = canonicalize_event(e)
        assert isinstance(result, bytes)

    def test_utf8_encoded(self):
        e = make_event(1)
        result = canonicalize_event(e)
        # Should decode as valid UTF-8
        decoded = result.decode("utf-8")
        assert decoded

    def test_sorted_keys(self):
        """Keys must be sorted in canonical JSON."""
        e = make_event(1)
        b = canonicalize_event(e)
        decoded = b.decode("utf-8")
        parsed  = json.loads(decoded)
        keys    = list(parsed.keys())
        assert keys == sorted(keys), f"Keys not sorted: {keys}"

    def test_compact_separators(self):
        """No extra whitespace."""
        e = make_event(1)
        b = canonicalize_event(e)
        decoded = b.decode("utf-8")
        assert "  " not in decoded
        assert ": " not in decoded  # no space after colon
        assert ", " not in decoded  # no space after comma

    def test_different_message_different_bytes(self):
        e1 = make_event(1, "original message")
        e2 = make_event(1, "MODIFIED message")
        assert canonicalize_event(e1) != canonicalize_event(e2)

    def test_different_event_id_different_bytes(self):
        e1 = make_event(1, event_id="evt-000001")
        e2 = make_event(1, event_id="evt-000002")
        assert canonicalize_event(e1) != canonicalize_event(e2)

    def test_different_sequence_different_bytes(self):
        e1 = make_event(1)
        e2 = make_event(2)
        assert canonicalize_event(e1) != canonicalize_event(e2)

    def test_sequence_stored_as_int(self):
        """Sequence must be stored as integer, not string."""
        e = make_event(42)
        b = canonicalize_event(e)
        parsed = json.loads(b.decode("utf-8"))
        assert isinstance(parsed["sequence"], int)
        assert parsed["sequence"] == 42

    def test_extra_fields_ignored(self):
        """Extra fields not in canonical schema must be ignored."""
        e = make_event(1)
        e_with_extra = {**e, "extra_field": "should be ignored", "metadata": {"key": "value"}}
        b1 = canonicalize_event(e)
        b2 = canonicalize_event(e_with_extra)
        assert b1 == b2

    def test_unicode_message_preserved(self):
        """Unicode in message must be preserved exactly."""
        e = make_event(1, msg="User 张三 performed login from 日本")
        b = canonicalize_event(e)
        parsed = json.loads(b.decode("utf-8"))
        assert parsed["message"] == "User 张三 performed login from 日本"

    def test_missing_required_field_raises(self):
        e = make_event(1)
        del e["message"]
        with pytest.raises(ValueError, match="missing required fields"):
            canonicalize_event(e)

    def test_invalid_sequence_type_raises(self):
        e = make_event(1)
        e["sequence"] = "1"  # string, not int
        with pytest.raises(ValueError, match="sequence must be an integer"):
            canonicalize_event(e)

    def test_validates_all_required_fields(self):
        for field in REQUIRED_FIELDS:
            e = make_event(1)
            del e[field]
            with pytest.raises(ValueError):
                canonicalize_event(e)


# ══════════════════════════════════════════════════════════════════════════
# SHA-256 Hashing Tests
# ══════════════════════════════════════════════════════════════════════════

class TestHashing:

    def test_returns_64_char_hex(self):
        e = make_event(1)
        h = hash_event(e)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_same_event_same_hash(self):
        e = make_event(1, "Login")
        assert hash_event(e) == hash_event(e)

    def test_different_message_different_hash(self):
        e1 = make_event(1, "Original message")
        e2 = make_event(1, "MODIFIED message")
        assert hash_event(e1) != hash_event(e2)

    def test_different_event_id_different_hash(self):
        e1 = {**make_event(1), "event_id": "evt-000001"}
        e2 = {**make_event(1), "event_id": "evt-000099"}
        assert hash_event(e1) != hash_event(e2)

    def test_different_sequence_different_hash(self):
        assert hash_event(make_event(1)) != hash_event(make_event(2))

    def test_different_case_id_different_hash(self):
        e1 = make_event(1, case_id="CASE-001")
        e2 = make_event(1, case_id="CASE-002")
        assert hash_event(e1) != hash_event(e2)

    def test_lowercase_output(self):
        e = make_event(1)
        h = hash_event(e)
        assert h == h.lower()

    def test_hash_pair_deterministic(self):
        h1 = "a" * 64
        h2 = "b" * 64
        assert hash_pair(h1, h2) == hash_pair(h1, h2)
        assert hash_pair(h1, h2) != hash_pair(h2, h1)  # NOT commutative

    def test_known_sha256_value(self):
        """Regression test: known input → known hash."""
        import hashlib
        e = make_event(1, "Test")
        b = canonicalize_event(e)
        expected = hashlib.sha256(b).hexdigest()
        assert hash_event(e) == expected


# ══════════════════════════════════════════════════════════════════════════
# Merkle Tree Tests
# ══════════════════════════════════════════════════════════════════════════

class TestMerkle:

    def _event_hashes(self, count):
        return [hash_event(make_event(i)) for i in range(1, count + 1)]

    def test_empty_returns_none_root(self):
        result = build_merkle_tree([])
        assert result["root"] is None
        assert result["entry_count"] == 0

    def test_single_leaf_root_equals_leaf(self):
        hashes = self._event_hashes(1)
        result = build_merkle_tree(hashes)
        assert result["root"] == hashes[0]
        assert result["entry_count"] == 1

    def test_two_leaves(self):
        hashes = self._event_hashes(2)
        result = build_merkle_tree(hashes)
        assert result["root"] is not None
        assert result["root"] != hashes[0]
        assert result["root"] != hashes[1]
        assert result["entry_count"] == 2

    def test_three_leaves_odd_count(self):
        """Odd count: last leaf is duplicated."""
        hashes = self._event_hashes(3)
        result = build_merkle_tree(hashes)
        assert result["root"] is not None
        assert result["entry_count"] == 3

    def test_ten_leaves(self):
        hashes = self._event_hashes(10)
        result = build_merkle_tree(hashes)
        assert result["root"] is not None
        assert result["entry_count"] == 10

    def test_hundred_leaves(self):
        hashes = self._event_hashes(100)
        result = build_merkle_tree(hashes)
        assert result["root"] is not None
        assert result["entry_count"] == 100

    def test_deterministic(self):
        """Same input → same root."""
        hashes = self._event_hashes(10)
        r1 = build_merkle_tree(hashes)["root"]
        r2 = build_merkle_tree(hashes)["root"]
        assert r1 == r2

    def test_modifying_one_event_changes_root(self):
        hashes  = self._event_hashes(10)
        root1   = build_merkle_tree(hashes)["root"]

        modified = hashes[:]
        modified[4] = hash_event(make_event(99, "TAMPERED"))
        root2 = build_merkle_tree(modified)["root"]

        assert root1 != root2

    def test_removing_one_event_changes_root(self):
        hashes  = self._event_hashes(10)
        root1   = build_merkle_tree(hashes)["root"]
        root2   = build_merkle_tree(hashes[:-1])["root"]
        assert root1 != root2

    def test_reordering_events_changes_root(self):
        hashes  = self._event_hashes(10)
        root1   = build_merkle_tree(hashes)["root"]
        swapped = hashes[:]
        swapped[0], swapped[1] = swapped[1], swapped[0]
        root2   = build_merkle_tree(swapped)["root"]
        assert root1 != root2

    def test_verify_root_correct(self):
        hashes      = self._event_hashes(5)
        result      = build_merkle_tree(hashes)
        assert verify_root(hashes, result["root"]) is True

    def test_verify_root_fails_on_tamper(self):
        hashes  = self._event_hashes(5)
        result  = build_merkle_tree(hashes)
        bad_hashes = hashes[:]
        bad_hashes[2] = "a" * 64
        assert verify_root(bad_hashes, result["root"]) is False

    def test_batch_id_format(self):
        batch_id = make_batch_id("CASE-001", 1)
        assert batch_id == "batch-CASE-001-000001"

    def test_batch_id_padding(self):
        batch_id = make_batch_id("CASE-001", 100)
        assert batch_id == "batch-CASE-001-000100"


# ══════════════════════════════════════════════════════════════════════════
# Attack Simulation Tests (no blockchain, uses mocks)
# ══════════════════════════════════════════════════════════════════════════

class TestTamperDetection:
    """Tests using the verifier with mocked blockchain calls."""

    def _make_events(self, count=5):
        return [make_event(i, f"Event {i}") for i in range(1, count + 1)]

    def _hashes(self, events):
        return [hash_event(e) for e in events]

    def _merkle_root(self, events):
        return compute_merkle_root(self._hashes(events))

    def _mock_batch(self, events, batch_id="batch-CASE-001-000001"):
        hashes = self._hashes(events)
        return {
            "merkle_root":     compute_merkle_root(hashes),
            "entry_count":     len(hashes),
            "timestamp":       1000000,
            "exists":          True,
            "event_ids":       [e["event_id"] for e in events],
            "event_sequences": [e["sequence"] for e in events],
            "event_hashes":    hashes,
        }

    def _mock_meta(self, events, batch_id="batch-CASE-001-000001"):
        hashes = self._hashes(events)
        return {
            "case_id":      "CASE-001",
            "batch_id":     batch_id,
            "merkle_root":  compute_merkle_root(hashes),
            "entry_count":  len(hashes),
            "tx_hash":      "0x" + "a" * 64,
            "event_hashes": hashes,
            "event_ids":    [e["event_id"] for e in events],
            "sequences":    [e["sequence"] for e in events],
        }

    @patch("backend.verifier.alert_store")
    @patch("backend.verifier.blockchain")
    def test_all_events_green(self, mock_bc, mock_alert):
        from backend.verifier import verify_batch, VerificationState
        events = self._make_events(5)
        mock_bc.get_batch_on_chain.return_value = self._mock_batch(events)
        mock_alert.get_batch_metadata.return_value = self._mock_meta(events)
        mock_alert.save_alert = MagicMock()

        result = verify_batch("CASE-001", "batch-CASE-001-000001", events)
        assert result.state == VerificationState.GREEN
        assert all(r.state == VerificationState.GREEN for r in result.event_results)

    @patch("backend.verifier.alert_store")
    @patch("backend.verifier.blockchain")
    def test_modified_event_detected(self, mock_bc, mock_alert):
        from backend.verifier import verify_batch, VerificationState
        original_events = self._make_events(5)
        mock_bc.get_batch_on_chain.return_value = self._mock_batch(original_events)
        mock_alert.get_batch_metadata.return_value = self._mock_meta(original_events)
        mock_alert.save_alert = MagicMock()

        # Modify event 3 (index 2)
        tampered = [e.copy() for e in original_events]
        tampered[2]["message"] = "TAMPERED EVENT"

        result = verify_batch("CASE-001", "batch-CASE-001-000001", tampered)
        assert result.state == VerificationState.MODIFIED

        # Find the modified result
        modified = [r for r in result.event_results if r.state == VerificationState.MODIFIED]
        assert len(modified) == 1
        assert modified[0].event_id == "evt-000003"

    @patch("backend.verifier.alert_store")
    @patch("backend.verifier.blockchain")
    def test_deleted_event_detected(self, mock_bc, mock_alert):
        from backend.verifier import verify_batch, VerificationState
        original_events = self._make_events(5)
        mock_bc.get_batch_on_chain.return_value = self._mock_batch(original_events)
        mock_alert.get_batch_metadata.return_value = self._mock_meta(original_events)
        mock_alert.save_alert = MagicMock()

        # Delete event at index 4 (sequence 5)
        truncated = original_events[:4]

        result = verify_batch("CASE-001", "batch-CASE-001-000001", truncated)
        assert result.state == VerificationState.DELETED

        deleted = [r for r in result.event_results if r.state == VerificationState.DELETED]
        assert len(deleted) == 1

    @patch("backend.verifier.alert_store")
    @patch("backend.verifier.blockchain")
    def test_middle_deletion_detected(self, mock_bc, mock_alert):
        """Test middle deletion: 100 events, delete event 51 -> exactly one DELETED, 0 MODIFIED"""
        from backend.verifier import verify_batch, VerificationState
        from demo.generate_logs import generate_events
        original_events = generate_events(case_id="CASE-001", count=100)
        mock_bc.get_batch_on_chain.return_value = self._mock_batch(original_events)
        mock_alert.get_batch_metadata.return_value = self._mock_meta(original_events)
        mock_alert.save_alert = MagicMock()

        # Delete event 51 (index 50)
        deleted_event = original_events[50]
        tampered = original_events[:50] + original_events[51:]
        assert len(tampered) == 99

        result = verify_batch("CASE-001", "batch-CASE-001-000001", tampered)
        assert result.state == VerificationState.DELETED
        deleted = [r for r in result.event_results if r.state == VerificationState.DELETED]
        assert len(deleted) == 1
        assert deleted[0].sequence == 51
        assert deleted[0].event_id == deleted_event["event_id"]
        # Crucial check: NOT 50 modified events!
        assert result.summary["modified"] == 0
        assert result.summary["deleted"] == 1
        assert result.summary["unexpected"] == 0
        assert result.summary["reordered"] == 0
        assert result.summary["green"] == 99

    @patch("backend.verifier.alert_store")
    @patch("backend.verifier.blockchain")
    def test_middle_modification_detected(self, mock_bc, mock_alert):
        """Test middle modification: 100 events, modify event 51 -> exactly one MODIFIED event"""
        from backend.verifier import verify_batch, VerificationState
        from demo.generate_logs import generate_events
        original_events = generate_events(case_id="CASE-001", count=100)
        mock_bc.get_batch_on_chain.return_value = self._mock_batch(original_events)
        mock_alert.get_batch_metadata.return_value = self._mock_meta(original_events)
        mock_alert.save_alert = MagicMock()

        tampered = [e.copy() for e in original_events]
        tampered[50]["message"] = "ATTACKER MODIFIED EVENT 51"

        result = verify_batch("CASE-001", "batch-CASE-001-000001", tampered)
        assert result.state == VerificationState.MODIFIED
        modified = [r for r in result.event_results if r.state == VerificationState.MODIFIED]
        assert len(modified) == 1
        assert modified[0].sequence == 51
        assert modified[0].event_id == original_events[50]["event_id"]
        assert result.summary["modified"] == 1
        assert result.summary["deleted"] == 0
        assert result.summary["unexpected"] == 0
        assert result.summary["reordered"] == 0
        assert result.summary["green"] == 99

    @patch("backend.verifier.alert_store")
    @patch("backend.verifier.blockchain")
    def test_reordered_event_detected(self, mock_bc, mock_alert):
        """Test swap events 51 and 52 -> REORDERED detected"""
        from backend.verifier import verify_batch, VerificationState
        from demo.generate_logs import generate_events
        original_events = generate_events(case_id="CASE-001", count=100)
        mock_bc.get_batch_on_chain.return_value = self._mock_batch(original_events)
        mock_alert.get_batch_metadata.return_value = self._mock_meta(original_events)
        mock_alert.save_alert = MagicMock()

        tampered = [e.copy() for e in original_events]
        tampered[50]["sequence"] = 52
        tampered[51]["sequence"] = 51
        tampered[50], tampered[51] = tampered[51], tampered[50]

        result = verify_batch("CASE-001", "batch-CASE-001-000001", tampered)
        assert result.state == VerificationState.REORDERED
        reordered = [r for r in result.event_results if r.state == VerificationState.REORDERED]
        assert len(reordered) >= 1
        assert result.summary["modified"] == 0
        assert result.summary["reordered"] >= 1

    @patch("backend.verifier.alert_store")
    @patch("backend.verifier.blockchain")
    def test_unexpected_event_detected(self, mock_bc, mock_alert):
        from backend.verifier import verify_batch, VerificationState
        original_events = self._make_events(5)
        mock_bc.get_batch_on_chain.return_value = self._mock_batch(original_events)
        mock_alert.get_batch_metadata.return_value = self._mock_meta(original_events)
        mock_alert.save_alert = MagicMock()

        # Add an extra event
        extra_events = original_events + [make_event(99, "INJECTED EVENT")]

        result = verify_batch("CASE-001", "batch-CASE-001-000001", extra_events)
        assert result.state == VerificationState.UNEXPECTED

        unexpected = [r for r in result.event_results if r.state == VerificationState.UNEXPECTED]
        assert len(unexpected) == 1

    @patch("backend.verifier.alert_store")
    @patch("backend.verifier.blockchain")
    def test_restored_clean_state_green(self, mock_bc, mock_alert):
        """Test restore clean state -> GREEN"""
        from backend.verifier import verify_batch, VerificationState
        from demo.generate_logs import generate_events
        original_events = generate_events(case_id="CASE-001", count=100)
        mock_bc.get_batch_on_chain.return_value = self._mock_batch(original_events)
        mock_alert.get_batch_metadata.return_value = self._mock_meta(original_events)
        mock_alert.save_alert = MagicMock()

        result = verify_batch("CASE-001", "batch-CASE-001-000001", original_events)
        assert result.state == VerificationState.GREEN
        assert result.summary["green"] == 100
        assert result.summary["modified"] == 0
        assert result.summary["deleted"] == 0

    def test_historical_alert_does_not_force_red(self):
        """Test old historical alerts in MongoDB do not force dashboard RED when clean"""
        from backend.app import app
        from backend.verifier import VerificationState, EventVerificationResult, BatchVerificationResult
        from unittest.mock import patch, MagicMock
        with patch("backend.app.alert_store") as mock_alert, \
             patch("backend.app.verify_engine") as mock_ve, \
             patch("backend.app.blockchain") as mock_bc, \
             patch("backend.app.LocalLogGetter") as mock_getter:
            
            mock_alert.is_mongodb_available.return_value = True
            mock_bc.blockchain_status.return_value = {"device1": {"connected": True, "block": 10}, "device2": {"connected": False}}
            mock_bc.get_case_batches.return_value = ["batch-1"]
            mock_alert.get_batch_metadata.return_value = {"sequences": [1]}
            mock_alert.get_case_alerts.return_value = [{"alert_type": "MODIFIED", "status": "RESOLVED", "event_id": "e1"}]
            mock_alert.get_alert_stats.return_value = {"MODIFIED": 1, "total_alerts": 1}
            
            mock_getter.return_value.fetch_events.return_value = [{"event_id": "e1", "sequence": 1}]
            clean_er = EventVerificationResult(
                event_id="e1",
                sequence=1,
                state=VerificationState.GREEN,
                expected_hash="h1",
                actual_hash="h1",
            )
            mock_res = BatchVerificationResult(
                case_id="CASE-001",
                batch_id="batch-1",
                state=VerificationState.GREEN,
                event_results=[clean_er],
            )
            mock_ve.verify_batch.return_value = mock_res
            mock_ve.VerificationState = VerificationState
            
            client = app.test_client()
            res = client.get("/api/status")
            assert res.status_code == 200
            data = res.get_json()
            assert data["integrity"] == "GREEN"

    def test_unique_batch_ids_across_runs(self):
        """Test unique batch IDs across separate demo runs"""
        from backend.merkle import make_batch_id
        b1 = make_batch_id("CASE-RUN-001", 1)
        b2 = make_batch_id("CASE-RUN-002", 1)
        assert b1 != b2
        b3 = make_batch_id("CASE-RUN-001", 1, run_id="RUN-A")
        b4 = make_batch_id("CASE-RUN-001", 1, run_id="RUN-B")
        assert b3 != b4

    @patch("backend.verifier.alert_store")
    @patch("backend.verifier.blockchain")
    def test_blockchain_error_handled(self, mock_bc, mock_alert):
        from backend.verifier import verify_batch, VerificationState
        mock_bc.get_batch_on_chain.side_effect = ConnectionError("Node offline")
        mock_alert.get_batch_metadata.return_value = None

        result = verify_batch("CASE-001", "batch-CASE-001-000001", [])
        assert result.state == VerificationState.BLOCKCHAIN_ERROR

    @patch("backend.verifier.alert_store")
    @patch("backend.verifier.blockchain")
    def test_missing_commitment(self, mock_bc, mock_alert):
        from backend.verifier import verify_batch, VerificationState
        mock_bc.get_batch_on_chain.return_value = None

        result = verify_batch("CASE-001", "batch-CASE-001-000001", [])
        assert result.state == VerificationState.MISSING_COMMITMENT

    @patch("backend.verifier.alert_store")
    @patch("backend.verifier.blockchain")
    def test_mongodb_metadata_never_acts_as_trusted_fallback(self, mock_bc, mock_alert):
        """CRITICAL: Even if MongoDB has complete batch metadata, if on_chain is None, verify_batch MUST return MISSING_COMMITMENT (PART 1)."""
        from backend.verifier import verify_batch, VerificationState
        from demo.generate_logs import generate_events
        events = generate_events("CASE-001", count=10)
        
        # Blockchain has no record of this batch
        mock_bc.get_batch_on_chain.return_value = None
        
        # MongoDB HAS full batch metadata
        mock_alert.get_batch_metadata.return_value = {
            "merkle_root": "0x" + "a" * 64,
            "entry_count": 10,
            "event_hashes": ["0x" + "b" * 64] * 10,
            "event_ids": [f"evt-{i+1:06d}" for i in range(10)],
            "sequences": list(range(1, 11)),
            "tx_hash": "0xFAKE_TX",
        }

        result = verify_batch("CASE-001", "batch-CASE-001-000001", events)
        assert result.state == VerificationState.MISSING_COMMITMENT
        assert result.state != VerificationState.GREEN

    def test_api_status_reports_blockchain_error_when_device1_offline(self):
        """Dashboard API must report BLOCKCHAIN_ERROR when Device 1 is disconnected (PART 2 & 3)."""
        from backend.app import app
        with patch("backend.app.blockchain") as mock_bc, \
             patch("backend.app.LocalLogGetter") as mock_getter:
            
            mock_bc.blockchain_status.return_value = {"device1": {"connected": False}}
            mock_getter.return_value.fetch_events.return_value = [{"event_id": "e1", "sequence": 1}]
            
            client = app.test_client()
            res = client.get("/api/status")
            assert res.status_code == 200
            data = res.get_json()
            assert data["integrity"] == "BLOCKCHAIN_ERROR"
            assert "Unable to connect to Device 1" in data.get("status_reason", "")

    def test_api_status_reports_missing_commitment_when_no_blockchain_batches(self):
        """Dashboard API must report MISSING_COMMITMENT when events exist but no blockchain commitment exists (PART 2 & 3)."""
        from backend.app import app
        with patch("backend.app.blockchain") as mock_bc, \
             patch("backend.app.LocalLogGetter") as mock_getter:
            
            mock_bc.blockchain_status.return_value = {"device1": {"connected": True}}
            mock_bc.get_case_batches.return_value = []
            mock_getter.return_value.fetch_events.return_value = [{"event_id": "e1", "sequence": 1}]
            
            client = app.test_client()
            res = client.get("/api/status")
            assert res.status_code == 200
            data = res.get_json()
            assert data["integrity"] == "MISSING_COMMITMENT"

    def test_api_status_reports_no_data(self):
        """Dashboard API must report NO_DATA when no logs and no blockchain commitments exist (PART 2 & 3)."""
        from backend.app import app
        with patch("backend.app.blockchain") as mock_bc, \
             patch("backend.app.LocalLogGetter") as mock_getter:
            
            mock_bc.blockchain_status.return_value = {"device1": {"connected": True}}
            mock_bc.get_case_batches.return_value = []
            mock_getter.return_value.fetch_events.return_value = []
            
            client = app.test_client()
            res = client.get("/api/status")
            assert res.status_code == 200
            data = res.get_json()
            assert data["integrity"] == "NO_DATA"

    def test_contract_append_only_duplicate_rejection_logic(self):
        """Verify duplicate batch rejection logic: same batch ID rejected, different batch ID accepted (PART 8 & 9)."""
        # Simulated contract store
        anchored_batches = {}

        def anchor_batch(case_id, batch_id, root):
            key = f"{case_id}:{batch_id}"
            if key in anchored_batches:
                raise ValueError("Execution reverted: Batch already anchored")
            anchored_batches[key] = root
            return {"status": 1}

        # First anchor succeeds
        r1 = anchor_batch("CASE-001", "batch-001", "rootA")
        assert r1["status"] == 1
        assert anchored_batches["CASE-001:batch-001"] == "rootA"

        # Duplicate anchor fails / reverts
        with pytest.raises(ValueError, match="Batch already anchored"):
            anchor_batch("CASE-001", "batch-001", "rootA_modified")

        # Verify original batch remains untouched
        assert anchored_batches["CASE-001:batch-001"] == "rootA"

        # Unique batch for same case succeeds
        r2 = anchor_batch("CASE-001", "batch-002", "rootB")
        assert r2["status"] == 1
        assert anchored_batches["CASE-001:batch-002"] == "rootB"


# ══════════════════════════════════════════════════════════════════════════
# Pipeline Tests (no blockchain)
# ══════════════════════════════════════════════════════════════════════════

class TestPipeline:

    @patch("backend.pipeline.verify_engine")
    @patch("backend.pipeline.alert_store")
    @patch("backend.pipeline.blockchain")
    def test_pipeline_success(self, mock_bc, mock_alert, mock_verify):
        from backend.pipeline import ingest_events
        from backend.verifier import VerificationState

        mock_bc.batch_exists.return_value = False
        mock_bc.anchor_batch.return_value = {
            "tx_hash": "0x" + "b" * 64,
            "block_number": 42,
            "gas_used": 100000,
            "status": "ANCHORED",
        }
        mock_alert.save_batch_metadata.return_value = "some-id"
        mock_verify_result = MagicMock()
        mock_verify_result.state = VerificationState.GREEN
        mock_verify.verify_batch.return_value = mock_verify_result
        mock_verify.VerificationState = VerificationState

        events = [make_event(i, f"Event {i}") for i in range(1, 6)]
        result = ingest_events(events)

        assert result["status"]       == "ANCHORED"
        assert result["entry_count"]  == 5
        assert result["case_id"]      == "CASE-001"
        assert result["verification"] == "PASS"
        assert len(result["merkle_root"]) == 64
        assert len(result["event_hashes"]) == 5

    @patch("backend.pipeline.blockchain")
    def test_pipeline_rejects_empty(self, mock_bc):
        from backend.pipeline import ingest_events, PipelineError
        with pytest.raises(PipelineError, match="No events provided"):
            ingest_events([])

    @patch("backend.pipeline.blockchain")
    def test_pipeline_rejects_mixed_case_ids(self, mock_bc):
        from backend.pipeline import ingest_events, PipelineError
        events = [
            make_event(1, case_id="CASE-001"),
            make_event(2, case_id="CASE-002"),
        ]
        with pytest.raises(PipelineError, match="Mixed case_ids"):
            ingest_events(events)

    @patch("backend.pipeline.blockchain")
    def test_pipeline_rejects_invalid_event(self, mock_bc):
        from backend.pipeline import ingest_events, PipelineError
        bad_event = {"event_id": "x"}  # missing required fields
        with pytest.raises(PipelineError):
            ingest_events([bad_event])

    @patch("backend.pipeline.blockchain")
    def test_pipeline_rejects_duplicate_batch(self, mock_bc):
        from backend.pipeline import ingest_events, PipelineError
        mock_bc.batch_exists.return_value = True
        events = [make_event(i) for i in range(1, 6)]
        with pytest.raises(PipelineError, match="already anchored"):
            ingest_events(events)


# ══════════════════════════════════════════════════════════════════════════
# Adapter Interface Tests
# ══════════════════════════════════════════════════════════════════════════

class TestAdapters:

    def test_local_getter_interface(self):
        from adapters.local_getter import LocalLogGetter
        getter = LocalLogGetter()
        assert hasattr(getter, "fetch_events")
        assert hasattr(getter, "health_check")

    def test_aws_getter_interface(self):
        from adapters.aws_getter import AWSLogGetter
        getter = AWSLogGetter()
        assert hasattr(getter, "fetch_events")
        assert hasattr(getter, "health_check")

    def test_azure_getter_interface(self):
        from adapters.azure_getter import AzureLogGetter
        getter = AzureLogGetter()
        assert hasattr(getter, "fetch_events")
        assert hasattr(getter, "health_check")

    def test_local_getter_health_check(self, tmp_path):
        from adapters.local_getter import LocalLogGetter
        getter = LocalLogGetter(log_dir=str(tmp_path))
        result = getter.health_check()
        assert result["status"] == "ok"
        assert result["provider"] == "local"

    def test_local_getter_fetch_events(self, tmp_path):
        from adapters.local_getter import LocalLogGetter
        getter = LocalLogGetter(log_dir=str(tmp_path))

        events = [make_event(i) for i in range(1, 6)]
        getter.write_events("CASE-001", events)

        loaded = getter.fetch_events("CASE-001")
        assert len(loaded) == 5
        assert loaded[0]["sequence"] == 1
        assert loaded[-1]["sequence"] == 5

    def test_local_getter_sorted_by_sequence(self, tmp_path):
        from adapters.local_getter import LocalLogGetter
        getter = LocalLogGetter(log_dir=str(tmp_path))

        # Write in reverse order
        events = [make_event(i) for i in range(5, 0, -1)]
        getter.write_events("CASE-001", events)

        loaded = getter.fetch_events("CASE-001")
        sequences = [e["sequence"] for e in loaded]
        assert sequences == sorted(sequences)

    def test_local_getter_missing_case(self, tmp_path):
        from adapters.local_getter import LocalLogGetter
        getter = LocalLogGetter(log_dir=str(tmp_path))
        events = getter.fetch_events("NONEXISTENT-CASE")
        assert events == []


# ══════════════════════════════════════════════════════════════════════════
# Demo Generator Tests
# ══════════════════════════════════════════════════════════════════════════

class TestDemoGenerator:

    def test_generates_correct_count(self):
        from demo.generate_logs import generate_events
        events = generate_events(count=100)
        assert len(events) == 100

    def test_generates_normalized_schema(self):
        from demo.generate_logs import generate_events
        from backend.canonical import REQUIRED_FIELDS
        events = generate_events(count=5)
        for e in events:
            for field in REQUIRED_FIELDS:
                assert field in e, f"Missing field '{field}' in event: {e}"

    def test_sequences_are_sequential(self):
        from demo.generate_logs import generate_events
        events = generate_events(count=10)
        sequences = [e["sequence"] for e in events]
        assert sequences == list(range(1, 11))

    def test_unique_event_ids(self):
        from demo.generate_logs import generate_events
        events = generate_events(count=50)
        ids = [e["event_id"] for e in events]
        assert len(ids) == len(set(ids))

    def test_deterministic(self):
        """Same seed → same events."""
        from demo.generate_logs import generate_events
        events1 = generate_events(count=10)
        events2 = generate_events(count=10)
        assert events1 == events2

    def test_all_events_hashable(self):
        from demo.generate_logs import generate_events
        events = generate_events(count=100)
        for e in events:
            h = hash_event(e)
            assert len(h) == 64


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
