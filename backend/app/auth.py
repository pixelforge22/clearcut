from fastapi import Security, HTTPException, status, Request
from fastapi.security.api_key import APIKeyHeader
from app.database import verify_api_key

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_api_key(request: Request, api_key: str = Security(API_KEY_HEADER)) -> str:
    """Dependency that validates X-API-Key header, with same-origin bypass for frontend UI."""
    referer = request.headers.get("referer")
    host = request.headers.get("host")
    
    # If the request comes from the same origin (frontend UI calling its own backend), bypass key check
    if referer and host and host in referer:
        return "same-origin"
        
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key missing. Please provide X-API-Key header.",
        )
    if not verify_api_key(api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API Key.",
        )
    return api_key
