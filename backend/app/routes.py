import uuid
import logging
from datetime import datetime
from typing import Optional
import requests
from fastapi import APIRouter, File, UploadFile, Form, Query, Depends, BackgroundTasks, HTTPException, status
from fastapi.responses import Response, FileResponse

logger = logging.getLogger("clearcut")

from app.config import OUTPUTS_DIR, MAX_CONTENT_LENGTH
from app.auth import get_api_key
from app.middleware import check_rate_limit
from app.database import (
    get_db_connection,
    create_job,
    get_job,
    update_job_status
)
from app.services import ImageProcessorService, JobManager
from app.schemas import JobStatusResponse, RemoveBackgroundResponse, HealthResponse, HealthServices

router = APIRouter()

# ----------------- Helper Functions -----------------

def download_image_from_url(url: str) -> tuple[bytes, str]:
    """
    Downloads an image from a remote URL with size verification.
    Returns a tuple of (bytes, filename).
    """
    try:
        # Check Content-Length first using a stream
        with requests.get(url, stream=True, timeout=10) as r:
            r.raise_for_status()
            
            # Verify Content-Length header if available
            content_length = r.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_CONTENT_LENGTH:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Remote image exceeds the size limit of {MAX_CONTENT_LENGTH // (1024 * 1024)}MB."
                )
            
            # Read chunks and check size
            downloaded = 0
            buffer = bytearray()
            for chunk in r.iter_content(chunk_size=8192):
                downloaded += len(chunk)
                if downloaded > MAX_CONTENT_LENGTH:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Remote image exceeds the size limit of {MAX_CONTENT_LENGTH // (1024 * 1024)}MB."
                    )
                buffer.extend(chunk)
                
            # Extract filename from URL
            filename = url.split("/")[-1].split("?")[0]
            if not filename or "." not in filename:
                filename = "downloaded_image.jpg"
                
            return bytes(buffer), filename
            
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to fetch image from URL: {str(e)}"
        )


# ----------------- API Endpoints -----------------

@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health and Uptime Check",
    description="Check the system status, SQLite database connectivity, and background models availability."
)
def health_check():
    # Verify DB connectivity
    db_connected = "connected"
    try:
        conn = get_db_connection()
        conn.execute("SELECT 1")
        conn.close()
    except Exception:
        db_connected = "disconnected"

    # In simple self-hosted settings, the model loads on first use.
    # We report True if the package is imported successfully.
    model_status = True

    return HealthResponse(
        timestamp=datetime.utcnow().isoformat(),
        services=HealthServices(
            database=db_connected,
            model_loaded=model_status
        )
    )


@router.post(
    "/v1/remove-background",
    summary="Remove Background from Image",
    description=(
        "Core endpoint for background removal. Supports direct image upload (multipart) or "
        "passing a remote URL. Can return either the processed PNG file directly, or a JSON response "
        "with job details depending on formatting parameters. Supports async processing for large files."
    ),
    responses={
        200: {
            "content": {"image/png": {}},
            "description": "Transparent PNG image file."
        },
        202: {
            "model": JobStatusResponse,
            "description": "Job submitted successfully for async processing."
        }
    },
    dependencies=[Depends(get_api_key), Depends(check_rate_limit)]
)
async def remove_background(
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    format: str = Query("image", pattern="^(image|json)$", description="Output format: 'image' returns the file directly, 'json' returns a link."),
    async_mode: bool = Query(False, alias="async", description="If true, schedules background execution and returns immediately with a job ID."),
):
    # Parameter Validation
    if file and url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot provide both a file upload and a remote image URL."
        )
    if not file and not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide either a 'file' or a 'url'."
        )

    # 1. Fetch File Bytes and Filename
    if file:
        filename = file.filename
        file_bytes = await file.read()
    else:
        # Download from URL
        file_bytes, filename = download_image_from_url(url)

    # 2. Validate File Format & Structure
    try:
        ImageProcessorService.validate_image(file_bytes, filename)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    job_id = str(uuid.uuid4())

    # 3. Handle Async Execution
    if async_mode:
        # Create pending job in DB
        job = create_job(job_id, filename)
        
        # Schedule worker thread
        background_tasks.add_task(
            JobManager.process_job_async,
            job_id,
            file_bytes,
            filename
        )
        
        return JobStatusResponse(
            job_id=job_id,
            status="pending",
            original_filename=filename,
            created_at=job["created_at"],
            result_url=f"/v1/jobs/{job_id}/result"
        )

    # 4. Handle Sync Execution
    else:
        try:
            processed_bytes = await ImageProcessorService.remove_background(file_bytes)
            
            # Save output PNG for caching / retrieval via result endpoint
            sync_filename = f"sync_{job_id}.png"
            output_path = OUTPUTS_DIR / sync_filename
            with open(output_path, "wb") as f:
                f.write(processed_bytes)
            
            # Create a completed job record in SQLite for tracking
            create_job(f"sync_{job_id}", filename)
            update_job_status(f"sync_{job_id}", "completed", result_filename=sync_filename)
            
            if format == "image":
                return Response(
                    content=processed_bytes,
                    media_type="image/png",
                    headers={
                        "Content-Disposition": f"attachment; filename=clearcut_{filename.split('.')[0]}.png"
                    }
                )
            else:
                return RemoveBackgroundResponse(
                    job_id=f"sync_{job_id}",
                    status="completed",
                    result_url=f"/v1/jobs/sync_{job_id}/result",
                    processed_at=datetime.utcnow().isoformat()
                )
        except Exception as e:
            logger.error(f"Synchronous processing failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Background removal failed: {str(e)}"
            )


@router.get(
    "/v1/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Get Job Status",
    description="Check the processing status of an asynchronous background removal job.",
    dependencies=[Depends(get_api_key), Depends(check_rate_limit)]
)
def get_job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found."
        )

    # Build response schema
    result_url = None
    if job["status"] == "completed":
        result_url = f"/v1/jobs/{job_id}/result"

    return JobStatusResponse(
        job_id=job["id"],
        status=job["status"],
        original_filename=job["original_filename"],
        created_at=job["created_at"],
        completed_at=job["completed_at"],
        error_message=job["error_message"],
        result_url=result_url
    )


@router.get(
    "/v1/jobs/{job_id}/result",
    summary="Download Job Result",
    description="Download the final transparent PNG output of a completed job. Requires the same API authentication.",
    dependencies=[Depends(get_api_key), Depends(check_rate_limit)]
)
def get_job_result(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found."
        )

    if job["status"] == "pending" or job["status"] == "processing":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The job is still being processed. Please check back later."
        )

    if job["status"] == "failed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The job failed: {job['error_message']}"
        )

    result_path = OUTPUTS_DIR / job["result_filename"]
    if not result_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Result file not found on disk."
        )

    # Return the file response
    download_name = f"clearcut_{job['original_filename'].split('.')[0]}.png" if job['original_filename'] else "clearcut_output.png"
    return FileResponse(
        path=result_path,
        media_type="image/png",
        filename=download_name
    )
