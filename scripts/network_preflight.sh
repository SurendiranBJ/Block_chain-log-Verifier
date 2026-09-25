#!/usr/bin/env bash
# LogChain - Network & Port Pre-Flight Check (Bash)
set -euo pipefail

ROLE="${1:-device1}"
PEER_IP="${2:-}"

echo "============================================================"
echo " LogChain - Network Pre-Flight Check (Role: $ROLE)"
echo "============================================================"

# 1. Local IPv4 Addresses
echo ""
echo "[*] Local IPv4 Addresses:"
if command -v hostname &>/dev/null && hostname -I &>/dev/null; then
    for ip in $(hostname -I); do
        if [[ ! "$ip" =~ ^127\. ]]; then
            echo "    - $ip"
        fi
    done
elif command -v ip &>/dev/null; then
    ip -4 addr show | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | grep -v '127.0.0.1' | while read -r line; do
        echo "    - $line"
    done
else
    ifconfig 2>/dev/null | grep -E 'inet [0-9]' | awk '{print "    - " $2}' || true
fi

# 2. Peer Reachability
if [ -n "$PEER_IP" ]; then
    echo ""
    echo "[*] Checking Peer Reachability ($PEER_IP)..."
    if ping -c 2 -W 2 "$PEER_IP" &>/dev/null; then
        echo "  [PASS] Ping to peer $PEER_IP succeeded."
    else
        echo "  [WARN] Ping to peer $PEER_IP failed (may be blocked by ICMP firewall rules)."
    fi
fi

# 3. Port Check Function
test_port() {
    local port="$1"
    local name="$2"
    if command -v nc &>/dev/null; then
        if nc -z -w 1 127.0.0.1 "$port" 2>/dev/null; then
            echo "  [LISTENING] Port $port ($name) is ACTIVE"
        else
            echo "  [AVAILABLE] Port $port ($name) is not currently listening"
        fi
    elif command -v curl &>/dev/null; then
        if curl -s -m 1 "http://127.0.0.1:$port" &>/dev/null; then
            echo "  [LISTENING] Port $port ($name) is ACTIVE"
        else
            echo "  [AVAILABLE] Port $port ($name) is not listening"
        fi
    fi
}

echo ""
echo "[*] Checking Local Ports:"
if [ "$ROLE" == "device1" ]; then
    test_port 30303 "Device 1 P2P"
    test_port 8545  "Device 1 RPC"
    test_port 5000  "Flask Dashboard & Ingest"
    test_port 27017 "MongoDB (localhost only)"
elif [ "$ROLE" == "device2" ]; then
    test_port 30304 "Device 2 P2P"
    test_port 8546  "Device 2 RPC"
fi

# 4. Toolchain Check
echo ""
echo "[*] Toolchain Verification:"
for cmd in python3 git curl; do
    if command -v "$cmd" &>/dev/null; then
        echo "  [PASS] $cmd found"
    else
        echo "  [FAIL] $cmd not found"
    fi
done

# 5. Geth Compatibility Check
echo ""
echo "[*] Geth Version Check:"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/check_geth_version.sh" ]; then
    bash "$SCRIPT_DIR/check_geth_version.sh" || true
fi

echo "============================================================"
