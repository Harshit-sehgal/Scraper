import time
from typing import Any

import requests

API = "http://localhost:8000"


def main() -> None:
    payload: Any = {
        "name": "Live DDG Scrape",
        "mode": "auto",
        "urls": [],
        "topic": "interior designers",
        "location": "Chennai",
        "schema_fields": [
            {"name": "company_name", "field_type": "string"},
            {"name": "contact_phone", "field_type": "phone"},
        ],
        "max_pages": 15,
    }
    response = requests.post(f"{API}/api/jobs", json=payload)
    response.raise_for_status()
    job_id = response.json()["job_id"]
    time.sleep(25)
    result = requests.get(f"{API}/api/jobs/{job_id}")
    result.raise_for_status()


if __name__ == "__main__":
    main()
