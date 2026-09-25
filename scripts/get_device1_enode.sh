#!/usr/bin/env bash
# LogChain - Get Device 1 Enode via Local IPC (No Public Admin RPC)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

if [ -f "$ROOT_DIR/.env" ]; then
    source "$ROOT_DIR/.env"
fi

DEVICE1_IP="${DEVICE1_IP:-127.0.0.1}"

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
if [ -S "$ROOT_DIR/node1_data/geth.ipc" ]; then
    IPC_PATH="$ROOT_DIR/node1_data/geth.ipc"
elif [ -S "$ROOT_DIR/node1_data/geth1.ipc" ]; then
    IPC_PATH="$ROOT_DIR/node1_data/geth1.ipc"
elif [ -e "\\\\.\\pipe\\geth1.ipc" ] 2>/dev/null; then
    IPC_PATH="\\\\.\\pipe\\geth1.ipc"
elif [ -e "\\\\.\\pipe\\geth.ipc" ] 2>/dev/null; then
    IPC_PATH="\\\\.\\pipe\\geth.ipc"
else
    # Default POSIX datadir check
    IPC_PATH="$ROOT_DIR/node1_data/geth.ipc"
fi

RAW_ENODE=$("$GETH_BIN" --exec "admin.nodeInfo.enode" attach "$IPC_PATH" 2>/dev/null | tr -d '"' || true)

if [ -z "$RAW_ENODE" ] || [[ "$RAW_ENODE" == *"Error"* ]]; then
    echo "[FAIL] Could not query Device 1 enode via local IPC ($IPC_PATH)."
    echo "       Is Device 1 Geth running? Check: ./scripts/start_device1.sh"
    exit 1
fi

# Replace 127.0.0.1 or [::] with actual advertised LAN IP
PUBLIC_ENODE=$(echo "$RAW_ENODE" | sed -E "s/(@)(127\.0\.0\.1|\[::\]|0\.0\.0\.0)(:)/\1${DEVICE1_IP}\3/")

echo "$PUBLIC_ENODE"
