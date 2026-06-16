import time
from typing import Any

import requests

API = "http://localhost:8000"


def main() -> None:
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
        msg = f"Error: {r1.text}"
        raise SystemExit(msg)
    job_id = r1.json()["job_id"]

    time.sleep(1)
    requests.delete(f"{API}/api/jobs/{job_id}")

    r3 = requests.get(f"{API}/api/recycle_bin")
    [j["id"] for j in r3.json().get("jobs", [])]

    requests.post(f"{API}/api/recycle_bin/{job_id}/restore")

    requests.delete(f"{API}/api/jobs/{job_id}")

    requests.delete(f"{API}/api/recycle_bin/{job_id}")

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
    rcrawler.json()["job_id"]


if __name__ == "__main__":
    main()
