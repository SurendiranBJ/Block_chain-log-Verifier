# Deployment Checklist & Migration Guide

## Pre-Deployment Checklist

### 1. System Requirements
- [ ] Kali Linux (PC1 and PC2)
- [ ] Python 3.8 or higher
- [ ] MongoDB 4.4 or higher
- [ ] Geth nodes running and synced
- [ ] Smart contracts deployed
- [ ] Network connectivity between PC1 and PC2

### 2. File Preparation
- [ ] All new files copied to ~/logchain/
- [ ] Execute permissions set on .sh scripts
- [ ] Contract ABI files present (LogIntegrityV2_abi.json)
- [ ] Original config.json backed up

### 3. Dependency Installation
- [ ] requirements.txt available
- [ ] MongoDB installed and running
- [ ] Python packages installed (Flask, pymongo, flask-login, web3, watchdog)

## Migration Steps (From Old to New System)

### Step 1: Backup Current System
```bash
cd ~/logchain
mkdir backup_$(date +%Y%m%d)
cp -r *.py *.json templates/ backup_$(date +%Y%m%d)/
```

### Step 2: Copy New Files
```bash
# Copy all new files to ~/logchain/
cp app_auth.py ~/logchain/
cp models.py ~/logchain/
cp watcher_multiuser.py ~/logchain/
cp requirements.txt ~/logchain/
cp setup_multiuser.sh ~/logchain/
cp start_multiuser.sh ~/logchain/
cp -r templates/ ~/logchain/
```

### Step 3: Install Dependencies
```bash
cd ~/logchain
chmod +x setup_multiuser.sh
./setup_multiuser.sh
```

### Step 4: Verify MongoDB
```bash
# Check MongoDB status
sudo systemctl status mongod

# Test connection
python3 -c "from pymongo import MongoClient; client = MongoClient(); print('MongoDB OK')"
```

### Step 5: Initialize Database
```bash
python3 << EOF
from models import Database
db = Database()
print("Database initialized")
print("Admin user: admin/admin123")
EOF
```

### Step 6: Test System
```bash
# Start services
./start_multiuser.sh

# In another terminal, check if running
curl http://localhost:5000
```

### Step 7: Migrate Existing Data (Optional)
```python
# If you have existing log data to migrate:
from models import Database
import json

db = Database()

# Create admin's log entry
with open('config.json', 'r') as f:
    config = json.load(f)

admin = db.get_user_by_username('admin')
if admin:
    log_id, error = db.add_log_source(
        user_id=admin['_id'],
        log_path=config['LOG_FILE'],
        case_id=config['CASE_ID'],
        description='Migrated from original system'
    )
    print(f"Migrated log: {log_id}")
```

## Post-Deployment Configuration

### 1. Change Default Admin Password
```python
from models import Database
from werkzeug.security import generate_password_hash

db = Database()
new_password = "YourSecurePassword123!"  # CHANGE THIS
db.users.update_one(
    {'username': 'admin'},
    {'$set': {'password': generate_password_hash(new_password)}}
)
print("Admin password updated")
```

### 2. Set Environment Variables
```bash
# Create .env file
cat > ~/.logchain_env << EOF
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
MONGODB_URI=mongodb://localhost:27017/
FLASK_ENV=production
EOF

# Load in future sessions
echo "source ~/.logchain_env" >> ~/.bashrc
```

### 3. Configure Firewall
```bash
# Allow Flask port
sudo ufw allow 5000/tcp

# Allow MongoDB (if accessed remotely)
sudo ufw allow 27017/tcp
```

### 4. Setup Autostart (systemd)
```bash
# Create Flask service
sudo nano /etc/systemd/system/logchain-web.service
```

Add:
```ini
[Unit]
Description=LogChain Web Dashboard
After=network.target mongod.service

[Service]
Type=simple
User=sura
WorkingDirectory=/home/sura/logchain
Environment="PATH=/usr/bin:/usr/local/bin"
ExecStart=/usr/bin/python3 /home/sura/logchain/app_auth.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
# Create Watcher service
sudo nano /etc/systemd/system/logchain-monitor.service
```

Add:
```ini
[Unit]
Description=LogChain Log Monitor
After=network.target mongod.service

[Service]
Type=simple
User=sura
WorkingDirectory=/home/sura/logchain
Environment="PATH=/usr/bin:/usr/local/bin"
ExecStart=/usr/bin/python3 /home/sura/logchain/watcher_multiuser.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable logchain-web.service
sudo systemctl enable logchain-monitor.service
sudo systemctl start logchain-web.service
sudo systemctl start logchain-monitor.service
```

## Testing Checklist

### Functional Testing
- [ ] Can access login page (http://localhost:5000)
- [ ] Can login with admin/admin123
- [ ] Dashboard loads without errors
- [ ] Can create new user account
- [ ] New user can login
- [ ] User can add log source
- [ ] Log monitoring starts automatically
- [ ] New entries appear on blockchain
- [ ] Admin can view all users
- [ ] Admin can enable/disable users
- [ ] Statistics update in real-time
- [ ] Activity log shows events

### Integration Testing
- [ ] MongoDB connection stable
- [ ] Blockchain connection stable
- [ ] File monitoring triggers correctly
- [ ] Hashes submitted to blockchain
- [ ] Database updates after submissions
- [ ] Multiple users can monitor simultaneously
- [ ] Sessions persist correctly
- [ ] Logout works properly

### Security Testing
- [ ] Cannot access dashboard without login
- [ ] Regular user cannot access admin panel
- [ ] Passwords are hashed in database
- [ ] Session expires after logout
- [ ] CSRF protection active
- [ ] SQL injection not possible (using MongoDB)
- [ ] XSS protection in templates

## Troubleshooting Guide

### Issue: MongoDB won't start
```bash
# Check logs
sudo tail -f /var/log/mongodb/mongod.log

# Check configuration
sudo nano /etc/mongod.conf

# Restart service
sudo systemctl restart mongod
```

### Issue: Flask app crashes
```bash
# Check Python errors
python3 app_auth.py

# Check dependencies
pip list | grep -i flask
pip list | grep -i pymongo

# Reinstall if needed
pip install --break-system-packages --force-reinstall Flask pymongo flask-login
```

### Issue: Watcher not monitoring
```bash
# Check watcher logs
tail -f watcher.log

# Verify log paths in database
python3 << EOF
from models import Database
db = Database()
logs = db.get_active_logs()
for log in logs:
    print(f"{log['case_id']}: {log['log_path']}")
EOF

# Check file permissions
ls -la /path/to/your/logfile.log
```

### Issue: Cannot connect to blockchain
```bash
# Verify Geth is running
ps aux | grep geth

# Test RPC connection
curl -X POST -H "Content-Type: application/json" \
  --data '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' \
  http://localhost:8545
```

### Issue: Users can't login
```bash
# Check if user exists
python3 << EOF
from models import Database
db = Database()
users = db.get_all_users()
for u in users:
    print(f"{u['username']}: {u['is_active']}")
EOF

# Reset admin password
python3 << EOF
from models import Database
from werkzeug.security import generate_password_hash
db = Database()
db.users.update_one(
    {'username': 'admin'},
    {'$set': {'password': generate_password_hash('admin123')}}
)
print("Password reset to: admin123")
EOF
```

## Performance Optimization

### 1. MongoDB Indexing
```javascript
// In MongoDB shell
use logchain_db

// Create compound index for faster queries
db.logs.createIndex({ "user_id": 1, "is_active": 1 })
db.activities.createIndex({ "user_id": 1, "timestamp": -1 })
```

### 2. Flask Optimization
```python
# In app_auth.py, add caching (install flask-caching first)
from flask_caching import Cache

cache = Cache(app, config={'CACHE_TYPE': 'simple'})

@app.route('/api/stats')
@login_required
@cache.cached(timeout=5)  # Cache for 5 seconds
def get_stats():
    # ... existing code
```

### 3. Reduce Polling Frequency
```javascript
// In dashboard.html, change from 5000ms to 10000ms
setInterval(function() {
    $.get('/api/stats', function(data) {
        // ... update stats
    });
}, 10000);  // 10 seconds instead of 5
```

## Maintenance Tasks

### Daily
- [ ] Check system logs for errors
- [ ] Verify blockchain sync status
- [ ] Monitor disk space

### Weekly
- [ ] Review user activity logs
- [ ] Check database size
- [ ] Backup MongoDB database
- [ ] Update statistics

### Monthly
- [ ] Review and clean old activity logs
- [ ] Update system dependencies
- [ ] Security audit
- [ ] Performance review

### Backup MongoDB
```bash
# Create backup
mongodump --db logchain_db --out /backup/mongodb/$(date +%Y%m%d)

# Restore backup
mongorestore --db logchain_db /backup/mongodb/20240101/logchain_db
```

## Rollback Procedure

If you need to revert to the old system:

```bash
cd ~/logchain

# Stop new services
pkill -f app_auth.py
pkill -f watcher_multiuser.py

# Restore old files
cp backup_YYYYMMDD/*.py .

# Start old system
python3 app.py &
python3 watcher.py &
```

## Support Resources

- MongoDB Documentation: https://docs.mongodb.com/
- Flask Documentation: https://flask.palletsprojects.com/
- Flask-Login: https://flask-login.readthedocs.io/
- Web3.py: https://web3py.readthedocs.io/

---

**Deployment Date:** ___________
**Deployed By:** ___________
**Version:** 2.0 Multi-User
**Status:** ___________
