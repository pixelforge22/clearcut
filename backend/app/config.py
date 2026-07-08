import os
from pathlib import Path

# Base Directory of the app
BASE_DIR = Path(__file__).resolve().parent.parent

# Data directory for DB, uploads, and outputs
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Configuration Variables
DATABASE_URL = os.getenv("DATABASE_URL", str(DATA_DIR / "clearcut.db"))
UPLOADS_DIR = Path(os.getenv("UPLOADS_DIR", str(DATA_DIR / "uploads")))
OUTPUTS_DIR = Path(os.getenv("OUTPUTS_DIR", str(DATA_DIR / "outputs")))

# Ensure directories exist
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# File settings
MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 10 * 1024 * 1024))  # 10MB
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

# Security & Limits
DEFAULT_API_KEY = os.getenv("DEFAULT_API_KEY", "clearcut_dev_key_2026")
RATE_LIMIT_LIMIT = int(os.getenv("RATE_LIMIT_LIMIT", 60))  # requests
RATE_LIMIT_PERIOD = int(os.getenv("RATE_LIMIT_PERIOD", 60))  # seconds

# Serving frontend
SERVE_STATIC = os.getenv("SERVE_STATIC", "true").lower() in ("true", "1", "yes")
_default_frontend = str(BASE_DIR.parent / "frontend")
FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", _default_frontend))
