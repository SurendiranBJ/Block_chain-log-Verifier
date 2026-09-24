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
    batches = alert_store.get_case_batches_local(case_id)

    # Check on-chain if local empty
    if not batches:
        onchain_batch_ids = blockchain.get_case_batches(case_id)
        batches = [{"batch_id": bid} for bid in onchain_batch_ids]

    current_batch_id = batches[-1]["batch_id"] if batches else "None"
    integrity = "GREEN"
    active_violations = []

    stats = {
        "total":      len(events),
        "verified":   0,
        "modified":   0,
        "deleted":    0,
        "unexpected": 0,
        "reordered":  0,
    }

    if batches:
        for batch_meta in batches:
            batch_id = batch_meta["batch_id"]
            seq_list = batch_meta.get("sequences", [])
            if seq_list:
                batch_events = [e for e in events if e.get("sequence") in seq_list]
            else:
                batch_events = events

            res = verify_engine.verify_batch(case_id, batch_id, batch_events)
            state_val = getattr(res.state, "value", str(res.state))
            if state_val != "GREEN":
                integrity = "RED"

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
    Body: {"case_id": "...", "events": [...]}
    Cloud adapter integration boundary.
    Validates schema, canonicalizes, SHA-256 hashes, Merkle batches, anchors, verifies.
    """
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
    batches = alert_store.get_case_batches_local(case_id)

    if not batches:
        onchain_batch_ids = blockchain.get_case_batches(case_id)
        batches = [{"batch_id": bid} for bid in onchain_batch_ids]

    if not batches:
        return jsonify({
            "success": False,
            "error":   f"No batch metadata found on blockchain or local for {case_id}. Run ingestion first.",
        }), 404

    results_by_batch = []
    for batch_meta in batches:
        batch_id = batch_meta["batch_id"]
        seq_list = batch_meta.get("sequences", [])
        batch_events = [e for e in events if e.get("sequence") in seq_list] if seq_list else events

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

    overall = "GREEN"
    for r in results_by_batch:
        if r["state"] != "GREEN":
            overall = r["state"]
            break

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
    5. Ingests and anchors new batch with unique batch ID
    6. Verifies clean state -> dashboard GREEN
    """
    from demo.generate_logs import generate_events
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    new_case_id = f"CASE-DEMO-{now_str}"

    set_current_case_id(new_case_id)
    cleared_alerts = alert_store.clear_demo_alerts()
    cleared_batches = alert_store.clear_batch_metadata()

    events = generate_events(case_id=new_case_id, count=100)
    getter = LocalLogGetter()
    getter.write_events(new_case_id, events)

    # Ingest & Anchor new batch
    ingest_res = ingest_events(events)

    return jsonify({
        "success":          True,
        "case_id":          new_case_id,
        "batch_id":         ingest_res.get("batch_id"),
        "cleared_alerts":   cleared_alerts,
        "cleared_batches":  cleared_batches,
        "events_generated": len(events),
        "status":           ingest_res.get("status"),
        "verification":     ingest_res.get("verification"),
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
