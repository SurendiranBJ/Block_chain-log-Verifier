#!/usr/bin/env bash
# LogChain - Verify P2P Peering & Block Synchronization
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

if [ -f "$ROOT_DIR/.env" ]; then
    source "$ROOT_DIR/.env"
fi

DEVICE1_RPC="${DEVICE1_RPC:-http://127.0.0.1:8545}"
DEVICE2_RPC="${DEVICE2_RPC:-http://127.0.0.1:8546}"

echo "============================================================"
echo " LogChain - Peering & Block Synchronization Verification"
echo "============================================================"

check_node() {
    local name="$1"
    local rpc="$2"

    local resp
    resp=$(curl -s -m 3 -X POST "$rpc" \
        -H "Content-Type: application/json" \
        -d '{"jsonrpc":"2.0","method":"net_peerCount","params":[],"id":1}' 2>/dev/null || echo "")

    if [ -z "$resp" ]; then
        echo "  [OFFLINE] $name ($rpc) unreachable."
        return 1
    fi

    local peers_hex
    peers_hex=$(echo "$resp" | python3 -c "import sys, json; print(json.load(sys.stdin).get('result', '0x0'))" 2>/dev/null || echo "0x0")
    local peers=$((16#${peers_hex#0x}))

    local block_resp
    block_resp=$(curl -s -m 3 -X POST "$rpc" \
        -H "Content-Type: application/json" \
        -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' 2>/dev/null || echo "")
    local block_hex
    block_hex=$(echo "$block_resp" | python3 -c "import sys, json; print(json.load(sys.stdin).get('result', '0x0'))" 2>/dev/null || echo "0x0")
    local block=$((16#${block_hex#0x}))

    echo "  [ONLINE]  $name:"
    echo "            Peers: $peers"
    echo "            Block: #$block"
    return 0
}

check_node "Device 1 (Primary Node)" "$DEVICE1_RPC" || true
check_node "Device 2 (Validator)"    "$DEVICE2_RPC" || true

echo "============================================================"
