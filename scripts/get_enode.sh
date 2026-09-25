#!/usr/bin/env bash
# LogChain - Get Node Enode via Local IPC (No Public Admin RPC)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_NODE="${1:-1}"

if [ "$TARGET_NODE" = "2" ]; then
    exec "$SCRIPT_DIR/get_device2_enode.sh"
else
    exec "$SCRIPT_DIR/get_device1_enode.sh"
fi
