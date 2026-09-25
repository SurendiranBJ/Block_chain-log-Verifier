"""
LogChain - Remote Ingestion Test Client
=======================================
Simulates Friend's Laptop posting cloud logs over LAN to Device 1.
Tests authentication, validation, Merkle root computation, and blockchain anchoring.

Usage:
    python scripts/test_remote_ingest.py --url http://127.0.0.1:5000/api/ingest --token lc-hackathon-token-2026
    python scripts/test_remote_ingest.py --url http://192.168.1.100:5000/api/ingest --token YOUR_TOKEN
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from backend.canonical import validate_event, canonicalize_event
from backend.hashing import hash_event


def make_deterministic_events(case_id: str) -> list[dict]:
    return [
        {
            "event_id": f"rem-aws-{case_id}-001",
            "provider": "aws",
            "service": "cloudtrail",
            "source": "cloudtrail",
            "case_id": case_id,
            "sequence": 1,
            "timestamp": "2026-09-25T04:00:00Z",
            "message": "AWS: IAM CreateUser for devops-engineer",
        },
        {
            "event_id": f"rem-aws-{case_id}-002",
            "provider": "aws",
            "service": "s3",
            "source": "cloudtrail",
            "case_id": case_id,
            "sequence": 2,
            "timestamp": "2026-09-25T04:01:00Z",
            "message": "AWS: S3 PutBucketPolicy on finance-records",
        },
        {
            "event_id": f"rem-aws-{case_id}-003",
            "provider": "aws",
            "service": "kms",
            "source": "cloudtrail",
            "case_id": case_id,
            "sequence": 3,
            "timestamp": "2026-09-25T04:02:00Z",
            "message": "AWS: KMS EnableKeyRotation on production-master-key",
        },
    ]


def main():
    parser = argparse.ArgumentParser(description="Test Remote Ingestion from Friend Laptop to Device 1")
    parser.add_argument("--url", default=os.getenv("DEVICE1_INGEST_URL", "http://127.0.0.1:5000/api/ingest"), help="Device 1 /api/ingest endpoint")
    parser.add_argument("--token", default=os.getenv("INGEST_API_TOKEN", "lc-hackathon-token-2026"), help="INGEST_API_TOKEN secret")
    parser.add_argument("--case-id", default="CASE-CLOUD-001", help="Target case identifier")

    args = parser.parse_args()

    print("============================================================")
    print(" LogChain - Remote Ingestion Test (Friend Laptop -> Device 1)")
    print("============================================================")
    print(f"[*] Target Endpoint: {args.url}")
    print(f"[*] Case ID:         {args.case_id}")
    print(f"[*] Auth Token:      {'***' + args.token[-4:] if len(args.token) > 4 else 'PRESENT'}")

    events = make_deterministic_events(args.case_id)

    # 1. Local validation before sending
    for idx, e in enumerate(events, 1):
        err = validate_event(e)
        if err:
            print(f"[FAIL] Local validation failed on event #{idx}: {err}")
            sys.exit(1)

    print(f"[*] Prepared {len(events)} valid normalized events:")
    for e in events:
        h = hash_event(e)
        print(f"    - Seq #{e['sequence']}: {e['event_id']} (SHA-256: {h[:16]}...)")

    payload = json.dumps({"case_id": args.case_id, "events": events}).encode("utf-8")
    req = urllib.request.Request(
        args.url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": args.token,
        },
        method="POST",
    )

    print(f"\n[*] Transmitting payload to Device 1...")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            status_code = resp.status
            body = resp.read().decode("utf-8")
            data = json.loads(body)

            print(f"[+] HTTP Status: {status_code}")
            if data.get("success") or data.get("status") == "ANCHORED":
                print("============================================================")
                print("  [PASS] INGESTION & ANCHORING SUCCESSFUL!")
                print(f"         Batch ID:        {data.get('batch_id')}")
                print(f"         Entry Count:     {data.get('entry_count')}")
                print(f"         Merkle Root:     {data.get('merkle_root')}")
                print(f"         Status:          {data.get('status')}")
                print(f"         Verification:    {data.get('verification')}")
                print(f"         Tx Hash:         {data.get('transaction_hash')}")
                print(f"         Block Number:    #{data.get('block_number')}")
                print("============================================================")
                sys.exit(0)
            else:
                print(f"[FAIL] Ingestion rejected by server: {data.get('error')}")
                sys.exit(1)

    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="ignore")
        print(f"\n[FAIL] HTTP Error {exc.code}: {exc.reason}")
        try:
            err_json = json.loads(err_body)
            print(f"       Details: {err_json.get('error', err_body)}")
        except Exception:
            print(f"       Raw Body: {err_body}")
        sys.exit(1)
    except Exception as exc:
        print(f"\n[FAIL] Network connection error: {exc}")
        print("       Ensure Flask is running on Device 1 and port 5000 is open in firewall.")
        sys.exit(1)


if __name__ == "__main__":
    main()
