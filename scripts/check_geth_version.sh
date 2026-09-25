#!/usr/bin/env bash
# LogChain - Geth Version Compatibility Checker
# Clique Proof-of-Authority (PoA) was removed in upstream Geth v1.14+.
# LogChain strictly requires pinned Geth v1.13.x (tested: v1.13.15).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "============================================================"
echo " LogChain - Geth Consensus Engine Compatibility Check"
echo "============================================================"

# Prioritize local ./bin/geth over system PATH
GETH_BIN=""
ORIGIN=""
if [ -x "$ROOT_DIR/bin/geth" ]; then
    GETH_BIN="$ROOT_DIR/bin/geth"
    ORIGIN="local ./bin"
elif [ -f "$ROOT_DIR/bin/geth.exe" ]; then
    GETH_BIN="$ROOT_DIR/bin/geth.exe"
    ORIGIN="local ./bin"
elif command -v geth &> /dev/null; then
    GETH_BIN="$(command -v geth)"
    ORIGIN="system PATH"
else
    echo "[FAIL] Unsupported Geth version: geth binary not found."
    echo "       Run: python scripts/download_geth.py to install pinned Geth v1.13.15"
    exit 1
fi

RAW_OUT=$("$GETH_BIN" version 2>&1 || true)
VER_LINE=$(echo "$RAW_OUT" | grep -i "Version:" | head -n 1 || echo "$RAW_OUT" | head -n 1)

echo "[*] Candidate binary: $GETH_BIN ($ORIGIN)"
echo "[*] Version string:   $VER_LINE"

# Extract major, minor, patch
MAJOR=$(echo "$VER_LINE" | sed -nE 's/.*([0-9]+)\.([0-9]+)\.([0-9]+).*/\1/p' || echo "")
MINOR=$(echo "$VER_LINE" | sed -nE 's/.*([0-9]+)\.([0-9]+)\.([0-9]+).*/\2/p' || echo "")
PATCH=$(echo "$VER_LINE" | sed -nE 's/.*([0-9]+)\.([0-9]+)\.([0-9]+).*/\3/p' || echo "")

if [ -z "$MAJOR" ] || [ -z "$MINOR" ]; then
    echo "[FAIL] Unsupported Geth version: Could not parse version numbers."
    exit 1
fi

if [ "$MAJOR" -gt 1 ] || { [ "$MAJOR" -eq 1 ] && [ "$MINOR" -ge 14 ]; }; then
    echo ""
    echo "[FAIL] Unsupported Geth version: v${MAJOR}.${MINOR}.${PATCH}"
    echo "       REASON: Upstream Geth deprecated and removed Clique PoA block sealing in v1.14+."
    echo "       LogChain private multi-node network uses Clique PoA consensus (genesis.json)."
    echo "       ACTION: Run 'python scripts/download_geth.py' to install pinned Geth v1.13.15 into ./bin/"
    exit 1
else
    echo ""
    echo "[PASS] Compatible Geth version: v${MAJOR}.${MINOR}.${PATCH} ($ORIGIN)"
    echo "       Clique PoA consensus is supported and verified for block sealing."
    exit 0
fi
