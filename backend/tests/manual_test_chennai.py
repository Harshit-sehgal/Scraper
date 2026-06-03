import json
import time
from pathlib import Path
from typing import Any

import requests


def main():
    payload: Any = {
        "name": "B2B Chennai Interior Designers",
        "urls": [
            "https://irishinterior.com/contact-us/",
            "https://dlifeinteriors.com/contact-us/",
            "https://theplank.in/contact/",
            "https://vibrantspaces.in/contact-us/",
            "https://arcmeninterior.com/contact-us/",
        ],
        "schema_fields": [
            {
                "name": "company_name",
                "field_type": "string",
                "description": "name of the company",
                "required": True,
            },
            {
                "name": "contact_phone",
                "field_type": "phone",
                "description": "phone number",
                "required": False,
            },
            {
                "name": "email",
                "field_type": "email",
                "description": "contact email address",
                "required": False,
            },
            {
                "name": "address",
                "field_type": "string",
                "description": "physical office address",
                "required": False,
            },
        ],
        "pagination": False,
        "deduplicate": True,
        "deduplicate_field": "company_name",
    }

    print("Submitting job...")
    res = requests.post("http://localhost:8000/api/jobs", json=payload)
    res.raise_for_status()
    job_id = res.json()["job_id"]
    print(f"Job ID: {job_id}")

    while True:
        time.sleep(2)
        status_response = requests.get(f"http://localhost:8000/api/jobs/{job_id}")
        status_response.raise_for_status()
        status = status_response.json()
        print(f"Status: {status['status']}")
        if status["status"] in ["completed", "failed"]:
            break

    print("\n=== AI Insight ===")
    print(status.get("analysis", "None"))
    print("\n=== Data Snippet ===")
    print(json.dumps(status.get("results", [])[:15], indent=2))
    print(f"\nTotal extracted: {status.get('filtered_records', 0)}")

    output_path = Path(__file__).resolve().parents[2] / "chennai_leads.json"
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(status.get("results", []), f, indent=2)
    print(f"Saved all leads to {output_path}")


if __name__ == "__main__":
    main()
