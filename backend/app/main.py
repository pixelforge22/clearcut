import logging
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import SERVE_STATIC, FRONTEND_DIR
from app.database import init_db
from app.middleware import StructuredLoggingMiddleware
from app.routes import router as api_router

# Configure Logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("clearcut")

# Initialize Database Schema
init_db()

# Create FastAPI Instance
app = FastAPI(
    title="ClearCut Background Removal API",
    description=(
        "Production-ready API for automated image background removal using U²-Net. "
        "Supports direct multipart uploads, remote URLs, synchronous & asynchronous processing, "
        "secured by API Keys and protected by rate limiting. Serves the ClearCut dashboard."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 1. Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permits frontend execution on alternate domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Add Structured Logging Middleware
app.add_middleware(StructuredLoggingMiddleware)

# 3. Register API Router
app.include_router(api_router)

# 4. Mount Frontend Static Files (Must be registered last to avoid route collision)
if SERVE_STATIC:
    if FRONTEND_DIR.exists():
        logger.info(f"Serving frontend static files from: {FRONTEND_DIR}")
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    else:
        logger.warning(
            f"Frontend directory not found at '{FRONTEND_DIR}'. "
            "Frontend static files will not be served."
        )
else:
    logger.info("Static file serving is disabled via SERVE_STATIC config.")
