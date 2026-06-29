"""Tests for notification integration endpoints (Feat 36)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _create_job(client: TestClient) -> str:
    payload = {
        "name": "notif-test-job",
        "mode": "manual",
        "urls": ["https://example.com"],
        "schema_fields": [{"name": "title", "field_type": "string"}],
    }
    resp = client.post("/api/jobs", json=payload)
    assert resp.status_code == 201
    return resp.json()["job_id"]


def test_create_slack_channel(client: TestClient) -> None:
    job_id = _create_job(client)
    resp = client.post(
        f"/api/jobs/{job_id}/notification-channels",
        json={"type": "slack", "webhook_url": "https://hooks.slack.com/test", "events": ["completed"]},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["type"] == "slack"
    assert body["enabled"] is True


def test_create_discord_channel(client: TestClient) -> None:
    job_id = _create_job(client)
    resp = client.post(
        f"/api/jobs/{job_id}/notification-channels",
        json={"type": "discord", "webhook_url": "https://discord.com/api/webhooks/test"},
    )
    assert resp.status_code == 201
    assert resp.json()["type"] == "discord"


def test_create_teams_channel(client: TestClient) -> None:
    job_id = _create_job(client)
    resp = client.post(
        f"/api/jobs/{job_id}/notification-channels",
        json={"type": "teams", "webhook_url": "https://outlook.office.com/webhook/test"},
    )
    assert resp.status_code == 201


def test_list_channels(client: TestClient) -> None:
    job_id = _create_job(client)
    client.post(
        f"/api/jobs/{job_id}/notification-channels",
        json={"type": "slack", "webhook_url": "https://hooks.slack.com/1"},
    )
    client.post(
        f"/api/jobs/{job_id}/notification-channels",
        json={"type": "discord", "webhook_url": "https://discord.com/webhooks/2"},
    )
    resp = client.get(f"/api/jobs/{job_id}/notification-channels")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_update_channel(client: TestClient) -> None:
    job_id = _create_job(client)
    create = client.post(
        f"/api/jobs/{job_id}/notification-channels",
        json={"type": "slack", "webhook_url": "https://hooks.slack.com/old"},
    )
    channel_id = create.json()["id"]
    resp = client.patch(
        f"/api/jobs/{job_id}/notification-channels/{channel_id}",
        json={"webhook_url": "https://hooks.slack.com/new"},
    )
    assert resp.status_code == 200
    assert resp.json()["webhook_url"] == "https://hooks.slack.com/new"


def test_delete_channel(client: TestClient) -> None:
    job_id = _create_job(client)
    create = client.post(
        f"/api/jobs/{job_id}/notification-channels",
        json={"type": "slack", "webhook_url": "https://hooks.slack.com/del"},
    )
    channel_id = create.json()["id"]
    resp = client.delete(f"/api/jobs/{job_id}/notification-channels/{channel_id}")
    assert resp.status_code == 204


def test_list_after_delete(client: TestClient) -> None:
    job_id = _create_job(client)
    c1 = client.post(
        f"/api/jobs/{job_id}/notification-channels",
        json={"type": "slack", "webhook_url": "https://hooks.slack.com/1"},
    ).json()
    c2 = client.post(
        f"/api/jobs/{job_id}/notification-channels",
        json={"type": "discord", "webhook_url": "https://discord.com/2"},
    ).json()
    client.delete(f"/api/jobs/{job_id}/notification-channels/{c1['id']}")
    channels = client.get(f"/api/jobs/{job_id}/notification-channels").json()
    assert len(channels) == 1
    assert channels[0]["id"] == c2["id"]


def test_channel_invalid_type_returns_422(client: TestClient) -> None:
    job_id = _create_job(client)
    resp = client.post(
        f"/api/jobs/{job_id}/notification-channels",
        json={"type": "pagerduty", "webhook_url": "https://example.com/hook"},
    )
    assert resp.status_code == 422


def test_channel_not_found(client: TestClient) -> None:
    job_id = _create_job(client)
    resp = client.delete(f"/api/jobs/{job_id}/notification-channels/non-existent")
    assert resp.status_code == 404
