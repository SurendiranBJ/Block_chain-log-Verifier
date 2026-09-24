"""
LogChain - Demo Log Generator
Generates 100 deterministic demo events for CASE-001.
Events use realistic cloud-style actions.
"""
import json
import sys
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import DEMO_CASE_ID, DEMO_LOG_DIR


# Realistic cloud-style event templates
EVENT_TEMPLATES = [
    # Authentication
    ("cloudtrail", "iam",   "ConsoleLogin",           "User {user} performed ConsoleLogin from IP {ip}"),
    ("cloudtrail", "iam",   "AssumeRole",             "User {user} assumed role {role}"),
    ("cloudtrail", "iam",   "CreateUser",             "Admin {user} created IAM user {target}"),
    ("cloudtrail", "iam",   "DeleteUser",             "Admin {user} deleted IAM user {target}"),
    ("cloudtrail", "iam",   "AttachUserPolicy",       "Admin {user} attached policy {policy} to {target}"),
    ("cloudtrail", "iam",   "DetachRolePolicy",       "Admin {user} detached policy {policy} from {role}"),
    ("cloudtrail", "iam",   "CreateAccessKey",        "User {user} created access key for {target}"),
    ("cloudtrail", "iam",   "DeleteAccessKey",        "User {user} deleted access key"),
    # S3
    ("cloudtrail", "s3",    "GetObject",              "User {user} accessed s3://{bucket}/{key}"),
    ("cloudtrail", "s3",    "PutObject",              "User {user} uploaded s3://{bucket}/{key}"),
    ("cloudtrail", "s3",    "DeleteObject",           "User {user} deleted s3://{bucket}/{key}"),
    ("cloudtrail", "s3",    "CreateBucket",           "User {user} created S3 bucket {bucket}"),
    ("cloudtrail", "s3",    "DeleteBucket",           "User {user} deleted S3 bucket {bucket}"),
    ("cloudtrail", "s3",    "PutBucketPolicy",        "User {user} modified bucket policy on {bucket}"),
    # EC2
    ("cloudtrail", "ec2",   "RunInstances",           "User {user} launched EC2 instance {instance}"),
    ("cloudtrail", "ec2",   "TerminateInstances",     "User {user} terminated EC2 instance {instance}"),
    ("cloudtrail", "ec2",   "AuthorizeSecurityGroup", "User {user} modified security group {sg}"),
    ("cloudtrail", "ec2",   "CreateKeyPair",          "User {user} created EC2 key pair"),
    # Lambda
    ("cloudtrail", "lambda","InvokeFunction",         "User {user} invoked Lambda function {func}"),
    ("cloudtrail", "lambda","CreateFunction",         "User {user} deployed Lambda function {func}"),
    ("cloudtrail", "lambda","UpdateFunctionCode",     "User {user} updated Lambda function {func}"),
    # Config
    ("cloudtrail", "config","PutConfigRule",          "Admin {user} created config rule {rule}"),
    ("cloudtrail", "config","DeleteConfigRule",       "Admin {user} deleted config rule {rule}"),
    # CloudWatch
    ("cloudtrail", "cloudwatch", "PutMetricAlarm",   "User {user} created alarm {alarm}"),
    ("cloudtrail", "cloudwatch", "DeleteAlarms",     "User {user} deleted alarm {alarm}"),
]

USERS    = ["admin", "alice", "bob", "carol", "devops", "security-bot", "ci-deploy"]
IPS      = ["10.0.1.5", "10.0.2.12", "172.16.0.4", "192.168.1.100"]
BUCKETS  = ["prod-logs", "dev-artifacts", "backup-store", "audit-data"]
KEYS     = ["logs/2026/09/app.log", "artifacts/build-42.zip", "reports/q3.pdf"]
ROLES    = ["AdminRole", "ReadOnlyRole", "LambdaExecutionRole", "DevOpsRole"]
POLICIES = ["AdministratorAccess", "ReadOnlyAccess", "S3FullAccess", "LambdaBasicExecution"]
TARGETS  = ["newuser01", "tempuser", "svc-account", "test-user"]
INSTANCES= ["i-0a1b2c3d4e5f67890", "i-0fedcba9876543210"]
SGS      = ["sg-prod-web", "sg-dev-internal", "sg-db-access"]
FUNCS    = ["data-processor", "log-shipper", "alert-handler", "auth-validator"]
RULES    = ["require-mfa", "s3-public-block", "cloudtrail-enabled"]
ALARMS   = ["high-cpu", "error-rate", "billing-threshold"]


def _pick(lst, idx):
    return lst[idx % len(lst)]


def generate_events(
    case_id: str = DEMO_CASE_ID,
    count:   int = 100,
    base_ts: datetime = None,
) -> list[dict]:
    """
    Generate `count` deterministic demo events.
    All values are deterministic based on index for reproducibility.
    """
    if base_ts is None:
        base_ts = datetime(2026, 9, 25, 0, 0, 0, tzinfo=timezone.utc)

    events = []
    for i in range(1, count + 1):
        tmpl = EVENT_TEMPLATES[(i - 1) % len(EVENT_TEMPLATES)]
        service, svc_short, action, msg_tmpl = tmpl

        user    = _pick(USERS,    i)
        ip      = _pick(IPS,      i)
        bucket  = _pick(BUCKETS,  i)
        key     = _pick(KEYS,     i)
        role    = _pick(ROLES,    i)
        policy  = _pick(POLICIES, i)
        target  = _pick(TARGETS,  i)
        inst    = _pick(INSTANCES,i)
        sg      = _pick(SGS,      i)
        func    = _pick(FUNCS,    i)
        rule    = _pick(RULES,    i)
        alarm   = _pick(ALARMS,   i)

        message = msg_tmpl.format(
            user=user, ip=ip, bucket=bucket, key=key, role=role,
            policy=policy, target=target, instance=inst, sg=sg,
            func=func, rule=rule, alarm=alarm,
        )

        ts = (base_ts + timedelta(minutes=(i - 1) * 3)).strftime("%Y-%m-%dT%H:%M:%SZ")

        events.append({
            "event_id":  f"evt-{i:06d}",
            "provider":  "local",
            "service":   svc_short,
            "source":    service,
            "case_id":   case_id,
            "sequence":  i,
            "timestamp": ts,
            "message":   message,
        })

    return events


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate LogChain demo events")
    parser.add_argument("--case-id", default=DEMO_CASE_ID)
    parser.add_argument("--count",   type=int, default=100)
    parser.add_argument("--out-dir", default=DEMO_LOG_DIR)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    events = generate_events(case_id=args.case_id, count=args.count)

    out_file = out_dir / f"{args.case_id}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2, ensure_ascii=False)

    print(f"[+] Generated {len(events)} events for {args.case_id}")
    print(f"[+] Output: {out_file}")
    print(f"[+] Sample event:")
    print(json.dumps(events[0], indent=4))
    print(f"[+] Last event:")
    print(json.dumps(events[-1], indent=4))


if __name__ == "__main__":
    main()
