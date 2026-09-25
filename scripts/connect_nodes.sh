#!/usr/bin/env bash
# LogChain - Connect Device 1 and Device 2 as P2P Peers
# Uses safe local IPC administration (NEVER exposes admin over public HTTP)
# Supports static-nodes.json persistence across node restarts.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

if [ -f "$ROOT_DIR/.env" ]; then
    source "$ROOT_DIR/.env"
fi

DEVICE1_IP="${DEVICE1_IP:-127.0.0.1}"
DEVICE2_IP="${DEVICE2_IP:-127.0.0.1}"
DEVICE1_RPC="${DEVICE1_RPC:-http://127.0.0.1:8545}"

echo "============================================================"
echo " LogChain - Secure Peer Connection (Local IPC Administration)"
echo "============================================================"

# Find Geth binary
if [ -x "$ROOT_DIR/bin/geth" ]; then
    GETH_BIN="$ROOT_DIR/bin/geth"
elif [ -f "$ROOT_DIR/bin/geth.exe" ]; then
    GETH_BIN="$ROOT_DIR/bin/geth.exe"
elif command -v geth &> /dev/null; then
    GETH_BIN="$(command -v geth)"
else
    echo "[ERROR] geth binary not found. Run: python scripts/download_geth.py"
    exit 1
fi

# Locate Device 1 IPC
D1_IPC=""
if [ -S "$ROOT_DIR/node1_data/geth.ipc" ]; then
    D1_IPC="$ROOT_DIR/node1_data/geth.ipc"
elif [ -S "$ROOT_DIR/node1_data/geth1.ipc" ]; then
    D1_IPC="$ROOT_DIR/node1_data/geth1.ipc"
elif [ -e "\\\\.\\pipe\\geth1.ipc" ] 2>/dev/null; then
    D1_IPC="\\\\.\\pipe\\geth1.ipc"
elif [ -e "\\\\.\\pipe\\geth.ipc" ] 2>/dev/null; then
    D1_IPC="\\\\.\\pipe\\geth.ipc"
else
    D1_IPC="$ROOT_DIR/node1_data/geth.ipc"
fi

# 1. Determine Device 2 Enode
ENODE2="${1:-}"

if [ -z "$ENODE2" ]; then
    # Attempt local discovery if running on same host
    D2_IPC=""
    if [ -S "$ROOT_DIR/node2_data/geth2.ipc" ]; then
        D2_IPC="$ROOT_DIR/node2_data/geth2.ipc"
    elif [ -S "$ROOT_DIR/node2_data/geth.ipc" ]; then
        D2_IPC="$ROOT_DIR/node2_data/geth.ipc"
    elif [ -e "\\\\.\\pipe\\geth2.ipc" ] 2>/dev/null; then
        D2_IPC="\\\\.\\pipe\\geth2.ipc"
    fi

    if [ -n "$D2_IPC" ]; then
        echo "[*] Querying Device 2 enode locally via IPC ($D2_IPC)..."
        RAW_ENODE=$("$GETH_BIN" --exec "admin.nodeInfo.enode" attach "$D2_IPC" 2>/dev/null | tr -d '"' || true)
        if [ -n "$RAW_ENODE" ] && [[ "$RAW_ENODE" != *"Error"* ]]; then
            ENODE2=$(echo "$RAW_ENODE" | sed -E "s/(@)(127\.0\.0\.1|\[::\]|0\.0\.0\.0)(:)/\1${DEVICE2_IP}\3/")
        fi
    fi
fi

if [ -z "$ENODE2" ]; then
    echo "[!] Device 2 enode could not be retrieved automatically."
    echo "    On Laptop 2 (Device 2), run: ./scripts/get_device2_enode.sh"
    echo "    Then pass the enode as an argument to this script:"
    echo "    ./scripts/connect_nodes.sh <ENODE_URI>"
    exit 1
fi

echo "[PASS] Target Device 2 Enode:"
echo "       $ENODE2"

# 2. Add peer to Device 1 via Local IPC
echo "[*] Adding peer via Device 1 local IPC..."
ADD_RES=$("$GETH_BIN" --exec "admin.addPeer('$ENODE2')" attach "$D1_IPC" 2>/dev/null | tr -d '\r\n' || echo "false")

# 3. Persist peer in static-nodes.json for automatic reconnection
STATIC_JSON="$ROOT_DIR/node1_data/static-nodes.json"
GETH_STATIC_JSON="$ROOT_DIR/node1_data/geth/static-nodes.json"
python3 -c "
import json, sys
enode = '$ENODE2'
for path in ['$STATIC_JSON', '$GETH_STATIC_JSON']:
    try:
        from pathlib import Path
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        nodes = []
        if p.exists():
            try:
                nodes = json.loads(p.read_text())
            except Exception:
                nodes = []
        if enode not in nodes:
            nodes.append(enode)
        p.write_text(json.dumps(nodes, indent=2))
    except Exception as e:
        pass
" 2>/dev/null || true

echo "[*] Peer added via local IPC. Waiting for P2P handshake (5s)..."
sleep 5

# 4. Check peer count on Device 1
PEERS_HEX=$(curl -s -X POST "$DEVICE1_RPC" \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","method":"net_peerCount","params":[],"id":1}' \
    | python3 -c "import sys, json; print(json.load(sys.stdin).get('result', '0x0'))" 2>/dev/null || echo "0x0")

PEERS=$((16#${PEERS_HEX#0x}))

echo "============================================================"
if [ "$PEERS" -ge 1 ]; then
    echo "[PASS] Peering Successful! Device 1 has $PEERS active peer(s)."
    echo "       Static configuration saved to $STATIC_JSON."
    exit 0
else
    echo "[FAIL] Peer count is 0."
    echo "       Possible reasons:"
    echo "       1. Firewall blocking TCP/UDP 30303 (Device 1) or 30304 (Device 2)."
    echo "       2. Device 2 IP ($DEVICE2_IP) is not reachable from Device 1."
    echo "       3. Device 2 Geth is not currently running."
    echo "       Run: ./scripts/verify_peers.sh to inspect network status."
    exit 1
fi
