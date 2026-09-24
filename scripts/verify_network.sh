#!/usr/bin/env bash
# LogChain - Verify Blockchain Network Status
# Checks both nodes and reports: PASS / FAIL / BLOCKED
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
if [ -f "$ROOT_DIR/.env" ]; then source "$ROOT_DIR/.env"; fi

DEVICE1_RPC="${DEVICE1_RPC:-http://127.0.0.1:8545}"
DEVICE2_RPC="${DEVICE2_RPC:-http://127.0.0.1:8546}"
CHAIN_ID="${CHAIN_ID:-12345}"

rpc_call() {
    local url="$1" method="$2" params="${3:-[]}"
    curl -s --max-time 3 -X POST "$url" \
        -H "Content-Type: application/json" \
        -d "{\"jsonrpc\":\"2.0\",\"method\":\"$method\",\"params\":$params,\"id\":1}"
}

parse_result() {
    python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('result','ERROR'))" 2>/dev/null || echo "ERROR"
}

echo ""
echo "============================================================"
echo " LogChain Network Verification"
echo "============================================================"

# --- Device 1 ---
echo ""
echo "[ Device 1 - Primary ]"
D1_BLOCK=$(rpc_call "$DEVICE1_RPC" "eth_blockNumber" | python3 -c "import sys,json; d=json.load(sys.stdin); print(int(d['result'],16))" 2>/dev/null || echo "-1")
D1_CHAIN=$(rpc_call "$DEVICE1_RPC" "eth_chainId"    | python3 -c "import sys,json; d=json.load(sys.stdin); print(int(d['result'],16))" 2>/dev/null || echo "-1")
D1_PEERS=$(rpc_call "$DEVICE1_RPC" "net_peerCount"  | python3 -c "import sys,json; d=json.load(sys.stdin); print(int(d['result'],16))" 2>/dev/null || echo "-1")

if [ "$D1_BLOCK" != "-1" ]; then
    echo "  Status:    RUNNING"
    echo "  Block:     $D1_BLOCK"
    echo "  Chain ID:  $D1_CHAIN"
    echo "  Peers:     $D1_PEERS"
    D1_OK=true
    if [ "$D1_CHAIN" = "$CHAIN_ID" ]; then
        echo "  Chain ID:  [PASS] Matches expected $CHAIN_ID"
    else
        echo "  Chain ID:  [FAIL] Expected $CHAIN_ID, got $D1_CHAIN"
    fi
else
    echo "  Status:    NOT RUNNING"
    D1_OK=false
fi

# --- Device 2 ---
echo ""
echo "[ Device 2 - Independent Validator ]"
D2_BLOCK=$(rpc_call "$DEVICE2_RPC" "eth_blockNumber" | python3 -c "import sys,json; d=json.load(sys.stdin); print(int(d['result'],16))" 2>/dev/null || echo "-1")
D2_CHAIN=$(rpc_call "$DEVICE2_RPC" "eth_chainId"    | python3 -c "import sys,json; d=json.load(sys.stdin); print(int(d['result'],16))" 2>/dev/null || echo "-1")

if [ "$D2_BLOCK" != "-1" ]; then
    echo "  Status:    RUNNING"
    echo "  Block:     $D2_BLOCK"
    echo "  Chain ID:  $D2_CHAIN"
    D2_OK=true
    # Check sync
    DIFF=$(( D1_BLOCK - D2_BLOCK ))
    if [ "$DIFF" -le 2 ]; then
        echo "  Sync:      [PASS] Synchronized (diff=$DIFF blocks)"
    else
        echo "  Sync:      [WARN] Behind by $DIFF blocks"
    fi
else
    echo "  Status:    BLOCKED (Device 2 not reachable from this machine)"
    echo "  Note:      This is expected if Device 2 is a separate physical machine."
    D2_OK=false
fi

# --- Summary ---
echo ""
echo "============================================================"
echo " Summary"
echo "============================================================"
echo "  Device 1 Geth:     $( $D1_OK && echo 'PASS' || echo 'FAIL')"
echo "  Device 2 Geth:     $( $D2_OK && echo 'PASS' || echo 'BLOCKED')"
echo "  Peer Count (D1):   ${D1_PEERS:-N/A}"
echo "  Contract:          ${CONTRACT_ADDRESS:-NOT DEPLOYED}"
echo ""

if $D1_OK; then
    echo "[PASS] Device 1 is operational. Blockchain ready."
    exit 0
else
    echo "[FAIL] Device 1 is not running. Start it first."
    exit 1
fi
