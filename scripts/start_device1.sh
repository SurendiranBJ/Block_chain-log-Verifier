#!/usr/bin/env bash
# LogChain - Start Device 1 (Primary Validator Node)
# Usage: ./scripts/start_device1.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Load environment
if [ -f "$ROOT_DIR/.env" ]; then
    source "$ROOT_DIR/.env"
fi

DEVICE1_IP="${DEVICE1_IP:-127.0.0.1}"
CHAIN_ID="${CHAIN_ID:-12345}"
DATA_DIR="${ROOT_DIR}/node1_data"
P2P_PORT=30303
RPC_PORT=8545

echo "============================================================"
echo " LogChain - Starting Device 1 (Primary Validator Node)"
echo "============================================================"

# Locate compatible Geth binary (prioritizes pinned ./bin/geth)
GETH_BIN=""
if [ -x "$ROOT_DIR/bin/geth" ]; then
    GETH_BIN="$ROOT_DIR/bin/geth"
elif [ -f "$ROOT_DIR/bin/geth.exe" ]; then
    GETH_BIN="$ROOT_DIR/bin/geth.exe"
elif command -v geth &> /dev/null; then
    GETH_BIN="$(command -v geth)"
else
    echo "[ERROR] geth not found. Run: python scripts/download_geth.py"
    exit 1
fi

# Check version compatibility: Clique PoA requires Geth < 1.14
GETH_VER_STR="$("$GETH_BIN" version 2>&1 | grep -i "Version:" || "$GETH_BIN" version 2>&1 | head -n 1)"
echo "[*] Using Geth: $GETH_BIN ($GETH_VER_STR)"
if echo "$GETH_VER_STR" | grep -qE "Version:\s*1\.(1[4-9]|[2-9][0-9])"; then
    echo "[FAIL] Detected Geth >= 1.14. Clique PoA block sealing is not supported in Geth v1.14+."
    echo "       Run: python scripts/download_geth.py to install compatible pinned Geth v1.13.15 into ./bin/"
    exit 1
fi

# 1. Check validator account
if [ -z "${BLOCKCHAIN_ACCOUNT:-}" ]; then
    echo "[FAIL] BLOCKCHAIN_ACCOUNT not configured in .env"
    echo "Run: python scripts/setup_private_chain.py"
    exit 1
fi
echo "[PASS] Validator account configured: $BLOCKCHAIN_ACCOUNT"

# 2. Check password file
PWD_FILE="$DATA_DIR/password.txt"
if [ ! -f "$PWD_FILE" ]; then
    if [ -n "${BLOCKCHAIN_PASSWORD:-}" ]; then
        mkdir -p "$DATA_DIR"
        echo "${BLOCKCHAIN_PASSWORD}" > "$PWD_FILE"
        chmod 600 "$PWD_FILE" 2>/dev/null || true
    else
        echo "[FAIL] Neither $PWD_FILE nor BLOCKCHAIN_PASSWORD configured."
        echo "Run: python scripts/setup_private_chain.py"
        exit 1
    fi
fi

# 3. Genesis initialization
if [ ! -d "$DATA_DIR/geth" ]; then
    echo "[*] Initializing genesis block..."
    "$GETH_BIN" --datadir "$DATA_DIR" init "$ROOT_DIR/genesis.json"
fi
echo "[PASS] Genesis initialized"

# 4. Start Geth (Restricted HTTP API: eth,net,web3 for security)
echo "[*] Starting Geth validator node..."
"$GETH_BIN" \
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
    --unlock "${BLOCKCHAIN_ACCOUNT}" \
    --password "$PWD_FILE" \
    --mine \
    --miner.etherbase "${BLOCKCHAIN_ACCOUNT}" \
    --syncmode "full" \
    --gcmode "archive" \
    --nodiscover \
    --maxpeers 5 \
    --verbosity 3 \
    2>&1 | tee "$DATA_DIR/node1.log" &

NODE_PID=$!
echo "$NODE_PID" > "$DATA_DIR/node1.pid"

sleep 3
if kill -0 "$NODE_PID" 2>/dev/null; then
    echo "[PASS] Geth started (PID: $NODE_PID)"
    echo "[PASS] RPC reachable at http://$DEVICE1_IP:$RPC_PORT"
else
    echo "[FAIL] Geth failed to start. Check $DATA_DIR/node1.log"
    exit 1
fi
