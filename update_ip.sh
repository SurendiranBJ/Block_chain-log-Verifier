#!/bin/bash
# Get current IPs
PC1_IP=$(ip addr show wlan0 | grep "inet " | awk '{print $2}' | cut -d'/' -f1)
echo "PC1 IP detected: $PC1_IP"
echo "Enter PC2 IP:"
read PC2_IP

# Update all files
sed -i "s|http://[0-9.]*:8545|http://$PC1_IP:8545|g" ~/logchain/app.py
sed -i "s|http://[0-9.]*:8545|http://$PC1_IP:8545|g" ~/logchain/watcher.py
sed -i "s|http://[0-9.]*:8545|http://$PC1_IP:8545|g" ~/logchain/hash_and_submit.py
sed -i "s|http://[0-9.]*:8545|http://$PC1_IP:8545|g" ~/logchain/deploy_v2.py
sed -i "s|http://[0-9.]*:8545|http://$PC1_IP:8545|g" ~/logchain/hardhat.config.js
sed -i "s|http://[0-9.]*:8546|http://$PC2_IP:8546|g" ~/logchain/watcher.py

# Update startup scripts
sed -i "s/[0-9]\{1,3\}\.[0-9]\{1,3\}\.[0-9]\{1,3\}\.[0-9]\{1,3\}:30312/$PC2_IP:30312/g" ~/start_nodes.sh
sed -i "s/[0-9]\{1,3\}\.[0-9]\{1,3\}\.[0-9]\{1,3\}\.[0-9]\{1,3\}:30311/$PC1_IP:30311/g" ~/start_node2.sh

# Update node labels in dashboard
sed -i "s/Node 1 ([0-9.]*)/Node 1 ($PC1_IP)/g" ~/logchain/app.py
sed -i "s/Node 2 ([0-9.]*)/Node 2 ($PC2_IP)/g" ~/logchain/app.py

echo ""
echo "======================================"
echo "All files updated!"
echo "PC1: $PC1_IP"
echo "PC2: $PC2_IP"
echo "Dashboard: http://$PC1_IP:5000"
echo "======================================"
