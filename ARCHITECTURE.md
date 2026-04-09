# LogChain Multi-User System Architecture

## System Components Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER LAYER                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Admin      │  │   User 1     │  │   User 2     │          │
│  │  (Browser)   │  │  (Browser)   │  │  (Browser)   │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                  │                  │                   │
│         └──────────────────┼──────────────────┘                   │
│                            │                                      │
└────────────────────────────┼──────────────────────────────────────┘
                             │ HTTP
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              Flask Web Application (app_auth.py)          │  │
│  │  ┌────────────┐  ┌────────────┐  ┌─────────────────┐    │  │
│  │  │   Auth     │  │  Dashboard │  │   Admin Panel   │    │  │
│  │  │  System    │  │   Routes   │  │     Routes      │    │  │
│  │  └────────────┘  └────────────┘  └─────────────────┘    │  │
│  │                                                            │  │
│  │  ┌────────────────────────────────────────────────────┐  │  │
│  │  │          Flask-Login Session Management            │  │  │
│  │  └────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                            │                                      │
│                            │                                      │
│  ┌────────────────────────┴────────────────────────────────┐    │
│  │      Multi-User Log Monitor (watcher_multiuser.py)      │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐              │    │
│  │  │ Observer │  │ Observer │  │ Observer │  ...         │    │
│  │  │  User 1  │  │  User 2  │  │  User 3  │              │    │
│  │  │  Log 1   │  │  Log 1   │  │  Log 1   │              │    │
│  │  └──────────┘  └──────────┘  └──────────┘              │    │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                   │
└───────────────┬─────────────────────────┬─────────────────────────┘
                │                         │
                │                         │
                ▼                         ▼
┌─────────────────────────────┐  ┌──────────────────────────────┐
│      DATABASE LAYER         │  │    BLOCKCHAIN LAYER          │
├─────────────────────────────┤  ├──────────────────────────────┤
│                             │  │                              │
│  ┌─────────────────────┐   │  │  ┌────────────────────────┐ │
│  │  MongoDB Instance   │   │  │  │   Geth Node 1 (PC1)    │ │
│  │                     │   │  │  │   Port: 30311/8545     │ │
│  │  ┌──────────────┐   │   │  │  │                        │ │
│  │  │ users        │   │   │  │  │  Smart Contracts:      │ │
│  │  ├──────────────┤   │   │  │  │  - LogIntegrityV2      │ │
│  │  │ logs         │   │   │  │  │    (0x898e...0762)     │ │
│  │  ├──────────────┤   │   │  │  └────────────────────────┘ │
│  │  │ activities   │   │   │  │            ▲                 │
│  │  └──────────────┘   │   │  │            │ P2P             │
│  │                     │   │  │            ▼                 │
│  └─────────────────────┘   │  │  ┌────────────────────────┐ │
│                             │  │  │   Geth Node 2 (PC2)    │ │
└─────────────────────────────┘  │  │   Port: 30312/8546     │ │
                                 │  │   Validator Node       │ │
                                 │  └────────────────────────┘ │
                                 │                              │
                                 └──────────────────────────────┘
```

## Data Flow Diagram

### 1. User Login Flow
```
User → Login Page → Flask-Login → MongoDB (verify credentials)
                                      ↓
                                  Create Session
                                      ↓
                                  Redirect to Dashboard
```

### 2. Add Log Source Flow
```
User → Add Log Form → Flask App → Validate Path
                                       ↓
                                   MongoDB (store log config)
                                       ↓
                                   Return Success
                                       ↓
                                   Watcher Auto-detects
                                       ↓
                                   Start Monitoring
```

### 3. Log Monitoring Flow
```
Log File (Modified) → Watchdog Observer → Read New Lines
                                              ↓
                                         Compute SHA256
                                              ↓
                                         Submit to Blockchain
                                              ↓
                                         Smart Contract Storage
                                              ↓
                                         Update MongoDB Stats
```

### 4. Admin Management Flow
```
Admin → Admin Panel → View All Users/Logs → MongoDB Query
                           ↓
                      Perform Action (Enable/Disable/Delete)
                           ↓
                      Update MongoDB
                           ↓
                      Log Activity
```

## Database Collections

### Users Collection
- Stores user credentials (hashed passwords)
- Role-based access (admin/user)
- Account status (active/disabled)
- Login tracking

### Logs Collection
- Per-user log sources
- Case ID mapping
- Monitoring status
- Statistics (entries, verified count)

### Activities Collection
- Audit trail
- User actions
- Timestamps
- Details

## Security Layers

```
┌─────────────────────────────────────┐
│  1. Flask Session Security          │
│     - CSRF Protection                │
│     - Secure Cookies                 │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│  2. Authentication Layer             │
│     - Password Hashing (bcrypt)      │
│     - Session Management             │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│  3. Authorization Layer              │
│     - Role-Based Access Control      │
│     - Resource Ownership Checks      │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│  4. Blockchain Layer                 │
│     - Immutable Storage              │
│     - Cryptographic Hashing          │
│     - Smart Contract Validation      │
└─────────────────────────────────────┘
```

## Component Responsibilities

### app_auth.py
- Handle HTTP requests
- User authentication/authorization
- Render templates
- AJAX API endpoints
- Session management

### models.py
- Database connection
- User management
- Log source management
- Activity logging
- Data validation

### watcher_multiuser.py
- Monitor multiple log files
- Process new log entries
- Submit hashes to blockchain
- Update database statistics
- Auto-refresh monitoring list

### MongoDB
- Persistent data storage
- User credentials
- Log configurations
- Activity audit trail

### Blockchain (Geth + Smart Contracts)
- Immutable hash storage
- Tamper detection
- Distributed consensus
- Cryptographic verification

## Scalability Considerations

### Current Design
- Single Flask instance (development mode)
- One watcher process per system
- MongoDB single instance

### Production Enhancements
- Multiple Flask workers (Gunicorn/uWSGI)
- Load balancer (Nginx)
- MongoDB replica set
- Distributed watcher instances
- Redis for session storage
- Message queue (RabbitMQ/Redis) for async processing

## Deployment Architecture

```
Internet
   ↓
[Nginx Reverse Proxy] ← SSL/TLS Termination
   ↓
[Load Balancer]
   ↓
┌────────────┬────────────┬────────────┐
│ Flask App  │ Flask App  │ Flask App  │
│ Worker 1   │ Worker 2   │ Worker 3   │
└────────────┴────────────┴────────────┘
         ↓
   ┌─────────┴─────────┐
   ↓                   ↓
[MongoDB Replica]  [Blockchain Network]
Primary + Secondary    Node1 + Node2
```

This architecture provides:
- High availability
- Horizontal scalability
- Data redundancy
- Load distribution
- Security hardening
