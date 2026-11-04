#!/usr/bin/env bash
# Ubuntu/macOS local launch. Run from any directory; no Docker or MongoDB required.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
mode="ethereum"
run_demo=false
for arg in "$@"; do
  case "$arg" in
    --simulate) mode="--simulate" ;;
    --demo) run_demo=true ;;
    *) echo "Usage: bash scripts/start_local.sh [--simulate] [--demo]"; exit 2 ;;
  esac
done
if [[ "$mode" != "ethereum" && "$mode" != "--simulate" ]]; then
  echo 'Usage: bash scripts/start_local.sh [--simulate]'
  exit 2
fi
export PYTHONUNBUFFERED=1
pids=()
cleanup() {
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM
if [[ "$mode" == "--simulate" ]]; then
  py=python3
  data=runtime-simulation
  flags=(--simulate)
else
  if [[ ! -x .venv/bin/python ]]; then python3 -m venv .venv; fi
  py=.venv/bin/python
  "$py" -m pip install -r requirements-local.txt
  "$py" scripts/download_geth.py
  data=runtime
  flags=()
fi
mkdir -p "$data"
chmod 700 "$data"
if [[ "$mode" == "ethereum" ]]; then
  if [[ ! -f "$data/chain.json" ]]; then "$py" -m localchain.setup init --data "$data"; fi
  "$py" -m localchain.setup start --data "$data" > "$data/node-console.log" 2>&1 &
  pids+=("$!")
  "$py" - <<'PY'
import json,time
from urllib.request import Request,urlopen
for attempt in range(60):
    try:
        request=Request('http://127.0.0.1:8545',data=json.dumps({'jsonrpc':'2.0','id':1,'method':'eth_blockNumber','params':[]}).encode(),headers={'Content-Type':'application/json'})
        with urlopen(request,timeout=2) as response:
            result=json.load(response)
        if int(result.get('result','0x0'),16)>0:
            break
    except Exception:
        pass
    time.sleep(1)
else:
    raise SystemExit('Node did not seal a block. Inspect runtime/node-console.log.')
PY
  if "$py" -c 'import json,sys;sys.exit(bool(json.load(open("runtime/chain.json")).get("contract")))'; then
    "$py" -m localchain.setup deploy --data "$data"
  fi
fi
"$py" -m localchain.server --data "$data" "${flags[@]}" &
pids+=("$!")
"$py" - <<'PY'
import time
from urllib.request import urlopen
for attempt in range(30):
    try:
        if urlopen('http://127.0.0.1:8080',timeout=2).status==200:
            break
    except Exception:
        pass
    time.sleep(1)
else:
    raise SystemExit('Dashboard did not start. Check whether port 8080 is in use.')
PY
if [[ "$run_demo" == true ]]; then
  "$py" -m localchain.demo --data "$data" &
  pids+=("$!")
  echo "Optional demo: http://127.0.0.1:8081 (existing token workspace only)"
fi
echo "Dashboard: http://127.0.0.1:8080"
echo "Create your account and connect your project on the dashboard."
echo "Read your login token locally: cat $data/admin.token"
echo 'Press Ctrl+C to stop. Data and commitments are preserved.'
wait
