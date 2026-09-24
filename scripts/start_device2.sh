#!/usr/bin/env bash
# LogChain - Start Device 2 (Independent Validator Node)
# Usage: ./scripts/start_device2.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

if [ -f "$ROOT_DIR/.env" ]; then
    source "$ROOT_DIR/.env"
fi

DEVICE2_IP="${DEVICE2_IP:-127.0.0.1}"
CHAIN_ID="${CHAIN_ID:-12345}"
DATA_DIR="${ROOT_DIR}/node2_data"
P2P_PORT=30304
RPC_PORT=8546

echo "============================================================"
echo " LogChain - Starting Device 2 (Independent Validator Node)"
echo "============================================================"

if ! command -v geth &> /dev/null; then
    echo "[ERROR] geth not found."
    exit 1
fi

DEVICE2_ACCOUNT="${DEVICE2_ACCOUNT:-${BLOCKCHAIN_ACCOUNT:-}}"
if [ -z "$DEVICE2_ACCOUNT" ]; then
    echo "[FAIL] DEVICE2_ACCOUNT not configured in .env"
    echo "Run: python scripts/setup_private_chain.py"
    exit 1
fi
echo "[PASS] Device 2 Validator account configured: $DEVICE2_ACCOUNT"

PWD_FILE="$DATA_DIR/password.txt"
if [ ! -f "$PWD_FILE" ]; then
    if [ -n "${DEVICE2_PASSWORD:-${BLOCKCHAIN_PASSWORD:-}}" ]; then
        mkdir -p "$DATA_DIR"
        echo "${DEVICE2_PASSWORD:-${BLOCKCHAIN_PASSWORD:-}}" > "$PWD_FILE"
        chmod 600 "$PWD_FILE" 2>/dev/null || true
    fi
fi

if [ ! -d "$DATA_DIR/geth" ]; then
    echo "[*] Initializing genesis block on Device 2..."
    geth --datadir "$DATA_DIR" init "$ROOT_DIR/genesis.json"
fi
echo "[PASS] Genesis initialized"

# Start Geth as independent validator (Clique signer)
echo "[*] Starting Geth Device 2 validator node..."
if [ -f "$PWD_FILE" ]; then
    geth \
        --datadir "$DATA_DIR" \
        --networkid "$CHAIN_ID" \
        --port "$P2P_PORT" \
        --http \
        --http.addr "0.0.0.0" \
        --http.port "$RPC_PORT" \
        --http.api "eth,net,web3" \
        --http.corsdomain "*" \
        --http.vhosts "*" \
        --allow-insecure-unlock \
        --unlock "$DEVICE2_ACCOUNT" \
        --password "$PWD_FILE" \
        --mine \
        --miner.etherbase "$DEVICE2_ACCOUNT" \
        --syncmode "full" \
        --gcmode "archive" \
        --nodiscover \
        --maxpeers 5 \
        --verbosity 3 \
        2>&1 | tee "$DATA_DIR/node2.log" &
else
    # Replica mode if password file absent
    geth \
        --datadir "$DATA_DIR" \
        --networkid "$CHAIN_ID" \
        --port "$P2P_PORT" \
        --http \
        --http.addr "0.0.0.0" \
        --http.port "$RPC_PORT" \
        --http.api "eth,net,web3" \
        --http.corsdomain "*" \
        --http.vhosts "*" \
        --syncmode "full" \
        --gcmode "archive" \
        --nodiscover \
        --maxpeers 5 \
        --verbosity 3 \
        2>&1 | tee "$DATA_DIR/node2.log" &
fi

NODE_PID=$!
echo "$NODE_PID" > "$DATA_DIR/node2.pid"

sleep 3
if kill -0 "$NODE_PID" 2>/dev/null; then
    echo "[PASS] Device 2 Geth: RUNNING (PID: $NODE_PID)"
    echo "[PASS] RPC reachable at: http://$DEVICE2_IP:$RPC_PORT"
else
    echo "[FAIL] Geth Device 2 failed to start. Check $DATA_DIR/node2.log"
    exit 1
fi
