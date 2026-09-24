#!/usr/bin/env bash
# LogChain - Connect Device 1 and Device 2 as P2P Peers
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

if [ -f "$ROOT_DIR/.env" ]; then source "$ROOT_DIR/.env"; fi

DEVICE1_RPC="${DEVICE1_RPC:-http://127.0.0.1:8545}"
DEVICE2_RPC="${DEVICE2_RPC:-http://127.0.0.1:8546}"
DEVICE2_IP="${DEVICE2_IP:-127.0.0.1}"

echo "============================================================"
echo " LogChain - Connecting Peers"
echo "============================================================"

# Get Device 2 enode
echo "[*] Getting Device 2 enode..."
ENODE2=$(curl -s -X POST "$DEVICE2_RPC" \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","method":"admin_nodeInfo","params":[],"id":1}' \
    | python3 -c "import sys, json; d=json.load(sys.stdin); print(d['result']['enode'])" 2>/dev/null || echo "")

if [ -z "$ENODE2" ]; then
    echo "[ERROR] Could not get Device 2 enode. Is Device 2 running?"
    exit 1
fi

# Replace localhost/127.0.0.1 with actual Device 2 IP
ENODE2=$(echo "$ENODE2" | sed "s/127.0.0.1/$DEVICE2_IP/g")
ENODE2=$(echo "$ENODE2" | sed "s/\[::\]/$DEVICE2_IP/g")

echo "[+] Device 2 enode: ${ENODE2:0:60}..."

# Add Device 2 as peer on Device 1
echo "[*] Adding Device 2 as peer on Device 1..."
RESULT=$(curl -s -X POST "$DEVICE1_RPC" \
    -H "Content-Type: application/json" \
    -d "{\"jsonrpc\":\"2.0\",\"method\":\"admin_addPeer\",\"params\":[\"$ENODE2\"],\"id\":1}")

echo "[+] Peer add result: $RESULT"

sleep 5

# Verify peer count on Device 1
PEERS=$(curl -s -X POST "$DEVICE1_RPC" \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","method":"net_peerCount","params":[],"id":1}' \
    | python3 -c "import sys, json; d=json.load(sys.stdin); print(int(d['result'],16))" 2>/dev/null || echo "0")

echo ""
if [ "$PEERS" -ge 1 ]; then
    echo "[+] SUCCESS: Device 1 has $PEERS peer(s)"
else
    echo "[WARN] Peer count: $PEERS. Peers may still be connecting. Run verify_network.sh to check."
fi
