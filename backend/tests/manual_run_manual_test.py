import time

import requests

API = "http://localhost:8000"
payload = {
    "name": "Live DDG Scrape",
    "mode": "auto",
    "urls": [],
    "topic": "interior designers",
    "location": "Chennai",
    "schema_fields": [{"name": "company_name", "field_type": "string"}, {"name": "contact_phone", "field_type": "phone"}],
    "max_pages": 15
}
r = requests.post(f"{API}/api/jobs", json=payload)
job_id = r.json()["job_id"]
print("Job created! Waiting 20 seconds...")
time.sleep(25)
res = requests.get(f"{API}/api/jobs/{job_id}")
print("Status:", res.json().get('status'))
print("Extracted Data:", res.json().get('results')[:3])
