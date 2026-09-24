"""
LogChain - Azure Activity Log Getter (STUB)
============================================================
FOR MY FRIEND TO IMPLEMENT
============================================================

Instructions:
1. Fill in the TODO sections below.
2. Return normalized events matching the schema in adapters/base.py.
3. Do NOT modify anything in backend/ or contracts/.
4. See docs/FRIEND_INTEGRATION.md for full instructions.

Azure Activity Log event → Normalized event mapping:
    id               → event_id (last segment)
    "azure"          → provider
    operationName    → service
    resourceType     → source
    case_id          → from parameter
    sequence         → assign sequential integer (sort by eventTimestamp)
    eventTimestamp   → timestamp (ISO-8601 UTC)
    operationName    → message
"""
import logging
from typing import Optional

from adapters.base import LogGetter

logger = logging.getLogger(__name__)


class AzureLogGetter(LogGetter):
    """
    Fetches Activity Log events from Azure Monitor and returns normalized events.

    FRIEND: You only need to implement:
      - __init__: set up your Azure credentials/client
      - fetch_events: fetch from Azure Monitor and normalize
      - health_check: verify Azure connection

    DO NOT modify:
      - adapters/base.py
      - backend/hashing.py
      - backend/canonical.py
      - backend/merkle.py
      - backend/blockchain.py
      - backend/verifier.py
      - backend/pipeline.py
    """

    def __init__(
        self,
        subscription_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
    ):
        # TODO: Initialize Azure SDK client
        # from azure.monitor.query import LogsQueryClient
        # from azure.identity import ClientSecretCredential
        # credential = ClientSecretCredential(tenant_id, client_id, client_secret)
        # self.client = LogsQueryClient(credential)
        self.subscription_id = subscription_id
        logger.warning("AzureLogGetter: stub implementation. Implement fetch_events().")

    def fetch_events(self, case_id: str) -> list[dict]:
        """
        TODO: Implement this method.

        1. Query Azure Monitor Activity Logs for the subscription
        2. Sort events by eventTimestamp ascending
        3. Convert each event to normalized format using self.make_normalized_event()
        4. Return the list

        Example conversion:
            raw_event = {
                "id": "/subscriptions/xxx/resourceGroups/rg1/providers/.../eventhub/myevent",
                "eventTimestamp": "2026-09-25T03:20:00.000Z",
                "operationName": {"value": "Microsoft.Storage/storageAccounts/write"},
                "resourceType": {"value": "Microsoft.Storage/storageAccounts"},
                "caller": "admin@example.com",
                ...
            }

            normalized = self.make_normalized_event(
                event_id  = raw_event["id"].split("/")[-1],
                provider  = "azure",
                service   = raw_event["operationName"]["value"].split("/")[1].lower(),
                source    = "activitylog",
                case_id   = case_id,
                sequence  = <1-based index>,
                timestamp = raw_event["eventTimestamp"],
                message   = f"{raw_event['operationName']['value']} by {raw_event.get('caller', 'unknown')}",
            )
        """
        raise NotImplementedError(
            "AzureLogGetter.fetch_events() not yet implemented. "
            "See docs/FRIEND_INTEGRATION.md for instructions."
        )

    def health_check(self) -> dict:
        """
        TODO: Verify Azure Monitor connection.

        Example:
            try:
                # list subscriptions or similar lightweight call
                return {"status": "ok", "provider": "azure", "message": "Connected"}
            except Exception as e:
                return {"status": "error", "provider": "azure", "message": str(e)}
        """
        return {
            "status":          "stub",
            "provider":        "azure",
            "message":         "AzureLogGetter not yet implemented",
            "subscription_id": self.subscription_id,
        }
