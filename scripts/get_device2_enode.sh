#!/usr/bin/env bash
# LogChain - Get Device 2 Enode via Local IPC (No Public Admin RPC)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

if [ -f "$ROOT_DIR/.env" ]; then
    source "$ROOT_DIR/.env"
fi

DEVICE2_IP="${DEVICE2_IP:-127.0.0.1}"

# Find Geth binary
if [ -x "$ROOT_DIR/bin/geth" ]; then
    GETH_BIN="$ROOT_DIR/bin/geth"
elif [ -f "$ROOT_DIR/bin/geth.exe" ]; then
    GETH_BIN="$ROOT_DIR/bin/geth.exe"
elif command -v geth &> /dev/null; then
    GETH_BIN="$(command -v geth)"
else
    echo "[ERROR] geth binary not found."
    exit 1
fi

# Locate IPC endpoint
IPC_PATH=""
if [ -S "$ROOT_DIR/node2_data/geth2.ipc" ]; then
    IPC_PATH="$ROOT_DIR/node2_data/geth2.ipc"
elif [ -S "$ROOT_DIR/node2_data/geth.ipc" ]; then
    IPC_PATH="$ROOT_DIR/node2_data/geth.ipc"
elif [ -e "\\\\.\\pipe\\geth2.ipc" ] 2>/dev/null; then
    IPC_PATH="\\\\.\\pipe\\geth2.ipc"
elif [ -e "\\\\.\\pipe\\geth.ipc" ] 2>/dev/null; then
    IPC_PATH="\\\\.\\pipe\\geth.ipc"
else
    IPC_PATH="$ROOT_DIR/node2_data/geth2.ipc"
fi

RAW_ENODE=$("$GETH_BIN" --exec "admin.nodeInfo.enode" attach "$IPC_PATH" 2>/dev/null | tr -d '"' || true)

if [ -z "$RAW_ENODE" ] || [[ "$RAW_ENODE" == *"Error"* ]]; then
    echo "[FAIL] Could not query Device 2 enode via local IPC ($IPC_PATH)."
    echo "       Is Device 2 Geth running? Check: ./scripts/start_device2.sh"
    exit 1
fi

# Replace loopback address with advertised LAN IP
PUBLIC_ENODE=$(echo "$RAW_ENODE" | sed -E "s/(@)(127\.0\.0\.1|\[::\]|0\.0\.0\.0)(:)/\1${DEVICE2_IP}\3/")

echo "$PUBLIC_ENODE"
