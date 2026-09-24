"""
LogChain - Centralized Configuration
All environment-based configuration. No hard-coded secrets.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env")

# ── Blockchain ─────────────────────────────────────────────────────────────
DEVICE1_IP       = os.getenv("DEVICE1_IP", "127.0.0.1")
DEVICE2_IP       = os.getenv("DEVICE2_IP", "127.0.0.1")
DEVICE1_RPC      = os.getenv("DEVICE1_RPC", f"http://{DEVICE1_IP}:8545")
DEVICE2_RPC      = os.getenv("DEVICE2_RPC", f"http://{DEVICE2_IP}:8546")
CHAIN_ID         = int(os.getenv("CHAIN_ID", "12345"))

BLOCKCHAIN_PRIVATE_KEY = os.getenv("BLOCKCHAIN_PRIVATE_KEY", "")
BLOCKCHAIN_ACCOUNT     = os.getenv("BLOCKCHAIN_ACCOUNT", "")
CONTRACT_ADDRESS       = os.getenv("CONTRACT_ADDRESS", "")

# ── MongoDB ────────────────────────────────────────────────────────────────
MONGODB_URI     = os.getenv("MONGODB_URI", "mongodb://localhost:27017/logchain_db")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "logchain_db")

# ── Flask ──────────────────────────────────────────────────────────────────
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-in-production")
FLASK_DEBUG      = os.getenv("FLASK_DEBUG", "false").lower() == "true"
FLASK_PORT       = int(os.getenv("FLASK_PORT", "5000"))

# ── Demo ───────────────────────────────────────────────────────────────────
DEMO_CASE_ID     = os.getenv("DEMO_CASE_ID", "CASE-001")
DEMO_EVENT_COUNT = int(os.getenv("DEMO_EVENT_COUNT", "100"))
DEMO_LOG_DIR     = os.getenv("DEMO_LOG_DIR", str(_ROOT / "demo" / "sample_logs"))

# ── ABI Paths ──────────────────────────────────────────────────────────────
ABI_V3_PATH      = str(_ROOT / "backend" / "LogIntegrityV3_abi.json")
DEPLOYMENT_PATH  = str(_ROOT / "deployment.json")
