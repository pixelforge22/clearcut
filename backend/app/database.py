import sqlite3
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from app.config import DATABASE_URL, DEFAULT_API_KEY

logger = logging.getLogger("clearcut")

def get_db_connection():
    conn = sqlite3.connect(DATABASE_URL)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database schema and seeds the default API key if empty."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Create API Keys table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                key TEXT PRIMARY KEY,
                client_name TEXT NOT NULL,
                rate_limit_limit INTEGER DEFAULT 60,
                created_at TEXT NOT NULL,
                is_active INTEGER DEFAULT 1
            )
        """)
        
        # Create Jobs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL, -- 'pending', 'processing', 'completed', 'failed'
                error_message TEXT,
                original_filename TEXT,
                result_filename TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT
            )
        """)
        
        # Seed default API key if empty
        cursor.execute("SELECT COUNT(*) FROM api_keys")
        if cursor.fetchone()[0] == 0:
            now = datetime.utcnow().isoformat()
            cursor.execute(
                "INSERT INTO api_keys (key, client_name, rate_limit_limit, created_at, is_active) VALUES (?, ?, ?, ?, ?)",
                (DEFAULT_API_KEY, "Default Developer Key", 60, now, 1)
            )
            logger.info(f"Database initialized. Seeded default API Key: {DEFAULT_API_KEY}")
        else:
            logger.info("Database schema verified.")
        
        conn.commit()

def verify_api_key(key: str) -> bool:
    """Check if an API key exists and is active."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT is_active FROM api_keys WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row is not None and row["is_active"] == 1

def get_api_key_details(key: str) -> Optional[Dict[str, Any]]:
    """Retrieve details for an API key."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM api_keys WHERE key = ?", (key,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

def create_job(job_id: str, original_filename: Optional[str] = None) -> Dict[str, Any]:
    """Create a new job record with status 'pending'."""
    now = datetime.utcnow().isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO jobs (id, status, original_filename, created_at) VALUES (?, ?, ?, ?)",
            (job_id, "pending", original_filename, now)
        )
        conn.commit()
    return {
        "id": job_id,
        "status": "pending",
        "original_filename": original_filename,
        "created_at": now
    }

def update_job_status(
    job_id: str,
    status: str,
    error_message: Optional[str] = None,
    result_filename: Optional[str] = None
) -> None:
    """Update a job status and relevant details."""
    now = datetime.utcnow().isoformat() if status in ("completed", "failed") else None
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if status == "completed":
            cursor.execute(
                "UPDATE jobs SET status = ?, result_filename = ?, completed_at = ? WHERE id = ?",
                (status, result_filename, now, job_id)
            )
        elif status == "failed":
            cursor.execute(
                "UPDATE jobs SET status = ?, error_message = ?, completed_at = ? WHERE id = ?",
                (status, error_message, now, job_id)
            )
        else:
            cursor.execute(
                "UPDATE jobs SET status = ? WHERE id = ?",
                (status, job_id)
            )
        conn.commit()

def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a job by its ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
