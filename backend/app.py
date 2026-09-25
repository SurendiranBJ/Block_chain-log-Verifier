"""
LogChain - Flask Dashboard & API
Zero-Trust Cross-Cloud Log Integrity System
Judge-friendly dashboard with live integrity and exact attack visualization.
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template, request, abort
import markupsafe

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from backend.config import (
    FLASK_SECRET_KEY, FLASK_DEBUG, FLASK_PORT,
    CONTRACT_ADDRESS, get_current_case_id, set_current_case_id,
    DEVICE1_RPC, INGEST_API_TOKEN,
)
from backend import blockchain, alerts as alert_store
from backend.pipeline import ingest_events, PipelineError
from backend import verifier as verify_engine
from adapters.local_getter import LocalLogGetter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

template_dir = str(_PROJECT_ROOT / "dashboard" / "templates")
static_dir = str(_PROJECT_ROOT / "dashboard" / "static")

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
app.secret_key = FLASK_SECRET_KEY


# ── Security Headers ───────────────────────────────────────────────────────
@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"]         = "DENY"
    response.headers["X-XSS-Protection"]        = "1; mode=block"
    return response


def _er_to_dict(er: verify_engine.EventVerificationResult) -> dict:
    """Format an EventVerificationResult into an alert dict."""
    return {
        "type":          er.state.value,
        "event_id":      er.event_id,
        "sequence":      er.sequence,
        "expected_hash": er.expected_hash,
        "actual_hash":   er.actual_hash,
        "batch_id":      er.batch_id,
        "merkle_root":   er.merkle_root,
        "message":       er.message,
        "timestamp":     datetime.now(timezone.utc).isoformat(),
        "status":        "ACTIVE",
    }


# ── API Routes ─────────────────────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    """
    System status for dashboard polling representing CURRENT verification.
    GREEN = current data matches immutable blockchain commitment.
    RED   = current integrity violation exists.
    Historical alerts remain in database but do NOT force RED if data is clean.
    """
    case_id = get_current_case_id()
    chain_status = blockchain.blockchain_status()
    mongo_ok     = alert_store.is_mongodb_available()

    getter = LocalLogGetter()
    events = getter.fetch_events(case_id)

    stats = {
        "total":      len(events),
        "verified":   0,
        "modified":   0,
        "deleted":    0,
        "unexpected": 0,
        "reordered":  0,
    }
    active_violations = []
    latest_alert = None
    status_reason = ""
    current_batch_id = "None"
    integrity = "NO_DATA"

    # 1. Check Device 1 connection first
    device1_connected = chain_status.get("device1", {}).get("connected", False)
    if not device1_connected:
        integrity = "BLOCKCHAIN_ERROR"
        status_reason = "Blockchain Verification Unavailable: Unable to connect to Device 1."
    else:
        # 2. Query batches directly from blockchain
        try:
            onchain_batch_ids = blockchain.get_case_batches(case_id)
        except Exception as e:
            integrity = "BLOCKCHAIN_ERROR"
            status_reason = f"Blockchain Verification Unavailable: {e}"
            onchain_batch_ids = []

        if integrity != "BLOCKCHAIN_ERROR":
            if not onchain_batch_ids:
                if not events:
                    integrity = "NO_DATA"
                    status_reason = "No Data: No log events or blockchain commitments found."
                else:
                    integrity = "MISSING_COMMITMENT"
                    status_reason = f"No Trusted Commitment: No blockchain batch exists for {case_id}."
            else:
                current_batch_id = onchain_batch_ids[-1]
                batch_states = []

                for batch_id in onchain_batch_ids:
                    on_chain_b = blockchain.get_batch_on_chain(case_id, batch_id)
                    if on_chain_b:
                        committed_ids = set(on_chain_b.get("event_ids", []))
                        committed_seqs = set(on_chain_b.get("event_sequences", []))
                        batch_events = [e for e in events if e.get("event_id") in committed_ids or e.get("sequence") in committed_seqs]
                        if not batch_events and events:
                            batch_events = events
                    else:
                        batch_events = events

                    res = verify_engine.verify_batch(case_id, batch_id, batch_events)
                    batch_states.append(res.state)

                    for er in res.event_results:
                        er_val = getattr(er.state, "value", str(er.state))
                        if er_val == "GREEN":
                            stats["verified"] += 1
                        elif er_val == "MODIFIED":
                            stats["modified"] += 1
                            active_violations.append(_er_to_dict(er))
                        elif er_val == "DELETED":
                            stats["deleted"] += 1
                            active_violations.append(_er_to_dict(er))
                        elif er_val == "UNEXPECTED":
                            stats["unexpected"] += 1
                            active_violations.append(_er_to_dict(er))
                        elif er_val == "REORDERED":
                            stats["reordered"] += 1
                            active_violations.append(_er_to_dict(er))
                        elif er_val == "MERKLE_MISMATCH":
                            active_violations.append(_er_to_dict(er))

                # Derive current integrity state
                if any(s == verify_engine.VerificationState.BLOCKCHAIN_ERROR for s in batch_states):
                    integrity = "BLOCKCHAIN_ERROR"
                    status_reason = "Blockchain error occurred during batch verification."
                elif any(s == verify_engine.VerificationState.MISSING_COMMITMENT for s in batch_states):
                    integrity = "MISSING_COMMITMENT"
                    status_reason = f"No Trusted Commitment: Batch commitment missing for case {case_id}."
                elif any(s in (
                    verify_engine.VerificationState.MODIFIED,
                    verify_engine.VerificationState.DELETED,
                    verify_engine.VerificationState.UNEXPECTED,
                    verify_engine.VerificationState.REORDERED,
                    verify_engine.VerificationState.MERKLE_MISMATCH,
                ) for s in batch_states):
                    integrity = "RED"
                    status_reason = "Integrity Violation: Tampering detected against immutable blockchain commitment."
                elif all(s == verify_engine.VerificationState.GREEN for s in batch_states) and stats["verified"] > 0:
                    integrity = "GREEN"
                    status_reason = "Integrity Verified: Current data matches immutable blockchain commitment."
                elif not events:
                    integrity = "NO_DATA"
                    status_reason = "No Data."
                else:
                    integrity = "MISSING_COMMITMENT"
                    status_reason = f"No Trusted Commitment for case {case_id}."

    # Determine latest alert
    latest_alert = active_violations[0] if active_violations else None
    if not latest_alert:
        hist = alert_store.get_case_alerts(case_id, limit=1)
        if hist:
            h = hist[0]
            latest_alert = {
                "type":          h.get("alert_type"),
                "event_id":      h.get("event_id"),
                "sequence":      h.get("sequence"),
                "expected_hash": h.get("expected_hash", ""),
                "actual_hash":   h.get("actual_hash", ""),
                "batch_id":      h.get("batch_id", ""),
                "message":       h.get("extra", {}).get("message", h.get("message", f"{h.get('alert_type')} detected")),
                "timestamp":     h.get("timestamp"),
                "status":        h.get("status", "HISTORICAL"),
            }

    alert_stats = alert_store.get_alert_stats(case_id)

    return jsonify({
        "blockchain":        chain_status,
        "mongodb":           {"available": mongo_ok},
        "integrity":         integrity,
        "status_reason":     status_reason,
        "case_id":           case_id,
        "current_batch":     current_batch_id,
        "contract":          CONTRACT_ADDRESS or "Not deployed",
        "statistics":        stats,
        "alert_stats":       alert_stats,
        "active_violations": active_violations,
        "latest_alert":      latest_alert,
        "timestamp":         datetime.now(timezone.utc).isoformat(),
    })


@app.route("/api/alerts")
def api_alerts():
    """Get recent alerts for the case."""
    case_id = request.args.get("case_id", get_current_case_id())
    limit   = min(int(request.args.get("limit", 50)), 200)
    alerts  = alert_store.get_case_alerts(case_id, limit=limit)
    return jsonify({"alerts": alerts, "count": len(alerts)})


@app.route("/api/ingest", methods=["POST"])
def api_ingest():
    """
    POST /api/ingest
    Header: X-API-Key: <INGEST_API_TOKEN>
    Body: {"case_id": "...", "events": [...]}
    Cloud adapter integration boundary.
    Validates schema, canonicalizes, SHA-256 hashes, Merkle batches, anchors, verifies.
    """
    # ── Authentication Check ──────────────────────────────────────
    if INGEST_API_TOKEN:
        auth_token = request.headers.get("X-API-Key") or request.headers.get("Authorization", "").replace("Bearer ", "").strip()
        if not auth_token or auth_token != INGEST_API_TOKEN:
            return jsonify({
                "success": False,
                "error": "Unauthorized: Missing or invalid X-API-Key header",
            }), 401

    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"success": False, "error": "Invalid JSON body"}), 400

    events = data.get("events")
    if not events or not isinstance(events, list):
        return jsonify({"success": False, "error": "Missing or invalid 'events' array"}), 400

    case_id = data.get("case_id", get_current_case_id())
    for e in events:
        if not isinstance(e, dict):
            return jsonify({"success": False, "error": "Each event must be a dict"}), 400
        e.setdefault("case_id", case_id)

    try:
        result = ingest_events(events)
        return jsonify({"success": True, **result})
    except PipelineError as e:
        return jsonify({"success": False, "error": str(e)}), 422
    except Exception as e:
        logger.exception("Unexpected ingestion error")
        return jsonify({"success": False, "error": "Internal error"}), 500


@app.route("/api/verify", methods=["POST"])
def api_verify():
    """
    POST /api/verify
    Body: {"case_id": "..."}
    Verifies CURRENT case data directly against blockchain commitments.
    """
    data    = request.get_json(force=True, silent=True) or {}
    case_id = data.get("case_id", get_current_case_id())

    getter  = LocalLogGetter()
    events  = getter.fetch_events(case_id)

    w3 = blockchain.get_w3(1)
    if not w3.is_connected():
        return jsonify({
            "success": False,
            "case_id": case_id,
            "overall_state": "BLOCKCHAIN_ERROR",
            "error": f"Cannot connect to Device 1 blockchain node at {DEVICE1_RPC}",
        }), 503

    try:
        onchain_batch_ids = blockchain.get_case_batches(case_id)
    except Exception as e:
        return jsonify({
            "success": False,
            "case_id": case_id,
            "overall_state": "BLOCKCHAIN_ERROR",
            "error": f"Blockchain query error: {e}",
        }), 503

    if not onchain_batch_ids:
        return jsonify({
            "success": False,
            "case_id": case_id,
            "overall_state": "MISSING_COMMITMENT",
            "error": f"No blockchain batch commitments found for {case_id}. Run ingestion first.",
        }), 404

    results_by_batch = []
    for batch_id in onchain_batch_ids:
        on_chain_b = blockchain.get_batch_on_chain(case_id, batch_id)
        if on_chain_b:
            committed_ids = set(on_chain_b.get("event_ids", []))
            committed_seqs = set(on_chain_b.get("event_sequences", []))
            batch_events = [e for e in events if e.get("event_id") in committed_ids or e.get("sequence") in committed_seqs]
            if not batch_events and events:
                batch_events = events
        else:
            batch_events = events

        result = verify_engine.verify_batch(case_id, batch_id, batch_events)
        results_by_batch.append({
            "batch_id":    batch_id,
            "state":       result.state.value,
            "entry_count": result.entry_count,
            "merkle_root": result.merkle_root,
            "summary":     result.summary,
            "events": [
                {
                    "event_id":      r.event_id,
                    "sequence":      r.sequence,
                    "state":         r.state.value,
                    "expected_hash": r.expected_hash[:16] + "..." if r.expected_hash else "",
                    "actual_hash":   r.actual_hash[:16] + "..." if r.actual_hash else "",
                    "message":       r.message,
                }
                for r in result.event_results
                if r.state.value != "GREEN"
            ],
        })

    all_states = [r["state"] for r in results_by_batch]
    if any(s == "BLOCKCHAIN_ERROR" for s in all_states):
        overall = "BLOCKCHAIN_ERROR"
    elif any(s == "MISSING_COMMITMENT" for s in all_states):
        overall = "MISSING_COMMITMENT"
    elif any(s in ("MODIFIED", "DELETED", "UNEXPECTED", "REORDERED", "MERKLE_MISMATCH") for s in all_states):
        overall = "RED"
    elif all(s == "GREEN" for s in all_states) and all_states:
        overall = "GREEN"
    else:
        overall = all_states[0] if all_states else "NO_DATA"

    return jsonify({
        "success":        True,
        "case_id":        case_id,
        "overall_state":  overall,
        "batch_results":  results_by_batch,
    })


@app.route("/api/demo/reset", methods=["POST"])
def api_demo_reset():
    """
    Reset demo with append-only blockchain:
    1. Preserves blockchain
    2. Clears demo MongoDB state for previous runs
    3. Generates NEW unique demo case ID
    4. Generates fresh events
    5. Confirms blockchain connection
    6. Ingests and anchors new batch with unique batch ID (verifies receipt.status == 1)
    7. Verifies clean state against blockchain -> returns GREEN
    Fails with HTTP 500/503 if blockchain anchoring or retrieval fails.
    """
    from demo.generate_logs import generate_events
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    new_case_id = f"CASE-DEMO-{now_str}"

    # Check blockchain connection
    w3 = blockchain.get_w3(1)
    if not w3.is_connected():
        return jsonify({
            "success": False,
            "stage": "Blockchain connection",
            "error": f"Cannot connect to Device 1 blockchain node at {DEVICE1_RPC}",
        }), 503

    set_current_case_id(new_case_id)
    cleared_alerts = alert_store.clear_demo_alerts()
    cleared_batches = alert_store.clear_batch_metadata()

    events = generate_events(case_id=new_case_id, count=100)
    getter = LocalLogGetter()
    getter.write_events(new_case_id, events)

    # Ingest & Anchor new batch
    try:
        ingest_res = ingest_events(events)
        batch_id = ingest_res.get("batch_id")
    except Exception as e:
        return jsonify({
            "success": False,
            "stage": "Anchor transaction",
            "error": str(e),
        }), 500

    # Retrieve batch directly from blockchain
    on_chain = blockchain.get_batch_on_chain(new_case_id, batch_id)
    if not on_chain:
        return jsonify({
            "success": False,
            "stage": "Batch retrieval",
            "error": f"Batch {batch_id} could not be retrieved from blockchain after anchoring",
        }), 500

    # Verify directly against blockchain
    vres = verify_engine.verify_batch(new_case_id, batch_id, events)
    if vres.state != verify_engine.VerificationState.GREEN:
        return jsonify({
            "success": False,
            "stage": "Verification",
            "error": f"Verification state is {vres.state.value}",
        }), 500

    return jsonify({
        "success":          True,
        "case_id":          new_case_id,
        "batch_id":         batch_id,
        "cleared_alerts":   cleared_alerts,
        "cleared_batches":  cleared_batches,
        "events_generated": len(events),
        "status":           "ANCHORED",
        "verification":     "GREEN",
        "message":          f"Demo reset successfully with fresh case {new_case_id}.",
    })


# ── Page Routes ────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    return render_template("dashboard.html")


# ── Entry Point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=FLASK_PORT,
        debug=FLASK_DEBUG,
        use_reloader=False,
    )
