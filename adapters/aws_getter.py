"""
LogChain - AWS CloudTrail Log Getter (STUB)
============================================================
FOR MY FRIEND TO IMPLEMENT
============================================================

Instructions:
1. Fill in the TODO sections below.
2. Return normalized events matching the schema in adapters/base.py.
3. Do NOT modify anything in backend/ or contracts/.
4. See docs/FRIEND_INTEGRATION.md for full instructions.

AWS CloudTrail event → Normalized event mapping:
    eventID          → event_id
    "aws"            → provider
    eventSource      → service (e.g. "s3.amazonaws.com" → "s3")
    eventName        → source
    case_id          → from parameter
    sequence         → assign sequential integer (sort by eventTime)
    eventTime        → timestamp (ISO-8601 UTC)
    eventName + user → message
"""
import logging
import time
from typing import Optional

from adapters.base import LogGetter

logger = logging.getLogger(__name__)


class AWSLogGetter(LogGetter):
    """
    Fetches CloudTrail events from AWS and returns normalized events.

    FRIEND: You only need to implement:
      - __init__: set up your AWS credentials/client
      - fetch_events: fetch from CloudTrail and normalize
      - health_check: verify AWS connection

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
        region: str = "us-east-1",
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_session_token: Optional[str] = None,
    ):
        # TODO: Initialize boto3 client
        # import boto3
        # self.client = boto3.client(
        #     "cloudtrail",
        #     region_name=region,
        #     aws_access_key_id=aws_access_key_id,
        #     aws_secret_access_key=aws_secret_access_key,
        #     aws_session_token=aws_session_token,
        # )
        self.region = region
        logger.warning("AWSLogGetter: stub implementation. Implement fetch_events().")

    def fetch_events(self, case_id: str) -> list[dict]:
        """
        TODO: Implement this method.

        1. Call CloudTrail LookupEvents or GetQueryResults
        2. Sort events by eventTime ascending
        3. Convert each event to normalized format using self.make_normalized_event()
        4. Return the list

        Example conversion:
            raw_event = {
                "eventID": "abc-123",
                "eventTime": "2026-09-25T03:20:00Z",
                "eventSource": "s3.amazonaws.com",
                "eventName": "PutObject",
                "userIdentity": {"arn": "arn:aws:iam::123:user/admin"},
                ...
            }

            normalized = self.make_normalized_event(
                event_id  = raw_event["eventID"],
                provider  = "aws",
                service   = raw_event["eventSource"].split(".")[0],
                source    = "cloudtrail",
                case_id   = case_id,
                sequence  = <1-based index>,
                timestamp = raw_event["eventTime"],
                message   = f"{raw_event['eventName']} by {raw_event['userIdentity']['arn']}",
            )
        """
        raise NotImplementedError(
            "AWSLogGetter.fetch_events() not yet implemented. "
            "See docs/FRIEND_INTEGRATION.md for instructions."
        )

    def health_check(self) -> dict:
        """
        TODO: Verify AWS CloudTrail connection.

        Example:
            try:
                self.client.describe_trails()
                return {"status": "ok", "provider": "aws", "message": "Connected", "region": self.region}
            except Exception as e:
                return {"status": "error", "provider": "aws", "message": str(e)}
        """
        return {
            "status":   "stub",
            "provider": "aws",
            "message":  "AWSLogGetter not yet implemented",
            "region":   self.region,
        }
