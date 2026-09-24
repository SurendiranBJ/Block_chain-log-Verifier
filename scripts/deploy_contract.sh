#!/usr/bin/env bash
# LogChain - Safe contract deployment wrapper
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$ROOT_DIR"

if command -v python3 &>/dev/null; then
    python3 scripts/deploy_contract.py "$@"
elif command -v python &>/dev/null; then
    python scripts/deploy_contract.py "$@"
else
    echo "[ERROR] Python interpreter not found." >&2
    exit 1
fi
