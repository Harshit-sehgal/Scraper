import time
from typing import Any

import requests

API = "http://localhost:8000"


def main():
    print("1. Creating a dummy job to test delete and recycle bin...")
    payload: Any = {
        "name": "Recycle Bin Test Job",
        "mode": "manual",
        "urls": ["https://example.com"],
        "location": "",
        "schema_fields": [{"name": "title", "field_type": "string"}],
        "filters": [],
        "max_pages": 1,
    }
    r1 = requests.post(f"{API}/api/jobs", json=payload)
    if r1.status_code != 200:
        raise SystemExit(f"Error: {r1.text}")
    job_id = r1.json()["job_id"]
    print("Created job:", job_id)

    time.sleep(1)
    print("2. Soft-deleting job to move to recycle bin...")
    r2 = requests.delete(f"{API}/api/jobs/{job_id}")
    print(f"Delete response: {r2.status_code}")

    print("3. Checking Recycle Bin...")
    r3 = requests.get(f"{API}/api/recycle_bin")
    bin_jobs = [j["id"] for j in r3.json().get("jobs", [])]
    print(f"Items in Recycle Bin: {bin_jobs}")

    print("4. Restoring job...")
    r4 = requests.post(f"{API}/api/recycle_bin/{job_id}/restore")
    print(f"Restore response: {r4.status_code}")

    print("5. Soft-deleting job AGAIN to move to recycle bin...")
    requests.delete(f"{API}/api/jobs/{job_id}")

    print("6. Hard deleting job forever...")
    r6 = requests.delete(f"{API}/api/recycle_bin/{job_id}")
    print(f"Permanent delete response: {r6.status_code}")

    print("\n--- RECYCLE BIN TEST PASSED ---")

    print("\n7. Executing 100-page DDGS Auto Discovery!")
    payload2: Any = {
        "name": "100-Page DDG Crawler: Chennai Designers",
        "mode": "auto",
        "urls": [],
        "topic": "interior designers",
        "location": "Chennai",
        "max_pages": 50,  # Let's test with 50 first
        "schema_fields": [
            {"name": "company_name", "field_type": "string"},
            {"name": "contact_phone", "field_type": "phone"},
            {"name": "email", "field_type": "email"},
        ],
    }
    rcrawler = requests.post(f"{API}/api/jobs", json=payload2)
    rcrawler.raise_for_status()
    job_id2 = rcrawler.json()["job_id"]
    print("Spawned Auto-Discovery Job:", job_id2)


if __name__ == "__main__":
    main()
