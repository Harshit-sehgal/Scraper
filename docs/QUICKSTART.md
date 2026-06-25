# Quickstart Guide

Get up and running with DataForge in 5 minutes.

## Prerequisites

- Python 3.12+
- Node.js 18+ (for frontend)
- Docker (optional, for production)

## Quick Setup

### 1. Clone and Install

```bash
git clone https://github.com/your-org/dataforge-scraper.git
cd dataforge-scraper

# Install Python dependencies
python -m venv .venv
source .venv/bin/activate
pip install .
pip install -e ".[dev]"

# Install Playwright browsers
playwright install chromium

# Install frontend dependencies
npm install
```

### 2. Configure Environment

```bash
# Create environment file
cp .env.example .env

# Edit .env with your settings
# At minimum, set:
# - DATAFORGE_ENV=development
# - GROQ_API_KEY=your-groq-api-key (optional, for AI features)
```

### 3. Start the Server

```bash
# Start development server
make up

# Or run directly
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Access DataForge

Open your browser and go to:
- **Dashboard:** http://localhost:8000/app
- **API Docs:** http://localhost:8000/docs (development only)
- **Health Check:** http://localhost:8000/ready

## First Extraction

### 1. Create an API Key

```bash
# In development with no keys configured, you can skip authentication
# For production, create an API key:
curl -X POST http://localhost:8000/api/session \
  -H "Content-Type: application/json" \
  -d '{"api_key": "your-api-key"}'
```

### 2. Create a Job

```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "name": "My First Extraction",
    "urls": ["https://example.com"],
    "schema": {
      "fields": ["title", "description", "price"]
    }
  }'
```

### 3. Check Job Status

```bash
# Get job ID from response
JOB_ID="your-job-id"

# Check status
curl http://localhost:8000/api/jobs/$JOB_ID \
  -H "X-API-Key: your-api-key"
```

### 4. View Results

```bash
# Get results
curl http://localhost:8000/api/jobs/$JOB_ID/results \
  -H "X-API-Key: your-api-key"
```

## Docker Setup

### Development

```bash
# Start with Docker through the Makefile. This passes your host UID/GID
# into Compose so files created under bind mounts stay editable.
make up

# View logs
make logs

# Stop
make down
```

If you run Compose directly instead of `make up`, pass the same UID/GID
values explicitly:

```bash
DATAFORGE_DEV_UID="$(id -u)" DATAFORGE_DEV_GID="$(id -g)" docker compose up -d
```

### Production

```bash
# Build production image
make build-prod

# Start production stack
make prod

# Check health
curl http://localhost:8000/ready
```

## Common Tasks

### Add Custom Headers

```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "X-API-Key: your-api-key" \
  -d '{
    "name": "Custom Headers Job",
    "urls": ["https://example.com"],
    "headers": {
      "Authorization": "Bearer token",
      "X-Custom": "value"
    }
  }'
```

### Export Results

```bash
# Export as CSV
curl http://localhost:8000/api/jobs/$JOB_ID/export/csv \
  -H "X-API-Key: your-api-key" \
  -o results.csv

# Export as JSON
curl http://localhost:8000/api/jobs/$JOB_ID/export/json \
  -H "X-API-Key: your-api-key" \
  -o results.json

# Export as Excel
curl http://localhost:8000/api/jobs/$JOB_ID/export/excel \
  -H "X-API-Key: your-api-key" \
  -o results.xlsx
```

### Monitor Usage

```bash
# Check usage summary
curl http://localhost:8000/api/usage/summary \
  -H "X-API-Key: your-api-key"

# Check quota status
curl http://localhost:8000/api/quota \
  -H "X-API-Key: your-api-key"
```

## Troubleshooting

### Server Won't Start

```bash
# Check Python version
python --version  # Should be 3.12+

# Check dependencies
pip list | grep fastapi

# Check Playwright
playwright install chromium
```

### Jobs Failing

```bash
# Check logs
docker compose logs dataforge

# Check job events
curl http://localhost:8000/api/jobs/$JOB_ID/events \
  -H "X-API-Key: your-api-key"
```

### Authentication Issues

```bash
# In development, check if auth is required
curl http://localhost:8000/health

# For production, ensure API key is set
echo $X_API_KEY
```

## Next Steps

- Read the [API Documentation](API.md)
- Review [Extraction Quality](EXTRACTION_QUALITY.md)
- Set up [Monitoring](MONITORING.md)
- Configure [Billing](BILLING.md)

## Need Help?

- **GitHub Issues:** https://github.com/your-org/dataforge-scraper/issues
- **Documentation:** Check the `docs/` directory
- **API Reference:** http://localhost:8000/docs (development only)
