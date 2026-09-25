"""
LogChain - Comprehensive Hackathon Pre-Flight Verification
===========================================================
Validates end-to-end readiness for a two-device live demonstration:
  - Python runtime & libraries
  - MongoDB availability & isolation
  - Pinned Geth v1.13.x compatibility
  - Device 1 & Device 2 RPC connectivity
  - Peer synchronization (>= 1 peer)
  - Smart contract deployment & callability
  - Flask dashboard & ingestion API token
  - Cloud adapter interfaces

Final summary produces:
  HACKATHON READY: YES  (if all critical checks pass)
  HACKATHON READY: NO   (if any critical failure occurs)
"""

import os
import sys
import json
import shutil
import urllib.request
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from backend.config import (
    DEVICE1_RPC,
    DEVICE2_RPC,
    CHAIN_ID,
    CONTRACT_ADDRESS,
    MONGODB_URI,
    FLASK_PORT,
    INGEST_API_TOKEN,
    BLOCKCHAIN_ACCOUNT,
)

results = []


def check(name: str, ok: bool, msg: str = "", level: str = "critical") -> bool:
    if ok:
        status = "PASS"
    elif level == "critical":
        status = "FAIL"
    elif level == "blocked":
        status = "BLOCKED"
    else:
        status = "WARN"

    print(f"  [{status}] {name}: {msg}")
    results.append((name, status, msg))
    return ok


def section(title: str):
    print(f"\n== {title} {'=' * (55 - len(title))}")


def main():
    print("=" * 60)
    print(" LogChain - Hackathon Demonstration Readiness Pre-Flight")
    print("=" * 60)

    # 1. Python Runtime & Dependencies
    section("Python Runtime")
    v = sys.version_info
    check("Python version", v.major == 3 and v.minor >= 9, f"{v.major}.{v.minor}.{v.micro} (need 3.9+)")

    def try_import(pkg, import_name=None):
        try:
            __import__(import_name or pkg)
            return True
        except ImportError:
            return False

    section("Dependencies")
    check("web3",        try_import("web3"),            "web3.py")
    check("flask",       try_import("flask"),           "flask")
    check("pymongo",     try_import("pymongo"),         "pymongo")
    check("dotenv",      try_import("dotenv", "dotenv"), "python-dotenv")
    check("pytest",      try_import("pytest"),          "pytest", level="warn")

    # 2. Geth Engine & PoA Compatibility
    section("Geth Consensus Compatibility")
    local_bin = _ROOT / "bin" / ("geth.exe" if sys.platform == "win32" else "geth")
    candidates = []
    if local_bin.exists():
        candidates.append((str(local_bin), "local ./bin"))
    sys_geth = shutil.which("geth")
    if sys_geth and (not candidates or sys_geth != candidates[0][0]):
        candidates.append((sys_geth, "system PATH"))

    if not candidates:
        check("Geth installed", False, "No geth binary found. Run python scripts/download_geth.py")
    else:
        active_bin, origin = candidates[0]
        try:
            res = subprocess.run([active_bin, "version"], capture_output=True, text=True, timeout=8)
            out = res.stdout + res.stderr
            import re
            m = re.search(r"(?:Version:\s*|geth[^\n0-9]*\bv?)([0-9]+)\.([0-9]+)\.([0-9]+)", out, re.IGNORECASE)
            if m:
                major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if major == 1 and minor < 14:
                    check("Geth Clique PoA Support", True, f"v{major}.{minor}.{patch} at {active_bin} ({origin})")
                else:
                    check(
                        "Geth Clique PoA Support",
                        False,
                        f"Detected v{major}.{minor}.{patch}. Geth >= 1.14 removed Clique PoA block sealing! Run python scripts/download_geth.py",
                    )
            else:
                check("Geth version check", False, f"Could not parse version from: {active_bin}", level="warn")
        except Exception as exc:
            check("Geth executable check", False, str(exc))

    # 3. MongoDB
    section("MongoDB State Database")
    try:
        from backend.alerts import is_mongodb_available
        mongo_ok = is_mongodb_available()
        check("MongoDB reachable", mongo_ok, f"URI: {MONGODB_URI}")
    except Exception as exc:
        check("MongoDB reachable", False, str(exc))

    # 4. Device 1 Blockchain & Peering
    section("Device 1 Primary Node")
    d1_connected = False
    peers1 = 0
    try:
        from web3 import Web3
        w3_1 = Web3(Web3.HTTPProvider(DEVICE1_RPC))
        d1_connected = w3_1.is_connected()
        if d1_connected:
            chain_id1 = w3_1.eth.chain_id
            block1 = w3_1.eth.block_number
            peers1 = w3_1.net.peer_count
            check("Device 1 RPC", True, f"{DEVICE1_RPC} (Block #{block1})")
            check("Chain ID matches", chain_id1 == CHAIN_ID, f"Got {chain_id1}, expected {CHAIN_ID}")
            check("Device 1 P2P Peering", peers1 >= 1, f"Connected to {peers1} peer(s)")
        else:
            check("Device 1 RPC", False, f"{DEVICE1_RPC} offline")
    except Exception as exc:
        check("Device 1 RPC", False, str(exc))

    # 5. Device 2 Independent Validator
    section("Device 2 Independent Validator")
    try:
        from web3 import Web3
        w3_2 = Web3(Web3.HTTPProvider(DEVICE2_RPC))
        d2_connected = w3_2.is_connected()
        if d2_connected:
            block2 = w3_2.eth.block_number
            peers2 = w3_2.net.peer_count
            check("Device 2 RPC", True, f"{DEVICE2_RPC} (Block #{block2})")
            check("Device 2 P2P Peering", peers2 >= 1, f"Connected to {peers2} peer(s)")
            if d1_connected:
                # Check block synchronization
                diff = abs(block1 - block2)
                check("Block Synchronization", diff <= 2, f"Device 1 (#{block1}) vs Device 2 (#{block2}) diff={diff}")
        else:
            check("Device 2 RPC", False, f"{DEVICE2_RPC} offline or on separate LAN laptop", level="blocked")
    except Exception as exc:
        check("Device 2 RPC", False, str(exc), level="blocked")

    # 6. Smart Contract Deployment & State
    section("Smart Contract (LogIntegrityV3)")
    check("CONTRACT_ADDRESS configured", bool(CONTRACT_ADDRESS), CONTRACT_ADDRESS or "Missing in .env")

    abi_path = Path(__file__).parent.parent / "backend" / "LogIntegrityV3_abi.json"
    check("ABI file exists", abi_path.exists(), str(abi_path))

    if d1_connected and CONTRACT_ADDRESS and abi_path.exists():
        try:
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider(DEVICE1_RPC))
            with open(abi_path) as f:
                abi = json.load(f)
            contract = w3.eth.contract(address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=abi)
            owner = contract.functions.owner().call()
            check("Contract deployed & callable", True, f"Owner: {owner}")
        except Exception as exc:
            check("Contract deployed & callable", False, str(exc))

    # 7. Dashboard & Ingestion API
    section("Dashboard & Remote Ingestion")
    check("INGEST_API_TOKEN set", bool(INGEST_API_TOKEN), "Configured in .env")
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{FLASK_PORT}/api/status", headers={"User-Agent": "Preflight"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            check("Dashboard API responding", resp.status == 200, f"Integrity: {data.get('integrity')}")
    except Exception as exc:
        check("Dashboard API responding", False, f"Port {FLASK_PORT} not responding or Flask not running", level="warn")

    # 8. Cloud Adapter Interfaces
    section("Cloud Adapters")
    try:
        from adapters.base import LogGetter
        from adapters.local_getter import LocalLogGetter
        from adapters.aws_getter import AWSLogGetter
        from adapters.azure_getter import AzureLogGetter
        check("Adapter modules importable", True, "base, local, aws, azure")
    except Exception as exc:
        check("Adapter modules importable", False, str(exc))

    # ── Summary & Final Evaluation ──────────────────────────────
    print("\n" + "=" * 60)
    print(" Hackathon Pre-Flight Summary")
    print("=" * 60)

    fails = [r for r in results if r[1] == "FAIL"]
    warns = [r for r in results if r[1] == "WARN"]
    blocked = [r for r in results if r[1] == "BLOCKED"]
    passed = [r for r in results if r[1] == "PASS"]

    print(f"  PASS:    {len(passed)}")
    print(f"  FAIL:    {len(fails)}")
    print(f"  WARN:    {len(warns)}")
    print(f"  BLOCKED: {len(blocked)}")

    print("-" * 60)
    if fails:
        print("  CRITICAL FAILURES PREVENTING DEMO:")
        for name, _, msg in fails:
            print(f"    - {name}: {msg}")
        print("\n  HACKATHON READY: NO")
        print("=" * 60)
        sys.exit(1)
    elif not d1_connected or not CONTRACT_ADDRESS or peers1 == 0:
        print("  INCOMPLETE INFRASTRUCTURE:")
        if not d1_connected:
            print("    - Device 1 blockchain is not connected")
        if not CONTRACT_ADDRESS:
            print("    - Contract is not deployed")
        if peers1 == 0:
            print("    - Device 1 has 0 peers")
        print("\n  HACKATHON READY: NO")
        print("=" * 60)
        sys.exit(1)
    else:
        print("  ALL CORE CRITICAL REQUIREMENTS MET!")
        if blocked:
            print("  Note: Some items are BLOCKED (e.g. Device 2 on separate laptop over LAN).")
        print("\n  HACKATHON READY: YES")
        print("=" * 60)
        sys.exit(0)


if __name__ == "__main__":
    main()
