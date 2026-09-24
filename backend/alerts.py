"""
LogChain - MongoDB Alert Storage
Clean alert document schema with indexes.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from backend.config import MONGODB_URI, MONGODB_DB_NAME

logger = logging.getLogger(__name__)

_client: Optional[MongoClient] = None
_db = None


def _get_db():
    global _client, _db
    if _client is None:
        _client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=3000)
        _db = _client[MONGODB_DB_NAME]
        _ensure_indexes(_db)
    return _db


def _ensure_indexes(db):
    """Create indexes for performance and uniqueness."""
    alerts = db.alerts
    # Compound index: one alert per (case_id, batch_id, event_id, alert_type)
    alerts.create_index(
        [("case_id", ASCENDING), ("batch_id", ASCENDING),
         ("event_id", ASCENDING), ("alert_type", ASCENDING)],
        unique=True,
        name="unique_alert"
    )
    alerts.create_index([("case_id", ASCENDING), ("timestamp", DESCENDING)])
    alerts.create_index([("alert_type", ASCENDING)])
    alerts.create_index([("severity", ASCENDING)])

    # Batch metadata collection
    batches = db.batches
    batches.create_index(
        [("case_id", ASCENDING), ("batch_id", ASCENDING)],
        unique=True, name="unique_batch"
    )

    # Event metadata collection
    events = db.events
    events.create_index(
        [("case_id", ASCENDING), ("event_id", ASCENDING)],
        unique=True, name="unique_event"
    )
    events.create_index([("case_id", ASCENDING), ("sequence", ASCENDING)])


# ── Alert Documents ─────────────────────────────────────────────────────────

def save_alert(
    case_id: str,
    batch_id: str,
    event_id: str,
    sequence: int,
    alert_type: str,          # MODIFIED | DELETED | UNEXPECTED | REORDERED
    severity: str,            # CRITICAL | HIGH | MEDIUM | LOW
    expected_hash: str = "",
    actual_hash:   str = "",
    merkle_root:   str = "",
    tx_hash:       str = "",
    extra: dict = None,
) -> Optional[str]:
    """
    Save an alert document. Deduplicates by (case_id, batch_id, event_id, alert_type).
    Returns inserted document ID or None if duplicate (no update on dup).
    """
    db = _get_db()
    doc = {
        "case_id":       case_id,
        "batch_id":      batch_id,
        "event_id":      event_id,
        "sequence":      sequence,
        "alert_type":    alert_type,
        "severity":      severity,
        "expected_hash": expected_hash,
        "actual_hash":   actual_hash,
        "merkle_root":   merkle_root,
        "transaction_hash": tx_hash,
        "timestamp":     datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        doc.update(extra)
    try:
        result = db.alerts.insert_one(doc)
        logger.info(f"Alert saved: {alert_type} for {event_id}")
        return str(result.inserted_id)
    except DuplicateKeyError:
        logger.debug(f"Duplicate alert skipped: {alert_type} {event_id}")
        return None
    except Exception as e:
        logger.error(f"save_alert error: {e}")
        return None


def get_alerts(limit: int = 100, alert_type: str = None) -> list[dict]:
    """Get recent alerts, optionally filtered by type."""
    db = _get_db()
    query = {}
    if alert_type:
        query["alert_type"] = alert_type
    cursor = db.alerts.find(query, {"_id": 0}).sort("timestamp", DESCENDING).limit(limit)
    return list(cursor)


def get_case_alerts(case_id: str, limit: int = 200) -> list[dict]:
    """Get all alerts for a specific case."""
    db = _get_db()
    cursor = db.alerts.find(
        {"case_id": case_id}, {"_id": 0}
    ).sort("timestamp", DESCENDING).limit(limit)
    return list(cursor)


def clear_demo_alerts(case_id: str = None) -> int:
    """
    Clear alerts for demo reset. If case_id is given, only that case is cleared.
    Returns number of deleted documents.
    """
    db = _get_db()
    query = {"case_id": case_id} if case_id else {}
    result = db.alerts.delete_many(query)
    logger.info(f"Cleared {result.deleted_count} alerts")
    return result.deleted_count


# ── Batch Metadata ──────────────────────────────────────────────────────────

def save_batch_metadata(
    case_id:     str,
    batch_id:    str,
    merkle_root: str,
    entry_count: int,
    tx_hash:     str,
    event_hashes: list[str],
    event_ids:    list[str],
    sequences:    list[int],
) -> Optional[str]:
    """Persist batch metadata locally (in addition to blockchain anchor)."""
    db = _get_db()
    doc = {
        "case_id":      case_id,
        "batch_id":     batch_id,
        "merkle_root":  merkle_root,
        "entry_count":  entry_count,
        "tx_hash":      tx_hash,
        "event_hashes": event_hashes,
        "event_ids":    event_ids,
        "sequences":    sequences,
        "anchored_at":  datetime.now(timezone.utc).isoformat(),
    }
    try:
        result = db.batches.insert_one(doc)
        return str(result.inserted_id)
    except DuplicateKeyError:
        logger.debug(f"Batch metadata already exists: {batch_id}")
        return None
    except Exception as e:
        logger.error(f"save_batch_metadata error: {e}")
        return None


def get_batch_metadata(case_id: str, batch_id: str) -> Optional[dict]:
    """Retrieve locally stored batch metadata."""
    db = _get_db()
    return db.batches.find_one(
        {"case_id": case_id, "batch_id": batch_id}, {"_id": 0}
    )


def get_case_batches_local(case_id: str) -> list[dict]:
    """Get all locally stored batches for a case."""
    db = _get_db()
    return list(db.batches.find({"case_id": case_id}, {"_id": 0}).sort("anchored_at", 1))


def clear_batch_metadata(case_id: str = None) -> int:
    """Clear batch metadata for demo reset."""
    db = _get_db()
    query = {"case_id": case_id} if case_id else {}
    result = db.batches.delete_many(query)
    return result.deleted_count


# ── Statistics ──────────────────────────────────────────────────────────────

def get_alert_stats(case_id: str = None) -> dict:
    """Get alert count statistics by type."""
    db = _get_db()
    query = {"case_id": case_id} if case_id else {}
    pipeline = [
        {"$match": query},
        {"$group": {"_id": "$alert_type", "count": {"$sum": 1}}},
    ]
    result = list(db.alerts.aggregate(pipeline))
    stats = {
        "MODIFIED":    0,
        "DELETED":     0,
        "UNEXPECTED":  0,
        "REORDERED":   0,
        "total_alerts": 0,
    }
    for r in result:
        key = r["_id"]
        if key in stats:
            stats[key] = r["count"]
        stats["total_alerts"] += r["count"]
    return stats


def is_mongodb_available() -> bool:
    """Check if MongoDB is reachable."""
    try:
        _get_db()
        _client.server_info()
        return True
    except Exception:
        return False
