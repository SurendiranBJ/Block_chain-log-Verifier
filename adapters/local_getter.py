"""
LogChain - Local Log Getter
Reads demo events from local JSON files.
Used for hackathon demo and testing without cloud credentials.
"""
import json
import logging
import time
from pathlib import Path
from typing import Optional

from adapters.base import LogGetter
from backend.config import DEMO_LOG_DIR, DEMO_CASE_ID

logger = logging.getLogger(__name__)


class LocalLogGetter(LogGetter):
    """
    Reads normalized events from local JSON files.

    File format: demo/sample_logs/CASE-001.json
    Each file contains a JSON array of normalized events.

    This adapter is the reference implementation and demo source.
    It does NOT know anything about blockchain, Merkle, or contracts.
    """

    def __init__(self, log_dir: Optional[str] = None):
        self.log_dir = Path(log_dir or DEMO_LOG_DIR)

    def _case_file(self, case_id: str) -> Path:
        return self.log_dir / f"{case_id}.json"

    def fetch_events(self, case_id: str) -> list[dict]:
        """
        Load normalized events for a case from local JSON file.

        Returns events sorted by sequence ascending.
        """
        case_file = self._case_file(case_id)
        if not case_file.exists():
            logger.warning(f"Case file not found: {case_file}")
            return []

        with open(case_file, "r", encoding="utf-8") as f:
            events = json.load(f)

        if not isinstance(events, list):
            raise ValueError(f"Case file must contain a JSON array: {case_file}")

        # Sort by sequence to guarantee ordering
        events_sorted = sorted(events, key=lambda e: e.get("sequence", 0))
        logger.info(f"Loaded {len(events_sorted)} events for {case_id}")
        return events_sorted

    def health_check(self) -> dict:
        """Check if the local log directory exists and is readable."""
        t0 = time.monotonic()
        try:
            if not self.log_dir.exists():
                return {
                    "status":   "error",
                    "provider": "local",
                    "message":  f"Log directory not found: {self.log_dir}",
                }
            files = list(self.log_dir.glob("*.json"))
            latency = (time.monotonic() - t0) * 1000
            return {
                "status":     "ok",
                "provider":   "local",
                "message":    f"Found {len(files)} case file(s)",
                "latency_ms": round(latency, 2),
                "log_dir":    str(self.log_dir),
            }
        except Exception as e:
            return {
                "status":   "error",
                "provider": "local",
                "message":  str(e),
            }

    def list_cases(self) -> list[str]:
        """List all case IDs available locally."""
        if not self.log_dir.exists():
            return []
        return [f.stem for f in self.log_dir.glob("*.json")]

    def write_events(self, case_id: str, events: list[dict]) -> None:
        """
        Write events to local case file (used by demo generator and attack scripts).
        """
        self.log_dir.mkdir(parents=True, exist_ok=True)
        case_file = self._case_file(case_id)
        with open(case_file, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=2, ensure_ascii=False)
        logger.info(f"Wrote {len(events)} events to {case_file}")
