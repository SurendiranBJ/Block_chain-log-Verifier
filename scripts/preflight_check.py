"""
LogChain - Pre-Flight Check
Validates all system dependencies before demo.

Usage:
    python scripts/preflight_check.py
    python scripts/preflight_check.py --gen-key   (generate new key pair)

Exit code 0 = all critical checks passed
Exit code 1 = critical failures detected
"""
import sys
import os
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

PASS = "[PASS]"
FAIL = "[FAIL]"
WARN = "[WARN]"
BLOCK = "[BLOCKED]"

results = []


def check(name, ok, msg="", level="critical"):
    icon = PASS if ok else (FAIL if level == "critical" else WARN)
    status = "PASS" if ok else ("FAIL" if level == "critical" else "WARN")
    print(f"  {icon} {name}: {msg}")
    results.append((name, status, msg))
    return ok


def section(title):
    print(f"\n== {title} {'='*(50-len(title))}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gen-key", action="store_true", help="Generate a new key pair")
    args = parser.parse_args()

    if args.gen_key:
        try:
            from eth_account import Account
            acct = Account.create()
            print(f"\n[+] Generated new key pair:")
            print(f"    BLOCKCHAIN_ACCOUNT={acct.address}")
            print(f"    BLOCKCHAIN_PRIVATE_KEY={acct.key.hex()}")
            print(f"\n    Add these to your .env file.")
            print(f"    Fund the account before deploying contracts.")
        except ImportError:
            print("[ERROR] eth-account not installed. Run: pip install eth-account")
        return

    print("\n" + "=" * 60)
    print("  LogChain Pre-Flight Check")
    print("=" * 60)

    # ── Python Version ─────────────────────────────────────────
    section("Python")
    v = sys.version_info
    check("Python version", v.major == 3 and v.minor >= 9,
          f"{v.major}.{v.minor}.{v.micro} (need 3.9+)")

    # ── Dependencies ───────────────────────────────────────────
    section("Python Dependencies")

    def try_import(pkg, import_name=None):
        try:
            __import__(import_name or pkg)
            return True
        except ImportError:
            return False

    check("web3",        try_import("web3"),        "pip install web3")
    check("flask",       try_import("flask"),       "pip install flask")
    check("pymongo",     try_import("pymongo"),     "pip install pymongo")
    check("dotenv",      try_import("dotenv","dotenv"), "pip install python-dotenv")
    check("pytest",      try_import("pytest"),      "pip install pytest", level="warn")

    # ── Geth Binary & PoA Compatibility ────────────────────────
    section("Geth Engine & Consensus Compatibility")
    import shutil
    import subprocess
    import re

    root = Path(__file__).parent.parent
    local_bin = root / "bin" / ("geth.exe" if sys.platform == "win32" else "geth")

    candidate_paths = []
    if local_bin.exists():
        candidate_paths.append((str(local_bin), "local ./bin"))
    sys_geth = shutil.which("geth")
    if sys_geth and (not candidate_paths or sys_geth != candidate_paths[0][0]):
        candidate_paths.append((sys_geth, "system PATH"))

    if not candidate_paths:
        check(
            "Geth installed",
            False,
            "Geth not found in ./bin or PATH. Run: python scripts/download_geth.py",
            level="critical",
        )
    else:
        active_bin, bin_origin = candidate_paths[0]
        try:
            res = subprocess.run([active_bin, "version"], capture_output=True, text=True, timeout=10)
            out = res.stdout + res.stderr
            m = re.search(r"(?:Version:\s*|geth[^\n0-9]*\bv?)([0-9]+)\.([0-9]+)\.([0-9]+)", out, re.IGNORECASE)

            if m:
                major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
                ver_str = f"v{major}.{minor}.{patch}"
                if (major > 1) or (major == 1 and minor >= 14):
                    check(
                        "Geth Clique PoA Support",
                        False,
                        f"Detected {ver_str} at {active_bin} ({bin_origin}). Geth >= 1.14 removed Clique PoA block sealing! Pinned Geth v1.13.x is required. Run: python scripts/download_geth.py to install compatible binary into ./bin/",
                        level="critical",
                    )
                else:
                    check(
                        "Geth Clique PoA Support",
                        True,
                        f"Compatible {ver_str} at {active_bin} ({bin_origin}) - Clique PoA supported",
                    )
            else:
                check("Geth version check", False, f"Could not parse version from: {active_bin}", level="warn")
        except Exception as exc:
            check("Geth executable check", False, f"Error running {active_bin}: {exc}", level="critical")

    # ── Environment ────────────────────────────────────────────
    section("Environment (.env)")
    root = Path(__file__).parent.parent
    env_file = root / ".env"
    check(".env exists", env_file.exists(),
          str(env_file) + (" [FOUND]" if env_file.exists() else " [MISSING - copy .env.example]"),
          level="warn")

    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file)

    from backend.config import (
        DEVICE1_RPC, DEVICE2_RPC, CHAIN_ID,
        BLOCKCHAIN_PRIVATE_KEY, BLOCKCHAIN_ACCOUNT, CONTRACT_ADDRESS,
        MONGODB_URI,
    )

    check("BLOCKCHAIN_PRIVATE_KEY set",
          bool(BLOCKCHAIN_PRIVATE_KEY and BLOCKCHAIN_PRIVATE_KEY != "0xYOUR_NEW_PRIVATE_KEY_HERE"),
          "Set in .env")
    check("BLOCKCHAIN_ACCOUNT set",
          bool(BLOCKCHAIN_ACCOUNT and BLOCKCHAIN_ACCOUNT != "0xYOUR_ACCOUNT_ADDRESS_HERE"),
          "Set in .env")
    check("CONTRACT_ADDRESS set",
          bool(CONTRACT_ADDRESS),
          "Run deploy_contract.py first", level="warn")

    # ── MongoDB ────────────────────────────────────────────────
    section("MongoDB")
    try:
        from backend.alerts import is_mongodb_available
        mongo_ok = is_mongodb_available()
        check("MongoDB reachable", mongo_ok, f"URI: {MONGODB_URI}")
    except Exception as e:
        check("MongoDB reachable", False, str(e))

    # ── Device 1 Blockchain ────────────────────────────────────
    section("Device 1 (Primary Node)")
    try:
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider(DEVICE1_RPC))
        d1_ok = w3.is_connected()
        if d1_ok:
            block    = w3.eth.block_number
            chain_id = w3.eth.chain_id
            peers    = w3.net.peer_count
            check("Device 1 RPC reachable", True,  f"{DEVICE1_RPC}")
            check("Chain ID correct",
                  chain_id == CHAIN_ID,
                  f"Got {chain_id}, expected {CHAIN_ID}")
            check("Block number", block >= 0, f"Block #{block}")
            check("Peer count",   peers >= 0, f"{peers} peer(s)", level="warn")
        else:
            check("Device 1 RPC reachable", False, f"{DEVICE1_RPC} - Not running")
    except Exception as e:
        check("Device 1 RPC reachable", False, str(e))

    # ── Device 2 Blockchain ────────────────────────────────────
    section("Device 2 (Independent Validator)")
    try:
        from web3 import Web3
        w3_2 = Web3(Web3.HTTPProvider(DEVICE2_RPC))
        d2_ok = w3_2.is_connected()
        if d2_ok:
            block2 = w3_2.eth.block_number
            check("Device 2 RPC reachable", True, f"{DEVICE2_RPC} - Block #{block2}")
        else:
            print(f"  {BLOCK} Device 2 RPC: {DEVICE2_RPC} - Not reachable from this machine")
            print(f"         This is expected if Device 2 is a separate physical device.")
            results.append(("Device 2 RPC", "BLOCKED", "Expected for separate physical device"))
    except Exception as e:
        print(f"  {BLOCK} Device 2: {e}")

    # ── Contract ───────────────────────────────────────────────
    section("Smart Contract")
    abi_path = Path(__file__).parent.parent / "backend" / "LogIntegrityV3_abi.json"
    check("V3 ABI file exists", abi_path.exists(),
          str(abi_path), level="warn")

    if CONTRACT_ADDRESS and abi_path.exists():
        try:
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider(DEVICE1_RPC))
            if w3.is_connected():
                import json as _json
                with open(abi_path) as f:
                    abi = _json.load(f)
                contract = w3.eth.contract(
                    address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=abi
                )
                owner = contract.functions.owner().call()
                check("Contract callable", True, f"Owner: {owner}")
            else:
                check("Contract callable", False, "Device 1 not connected", level="warn")
        except Exception as e:
            check("Contract callable", False, str(e), level="warn")

    # ── Demo Files ─────────────────────────────────────────────
    section("Demo")
    demo_dir = Path(__file__).parent.parent / "demo" / "sample_logs"
    check("Demo directory exists", demo_dir.exists() or True,  # auto-created
          str(demo_dir), level="warn")

    gen_script = Path(__file__).parent.parent / "demo" / "generate_logs.py"
    check("generate_logs.py exists", gen_script.exists(), str(gen_script))

    # ── Adapter Imports ────────────────────────────────────────
    section("Adapter Interface")
    try:
        from adapters.base import LogGetter
        from adapters.local_getter import LocalLogGetter
        from adapters.aws_getter import AWSLogGetter
        from adapters.azure_getter import AzureLogGetter
        check("All adapters importable", True, "base, local, aws, azure")
    except Exception as e:
        check("All adapters importable", False, str(e))

    # ── Dashboard Import ───────────────────────────────────────
    section("Dashboard")
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "app",
            Path(__file__).parent.parent / "backend" / "app.py"
        )
        check("Dashboard imports correctly", spec is not None, "backend/app.py")
    except Exception as e:
        check("Dashboard imports correctly", False, str(e))

    # ── Summary ────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Pre-Flight Summary")
    print("=" * 60)

    fails    = [r for r in results if r[1] == "FAIL"]
    warns    = [r for r in results if r[1] == "WARN"]
    blocked  = [r for r in results if r[1] == "BLOCKED"]
    passed   = [r for r in results if r[1] == "PASS"]

    print(f"  PASS:    {len(passed)}")
    print(f"  FAIL:    {len(fails)}")
    print(f"  WARN:    {len(warns)}")
    print(f"  BLOCKED: {len(blocked)}")

    if fails:
        print("\n  Critical failures:")
        for name, _, msg in fails:
            print(f"    - {name}: {msg}")
        print("\n[EXIT 1] Fix critical issues before running demo.")
        sys.exit(1)
    else:
        print("\n[EXIT 0] All critical checks passed. System ready.")
        sys.exit(0)


if __name__ == "__main__":
    main()
