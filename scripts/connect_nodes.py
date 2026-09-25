"""
LogChain - Cross-Platform Secure Node Peering
==============================================
Connects Device 1 and Device 2 using safe local IPC administration.
Avoids exposing Geth admin RPC over HTTP.
Persists peering in static-nodes.json.

Usage:
    python scripts/connect_nodes.py
    python scripts/connect_nodes.py --enode "enode://...@<DEVICE2_IP>:30304"
"""

import os
import sys
import json
import time
import subprocess
import argparse
from pathlib import Path
from web3 import Web3

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from backend.config import DEVICE1_RPC, DEVICE2_RPC, DEVICE1_IP, DEVICE2_IP


def get_geth_binary():
    local_bin = _ROOT / "bin" / ("geth.exe" if sys.platform == "win32" else "geth")
    if local_bin.exists():
        return str(local_bin)
    import shutil
    sys_geth = shutil.which("geth")
    if sys_geth:
        return sys_geth
    raise FileNotFoundError("Geth binary not found. Run python scripts/download_geth.py")


def get_ipc_path(node_num: int) -> str:
    datadir = _ROOT / f"node{node_num}_data"
    if sys.platform == "win32":
        # Windows named pipe paths
        for pipe_name in [f"geth{node_num}.ipc", "geth.ipc"]:
            pipe_full = rf"\\.\pipe\{pipe_name}"
            # Check if file exists or test with geth
            return pipe_full
        return rf"\\.\pipe\geth{node_num}.ipc"
    else:
        for fname in [f"geth{node_num}.ipc", "geth.ipc"]:
            p = datadir / fname
            if p.exists():
                return str(p)
        return str(datadir / "geth.ipc")


def get_enode_via_ipc(node_num: int, advertised_ip: str) -> str:
    geth_bin = get_geth_binary()
    ipc = get_ipc_path(node_num)
    try:
        res = subprocess.run(
            [geth_bin, "--exec", "admin.nodeInfo.enode", "attach", ipc],
            capture_output=True,
            text=True,
            timeout=8,
        )
        out = (res.stdout + res.stderr).strip().replace('"', "")
        if "enode://" in out:
            # Extract enode line
            for line in out.splitlines():
                if line.startswith("enode://"):
                    import re
                    # Replace loopback with advertised IP
                    return re.sub(r"@(127\.0\.0\.1|\[::\]|0\.0\.0\.0):", f"@{advertised_ip}:", line)
    except Exception as exc:
        pass
    return ""


def add_peer_via_ipc(node_num: int, target_enode: str) -> bool:
    geth_bin = get_geth_binary()
    ipc = get_ipc_path(node_num)
    try:
        res = subprocess.run(
            [geth_bin, "--exec", f"admin.addPeer('{target_enode}')", "attach", ipc],
            capture_output=True,
            text=True,
            timeout=8,
        )
        out = (res.stdout + res.stderr).strip().lower()
        return "true" in out
    except Exception:
        return False


def save_static_nodes(node_num: int, enode: str):
    datadir = _ROOT / f"node{node_num}_data"
    for target in [datadir / "static-nodes.json", datadir / "geth" / "static-nodes.json"]:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            nodes = []
            if target.exists():
                try:
                    nodes = json.loads(target.read_text(encoding="utf-8"))
                except Exception:
                    nodes = []
            if enode not in nodes:
                nodes.append(enode)
            target.write_text(json.dumps(nodes, indent=2), encoding="utf-8")
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="Secure Geth Peer Connector")
    parser.add_argument("--enode", help="Device 2 enode URI (if connecting from separate laptop)")
    args = parser.parse_args()

    print("=" * 60)
    print(" LogChain - Secure Peer Connection")
    print("============================================================")

    enode2 = args.enode
    if not enode2:
        enode2 = get_enode_via_ipc(2, DEVICE2_IP)

    if not enode2:
        print("[FAIL] Device 2 enode could not be discovered automatically.")
        print("       On Laptop 2 (Device 2), run:")
        print("       python scripts/connect_nodes.py --show-enode")
        print("       Then on Device 1 pass the enode: python scripts/connect_nodes.py --enode <URI>")
        sys.exit(1)

    print(f"[*] Target Device 2 Enode:")
    print(f"    {enode2}")

    # Add peer to Node 1
    ok = add_peer_via_ipc(1, enode2)
    save_static_nodes(1, enode2)
    print(f"[*] Added peer via Node 1 local IPC: {'SUCCESS' if ok else 'DISPATCHED'}")
    print(f"[*] Saved to static-nodes.json for automatic reconnect.")

    print("[*] Waiting for P2P handshake (5s)...")
    time.sleep(5)

    try:
        w1 = Web3(Web3.HTTPProvider(DEVICE1_RPC))
        peers = w1.net.peer_count
        if peers >= 1:
            print(f"\n[PASS] Peering Successful! Device 1 has {peers} peer(s).")
            print(f"       Device 1 block height: #{w1.eth.block_number}")
            sys.exit(0)
        else:
            print(f"\n[FAIL] Peer count is 0 on Device 1.")
            print(f"       Ensure Device 2 is running and ports 30303/30304 are open in firewall.")
            sys.exit(1)
    except Exception as exc:
        print(f"[FAIL] Error checking peer status: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    if "--show-enode" in sys.argv:
        en = get_enode_via_ipc(2, DEVICE2_IP) or get_enode_via_ipc(1, DEVICE1_IP)
        if en:
            print(en)
        else:
            print("Could not query enode via IPC.")
    else:
        main()
