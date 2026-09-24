"""
LogChain - Flask Dashboard & API
Zero-Trust Cross-Cloud Log Integrity System
Judge-friendly dashboard with integrity visualization.
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template, request, abort
import markupsafe

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import (
    FLASK_SECRET_KEY, FLASK_DEBUG, FLASK_PORT,
    DEMO_CASE_ID, CONTRACT_ADDRESS,
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

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = FLASK_SECRET_KEY

# ── Security Headers ───────────────────────────────────────────────────────
@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"]         = "DENY"
    response.headers["X-XSS-Protection"]        = "1; mode=block"
    return response


# ── API Routes ─────────────────────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    """System status for dashboard polling."""
    chain_status = blockchain.blockchain_status()
    alert_stats  = alert_store.get_alert_stats(DEMO_CASE_ID)
    mongo_ok     = alert_store.is_mongodb_available()

    # Determine overall integrity state
    alerts = alert_store.get_case_alerts(DEMO_CASE_ID, limit=1)
    integrity = "GREEN" if not alerts else "RED"

    return jsonify({
        "blockchain":  chain_status,
        "mongodb":     {"available": mongo_ok},
        "integrity":   integrity,
        "case_id":     DEMO_CASE_ID,
        "contract":    CONTRACT_ADDRESS or "Not deployed",
        "alert_stats": alert_stats,
        "timestamp":   datetime.now(timezone.utc).isoformat(),
    })


@app.route("/api/alerts")
def api_alerts():
    """Get recent alerts."""
    case_id   = request.args.get("case_id", DEMO_CASE_ID)
    limit     = min(int(request.args.get("limit", 50)), 200)
    alerts    = alert_store.get_case_alerts(case_id, limit=limit)
    return jsonify({"alerts": alerts, "count": len(alerts)})


@app.route("/api/ingest", methods=["POST"])
def api_ingest():
    """
    POST /api/ingest
    Body: {"case_id": "CASE-001", "events": [...]}

    This is the clean integration point for cloud adapters.
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"success": False, "error": "Invalid JSON body"}), 400

    events = data.get("events")
    if not events or not isinstance(events, list):
        return jsonify({"success": False, "error": "Missing or invalid 'events' array"}), 400

    case_id = data.get("case_id", DEMO_CASE_ID)
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
    Body: {"case_id": "CASE-001"}
    Runs verification and returns results.
    """
    data    = request.get_json(force=True, silent=True) or {}
    case_id = data.get("case_id", DEMO_CASE_ID)

    getter  = LocalLogGetter()
    events  = getter.fetch_events(case_id)
    batches = alert_store.get_case_batches_local(case_id)

    if not batches:
        return jsonify({
            "success": False,
            "error":   f"No local batch metadata found for {case_id}. Run ingestion first.",
        }), 404

    results_by_batch = []
    for batch_meta in batches:
        batch_id = batch_meta["batch_id"]
        seq_list = batch_meta.get("sequences", [])
        batch_events = [e for e in events if e.get("sequence") in seq_list]

        result = verify_engine.verify_batch(case_id, batch_id, batch_events)
        results_by_batch.append({
            "batch_id":    batch_id,
            "state":       result.state.value,
            "entry_count": result.entry_count,
            "summary":     result.summary,
            "events": [
                {
                    "event_id":     r.event_id,
                    "sequence":     r.sequence,
                    "state":        r.state.value,
                    "expected_hash": r.expected_hash[:16] + "..." if r.expected_hash else "",
                    "actual_hash":   r.actual_hash[:16] + "..." if r.actual_hash else "",
                    "message":      r.message,
                }
                for r in result.event_results
                if r.state.value != "GREEN"  # only violations
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
    """Reset demo state (clears alerts, regenerates events)."""
    case_id = request.get_json(force=True, silent=True) or {}
    case_id = case_id.get("case_id", DEMO_CASE_ID)

    cleared_alerts = alert_store.clear_demo_alerts(case_id)
    cleared_batches = alert_store.clear_batch_metadata(case_id)

    # Regenerate events
    from demo.generate_logs import generate_events
    events = generate_events(case_id=case_id, count=100)
    getter = LocalLogGetter()
    getter.write_events(case_id, events)

    return jsonify({
        "success":        True,
        "cleared_alerts": cleared_alerts,
        "cleared_batches": cleared_batches,
        "events_generated": len(events),
        "message":        f"Demo reset for {case_id}. Run ingestion to re-anchor.",
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
