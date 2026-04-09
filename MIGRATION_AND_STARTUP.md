# Migration & Startup Guide: Multi-User Update

## 🌟 Features Added (New State)
- **User Authentication:** Flask-Login securely handles user sessions and passwords through Bcrypt hashing.
- **Role-Based Access Control:** Distinguishes between Admin actions (manage users/logs cluster-wide) and regular Users.
- **MongoDB Integration (`logchain_db`):** Replaces static JSON configuration files. Stores user profiles, log paths globally, and maintains an audit trail.
- **Multi-User Log Monitoring:** `watcher_multiuser.py` runs as a scalable background daemon. It polls MongoDB for active configurations and spins up dynamic `watchdog` observers whenever a user adds a new log.
- **Custom Web UI (`templates/`):** Clean and responsive HTML interfaces (`dashboard.html`, `admin.html`, `login.html`) utilizing dark-themed Bootstrap.
- **RESTful Endpoints:** Upgraded AJAX APIs (`/api/stats`, `/api/entries/<case_id>`) fetch blockchain verifications in real-time from the backend.

## 🔄 Previous State vs. New State
To simplify modifying or reversing the system, here is how the core files have shifted:

| Component | Previous State (Single-User) | New State (Multi-User) | Change Impact |
|-----------|------------------------------|------------------------|---------------|
| **Web Server** | `app.py` | `app_auth.py` | Integrated auth wrappers; HTML hardcoding removed. |
| **Daemon** | `watcher.py` | `watcher_multiuser.py` | Migrated from watching 1 `config.json` path to dynamic MongoDB queries. |
| **Persistence** | `config.json` | **MongoDB** (`models.py`)| Local configuration is retired in favor of database rows. |
| **User Interface**| Internal python strings | `templates/` folder | Allows custom styling via standard HTML pages. |
| **Blockchain Sync**| `hash_and_submit.py` | `hash_and_submit.py` | **UNCHANGED**. Core integrity works exactly as before. |

## ⏪ How to Reverse Changes (Downgrade to Previous State)
Because the old files were intentionally preserved, you can easily switch back to the prior single-user setup without rewriting code.

1. **Stop the New Services:**
   ```bash
   pkill -f "app_auth.py"
   pkill -f "watcher_multiuser.py"
   ```
2. **Start the Legacy Services:**
   ```bash
   cd ~/logchain
   nohup python3 app.py > app_legacy.log 2>&1 &
   nohup python3 watcher.py > watcher_legacy.log 2>&1 &
   ```
*(Keep your original `config.json` updated with your single-target `LOG_FILE` and `CASE_ID`, as the legacy scripts depend on it.)*

---

## 🚀 How to Start the Full Project

The private Ethereum network operates on two LAN machines (PC1 Sura and PC2 Vaysh) utilizing DHCP. Follow this strict sequence whenever the IPs change.

### 1. Initialize Node 2 (PC2 - Vaysh)
On Vaishnavan's machine:
1. Open the terminal.
2. Execute the node startup script:
   ```bash
   cd ~
   ./start_node2.sh
   ```
3. Look for the prompt asking for the IP address and input the latest DHCP-assigned IP. Ensure the node launches and listens.

### 2. Initialize Node 1 & Multi-User App (PC1 - Sura Main)
On Sura's machine:
1. **Launch the Blockchain Node:**
   ```bash
   cd ~/logchain
   ./start_all.sh
   ```
   *Enter the current PC1 IP address when prompted to finalize P2P connectivity with Node 2.*

2. **Ensure the Database is Active:**
   ```bash
   sudo systemctl status mongod
   # If stopped, run: sudo systemctl start mongod
   ```

3. **Start the Multi-User Web App & Watcher:**
   ```bash
   ./start_multiuser.sh
   ```
   *(This launches the authenticated `app_auth.py` and the `watcher_multiuser.py` components in the background.)*

4. **Access the Application:**
   Open a browser to `http://localhost:5000` (or `http://<PC1-IP>:5000` from Vaysh's PC). 
   **Default Login:** `admin` / `admin123`
