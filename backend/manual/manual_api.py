import time

import requests

BASE_URL = "http://127.0.0.1:8000"


def wait_for_job(job_id) -> None:
    for _ in range(60):
        res = requests.get(f"{BASE_URL}/api/jobs/{job_id}")
        data = res.json()
        if data["status"] in ["completed", "failed", "canceled"]:
            return
        time.sleep(2)


def test_manual() -> None:
    res = requests.post(
        f"{BASE_URL}/api/jobs",
        json={
            "name": "Manual Test",
            "mode": "manual",
            "intent": "Get interior designers",
            "topic": "interior designers",
            "urls": ["https://irishinterior.com/contact-us/"],
            "schema_fields": [
                {"name": "company_name", "field_type": "string", "description": "name of company", "required": True},
                {"name": "email", "field_type": "email", "description": "email address", "required": False},
            ],
            "source_policy": "all_sources",
        },
    )
    job_id = res.json()["job_id"]
    wait_for_job(job_id)


def test_auto() -> None:
    res = requests.post(
        f"{BASE_URL}/api/jobs",
        json={
            "name": "Auto Test",
            "mode": "auto",
            "intent": "Get interior designers in Chennai",
            "topic": "interior designers in chennai",
            "location": "chennai",
            "schema_fields": [
                {"name": "company_name", "field_type": "string", "description": "name of company", "required": True},
                {"name": "email", "field_type": "email", "description": "email address", "required": False},
            ],
            "max_pages": 1,
            "source_policy": "all_sources",
        },
    )
    job_id = res.json()["job_id"]
    wait_for_job(job_id)


if __name__ == "__main__":
    test_manual()
    test_auto()
