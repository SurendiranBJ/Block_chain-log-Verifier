#!/usr/bin/env bash
# LogChain - Start Device 2 (Independent Validator)
# Usage: ./scripts/start_device2.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

if [ -f "$ROOT_DIR/.env" ]; then source "$ROOT_DIR/.env"; fi

DEVICE2_IP="${DEVICE2_IP:-127.0.0.1}"
CHAIN_ID="${CHAIN_ID:-12345}"
DATA_DIR="${ROOT_DIR}/node2_data"
P2P_PORT=30304
RPC_PORT=8546

echo "============================================================"
echo " LogChain - Starting Device 2 (Independent Validator)"
echo "============================================================"
echo " Chain ID:  $CHAIN_ID"
echo " RPC:       http://$DEVICE2_IP:$RPC_PORT"
echo " P2P:       $DEVICE2_IP:$P2P_PORT"
echo " Data Dir:  $DATA_DIR"
echo "============================================================"

if ! command -v geth &> /dev/null; then
    echo "[ERROR] geth not found."
    exit 1
fi

if [ ! -d "$DATA_DIR/geth" ]; then
    echo "[*] Initializing genesis block on Device 2..."
    geth --datadir "$DATA_DIR" init "$ROOT_DIR/genesis.json"
    echo "[+] Genesis initialized"
fi

echo "[*] Starting geth node (Device 2 - read-only validator)..."
geth \
    --datadir "$DATA_DIR" \
    --networkid "$CHAIN_ID" \
    --port "$P2P_PORT" \
    --http \
    --http.addr "0.0.0.0" \
    --http.port "$RPC_PORT" \
    --http.api "eth,net,web3,clique" \
    --http.corsdomain "*" \
    --http.vhosts "*" \
    --syncmode "full" \
    --gcmode "archive" \
    --nodiscover \
    --maxpeers 5 \
    --verbosity 3 \
    2>&1 | tee "$DATA_DIR/node2.log" &

NODE_PID=$!
echo "[+] Geth Device 2 started with PID: $NODE_PID"
echo "$NODE_PID" > "$DATA_DIR/node2.pid"

sleep 3
if kill -0 "$NODE_PID" 2>/dev/null; then
    echo "[+] Device 2 Geth: RUNNING"
    echo "[+] RPC available at: http://$DEVICE2_IP:$RPC_PORT"
    echo ""
    echo "[i] Next: run ./scripts/connect_nodes.sh to peer Device 1 and Device 2"
else
    echo "[ERROR] Geth Device 2 failed to start. Check $DATA_DIR/node2.log"
    exit 1
fi
