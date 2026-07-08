"""
test_api.py - Integration tests for ClearCut API endpoints.

Uses FastAPI's TestClient to fire real HTTP requests against the full
application stack (minus the rembg model, which is mocked).
All tests use an isolated temporary database seeded via conftest.py.
"""
import io
import pytest
from PIL import Image
from unittest.mock import patch
from tests.conftest import make_test_image


# ─────────────────────────────────────────────────────────────────────────────
# Health Endpoint
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        """GET /health should always be accessible without an API key."""
        res = client.get("/health")
        assert res.status_code == 200

    def test_health_response_schema(self, client):
        """Health response must contain status, version, and services fields."""
        res = client.get("/health")
        data = res.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "timestamp" in data
        assert "services" in data
        assert "database" in data["services"]
        assert "model_loaded" in data["services"]

    def test_health_db_connected(self, client):
        """Database service should report as 'connected'."""
        res = client.get("/health")
        data = res.json()
        assert data["services"]["database"] == "connected"


# ─────────────────────────────────────────────────────────────────────────────
# Authentication
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthentication:
    def test_missing_api_key_returns_401(self, client):
        """Requests without X-API-Key header must return 401."""
        img_bytes = make_test_image("JPEG")
        files = {"file": ("test.jpg", img_bytes, "image/jpeg")}
        res = client.post("/v1/remove-background", files=files)
        assert res.status_code == 401
        assert "API Key missing" in res.json()["detail"]

    def test_invalid_api_key_returns_401(self, client):
        """Requests with a wrong API key must return 401."""
        img_bytes = make_test_image("JPEG")
        files = {"file": ("test.jpg", img_bytes, "image/jpeg")}
        res = client.post(
            "/v1/remove-background",
            files=files,
            headers={"X-API-Key": "totally_wrong_key"}
        )
        assert res.status_code == 401
        assert "Invalid or inactive" in res.json()["detail"]


# ─────────────────────────────────────────────────────────────────────────────
# Input Validation
# ─────────────────────────────────────────────────────────────────────────────

class TestInputValidation:
    def test_non_image_file_returns_400(self, client, auth_headers):
        """Uploading a text file should be rejected with a 400 and a descriptive error."""
        txt_bytes = b"This is a plain text file, not an image"
        files = {"file": ("document.txt", txt_bytes, "text/plain")}
        res = client.post("/v1/remove-background", files=files, headers=auth_headers)
        assert res.status_code == 400
        err = res.json()["detail"]
        assert "extension" in err.lower() or "unsupported" in err.lower()

    def test_corrupt_image_returns_400(self, client, auth_headers):
        """Uploading bytes that look like an image but are corrupt must return 400."""
        corrupt = b"\xff\xd8\xff\xe0" + b"\x00" * 50  # JPEG magic bytes but garbage
        files = {"file": ("photo.jpg", corrupt, "image/jpeg")}
        res = client.post("/v1/remove-background", files=files, headers=auth_headers)
        assert res.status_code == 400
        assert "corrupt" in res.json()["detail"].lower() or "invalid" in res.json()["detail"].lower()

    def test_oversized_file_returns_400(self, client, auth_headers):
        """Files larger than 10MB must be rejected with a 400."""
        big_data = b"x" * (11 * 1024 * 1024)  # 11MB
        files = {"file": ("huge.jpg", big_data, "image/jpeg")}
        res = client.post("/v1/remove-background", files=files, headers=auth_headers)
        assert res.status_code == 400
        assert "size exceeds" in res.json()["detail"].lower()

    def test_no_file_no_url_returns_400(self, client, auth_headers):
        """Sending a request with neither file nor url must return 400."""
        res = client.post("/v1/remove-background", headers=auth_headers)
        assert res.status_code == 400
        assert "provide either" in res.json()["detail"].lower()

    def test_both_file_and_url_returns_400(self, client, auth_headers):
        """Providing both file and url simultaneously must return 400."""
        img_bytes = make_test_image("JPEG")
        data = {"url": "http://example.com/image.jpg"}
        files = {"file": ("test.jpg", img_bytes, "image/jpeg")}
        res = client.post("/v1/remove-background", files=files, data=data, headers=auth_headers)
        assert res.status_code == 400
        assert "both" in res.json()["detail"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# Background Removal — Sync (mocked rembg)
# ─────────────────────────────────────────────────────────────────────────────

class TestRemoveBackground:
    def _make_mock_png(self) -> bytes:
        """Create a valid RGBA PNG output to return from the mock."""
        output = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        buf = io.BytesIO()
        output.save(buf, format="PNG")
        return buf.getvalue()

    def test_valid_jpeg_returns_png(self, client, auth_headers):
        """A valid JPEG upload must return a 200 with image/png content type."""
        img_bytes = make_test_image("JPEG")
        mock_png = self._make_mock_png()

        with patch("app.services.rembg.remove", return_value=mock_png):
            files = {"file": ("photo.jpg", img_bytes, "image/jpeg")}
            res = client.post(
                "/v1/remove-background?format=image",
                files=files,
                headers=auth_headers
            )
        assert res.status_code == 200
        assert res.headers["content-type"] == "image/png"
        # Verify it's a valid PNG
        parsed = Image.open(io.BytesIO(res.content))
        assert parsed.format == "PNG"

    def test_format_json_returns_metadata(self, client, auth_headers):
        """Using ?format=json must return job metadata with a result_url."""
        img_bytes = make_test_image("PNG")
        mock_png = self._make_mock_png()

        with patch("app.services.rembg.remove", return_value=mock_png):
            files = {"file": ("image.png", img_bytes, "image/png")}
            res = client.post(
                "/v1/remove-background?format=json",
                files=files,
                headers=auth_headers
            )
        assert res.status_code == 200
        data = res.json()
        assert "job_id" in data
        assert "result_url" in data
        assert data["status"] == "completed"

    def test_async_mode_returns_202_with_job(self, client, auth_headers):
        """Using ?async=true must return a job object without waiting for processing."""
        img_bytes = make_test_image("JPEG")
        mock_png = self._make_mock_png()

        with patch("app.services.rembg.remove", return_value=mock_png):
            files = {"file": ("async.jpg", img_bytes, "image/jpeg")}
            res = client.post(
                "/v1/remove-background?async=true",
                files=files,
                headers=auth_headers
            )
        # Should return 200 with a pending/processing job response
        assert res.status_code == 200
        data = res.json()
        assert "job_id" in data
        assert data["status"] in ("pending", "processing", "completed")


# ─────────────────────────────────────────────────────────────────────────────
# Jobs Endpoints
# ─────────────────────────────────────────────────────────────────────────────

class TestJobEndpoints:
    def test_get_nonexistent_job_returns_404(self, client, auth_headers):
        """Requesting a job that doesn't exist should return 404."""
        res = client.get("/v1/jobs/nonexistent-job-id-abc", headers=auth_headers)
        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()

    def test_get_job_result_nonexistent_returns_404(self, client, auth_headers):
        """Requesting a result for a missing job should return 404."""
        res = client.get("/v1/jobs/bad-id-xyz/result", headers=auth_headers)
        assert res.status_code == 404

    def test_completed_job_has_result_url(self, client, auth_headers):
        """A job that completes successfully should have result_url in status response."""
        img_bytes = make_test_image("JPEG")
        output_img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        buf = io.BytesIO()
        output_img.save(buf, format="PNG")
        mock_png = buf.getvalue()

        with patch("app.services.rembg.remove", return_value=mock_png):
            # Create a sync job first to get a job_id
            files = {"file": ("check.jpg", img_bytes, "image/jpeg")}
            post_res = client.post(
                "/v1/remove-background?format=json",
                files=files,
                headers=auth_headers
            )
        assert post_res.status_code == 200
        job_id = post_res.json()["job_id"]

        # Query the job status
        status_res = client.get(f"/v1/jobs/{job_id}", headers=auth_headers)
        assert status_res.status_code == 200
        data = status_res.json()
        assert data["status"] == "completed"
        assert data["result_url"] is not None
