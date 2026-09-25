"""
LogChain - Cross-Platform Node Runner (Device 1 & Device 2)
=============================================================
Manages local Geth PoA nodes on Windows, Linux, and macOS.
Prioritizes the pinned Geth v1.13.15 binary in ./bin/.

Usage:
    python scripts/start_nodes.py --node 1       # Start Device 1 (port 8545)
    python scripts/start_nodes.py --node 2       # Start Device 2 (port 8546)
    python scripts/start_nodes.py --all          # Start both nodes locally
    python scripts/start_nodes.py --stop         # Stop running nodes
    python scripts/start_nodes.py --status       # Check node process & RPC status
"""

import os
import sys
import time
import shutil
import signal
import subprocess
import argparse
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from backend.config import (
    CHAIN_ID,
    BLOCKCHAIN_ACCOUNT,
    BLOCKCHAIN_PASSWORD,
    DEVICE2_ACCOUNT,
    DEVICE2_PASSWORD,
    DEVICE1_RPC,
    DEVICE2_RPC,
)


def find_compatible_geth():
    """Locate geth binary and verify it supports Clique PoA (< v1.14)."""
    candidates = []
    local_bin = _ROOT / "bin" / ("geth.exe" if sys.platform == "win32" else "geth")
    if local_bin.exists():
        candidates.append((local_bin, "local ./bin"))

    sys_geth = shutil.which("geth")
    if sys_geth and (not candidates or sys_geth != str(candidates[0][0])):
        candidates.append((Path(sys_geth), "system PATH"))

    if not candidates:
        print("[FAIL] Geth binary not found in ./bin or system PATH.")
        print("       Run: python scripts/download_geth.py")
        sys.exit(1)

    for bin_path, origin in candidates:
        try:
            res = subprocess.run([str(bin_path), "version"], capture_output=True, text=True, timeout=10)
            out = res.stdout + res.stderr
            m = re.search(r"(?:Version:\s*|geth[^\n0-9]*\bv?)([0-9]+)\.([0-9]+)\.([0-9]+)", out, re.IGNORECASE)
            if m:
                major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if major == 1 and minor < 14:
                    return str(bin_path), f"v{major}.{minor}.{patch} ({origin})"
                else:
                    print(f"[WARN] Found Geth v{major}.{minor}.{patch} at {bin_path} ({origin})")
                    print(f"       Geth >= 1.14 removed Clique PoA block sealing.")
        except Exception as exc:
            print(f"[WARN] Error inspecting {bin_path}: {exc}")

    print("\n[FAIL] No compatible Geth (< v1.14) was found.")
    print("       LogChain uses Clique PoA consensus, which requires Geth v1.13.x.")
    print("       Run: python scripts/download_geth.py to automatically install pinned v1.13.15.")
    sys.exit(1)


def is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            res = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return str(pid) in res.stdout
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


def stop_node(node_num: int):
    datadir = _ROOT / f"node{node_num}_data"
    pid_file = datadir / f"node{node_num}.pid"
    if not pid_file.exists():
        print(f"[*] Node {node_num}: No pid file found at {pid_file}")
        return

    try:
        pid = int(pid_file.read_text().strip())
    except Exception:
        pid = 0

    if pid and is_process_running(pid):
        print(f"[*] Stopping Node {node_num} (PID: {pid})...")
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        else:
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(1)
                if is_process_running(pid):
                    os.kill(pid, signal.SIGKILL)
            except Exception:
                pass
        print(f"[PASS] Node {node_num} stopped.")
    else:
        print(f"[*] Node {node_num} (PID {pid}) was not running.")

    if pid_file.exists():
        pid_file.unlink(missing_ok=True)


def check_rpc_alive(url: str, timeout: int = 2) -> bool:
    try:
        import urllib.request
        import json
        req = urllib.request.Request(
            url,
            data=json.dumps({"jsonrpc": "2.0", "method": "web3_clientVersion", "params": [], "id": 1}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        res = urllib.request.urlopen(req, timeout=timeout)
        data = json.loads(res.read())
        return "result" in data
    except Exception:
        return False


def start_node(node_num: int, geth_bin: str, clean: bool = False):
    datadir = _ROOT / f"node{node_num}_data"
    datadir.mkdir(parents=True, exist_ok=True)
    pid_file = datadir / f"node{node_num}.pid"
    log_file = datadir / f"node{node_num}.log"

    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            if is_process_running(pid):
                print(f"[!] Node {node_num} is already running with PID {pid}")
                return
        except Exception:
            pass

    if clean and (datadir / "geth").exists():
        print(f"[*] Cleaning stale chaindata in {datadir / 'geth'}...")
        shutil.rmtree(datadir / "geth", ignore_errors=True)

    # Node accounts & passwords must be strictly distinct
    if node_num == 1:
        account = BLOCKCHAIN_ACCOUNT
        pwd = BLOCKCHAIN_PASSWORD
        acct_var = "BLOCKCHAIN_ACCOUNT"
        pwd_var = "BLOCKCHAIN_PASSWORD"
    else:
        account = DEVICE2_ACCOUNT
        pwd = DEVICE2_PASSWORD
        acct_var = "DEVICE2_ACCOUNT"
        pwd_var = "DEVICE2_PASSWORD"

    if not account:
        print(f"[FAIL] Node {node_num} account not configured in .env (missing {acct_var}).")
        print("       Device 2 MUST have its own independent validator account.")
        print("       Run: python scripts/setup_private_chain.py")
        sys.exit(1)

    # Ensure password file
    pwd_file = datadir / "password.txt"
    if not pwd_file.exists():
        if pwd:
            pwd_file.write_text(pwd)
        else:
            print(f"[FAIL] Missing password file at {pwd_file} and {pwd_var} not configured in .env")
            print("       Run: python scripts/setup_private_chain.py")
            sys.exit(1)

    # Genesis initialization
    if not (datadir / "geth").exists():
        genesis_file = _ROOT / "genesis.json"
        if not genesis_file.exists():
            print(f"[FAIL] Genesis file not found at {genesis_file}")
            print("       Run: python scripts/setup_private_chain.py")
            sys.exit(1)
        print(f"[*] Initializing Node {node_num} genesis...")
        init_res = subprocess.run(
            [geth_bin, "--datadir", str(datadir), "init", str(genesis_file)],
            capture_output=True,
            text=True,
        )
        if init_res.returncode != 0:
            print(f"[FAIL] Genesis init failed:\n{init_res.stderr}")
            sys.exit(1)
        print(f"[PASS] Genesis initialized for Node {node_num}")

    # Ports
    rpc_port = 8545 if node_num == 1 else 8546
    p2p_port = 30303 if node_num == 1 else 30304
    auth_port = 8551 if node_num == 1 else 8552

    cmd = [
        geth_bin,
        "--datadir", str(datadir),
        "--networkid", str(CHAIN_ID),
        "--port", str(p2p_port),
        "--http",
        "--http.addr", "0.0.0.0",
        "--http.port", str(rpc_port),
        "--http.api", "eth,net,web3",
        "--http.corsdomain", "*",
        "--http.vhosts", "*",
        "--authrpc.port", str(auth_port),
        "--ipcpath", f"geth{node_num}.ipc",
        "--allow-insecure-unlock",
        "--unlock", account,
        "--password", str(pwd_file),
        "--mine",
        "--miner.etherbase", account,
        "--syncmode", "full",
        "--gcmode", "archive",
        "--nodiscover",
        "--maxpeers", "5",
        "--verbosity", "3",
    ]

    print(f"[*] Starting Geth Node {node_num} on RPC port {rpc_port}...")
    log_fp = open(log_file, "a", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        stdout=log_fp,
        stderr=subprocess.STDOUT,
        cwd=str(_ROOT),
    )

    pid_file.write_text(str(proc.pid))
    time.sleep(3)

    if proc.poll() is None and is_process_running(proc.pid):
        print(f"[PASS] Node {node_num} started! (PID: {proc.pid})")
        print(f"       RPC: http://127.0.0.1:{rpc_port}")
        print(f"       Log: {log_file}")
    else:
        print(f"[FAIL] Node {node_num} exited prematurely. Check log at {log_file}")


def show_status():
    print("=" * 60)
    print(" LogChain Node Status")
    print("=" * 60)

    for num, rpc in [(1, DEVICE1_RPC), (2, DEVICE2_RPC)]:
        datadir = _ROOT / f"node{num}_data"
        pid_file = datadir / f"node{num}.pid"
        pid = None
        running = False
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                running = is_process_running(pid)
            except Exception:
                pass

        rpc_alive = check_rpc_alive(rpc)
        status_icon = "[ONLINE]" if (running and rpc_alive) else ("[PARTIAL]" if running or rpc_alive else "[OFFLINE]")
        print(f"  {status_icon} Node {num}:")
        print(f"         PID: {pid if pid else 'None'} ({'Running' if running else 'Stopped'})")
        print(f"         RPC: {rpc} ({'Reachable' if rpc_alive else 'Unreachable'})")


def main():
    parser = argparse.ArgumentParser(description="LogChain Private Geth Node Manager")
    parser.add_argument("--node", type=int, choices=[1, 2], help="Start specific node (1 or 2)")
    parser.add_argument("--all", action="store_true", help="Start both Node 1 and Node 2 locally")
    parser.add_argument("--stop", action="store_true", help="Stop running nodes")
    parser.add_argument("--status", action="store_true", help="Show status of nodes")
    parser.add_argument("--clean", action="store_true", help="Clean stale chaindata before starting")

    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if args.stop:
        stop_node(1)
        stop_node(2)
        return

    geth_bin, ver_info = find_compatible_geth()
    print(f"[*] Compatible Geth binary: {geth_bin} ({ver_info})")

    if args.all:
        start_node(1, geth_bin, clean=args.clean)
        start_node(2, geth_bin, clean=args.clean)
        show_status()
    elif args.node:
        start_node(args.node, geth_bin, clean=args.clean)
        show_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
