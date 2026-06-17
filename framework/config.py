from pathlib import Path

FIRMAE_DIR  = Path.home() / "project/tools/FirmAE"
SCRATCH_DIR = FIRMAE_DIR / "scratch"
REPORTS_DIR = Path(__file__).parent / "reports"

DB_CONFIG = {
    "dbname":   "firmware",
    "user":     "firmadyne",
    "password": "firmadyne",
    "host":     "127.0.0.1",
}

VALKEY_HOST = "localhost"
VALKEY_PORT = 6379

NVD_API_KEY        = ""
NVD_RATE_LIMIT_SLEEP = 6.0  # seconds between requests; 5 req/30s without key

FIRMWARE_EXTENSIONS = {".zip", ".bin", ".img", ".trx", ".chk"}

EMULATION_WAIT_SECONDS = 600
