"""
LogChain - Friend Cloud Adapter Standalone Test Tool
=====================================================
Allows testing cloud log extraction and normalization locally on friend's laptop
WITHOUT requiring:
  - BLOCKCHAIN_PRIVATE_KEY
  - BLOCKCHAIN_ACCOUNT
  - CONTRACT_ADDRESS
  - MongoDB

Usage:
    python scripts/test_cloud_adapter.py --provider local
    python scripts/test_cloud_adapter.py --provider aws --mock
    python scripts/test_cloud_adapter.py --provider azure --mock
    python scripts/test_cloud_adapter.py --provider local --post-url http://192.168.1.100:5000/api/ingest --token YOUR_TOKEN
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from backend.canonical import validate_event, canonicalize_event, REQUIRED_FIELDS
from backend.hashing import hash_event


def generate_mock_cloud_events(provider: str, count: int, case_id: str) -> list[dict]:
    events = []
    for i in range(1, count + 1):
        if provider == "aws":
            events.append({
                "event_id": f"aws-trail-{i:05d}",
                "provider": "aws",
                "service": "iam" if i % 2 == 0 else "s3",
                "source": "cloudtrail",
                "case_id": case_id,
                "sequence": i,
                "timestamp": f"2026-09-25T03:{i:02d}:00Z",
                "message": f"AWS CloudTrail: {'AssumeRole' if i % 2 == 0 else 'GetObject'} by arn:aws:iam::123456789012:user/admin",
            })
        elif provider == "azure":
            events.append({
                "event_id": f"az-act-{i:05d}",
                "provider": "azure",
                "service": "Microsoft.KeyVault" if i % 2 == 0 else "Microsoft.Compute",
                "source": "activity_log",
                "case_id": case_id,
                "sequence": i,
                "timestamp": f"2026-09-25T03:{i:02d}:00Z",
                "message": f"Azure Activity: {'SecretGet' if i % 2 == 0 else 'VirtualMachines/write'} by principal admin@corp.com",
            })
        else:
            events.append({
                "event_id": f"loc-sim-{i:05d}",
                "provider": "local",
                "service": "auth",
                "source": "simulator",
                "case_id": case_id,
                "sequence": i,
                "timestamp": f"2026-09-25T03:{i:02d}:00Z",
                "message": f"Local Simulator: user login success (session {i})",
            })
    return events


def main():
    parser = argparse.ArgumentParser(description="Test Cloud Log Getter & Event Normalization")
    parser.add_argument("--provider", choices=["aws", "azure", "local"], default="local", help="Cloud provider to test")
    parser.add_argument("--case-id", default="CASE-CLOUD-001", help="Demo case ID")
    parser.add_argument("--count", type=int, default=5, help="Number of events to generate/fetch")
    parser.add_argument("--mock", action="store_true", help="Use mock cloud events instead of live API calls")
    parser.add_argument("--post-url", help="Optional Device 1 ingest URL (e.g. http://192.168.1.100:5000/api/ingest)")
    parser.add_argument("--token", default=os.getenv("INGEST_API_TOKEN", ""), help="X-API-Key token for Device 1")

    args = parser.parse_args()

    print("=" * 60)
    print(f" LogChain - Friend Cloud Adapter Test ({args.provider.upper()})")
    print(" (Zero Blockchain Credentials / Zero MongoDB Required)")
    print("=" * 60)

    events = []
    if args.mock or args.provider == "local":
        if args.provider == "local" and not args.mock:
            from adapters.local_getter import LocalLogGetter
            getter = LocalLogGetter()
            events = getter.fetch_events(args.case_id)[:args.count]
        else:
            print(f"[*] Generating {args.count} mock {args.provider.upper()} events...")
            events = generate_mock_cloud_events(args.provider, args.count, args.case_id)
    else:
        # Live provider test
        if args.provider == "aws":
            from adapters.aws_getter import AWSLogGetter
            getter = AWSLogGetter()
            hc = getter.health_check()
            print(f"[*] AWS Health Check: {hc}")
            try:
                events = getter.fetch_events(args.case_id)
            except NotImplementedError:
                print("[!] AWSLogGetter.fetch_events() is a stub. Falling back to mock data...")
                events = generate_mock_cloud_events("aws", args.count, args.case_id)
        elif args.provider == "azure":
            from adapters.azure_getter import AzureLogGetter
            getter = AzureLogGetter()
            hc = getter.health_check()
            print(f"[*] Azure Health Check: {hc}")
            try:
                events = getter.fetch_events(args.case_id)
            except NotImplementedError:
                print("[!] AzureLogGetter.fetch_events() is a stub. Falling back to mock data...")
                events = generate_mock_cloud_events("azure", args.count, args.case_id)

    print(f"\n[+] Total Events Obtained: {len(events)}")

    # 1. Validate Schema
    print("\n[*] Validating Event Normalization Schema...")
    for idx, e in enumerate(events, 1):
        err = validate_event(e)
        if err:
            print(f"  [FAIL] Event #{idx} failed schema validation: {err}")
            sys.exit(1)
    print("  [PASS] All events conform strictly to the required LogChain schema.")

    # 2. Display first 3 normalized events with SHA-256
    print(f"\n[*] Sample Normalized Events (Showing first {min(3, len(events))}):")
    for idx, e in enumerate(events[:3], 1):
        canonical_bytes = canonicalize_event(e)
        event_hash = hash_event(e)
        print(f"\n  --- Event #{idx} (seq: {e['sequence']}, id: {e['event_id']}) ---")
        print(f"      Provider:  {e['provider']} | Service: {e['service']} | Source: {e['source']}")
        print(f"      Timestamp: {e['timestamp']}")
        print(f"      Message:   {e['message']}")
        print(f"      SHA-256:   {event_hash}")

    # 3. Optional POST to Device 1
    if args.post_url:
        print(f"\n[*] Submitting {len(events)} events to Device 1 at {args.post_url}...")
        import urllib.request
        payload = json.dumps({"case_id": args.case_id, "events": events}).encode("utf-8")
        req = urllib.request.Request(
            args.post_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": args.token,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                print(f"  [PASS] Response (HTTP {resp.status}):")
                print(f"         Success:     {resp_data.get('success')}")
                print(f"         Batch ID:    {resp_data.get('batch_id')}")
                print(f"         Merkle Root: {resp_data.get('merkle_root')}")
                print(f"         Anchored:    {resp_data.get('anchored')}")
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="ignore")
            print(f"  [FAIL] HTTP Error {exc.code}: {err_body}")
            sys.exit(1)
        except Exception as exc:
            print(f"  [FAIL] Remote connection failed: {exc}")
            sys.exit(1)

    print("\n============================================================")
    print(" [PASS] Friend Cloud Adapter Test Completed Successfully!")
    print("============================================================")


if __name__ == "__main__":
    main()
