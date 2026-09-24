"""
LogChain - Abstract Adapter Base
All cloud/local log getters must implement this interface.

Your adapter should:
1. Inherit from LogGetter
2. Implement fetch_events(case_id) → list[dict]
3. Implement health_check() → dict
4. Return normalized events (see NORMALIZED_EVENT_SCHEMA)

The adapter must NEVER directly write to blockchain.
"""
from abc import ABC, abstractmethod
from typing import Optional

# Canonical normalized event schema
NORMALIZED_EVENT_SCHEMA = {
    "event_id":  str,   # required, unique within provider
    "provider":  str,   # "aws" | "azure" | "local" | ...
    "service":   str,   # "cloudtrail" | "activitylog" | ...
    "source":    str,   # source identifier
    "case_id":   str,   # investigation case ID
    "sequence":  int,   # 1-based ordering integer
    "timestamp": str,   # ISO-8601 UTC string e.g. "2026-09-25T03:20:00Z"
    "message":   str,   # human-readable event description
}


class LogGetter(ABC):
    """
    Abstract base class for all log source adapters.

    Implement this class to add a new cloud provider or log source.
    The core pipeline will call fetch_events() and health_check().
    """

    @abstractmethod
    def fetch_events(self, case_id: str) -> list[dict]:
        """
        Fetch and return normalized log events for the given case.

        Args:
            case_id: Investigation case identifier (e.g. "CASE-001")

        Returns:
            List of normalized event dicts matching NORMALIZED_EVENT_SCHEMA.
            Must contain at minimum the required fields.
            Must be sorted by sequence ascending.

        Raises:
            NotImplementedError: If not overridden.
            ConnectionError: If the source is unavailable.
            ValueError: If events cannot be normalized.
        """
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> dict:
        """
        Check if the log source is reachable and functional.

        Returns:
            {
                "status": "ok" | "error",
                "provider": str,
                "message": str,
                "latency_ms": float (optional)
            }
        """
        raise NotImplementedError

    def make_normalized_event(
        self,
        event_id:  str,
        provider:  str,
        service:   str,
        source:    str,
        case_id:   str,
        sequence:  int,
        timestamp: str,
        message:   str,
        **extra,
    ) -> dict:
        """
        Helper: Build a normalized event dict.
        Extra kwargs are ignored (not included in canonical hash).
        """
        return {
            "event_id":  event_id,
            "provider":  provider,
            "service":   service,
            "source":    source,
            "case_id":   case_id,
            "sequence":  sequence,
            "timestamp": timestamp,
            "message":   message,
        }
