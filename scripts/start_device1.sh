#!/usr/bin/env bash
# LogChain - Start Device 1 (Primary Node + Backend)
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
echo " LogChain - Starting Device 1 (Primary Node)"
echo "============================================================"
echo " Chain ID:  $CHAIN_ID"
echo " RPC:       http://$DEVICE1_IP:$RPC_PORT"
echo " P2P:       $DEVICE1_IP:$P2P_PORT"
echo " Data Dir:  $DATA_DIR"
echo "============================================================"

# Check geth installed
if ! command -v geth &> /dev/null; then
    echo "[ERROR] geth not found. Install: https://geth.ethereum.org/downloads"
    exit 1
fi

# Initialize if needed
if [ ! -d "$DATA_DIR/geth" ]; then
    echo "[*] Initializing genesis block..."
    geth --datadir "$DATA_DIR" init "$ROOT_DIR/genesis.json"
    echo "[+] Genesis initialized"
fi

# Check for JWT secret (create if missing)
JWT_FILE="$DATA_DIR/jwtsecret"
if [ ! -f "$JWT_FILE" ]; then
    openssl rand -hex 32 > "$JWT_FILE"
    echo "[+] JWT secret created: $JWT_FILE"
fi

# Start geth (Clique PoA)
echo "[*] Starting geth node..."
geth \
    --datadir "$DATA_DIR" \
    --networkid "$CHAIN_ID" \
    --port "$P2P_PORT" \
    --http \
    --http.addr "0.0.0.0" \
    --http.port "$RPC_PORT" \
    --http.api "eth,net,web3,personal,clique" \
    --http.corsdomain "*" \
    --http.vhosts "*" \
    --allow-insecure-unlock \
    --unlock "${BLOCKCHAIN_ACCOUNT:-}" \
    --password <(echo "${BLOCKCHAIN_PASSWORD:-}") \
    --mine \
    --miner.etherbase "${BLOCKCHAIN_ACCOUNT:-}" \
    --syncmode "full" \
    --gcmode "archive" \
    --nodiscover \
    --maxpeers 5 \
    --verbosity 3 \
    2>&1 | tee "$DATA_DIR/node1.log" &

NODE_PID=$!
echo "[+] Geth started with PID: $NODE_PID"
echo "$NODE_PID" > "$DATA_DIR/node1.pid"

sleep 3
if kill -0 "$NODE_PID" 2>/dev/null; then
    echo "[+] Device 1 Geth: RUNNING"
    echo "[+] RPC available at: http://$DEVICE1_IP:$RPC_PORT"
else
    echo "[ERROR] Geth failed to start. Check $DATA_DIR/node1.log"
    exit 1
fi
