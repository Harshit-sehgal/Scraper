# Tutorials & Examples

## Table of Contents

- [Tutorial 1: First Extraction](#tutorial-1-first-extraction)
- [Tutorial 2: Custom Schema Extraction](#tutorial-2-custom-schema-extraction)
- [Tutorial 3: Batch Processing](#tutorial-3-batch-processing)
- [Tutorial 4: API Integration](#tutorial-4-api-integration)
- [Tutorial 5: Webhook Notifications](#tutorial-5-webhook-notifications)
- [Example: E-commerce Product Scraping](#example-e-commerce-product-scraping)
- [Example: Job Listing Extraction](#example-job-listing-extraction)
- [Example: News Article Scraping](#example-news-article-scraping)

---

## Tutorial 1: First Extraction

### Goal
Extract data from a single webpage.

### Steps

1. **Start DataForge**
   ```bash
   make up
   ```

2. **Open Dashboard**
   Navigate to http://localhost:8000/app

3. **Create a Job**
   - Click "New" tab
   - Enter URL: `https://example.com`
   - Click "Analyze URL"

4. **Review Extraction**
   - DataForge will analyze the page
   - Review extracted fields
   - Adjust if needed

5. **Run Extraction**
   - Click "Start Extraction"
   - Monitor progress in Jobs tab

6. **View Results**
   - Click on completed job
   - View extracted data
   - Export as CSV/JSON/Excel

### Code equivalent
```python
import requests

# Create job
response = requests.post(
    "http://localhost:8000/api/jobs",
    headers={"X-API-Key": "your-api-key"},
    json={
        "name": "First Extraction",
        "urls": ["https://example.com"],
    }
)
job_id = response.json()["id"]

# Check status
response = requests.get(
    f"http://localhost:8000/api/jobs/{job_id}",
    headers={"X-API-Key": "your-api-key"}
)
print(response.json())
```

---

## Tutorial 2: Custom Schema Extraction

### Goal
Extract specific fields using a custom schema.

### Steps

1. **Create Schema**
   ```json
   {
     "fields": [
       {"name": "title", "selector": "h1"},
       {"name": "description", "selector": "meta[name='description']", "attribute": "content"},
       {"name": "price", "selector": ".price", "type": "number"},
       {"name": "image", "selector": "img.hero", "attribute": "src"}
     ]
   }
   ```

2. **Create Job with Schema**
   ```bash
   curl -X POST http://localhost:8000/api/jobs \
     -H "X-API-Key: your-api-key" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "Custom Schema Extraction",
       "urls": ["https://example.com/product"],
       "schema": {
         "fields": [
           {"name": "title", "selector": "h1"},
           {"name": "description", "selector": "meta[name='\''description'\'']", "attribute": "content"},
           {"name": "price", "selector": ".price", "type": "number"}
         ]
       }
     }'
   ```

3. **Review Results**
   - Results will match your schema
   - Each field extracted according to selector

### Schema Options
```python
schema = {
    "fields": [
        {
            "name": "field_name",           # Field name in output
            "selector": "css-selector",      # CSS selector
            "attribute": "href",             # HTML attribute (optional)
            "type": "number",                # Data type (optional)
            "required": True,                # Required field (optional)
            "default": "N/A"                 # Default value (optional)
        }
    ]
}
```

---

## Tutorial 3: Batch Processing

### Goal
Process multiple URLs efficiently.

### Steps

1. **Create Batch Job**
   ```bash
   curl -X POST http://localhost:8000/api/jobs \
     -H "X-API-Key: your-api-key" \
     -d '{
       "name": "Batch Extraction",
       "urls": [
         "https://example.com/page1",
         "https://example.com/page2",
         "https://example.com/page3"
       ]
     }'
   ```

2. **Monitor Progress**
   ```bash
   # Check job status
   curl http://localhost:8000/api/jobs?status=running \
     -H "X-API-Key: your-api-key"
   ```

3. **Export All Results**
   ```bash
   # Export as CSV
   curl http://localhost:8000/api/jobs/{job_id}/export/csv \
     -H "X-API-Key: your-api-key" \
     -o batch_results.csv
   ```

### Batch Best Practices
- Use 10-50 URLs per batch
- Add delays between batches
- Monitor rate limits
- Handle failures gracefully

---

## Tutorial 4: API Integration

### Goal
Integrate DataForge with your application.

### Example: Python Integration

```python
import requests
from typing import List, Dict

class DataForgeClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.headers = {"X-API-Key": api_key}

    def create_job(self, urls: List[str], name: str = None) -> Dict:
        """Create a new extraction job."""
        response = requests.post(
            f"{self.base_url}/api/jobs",
            headers=self.headers,
            json={
                "name": name or f"Job {len(urls)} URLs",
                "urls": urls
            }
        )
        return response.json()

    def get_job(self, job_id: str) -> Dict:
        """Get job status and results."""
        response = requests.get(
            f"{self.base_url}/api/jobs/{job_id}",
            headers=self.headers
        )
        return response.json()

    def get_results(self, job_id: str) -> List[Dict]:
        """Get extraction results."""
        response = requests.get(
            f"{self.base_url}/api/jobs/{job_id}/results",
            headers=self.headers
        )
        return response.json()

    def wait_for_completion(self, job_id: str, timeout: int = 300) -> Dict:
        """Wait for job to complete."""
        import time
        start = time.time()

        while time.time() - start < timeout:
            job = self.get_job(job_id)
            if job["status"] in ["completed", "failed"]:
                return job
            time.sleep(5)

        raise TimeoutError(f"Job {job_id} did not complete in {timeout}s")

# Usage
client = DataForgeClient("http://localhost:8000", "your-api-key")

# Create and run job
job = client.create_job(["https://example.com"])
print(f"Job created: {job['id']}")

# Wait for completion
job = client.wait_for_completion(job["id"])
print(f"Job status: {job['status']}")

# Get results
results = client.get_results(job["id"])
print(f"Extracted {len(results)} records")
```

### Example: JavaScript Integration

```javascript
class DataForgeClient {
  constructor(baseUrl, apiKey) {
    this.baseUrl = baseUrl;
    this.headers = { 'X-API-Key': apiKey };
  }

  async createJob(urls, name) {
    const response = await fetch(`${this.baseUrl}/api/jobs`, {
      method: 'POST',
      headers: {
        ...this.headers,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        name: name || `Job ${urls.length} URLs`,
        urls
      })
    });
    return response.json();
  }

  async getJob(jobId) {
    const response = await fetch(
      `${this.baseUrl}/api/jobs/${jobId}`,
      { headers: this.headers }
    );
    return response.json();
  }

  async waitForCompletion(jobId, timeout = 300) {
    const start = Date.now();
    while (Date.now() - start < timeout * 1000) {
      const job = await this.getJob(jobId);
      if (['completed', 'failed'].includes(job.status)) {
        return job;
      }
      await new Promise(r => setTimeout(r, 5000));
    }
    throw new Error(`Job ${jobId} timed out`);
  }
}

// Usage
const client = new DataForgeClient('http://localhost:8000', 'your-api-key');
const job = await client.createJob(['https://example.com']);
console.log(`Job created: ${job.id}`);
```

---

## Tutorial 5: Webhook Notifications

### Goal
Receive notifications when jobs complete.

### Steps

1. **Configure Webhook**
   ```bash
   curl -X POST http://localhost:8000/api/jobs \
     -H "X-API-Key: your-api-key" \
     -d '{
       "name": "Job with Webhook",
       "urls": ["https://example.com"],
       "webhook_url": "https://your-server.com/webhook",
       "webhook_events": ["completed", "failed"]
     }'
   ```

2. **Handle Webhook**
   ```python
   from fastapi import FastAPI, Request

   app = FastAPI()

   @app.post("/webhook")
   async def handle_webhook(request: Request):
       data = await request.json()

       if data["event"] == "completed":
           print(f"Job {data['job_id']} completed!")
           # Process results
       elif data["event"] == "failed":
           print(f"Job {data['job_id']} failed!")
           # Handle failure

       return {"status": "ok"}
   ```

---

## Example: E-commerce Product Scraping

### Goal
Extract product data from an e-commerce site.

### Schema
```json
{
  "fields": [
    {"name": "title", "selector": "h1.product-title"},
    {"name": "price", "selector": ".price-current", "type": "number"},
    {"name": "description", "selector": ".product-description"},
    {"name": "images", "selector": ".product-images img", "attribute": "src", "multiple": true},
    {"name": "rating", "selector": ".rating", "type": "number"},
    {"name": "reviews_count", "selector": ".reviews-count", "type": "number"},
    {"name": "sku", "selector": "[data-sku]", "attribute": "data-sku"}
  ]
}
```

### Code
```python
# Create extraction job
job = client.create_job(
    urls=["https://store.example.com/product/123"],
    name="Product Extraction"
)

# Wait and get results
job = client.wait_for_completion(job["id"])
results = client.get_results(job["id"])

# Process results
for product in results:
    print(f"Product: {product['title']}")
    print(f"Price: ${product['price']}")
    print(f"Rating: {product['rating']}/5")
```

---

## Example: Job Listing Extraction

### Goal
Extract job listings from a job board.

### Schema
```json
{
  "fields": [
    {"name": "title", "selector": ".job-title"},
    {"name": "company", "selector": ".company-name"},
    {"name": "location", "selector": ".job-location"},
    {"name": "salary", "selector": ".salary", "type": "string"},
    {"name": "description", "selector": ".job-description"},
    {"name": "posted_date", "selector": ".posted-date", "type": "date"},
    {"name": "url", "selector": "a.apply-link", "attribute": "href"}
  ]
}
```

### Pagination Handling
```python
# For paginated listings
urls = [
    "https://jobs.example.com/page/1",
    "https://jobs.example.com/page/2",
    "https://jobs.example.com/page/3"
]

job = client.create_job(urls, name="Job Listings Extraction")
```

---

## Example: News Article Scraping

### Goal
Extract news articles from a news site.

### Schema
```json
{
  "fields": [
    {"name": "title", "selector": "h1.article-title"},
    {"name": "author", "selector": ".author-name"},
    {"name": "published_date", "selector": "time", "attribute": "datetime"},
    {"name": "content", "selector": ".article-body"},
    {"name": "image", "selector": ".hero-image img", "attribute": "src"},
    {"name": "tags", "selector": ".article-tags", "multiple": true}
  ]
}
```

### Code
```python
# Extract multiple articles
article_urls = [
    "https://news.example.com/article/1",
    "https://news.example.com/article/2",
    "https://news.example.com/article/3"
]

job = client.create_job(article_urls, name="News Extraction")
job = client.wait_for_completion(job["id"])

# Get results
articles = client.get_results(job["id"])

for article in articles:
    print(f"Title: {article['title']}")
    print(f"Author: {article['author']}")
    print(f"Date: {article['published_date']}")
    print("---")
```

---

## Tips & Best Practices

### 1. Start Small
- Test with 1-2 URLs first
- Verify schema works
- Then scale up

### 2. Handle Errors
```python
try:
    job = client.wait_for_completion(job_id)
except TimeoutError:
    print("Job timed out")
except Exception as e:
    print(f"Error: {e}")
```

### 3. Respect Rate Limits
- Check rate limit headers
- Add delays between requests
- Use batch processing

### 4. Cache Results
- Cache extracted data
- Avoid re-extracting same pages
- Use idempotency keys

### 5. Monitor Quality
- Check extraction success rate
- Review data completeness
- Update selectors as needed

---

## Need Help?

- Check the [API Documentation](API.md)
- Review [Extraction Quality](EXTRACTION_QUALITY.md)
- Join our [Community](https://github.com/your-org/dataforge-scraper/discussions)
