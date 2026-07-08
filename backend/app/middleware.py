import time
import uuid
import json
import logging
from collections import defaultdict
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import RATE_LIMIT_LIMIT, RATE_LIMIT_PERIOD
from app.database import get_api_key_details

logger = logging.getLogger("clearcut")

class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id

        start_time = time.time()
        
        # Process request
        try:
            response = await call_next(request)
        except Exception as e:
            process_time = time.time() - start_time
            # Log failure
            log_data = {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "client_ip": request.client.host if request.client else None,
                "status_code": 500,
                "latency_ms": round(process_time * 1000, 2),
                "error": str(type(e).__name__),
                "message": str(e)
            }
            logger.error(json.dumps(log_data))
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"error": "Internal Server Error", "message": "An unexpected error occurred."}
            )

        process_time = time.time() - start_time
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = str(round(process_time * 1000, 2))

        log_data = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "client_ip": request.client.host if request.client else None,
            "status_code": response.status_code,
            "latency_ms": round(process_time * 1000, 2)
        }
        
        if response.status_code >= 400:
            logger.warning(json.dumps(log_data))
        else:
            logger.info(json.dumps(log_data))

        return response


class InMemoryRateLimiter:
    """In-memory rate limiter tracking API key request counts within a time window."""
    def __init__(self):
        # Maps api_key -> list of float timestamps
        self.history = defaultdict(list)

    def is_rate_limited(self, api_key: str) -> bool:
        now = time.time()
        window_start = now - RATE_LIMIT_PERIOD
        
        # Clean up old timestamps
        self.history[api_key] = [t for t in self.history[api_key] if t > window_start]
        
        # Get limit for this key (default if not in db details)
        limit = RATE_LIMIT_LIMIT
        key_details = get_api_key_details(api_key)
        if key_details and "rate_limit_limit" in key_details:
            limit = key_details["rate_limit_limit"]
            
        if len(self.history[api_key]) >= limit:
            return True
            
        # Record this request
        self.history[api_key].append(now)
        return False

# Global instance of rate limiter
rate_limiter = InMemoryRateLimiter()

async def check_rate_limit(request: Request):
    """FastAPI dependency to verify rate limits on protected routes."""
    # Retrieve X-API-Key from headers
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        # Auth dependency handles error for missing keys on endpoints requiring auth
        return
        
    if rate_limiter.is_rate_limited(api_key):
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Maximum of {RATE_LIMIT_LIMIT} requests per {RATE_LIMIT_PERIOD} seconds."
        )
