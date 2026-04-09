#!/bin/bash
echo "======================================"
echo "  STOPPING ALL LOGCHAIN SERVICES"
echo "======================================"

pkill -f geth
pkill -f app.py
pkill -f app_auth.py
pkill -f watcher.py
pkill -f watcher_multiuser.py
pkill -f dashboard_app.py
pkill -f monitor.py

sleep 2

# Verify everything stopped
echo ""
if pgrep -f geth > /dev/null; then
  echo "⚠️  Geth still running — force killing..."
  pkill -9 -f geth
else
  echo "✅ Geth stopped"
fi

if pgrep -f "app_auth.py\|app.py" > /dev/null; then
  echo "⚠️  Flask still running — force killing..."
  pkill -9 -f app_auth.py
  pkill -9 -f app.py
else
  echo "✅ Flask stopped"
fi

if pgrep -f "watcher_multiuser.py\|watcher.py" > /dev/null; then
  echo "⚠️  Watcher still running — force killing..."
  pkill -9 -f watcher_multiuser.py
  pkill -9 -f watcher.py
else
  echo "✅ Watcher stopped"
fi

echo ""
echo "======================================"
echo "ALL SERVICES STOPPED on PC1!"
echo "Tell your friend to run ~/stop_node2.sh"
echo "======================================"
