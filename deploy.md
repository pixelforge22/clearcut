# Deployment Guide

This guide walks you through deploying ClearCut to **Render** (recommended) and **Railway** as alternatives to running locally via Docker.

---

## Option 1: Render (Recommended)

Render is the easiest path — it supports Docker-based deployments with persistent disks.

### Step 1: Push to GitHub

```bash
git init
git add .
git commit -m "feat: initial ClearCut release"
git remote add origin https://github.com/YOUR_USERNAME/clearcut.git
git push -u origin main
```

### Step 2: Create a New Web Service on Render

1. Go to [render.com](https://render.com) and log in
2. Click **New → Web Service**
3. Connect your GitHub repository
4. Configure the service:
   - **Name**: `clearcut-api`
   - **Region**: Choose closest to you
   - **Branch**: `main`
   - **Root Directory**: `backend`
   - **Runtime**: Docker
   - **Dockerfile Path**: `./Dockerfile`
   - **Instance Type**: Standard (1 GB RAM minimum — the U²-Net model requires ~500MB)

### Step 3: Set Environment Variables

In the Render dashboard, add these environment variables:

| Key | Value |
|---|---|
| `DEFAULT_API_KEY` | A strong random string |
| `DATABASE_URL` | `/data/clearcut.db` |
| `UPLOADS_DIR` | `/data/uploads` |
| `OUTPUTS_DIR` | `/data/outputs` |
| `SERVE_STATIC` | `true` |

### Step 4: Add a Persistent Disk

1. Go to your service's **Disks** tab
2. Click **Add Disk**
3. Set **Mount Path** to `/data`
4. Set **Size** to at least 1 GB

This ensures your SQLite database and processed images persist between deploys.

### Step 5: Deploy

Click **Deploy** — Render will build the Docker image, download the U²-Net model, and start the service. The first build takes 5–10 minutes.

Your service will be live at: `https://clearcut-api.onrender.com`

---

## Option 2: Railway

Railway offers fast deployments with Nixpacks or Docker support.

### Step 1: Install Railway CLI

```bash
npm install -g @railway/cli
railway login
```

### Step 2: Initialize Project

```bash
# From the project root
railway init
railway link  # Link to existing Railway project if applicable
```

### Step 3: Deploy Backend

```bash
cd backend
railway up
```

### Step 4: Set Environment Variables

```bash
railway variables set DEFAULT_API_KEY=your_secret_key
railway variables set DATABASE_URL=/data/clearcut.db
railway variables set SERVE_STATIC=true
```

### Step 5: Add a Volume

In the Railway dashboard:
1. Go to your service → **Volumes**
2. Mount a volume at `/data`

### Step 6: Redeploy

```bash
railway up
```

---

## Option 3: Fly.io

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# From backend directory
cd backend
fly launch --dockerfile Dockerfile --name clearcut-api

# Set secrets
fly secrets set DEFAULT_API_KEY=your_secret_key

# Create a persistent volume
fly volumes create clearcut_data --region lhr --size 2

# Deploy
fly deploy
```

---

## Running Locally Without Docker

For development without Docker:

```bash
# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r backend/requirements.txt

# Run the dev server from the project root
uvicorn app.main:app --reload --port 8000 --app-dir backend
```

Then visit:
- **Frontend**: [http://localhost:8000](http://localhost:8000)
- **API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Frontend as Separate Static Site (Optional)

The frontend is plain HTML/CSS/JS with no build step, making it trivially deployable to any static host.

### Netlify

```bash
# Drag the /frontend folder to netlify.com/drop
# Or use CLI:
npx netlify-cli deploy --dir frontend --prod
```

Update the API host in the browser's **Settings** panel to point to your deployed backend URL.

### GitHub Pages

1. Copy the `/frontend` contents to a `gh-pages` branch
2. Enable GitHub Pages in repository settings → Source: `gh-pages`
3. Update the API host in the frontend settings panel to your backend's URL

---

## Production Checklist

- [ ] Change `DEFAULT_API_KEY` to a long, random string (never use the dev key in production)
- [ ] Set `SERVE_STATIC=false` if hosting the frontend separately
- [ ] Mount a persistent volume for `/data` (database + processed outputs)
- [ ] Set up HTTPS (automatic on Render, Railway, and Fly.io)
- [ ] Review rate limits (`RATE_LIMIT_LIMIT` / `RATE_LIMIT_PERIOD`) for your expected traffic
- [ ] Check the `/health` endpoint is reachable after deploy
