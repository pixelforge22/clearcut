# ClearCut — AI Background Removal API

> **Instant, pixel-perfect background removal powered by a self-hosted U²-Net model.**

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688?style=flat-square&logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=flat-square&logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-brightgreen?style=flat-square)

ClearCut is a full-stack, production-ready background removal service. It combines a robust REST API (FastAPI, Python) with a polished dark-mode dashboard featuring a real-time before/after comparison slider.

The entire stack — API, model, and frontend — runs from a single Docker command.

---

## ✨ Features

| Feature | Detail |
|---|---|
| **U²-Net Model** | Self-hosted background removal via `rembg` — no third-party API keys required |
| **Dual Input Modes** | Multipart file upload **or** remote image URL |
| **Sync & Async** | Immediate PNG response, or async job polling for large images |
| **API Key Auth** | `X-API-Key` header auth backed by SQLite |
| **Rate Limiting** | In-memory sliding window (60 req/min per key by default) |
| **Structured Logging** | JSON request logs with unique Request IDs and latency tracking |
| **Input Validation** | Rejects non-images, >10MB files, and corrupt uploads with clear JSON errors |
| **OpenAPI Docs** | Auto-generated Swagger UI at `/docs` with real descriptions and examples |
| **Premium Frontend** | Drag-and-drop upload, before/after slider, checkerboard transparency, code snippets |

---

## 🚀 One-Command Setup

**Prerequisites**: [Docker](https://www.docker.com/) and [Docker Compose](https://docs.docker.com/compose/).

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/clearcut.git
cd clearcut

# 2. Start the service (builds container, downloads model, starts server)
docker-compose up --build
```

The service will be available at:

- **Frontend Dashboard**: [http://localhost:8000](http://localhost:8000)
- **Swagger API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

> **Note:** The first build downloads the U²-Net model (~170MB). Subsequent startups use the cached image layer.

---

## 🔑 Authentication

All `/v1/*` endpoints require an `X-API-Key` header.

The default development key is seeded automatically on first start:

```
X-API-Key: clearcut_dev_key_2026
```

To use a custom key, set the `DEFAULT_API_KEY` environment variable before starting:

```bash
DEFAULT_API_KEY=my_secret_key docker-compose up
```

---

## 📡 API Reference

### `GET /health`
Check service status. No auth required.

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "healthy",
  "timestamp": "2026-07-08T02:00:00.000000",
  "version": "1.0.0",
  "services": { "database": "connected", "model_loaded": true }
}
```

---

### `POST /v1/remove-background`

Remove the background from an image. Accepts either a multipart file upload or a remote URL.

**Query Parameters:**
| Parameter | Type | Default | Description |
|---|---|---|---|
| `format` | `image` \| `json` | `image` | Return binary PNG or JSON with metadata |
| `async` | `boolean` | `false` | Submit as a background job, return immediately |

#### cURL — File Upload

```bash
curl -X POST "http://localhost:8000/v1/remove-background" \
  -H "X-API-Key: clearcut_dev_key_2026" \
  -F "file=@my_image.jpg" \
  --output result.png
```

#### cURL — Remote URL + JSON Response

```bash
curl -X POST "http://localhost:8000/v1/remove-background?format=json" \
  -H "X-API-Key: clearcut_dev_key_2026" \
  -F "url=https://example.com/photo.jpg"
```

#### Python

```python
import requests

url = "http://localhost:8000/v1/remove-background"
headers = {"X-API-Key": "clearcut_dev_key_2026"}

with open("my_image.jpg", "rb") as f:
    response = requests.post(url, headers=headers, files={"file": f})

if response.status_code == 200:
    with open("result.png", "wb") as out:
        out.write(response.content)
    print("✓ Background removed. Saved to result.png")
```

#### JavaScript (fetch)

```js
const formData = new FormData();
formData.append('file', document.querySelector('#fileInput').files[0]);

const response = await fetch('http://localhost:8000/v1/remove-background', {
  method: 'POST',
  headers: { 'X-API-Key': 'clearcut_dev_key_2026' },
  body: formData
});

const blob = await response.blob();
const url = URL.createObjectURL(blob);
// Use url to display the transparent PNG
```

---

### `GET /v1/jobs/{job_id}`

Check the status of an async job.

```bash
curl "http://localhost:8000/v1/jobs/{job_id}" \
  -H "X-API-Key: clearcut_dev_key_2026"
```

**Response:**
```json
{
  "job_id": "abc123...",
  "status": "completed",
  "original_filename": "photo.jpg",
  "created_at": "2026-07-08T02:00:00",
  "completed_at": "2026-07-08T02:00:04",
  "result_url": "/v1/jobs/abc123.../result"
}
```

Status values: `pending` → `processing` → `completed` | `failed`

---

### `GET /v1/jobs/{job_id}/result`

Download the final transparent PNG for a completed job.

```bash
curl "http://localhost:8000/v1/jobs/{job_id}/result" \
  -H "X-API-Key: clearcut_dev_key_2026" \
  --output result.png
```

---

## 🧪 Running Tests

```bash
# Install deps (from backend directory)
pip install -r backend/requirements.txt

# Run all tests
cd backend && pytest -v

# Run with coverage report
cd backend && pytest -v --tb=short
```

Tests cover:
- ✅ Image validation (size, extension, corruption)
- ✅ Valid image → transparent PNG output (mocked model)
- ✅ Missing / invalid API key → 401
- ✅ Non-image file → 400
- ✅ Oversized file → 400
- ✅ Async job creation and polling
- ✅ Non-existent job → 404

---

## 🗂 Project Structure

```
clearcut/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py          # FastAPI application factory
│   │   ├── config.py        # Environment-based configuration
│   │   ├── database.py      # SQLite helpers (api_keys, jobs tables)
│   │   ├── auth.py          # X-API-Key dependency
│   │   ├── middleware.py    # Structured logging + rate limiting
│   │   ├── services.py      # rembg wrapper + async job manager
│   │   ├── routes.py        # All API route handlers
│   │   └── schemas.py       # Pydantic response models
│   ├── tests/
│   │   ├── conftest.py      # Shared fixtures & test client
│   │   ├── test_services.py # Unit tests (image processing)
│   │   └── test_api.py      # Integration tests (HTTP endpoints)
│   ├── Dockerfile
│   ├── requirements.txt
│   └── pytest.ini
├── frontend/
│   ├── index.html           # Application shell
│   ├── css/style.css        # Premium dark-mode design system
│   └── js/app.js            # Client-side logic & API integration
├── docker-compose.yml
├── clearcut_postman_collection.json
├── deploy.md
├── .gitignore
└── README.md
```

---

## ⚙️ Configuration

All settings are controlled via environment variables (or `.env` file):

| Variable | Default | Description |
|---|---|---|
| `DEFAULT_API_KEY` | `clearcut_dev_key_2026` | Seed API key for development |
| `DATABASE_URL` | `./data/clearcut.db` | Path to SQLite database file |
| `UPLOADS_DIR` | `./data/uploads` | Temporary upload storage |
| `OUTPUTS_DIR` | `./data/outputs` | Processed PNG storage |
| `MAX_CONTENT_LENGTH` | `10485760` (10MB) | Maximum upload size in bytes |
| `RATE_LIMIT_LIMIT` | `60` | Max requests per time window |
| `RATE_LIMIT_PERIOD` | `60` | Time window in seconds |
| `SERVE_STATIC` | `true` | Whether to serve the frontend from FastAPI |

---

## 🛠 Tech Stack

| Layer | Technology |
|---|---|
| **API Framework** | [FastAPI](https://fastapi.tiangolo.com/) |
| **ML Model** | [rembg](https://github.com/danielgatis/rembg) (U²-Net) |
| **Image Processing** | [Pillow](https://pillow.readthedocs.io/) |
| **Database** | SQLite (via Python `sqlite3`) |
| **Containerization** | Docker + Docker Compose |
| **Testing** | pytest + pytest-asyncio + httpx |
| **Frontend** | Vanilla HTML/CSS/JS (Outfit font, zero frameworks) |

---

## 💡 Why I Built This

I built ClearCut as a showcase of what a well-engineered, production-ready API product looks like when built from scratch. The goal was to combine a technically sound backend — async processing, structured logging, rate limiting, OpenAPI docs, containerization — with a frontend that treats the user experience as a first-class concern.

Background removal is a concrete, demonstrable problem. It makes the before/after slider comparison immediately compelling to both technical and non-technical reviewers: you upload a photo, and seconds later you see the subject cut out with pixel-level precision against a transparency grid. There's no ambiguity about whether it's working.

---

## 📄 License

MIT — free to use for personal and commercial projects.
