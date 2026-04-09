#!/bin/bash

echo "======================================"
echo "  LOGCHAIN STARTUP SCRIPT"
echo "======================================"

# Step 1 — Detect current PC1 IP
PC1_IP=$(ip addr show wlan0 2>/dev/null | grep "inet " | awk '{print $2}' | cut -d'/' -f1)
if [ -z "$PC1_IP" ]; then
  PC1_IP=$(hostname -I | awk '{print $1}')
fi
echo "PC1 IP: $PC1_IP"

# Step 2 — Ask for PC2 IP
echo ""
echo "Enter PC2 IP (press Enter to use last known):"
read INPUT_IP
if [ -z "$INPUT_IP" ]; then
  PC2_IP=$(grep -o '[0-9]\{1,3\}\.[0-9]\{1,3\}\.[0-9]\{1,3\}\.[0-9]\{1,3\}' ~/logchain/watcher.py | grep "8546" | head -1 | cut -d':' -f1)
  if [ -z "$PC2_IP" ]; then PC2_IP="10.80.255.234"; fi
  echo "Using last known PC2 IP: $PC2_IP"
else
  PC2_IP=$INPUT_IP
fi

# Step 3 — Update all IPs in all files
echo ""
echo "Updating IPs in all files..."
for f in ~/logchain/app.py ~/logchain/app_auth.py ~/logchain/watcher.py ~/logchain/watcher_multiuser.py ~/logchain/hash_and_submit.py ~/logchain/deploy_v2.py ~/logchain/hardhat.config.js; do
  if [ -f "$f" ]; then
    sed -i "s|http://[0-9.]*:8545|http://$PC1_IP:8545|g" "$f"
    sed -i "s|http://[0-9.]*:8546|http://$PC2_IP:8546|g" "$f"
    sed -i "s/Node 1 ([0-9.]*)/Node 1 ($PC1_IP)/g" "$f"
    sed -i "s/Node 2 ([0-9.]*)/Node 2 ($PC2_IP)/g" "$f"
  fi
done
echo "IPs updated!"

# Step 4 — Kill old processes
echo ""
echo "Killing old processes..."
pkill -f geth
pkill -f app.py
pkill -f app_auth.py
pkill -f watcher.py
pkill -f watcher_multiuser.py
pkill -f dashboard_app.py
sleep 3

# Step 5 — Start Node 1
echo "Starting Node 1..."
nohup geth --datadir ~/logchain/node1 \
  --networkid 12345 \
  --port 30311 \
  --http --http.addr "0.0.0.0" \
  --http.port 8545 \
  --http.api "eth,net,web3,personal,miner,clique,admin" \
  --http.corsdomain "*" \
  --unlock 0x8b629ce3BB085B061D95C7f0d14d2BF63ECbA758 \
  --password ~/logchain/node1/password.txt \
  --mine \
  --miner.etherbase 0x8b629ce3BB085B061D95C7f0d14d2BF63ECbA758 \
  --allow-insecure-unlock \
  --nodiscover \
  > ~/logchain/node1.log 2>&1 &

echo "Waiting for node to start..."
sleep 10

# Step 6 — Add PC2 as peer
echo "Connecting to PC2 ($PC2_IP)..."
curl -s -X POST http://127.0.0.1:8545 \
  -H "Content-Type: application/json" \
  --data "{\"jsonrpc\":\"2.0\",\"method\":\"admin_addPeer\",\"params\":[\"enode://c6167d79f0d9c624b15bb08d814aef489010b6c0defbac127b4ed4bd799e4d0191cb11c018c7f9ea3ae1a495a42e6019d8847471e0de62b3ab18d9091d4cf80a@$PC2_IP:30312\"],\"id\":1}"

sleep 3
PEERS=$(curl -s -X POST http://127.0.0.1:8545 \
  -H "Content-Type: application/json" \
  --data '{"jsonrpc":"2.0","method":"net_peerCount","params":[],"id":1}')
echo "Peer status: $PEERS"

# Step 7 — Ensure MongoDB is running
echo ""
echo "Checking MongoDB..."
if ! pgrep -x mongod > /dev/null; then
  echo "Starting MongoDB..."
  sudo systemctl start mongod 2>/dev/null || sudo service mongod start 2>/dev/null || echo "⚠️  Could not auto-start mongod. Please start it manually."
else
  echo "✅ MongoDB is running"
fi

# Step 8 — Ensure admin user exists in MongoDB
echo "Ensuring admin user exists..."
python3 -c "
from models import Database
try:
    db = Database()
    if not db.get_user_by_username('admin'):
        db.create_user('admin', 'admin123', 'admin@example.com', 'admin')
        print('✅ Default admin user created: admin / admin123')
    else:
        print('✅ Admin user already exists')
except Exception as e:
    print(f'⚠️  MongoDB check: {e}')
" 2>/dev/null

# Step 9 — Start Multi-User Watcher Daemon
echo ""
echo "Starting Multi-User Watcher Daemon..."
cd ~/logchain && nohup python3 watcher_multiuser.py > ~/logchain/watcher_multiuser.log 2>&1 &
sleep 2

# Step 10 — Start Flask Auth App
echo "Starting Flask Auth App..."
cd ~/logchain && nohup python3 app_auth.py > ~/logchain/app_auth.log 2>&1 &
sleep 3

echo ""
echo "======================================"
echo "ALL SERVICES STARTED!"
echo "Dashboard:  http://$PC1_IP:5000"
echo "Login:      http://$PC1_IP:5000/login"
echo "Admin:      admin / admin123"
echo "======================================"
echo ""
echo "Useful commands:"
echo "  tail -f ~/logchain/node1.log              # geth logs"
echo "  tail -f ~/logchain/app_auth.log           # flask auth logs"
echo "  tail -f ~/logchain/watcher_multiuser.log  # watcher logs"
echo "  pgrep -f geth                             # check geth running"
echo "  pgrep -f app_auth.py                      # check flask running"
echo "  pgrep -f watcher_multiuser.py             # check watcher running"
