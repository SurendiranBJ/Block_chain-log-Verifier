# LogChain Multi-User System

**Decentralized Log Integrity Verification System with Multi-User Authentication**

## 🎯 Overview

This enhanced system adds complete user authentication, MongoDB database integration, and multi-user log monitoring capabilities to your existing blockchain-based log integrity verification system.

## ✨ New Features

### Authentication & User Management
- ✅ Login/Logout system with session management
- ✅ User registration
- ✅ Role-based access control (Admin/User)
- ✅ Default admin account (admin/admin123)
- ✅ Password hashing with bcrypt

### User Dashboard
- ✅ Per-user log source management
- ✅ Add/Remove/Pause log monitoring
- ✅ Real-time statistics (total logs, active monitoring, blockchain entries)
- ✅ Activity history tracking
- ✅ Blockchain connection status

### Admin Panel
- ✅ View all users and their logs
- ✅ Create/Delete/Enable/Disable user accounts
- ✅ System-wide activity monitoring
- ✅ View all active log monitoring across users

### Database (MongoDB)
- ✅ User credentials and profiles
- ✅ Log source configurations per user
- ✅ Activity logging for audit trails
- ✅ Persistent storage with indexing

### Multi-User Log Monitoring
- ✅ Each user can monitor their own log files
- ✅ Automatic background processing
- ✅ Per-user case ID management
- ✅ Independent monitoring status per log

## 📋 Prerequisites

- Existing blockchain setup (Geth nodes running)
- Python 3.8+
- MongoDB 4.4+
- Smart contracts deployed (LogIntegrityV2)

## 🚀 Installation

### 1. Install MongoDB (if not already installed)

```bash
# The setup script will do this automatically, or manually:
wget -qO - https://www.mongodb.org/static/pgp/server-6.0.asc | sudo apt-key add -
echo "deb [ arch=amd64,arm64 ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/6.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-6.0.list
sudo apt-get update
sudo apt-get install -y mongodb-org
sudo systemctl start mongod
sudo systemctl enable mongod
```

### 2. Run Setup Script

```bash
chmod +x setup_multiuser.sh
./setup_multiuser.sh
```

This will:
- Install MongoDB if needed
- Install Python dependencies
- Initialize the database
- Create default admin user

## 📁 New File Structure

```
~/logchain/
├── app_auth.py              # Enhanced Flask app with authentication
├── models.py                # MongoDB models and database handler
├── watcher_multiuser.py     # Multi-user log monitoring daemon
├── requirements.txt         # Updated dependencies
├── setup_multiuser.sh       # Setup script
├── templates/
│   ├── base.html           # Base template with navbar
│   ├── login.html          # Login page
│   ├── register.html       # Registration page
│   ├── dashboard.html      # User dashboard
│   ├── add_log.html        # Add log source form
│   └── admin.html          # Admin panel
├── LogIntegrityV2_abi.json # Contract ABI (existing)
└── ... (your existing files)
```

## 🎮 Usage

### Starting the System

**Terminal 1 - Flask Application:**
```bash
cd ~/logchain
python3 app_auth.py
```

**Terminal 2 - Log Monitor:**
```bash
cd ~/logchain
python3 watcher_multiuser.py
```

### Access the Dashboard
Open browser: `http://localhost:5000` or `http://<PC1-IP>:5000`

### Default Admin Login
- Username: `admin`
- Password: `admin123`

**⚠️ IMPORTANT: Change the admin password in production!**

## 👥 User Workflow

### For Regular Users

1. **Register Account**
   - Go to registration page
   - Create username, email, password
   - Wait for admin approval (or auto-approved)

2. **Login**
   - Use credentials to login
   - Redirected to personal dashboard

3. **Add Log Source**
   - Click "Add New Log"
   - Provide:
     - Case ID (e.g., CASE-2024-0078)
     - Full path to log file
     - Optional description
   - Click "Start Monitoring"

4. **Monitor Logs**
   - View real-time stats on dashboard
   - Pause/Resume monitoring
   - Delete log sources
   - View activity history

### For Administrators

1. **Login with Admin Account**
   - Use admin credentials
   - Access admin panel from navbar

2. **User Management**
   - Create new users manually
   - Enable/Disable user accounts
   - Delete users (and their logs)
   - View user activity

3. **System Monitoring**
   - View all monitored logs across all users
   - Check system-wide activity log
   - Monitor blockchain status

## 🗄️ Database Schema

### Users Collection
```javascript
{
  _id: ObjectId,
  username: String (unique),
  password: String (hashed),
  email: String,
  role: String ('admin' | 'user'),
  is_active: Boolean,
  created_at: DateTime,
  last_login: DateTime
}
```

### Logs Collection
```javascript
{
  _id: ObjectId,
  user_id: String,
  log_path: String,
  case_id: String,
  description: String,
  is_active: Boolean,
  created_at: DateTime,
  last_checked: DateTime,
  total_entries: Number,
  verified_entries: Number
}
```

### Activities Collection
```javascript
{
  _id: ObjectId,
  user_id: String,
  action: String,
  details: String,
  timestamp: DateTime
}
```

## 🔧 Configuration

### Environment Variables (Optional)
```bash
export SECRET_KEY="your-secret-key-here"
export MONGODB_URI="mongodb://localhost:27017/"
```

### Change Admin Password
```python
from models import Database
from werkzeug.security import generate_password_hash

db = Database()
db.users.update_one(
    {'username': 'admin'},
    {'$set': {'password': generate_password_hash('new_password')}}
)
```

## 🔐 Security Features

- ✅ Password hashing with Werkzeug
- ✅ Session-based authentication with Flask-Login
- ✅ Role-based access control
- ✅ CSRF protection (Flask built-in)
- ✅ Activity logging for audit trails
- ✅ User account enable/disable
- ✅ Secure blockchain key storage

## 📊 API Endpoints

### Authentication
- `GET/POST /login` - Login page
- `GET/POST /register` - Registration page
- `GET /logout` - Logout

### User Dashboard
- `GET /dashboard` - User dashboard
- `GET/POST /add_log` - Add log source
- `GET /toggle_log/<id>` - Pause/Resume monitoring
- `GET /delete_log/<id>` - Delete log source

### Admin Panel
- `GET /admin` - Admin panel
- `GET /admin/toggle_user/<id>` - Enable/Disable user
- `GET /admin/delete_user/<id>` - Delete user
- `POST /admin/create_user` - Create new user

### AJAX API
- `GET /api/entries/<case_id>` - Get blockchain entries
- `GET /api/stats` - Get user statistics

## 🐛 Troubleshooting

### MongoDB Connection Issues
```bash
# Check if MongoDB is running
sudo systemctl status mongod

# Start MongoDB
sudo systemctl start mongod

# Check MongoDB logs
sudo tail -f /var/log/mongodb/mongod.log
```

### Cannot Connect to Blockchain
```bash
# Check if Geth is running
ps aux | grep geth

# Test Web3 connection
python3 -c "from web3 import Web3; print(Web3(Web3.HTTPProvider('http://localhost:8545')).is_connected())"
```

### Port Already in Use
```bash
# Find process using port 5000
sudo lsof -i :5000

# Kill the process
sudo kill -9 <PID>
```

## 📈 Future Enhancements

- Email notifications for tamper detection
- Two-factor authentication (2FA)
- API key generation for programmatic access
- Export audit reports
- Dashboard charts and visualizations
- Multi-language support
- Mobile responsive improvements

## 🤝 Integration with Existing System

This system **replaces** `app.py` with `app_auth.py` and adds user authentication. Your existing components still work:

- ✅ Blockchain infrastructure (unchanged)
- ✅ Smart contracts (unchanged)
- ✅ `hash_and_submit.py` (now used by watcher_multiuser.py)
- ✅ `merkle.py` (still available for verification)

## 📝 License

Part of the LogChain Decentralized Log Integrity Verification System

## 👨‍💻 Author

Enhanced by Claude for Sura's Advanced Databases project
Original blockchain infrastructure by Sura

---

**Need Help?** Check the troubleshooting section or review the MongoDB/Flask-Login documentation.
