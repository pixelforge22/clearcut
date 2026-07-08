from pydantic import BaseModel, Field
from typing import Optional, Dict

class JobStatusResponse(BaseModel):
    job_id: str = Field(..., description="Unique UUID identifier for the async job.")
    status: str = Field(..., description="Current state: pending, processing, completed, failed.")
    original_filename: Optional[str] = Field(None, description="Original uploaded filename.")
    created_at: str = Field(..., description="ISO 8601 UTC timestamp of creation.")
    completed_at: Optional[str] = Field(None, description="ISO 8601 UTC timestamp of completion.")
    error_message: Optional[str] = Field(None, description="Detailed error explanation if job failed.")
    result_url: Optional[str] = Field(None, description="API endpoint to download the transparent PNG result.")

class RemoveBackgroundResponse(BaseModel):
    job_id: str = Field(..., description="Unique UUID identifier for the request.")
    status: str = Field(..., description="Processing status (always 'completed' for sync requests).")
    result_url: str = Field(..., description="API endpoint to download the transparent PNG result.")
    processed_at: str = Field(..., description="ISO 8601 UTC timestamp of processing.")

class HealthServices(BaseModel):
    database: str = Field(..., description="Status of connection to SQLite.")
    model_loaded: bool = Field(..., description="Indicates if the rembg execution engine is initialized.")

class HealthResponse(BaseModel):
    status: str = Field("healthy", description="Indicates overall api service availability.")
    timestamp: str = Field(..., description="ISO 8601 system time.")
    version: str = Field("1.0.0", description="Semver code version.")
    services: HealthServices
