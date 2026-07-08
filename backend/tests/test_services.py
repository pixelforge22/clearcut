"""
test_services.py - Unit tests for the ImageProcessorService.

The rembg model is mocked to ensure these tests run fast and offline,
focusing on validation logic and the service interface — not the ML model.
"""
import io
import pytest
from PIL import Image
from unittest.mock import patch, AsyncMock
from tests.conftest import make_test_image
from app.services import ImageProcessorService


class TestImageValidation:
    """Tests for ImageProcessorService.validate_image()"""

    def test_valid_jpeg_passes(self):
        """A clean JPEG should pass validation without raising."""
        img_bytes = make_test_image("JPEG")
        # Should not raise
        ImageProcessorService.validate_image(img_bytes, "photo.jpg")

    def test_valid_png_passes(self):
        """A clean PNG should pass validation without raising."""
        img_bytes = make_test_image("PNG")
        ImageProcessorService.validate_image(img_bytes, "photo.png")

    def test_valid_webp_passes(self):
        """A clean WEBP should pass validation without raising."""
        img_bytes = make_test_image("WEBP")
        ImageProcessorService.validate_image(img_bytes, "photo.webp")

    def test_empty_file_raises(self):
        """An empty byte string should fail with 'Empty file submitted'."""
        with pytest.raises(ValueError, match="Empty file"):
            ImageProcessorService.validate_image(b"", "empty.jpg")

    def test_oversized_file_raises(self):
        """A file exceeding MAX_CONTENT_LENGTH should raise a ValueError."""
        # Generate ~11MB of fake data
        oversized = b"x" * (11 * 1024 * 1024)
        with pytest.raises(ValueError, match="size exceeds the limit"):
            ImageProcessorService.validate_image(oversized, "big.jpg")

    def test_invalid_extension_raises(self):
        """Files with unsupported extensions (e.g. .txt) should be rejected."""
        img_bytes = make_test_image("JPEG")
        with pytest.raises(ValueError, match="Unsupported file extension"):
            ImageProcessorService.validate_image(img_bytes, "document.txt")

    def test_gif_extension_raises(self):
        """GIF is not in ALLOWED_EXTENSIONS and should fail."""
        img_bytes = make_test_image("JPEG")
        with pytest.raises(ValueError, match="Unsupported file extension"):
            ImageProcessorService.validate_image(img_bytes, "animation.gif")

    def test_corrupt_image_raises(self):
        """Bytes that don't form a valid image should raise ValueError."""
        corrupt_bytes = b"This is definitely not an image file at all!!!"
        with pytest.raises(ValueError, match="Corrupt or invalid image"):
            ImageProcessorService.validate_image(corrupt_bytes, "corrupt.jpg")

    def test_no_filename_skips_extension_check(self):
        """When no filename is provided, only size and structure are checked."""
        img_bytes = make_test_image("JPEG")
        # Should not raise — no filename means no extension check
        ImageProcessorService.validate_image(img_bytes, None)


class TestBackgroundRemoval:
    """Tests for ImageProcessorService.remove_background() — model is mocked."""

    @pytest.mark.asyncio
    async def test_remove_background_returns_bytes(self):
        """Mocked rembg.remove should return processed PNG bytes."""
        # Create a simple output PNG
        output_img = Image.new("RGBA", (50, 50), (0, 0, 0, 0))
        output_buf = io.BytesIO()
        output_img.save(output_buf, format="PNG")
        expected_output = output_buf.getvalue()

        input_bytes = make_test_image("JPEG")

        with patch("app.services.rembg.remove", return_value=expected_output) as mock_remove:
            result = await ImageProcessorService.remove_background(input_bytes)
            mock_remove.assert_called_once_with(input_bytes)
            assert result == expected_output
            assert isinstance(result, bytes)
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_remove_background_output_is_png(self):
        """The output from background removal should be a valid PNG."""
        output_img = Image.new("RGBA", (50, 50), (255, 0, 0, 128))
        output_buf = io.BytesIO()
        output_img.save(output_buf, format="PNG")
        mock_output = output_buf.getvalue()

        input_bytes = make_test_image("PNG")

        with patch("app.services.rembg.remove", return_value=mock_output):
            result = await ImageProcessorService.remove_background(input_bytes)
            # Parse the output as an image — it must be valid
            parsed = Image.open(io.BytesIO(result))
            assert parsed.format == "PNG"
