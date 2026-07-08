import json
import time

import requests

payload = {
    "name": "B2B Chennai Interior Designers",
    "urls": [
        "https://irishinterior.com/contact-us/",
        "https://dlifeinteriors.com/contact-us/",
        "https://theplank.in/contact/",
        "https://vibrantspaces.in/contact-us/",
        "https://arcmeninterior.com/contact-us/"
    ],
    "schema_fields": [
        {"name": "company_name", "field_type": "string", "description": "name of the company", "required": True},
        {"name": "contact_phone", "field_type": "phone", "description": "phone number", "required": False},
        {"name": "email", "field_type": "email", "description": "contact email address", "required": False},
        {"name": "address", "field_type": "string", "description": "physical office address", "required": False}
    ],
    "pagination": False,
    "deduplicate": True,
    "deduplicate_field": "company_name"
}

print("Submitting job...")
res = requests.post("http://localhost:8000/api/jobs", json=payload)
job_id = res.json()["job_id"]
print(f"Job ID: {job_id}")

while True:
    time.sleep(2)
    s = requests.get(f"http://localhost:8000/api/jobs/{job_id}").json()
    print(f"Status: {s['status']}")
    if s["status"] in ["completed", "failed"]:
        break

print("\n=== AI Insight ===")
print(s.get("analysis", "None"))
print("\n=== Data Snippet ===")
print(json.dumps(s.get("results", [])[:15], indent=2))
print(f"\nTotal extracted: {s.get('filtered_records', 0)}")

# Save exactly what the user wanted
with open("/home/harshit/Documents/Work/Money/scraper/chennai_leads.json", "w") as f:
    json.dump(s.get("results", []), f, indent=2)
print("Saved all leads to chennai_leads.json")
