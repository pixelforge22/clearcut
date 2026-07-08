import io
import asyncio
import logging
from pathlib import Path
from typing import Union, Optional
from PIL import Image, UnidentifiedImageError
import rembg

from app.config import OUTPUTS_DIR, MAX_CONTENT_LENGTH, ALLOWED_EXTENSIONS
from app.database import update_job_status

logger = logging.getLogger("clearcut")

class ImageProcessorService:
    @staticmethod
    def validate_image(file_bytes: bytes, filename: Optional[str] = None) -> None:
        """
        Validates image content length, extension, and file structure.
        Raises ValueError if validation fails.
        """
        # Validate size
        if len(file_bytes) > MAX_CONTENT_LENGTH:
            raise ValueError(f"File size exceeds the limit of {MAX_CONTENT_LENGTH // (1024 * 1024)}MB.")
        if len(file_bytes) == 0:
            raise ValueError("Empty file submitted.")

        # Validate extension if filename provided
        if filename:
            ext = filename.split(".")[-1].lower() if "." in filename else ""
            if ext not in ALLOWED_EXTENSIONS:
                raise ValueError(f"Unsupported file extension '.{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")

        # Validate image integrity using Pillow
        try:
            image = Image.open(io.BytesIO(file_bytes))
            image.verify()  # Verifies the file is not corrupt (reads header, does not decode data)
            
            # Re-open and try a simple load to ensure it's fully decodable
            image = Image.open(io.BytesIO(file_bytes))
            image.load()
        except (UnidentifiedImageError, IOError, SyntaxError) as e:
            logger.warning(f"Failed image validation: {str(e)}")
            raise ValueError("Corrupt or invalid image file structure.")

    @staticmethod
    async def remove_background(image_bytes: bytes) -> bytes:
        """
        Removes background from image bytes using rembg.
        Executed in a separate thread to prevent event loop blocking.
        """
        # Define blocking execution wrapper
        def _process():
            # rembg.remove takes bytes and returns bytes
            return rembg.remove(image_bytes)

        # Offload CPU-heavy processing to thread pool
        return await asyncio.to_thread(_process)


class JobManager:
    @staticmethod
    async def process_job_async(job_id: str, image_bytes: bytes, original_filename: str):
        """
        Asynchronously processes an image job, saving output and updating DB state.
        """
        logger.info(f"Starting background job {job_id} for {original_filename}")
        update_job_status(job_id, "processing")
        
        try:
            # Step 1: Remove background
            processed_bytes = await ImageProcessorService.remove_background(image_bytes)
            
            # Step 2: Save resulting PNG
            output_filename = f"{job_id}.png"
            output_path = OUTPUTS_DIR / output_filename
            
            with open(output_path, "wb") as f:
                f.write(processed_bytes)
                
            # Step 3: Update DB as complete
            update_job_status(job_id, "completed", result_filename=output_filename)
            logger.info(f"Job {job_id} completed successfully. Saved to {output_filename}")
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Job {job_id} failed: {error_msg}")
            update_job_status(job_id, "failed", error_message=error_msg)
