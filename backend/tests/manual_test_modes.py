import json

from fastapi.testclient import TestClient

from app.main import app


def get_client():
    return TestClient(app)


def test_manual_mode():
    client = get_client()
    print("=== Testing MANUAL Mode ===")
    response = client.post("/api/jobs", json={
        "name": "Test Manual Job",
        "mode": "manual",
        "intent": "Get interior designers in Chennai",
        "topic": "interior designers",
        "urls": ["https://irishinterior.com/contact-us/"],
        "schema_fields": [
            {"name": "company_name", "field_type": "string", "description": "name of company", "required": True},
            {"name": "email", "field_type": "email", "description": "email address", "required": False}
        ],
        "source_policy": "all_sources"  # Don't block any domain
    })
    print("Create Job Response:", response.json())
    job_id = response.json()["job_id"]

    # Wait for completion
    import time
    for _ in range(30):
        res = client.get(f"/api/jobs/{job_id}")
        status = res.json()["status"]
        if status in ["completed", "failed", "canceled"]:
            print("Job finished with status:", status)
            print("Results:", json.dumps(res.json().get("results", []), indent=2))
            break
        time.sleep(2)


def test_auto_mode():
    client = get_client()
    print("\n=== Testing AUTO Mode ===")
    response = client.post("/api/jobs", json={
        "name": "Test Auto Job",
        "mode": "auto",
        "intent": "Get interior designers in Chennai",
        "topic": "interior designers in chennai",
        "location": "chennai",
        "schema_fields": [
            {"name": "company_name", "field_type": "string", "description": "name of company", "required": True},
            {"name": "email", "field_type": "email", "description": "email address", "required": False}
        ],
        "max_pages": 1,  # Just test 1 page for speed
        "source_policy": "all_sources"  # Don't block any domain
    })
    print("Create Job Response:", response.json())
    job_id = response.json()["job_id"]

    import time
    for _ in range(30):
        res = client.get(f"/api/jobs/{job_id}")
        status = res.json()["status"]
        if status in ["completed", "failed", "canceled"]:
            print("Job finished with status:", status)
            print("Results:", json.dumps(res.json().get("results", []), indent=2))
            break
        time.sleep(2)


if __name__ == "__main__":
    test_manual_mode()
    test_auto_mode()
