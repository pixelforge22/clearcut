"""
conftest.py - Shared test fixtures and setup for ClearCut tests.

Sets up a temporary SQLite database, seeds a test API key, and provides
an httpx TestClient for integration tests without touching real data.
"""
import io
import os
import tempfile
import pytest
from PIL import Image
from fastapi.testclient import TestClient

# Point to a temporary database before importing app modules
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = _tmp.name
os.environ["DEFAULT_API_KEY"] = "test_api_key_12345"
os.environ["SERVE_STATIC"] = "false"

# Import after env is set
from app.main import app  # noqa: E402
from app.database import init_db  # noqa: E402

TEST_API_KEY = "test_api_key_12345"


def make_test_image(format: str = "JPEG", width: int = 100, height: int = 100) -> bytes:
    """Generate a small in-memory image for testing."""
    img = Image.new("RGB", (width, height), color=(73, 109, 137))
    buf = io.BytesIO()
    img.save(buf, format=format)
    buf.seek(0)
    return buf.getvalue()


@pytest.fixture(scope="session")
def client():
    """Test client scoped to the full test session."""
    init_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers():
    """Returns authorization headers for authenticated requests."""
    return {"X-API-Key": TEST_API_KEY}
