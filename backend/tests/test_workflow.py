"""Tests for the Workflow router and models."""

import pytest
from app.models import (
    Workflow,
    WorkflowCreate,
    WorkflowPaginationConfig,
    WorkflowStatus,
    WorkflowStep,
    WorkflowStepType,
    WorkflowUpdate,
)
from fastapi.testclient import TestClient


class TestWorkflowModel:
    """Tests for Workflow model creation and validation."""

    def test_create_workflow(self):
        wf = Workflow(
            name="Test Workflow",
            start_url="https://example.com/products",
        )
        assert wf.name == "Test Workflow"
        assert wf.status == WorkflowStatus.DRAFT
        assert wf.version == 1
        assert wf.total_runs == 0

    def test_workflow_with_steps(self):
        steps = [
            WorkflowStep(step_type=WorkflowStepType.OPEN, value="https://example.com/login"),
            WorkflowStep(step_type=WorkflowStepType.FILL, selector="#username", value="admin"),
            WorkflowStep(step_type=WorkflowStepType.CLICK, selector="#submit"),
        ]
        wf = Workflow(name="Login Flow", steps=steps)
        assert len(wf.steps) == 3
        assert wf.steps[0].step_type == WorkflowStepType.OPEN
        assert wf.steps[0].step_type.value == "goto"

    def test_workflow_id_generated(self):
        wf = Workflow(name="Auto ID Test")
        assert len(wf.id) == 36  # UUID length

    def test_workflow_status_transitions(self):
        wf = Workflow(name="Status Test")
        assert wf.status == WorkflowStatus.DRAFT
        wf.status = WorkflowStatus.ACTIVE
        assert wf.status == WorkflowStatus.ACTIVE
        wf.status = WorkflowStatus.PAUSED
        assert wf.status == WorkflowStatus.PAUSED
        wf.status = WorkflowStatus.FAILED
        assert wf.status == WorkflowStatus.FAILED

    def test_workflow_max_steps_validation(self):
        steps = [WorkflowStep(step_type=WorkflowStepType.OPEN, value=f"https://example.com/{i}") for i in range(101)]
        with pytest.raises(ValueError, match="more than 100 steps"):
            Workflow(name="Too Many Steps", steps=steps)

    def test_pagination_config(self):
        config = WorkflowPaginationConfig(
            enabled=True,
            strategy="next_button",
            max_pages=5,
        )
        assert config.enabled is True
        assert config.max_pages == 5


class TestWorkflowCreateRequest:
    """Tests for WorkflowCreate validation."""

    def test_valid_create(self):
        req = WorkflowCreate(name="My Workflow")
        assert req.name == "My Workflow"

    def test_empty_name_fails(self):
        with pytest.raises(ValueError, match="name"):
            WorkflowCreate(name="")

    def test_create_with_steps(self):
        steps = [
            WorkflowStep(step_type=WorkflowStepType.OPEN, value="https://example.com"),
        ]
        req = WorkflowCreate(name="Step Test", steps=steps)
        assert len(req.steps) == 1


class TestWorkflowUpdateRequest:
    """Tests for WorkflowUpdate partial updates."""

    def test_partial_update(self):
        req = WorkflowUpdate(name="Updated Name")
        assert req.name == "Updated Name"
        assert req.description is None

    def test_status_update(self):
        req = WorkflowUpdate(status=WorkflowStatus.ARCHIVED)
        assert req.status == WorkflowStatus.ARCHIVED


class TestWorkflowEndpoints:
    """Integration tests for the Workflow API endpoints."""

    def test_create_and_get(self, client: TestClient):
        """Create a workflow then retrieve it."""
        resp = client.post(
            "/api/workflows",
            json={"name": "Integration Test", "start_url": "https://example.com"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Integration Test"
        wf_id = data["id"]

        resp = client.get(f"/api/workflows/{wf_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Integration Test"

    def test_list_workflows(self, client: TestClient):
        """List should return workflows."""
        resp = client.get("/api/workflows")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    def test_update_workflow(self, client: TestClient):
        """Update a workflow name."""
        create_resp = client.post(
            "/api/workflows",
            json={"name": "Before Update"},
        )
        assert create_resp.status_code == 201
        wf_id = create_resp.json()["id"]

        update_resp = client.put(
            f"/api/workflows/{wf_id}",
            json={"name": "After Update"},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["name"] == "After Update"

    def test_delete_workflow(self, client: TestClient):
        """Delete a workflow and verify it no longer exists."""
        create_resp = client.post(
            "/api/workflows",
            json={"name": "To Be Deleted"},
        )
        assert create_resp.status_code == 201
        wf_id = create_resp.json()["id"]

        del_resp = client.delete(f"/api/workflows/{wf_id}")
        assert del_resp.status_code == 204

        get_resp = client.get(f"/api/workflows/{wf_id}")
        assert get_resp.status_code == 404

    def test_run_workflow(self, client: TestClient):
        """Queue a workflow for execution."""
        create_resp = client.post(
            "/api/workflows",
            json={"name": "Run Test", "start_url": "https://example.com"},
        )
        assert create_resp.status_code == 201
        wf_id = create_resp.json()["id"]

        run_resp = client.post(f"/api/workflows/{wf_id}/run")
        assert run_resp.status_code == 202
        data = run_resp.json()
        assert data["status"] == "queued"
        assert "job_id" in data

    def test_preview_workflow(self, client: TestClient):
        """Preview a workflow."""
        create_resp = client.post(
            "/api/workflows",
            json={"name": "Preview Test"},
        )
        assert create_resp.status_code == 201
        wf_id = create_resp.json()["id"]

        preview_resp = client.post(f"/api/workflows/{wf_id}/preview")
        assert preview_resp.status_code == 200
        assert preview_resp.json()["workflow_id"] == wf_id

    def test_404_on_missing_workflow(self, client: TestClient):
        """Accessing a non-existent workflow returns 404."""
        resp = client.get("/api/workflows/nonexistent-id")
        assert resp.status_code == 404


class TestWorkflowReplayPrompt9:
    """Prompt 9 characterization tests for workflow replay foundation."""

    SEARCH_HTML = """
    <html>
      <head><title>Search Fixture</title></head>
      <body>
        <form action="/search/results" method="get">
          <label for="q">Keyword</label>
          <input id="q" name="q" type="search" placeholder="Search products" required>
          <label for="category">Category</label>
          <select id="category" name="category">
            <option>Laptops</option>
            <option>Phones</option>
          </select>
          <button id="submit" type="submit">Search</button>
        </form>
        <div class="result">
          <span class="title">Laptop Pro</span>
          <span class="price">$1299</span>
        </div>
      </body>
    </html>
    """

    def _create_draft(self, client: TestClient) -> dict:
        resp = client.post(
            "/api/workflow-drafts/from-url-analysis",
            json={
                "original_url": "https://example.com/search/results?sessionId=abc123xyz789",
                "selected_start_url": "https://example.com/search",
                "detected_reason": "session URL test fixture",
            },
        )
        assert resp.status_code == 201
        return resp.json()

    def _create_mapped_workflow(self, client: TestClient) -> dict:
        draft = self._create_draft(client)
        resp = client.post(
            f"/api/workflow-drafts/{draft['id']}/manual-mapping",
            json={
                "name": "Fixture Search Workflow",
                "start_url": "https://example.com/search",
                "fields": [
                    {
                        "label": "Keyword",
                        "selector": "#q",
                        "value": "laptops",
                        "action": "fill",
                    },
                    {
                        "label": "Category",
                        "selector": "#category",
                        "value": "Laptops",
                        "action": "select",
                    },
                ],
                "submit_action": {"action": "click", "selector": "#submit"},
                "extraction_schema": [
                    {"name": "title", "field_type": "string", "required": False},
                    {"name": "price", "field_type": "string", "required": False},
                ],
            },
        )
        assert resp.status_code == 201
        return resp.json()

    def test_create_workflow_draft_from_session_url(self, client: TestClient):
        draft = self._create_draft(client)

        assert draft["initial_mode"] == "workflow_replay"
        assert draft["selected_start_url"] == "https://example.com/search"
        assert "abc123xyz789" not in draft["original_url"]
        assert draft["recommended_start_urls"]

    def test_field_detection_on_fixture_html(self, client: TestClient):
        draft = self._create_draft(client)

        resp = client.post(
            f"/api/workflow-drafts/{draft['id']}/detect-fields",
            json={"html_snapshot": self.SEARCH_HTML},
        )

        assert resp.status_code == 200
        data = resp.json()
        labels = {field["label"] for field in data["fields"]}
        types = {field["type"] for field in data["fields"]}
        assert {"Keyword", "Category"}.issubset(labels)
        assert "submit" in types
        keyword = next(field for field in data["fields"] if field["label"] == "Keyword")
        assert keyword["selector"] == "#q"
        assert keyword["confidence"] >= 0.75

    def test_manual_mapping_creates_workflow_steps(self, client: TestClient):
        workflow = self._create_mapped_workflow(client)

        assert workflow["mode"] == "workflow_replay"
        assert workflow["status"] == "draft"
        assert workflow["steps"][0]["step_type"] == "goto"
        assert [step["step_type"] for step in workflow["steps"][1:4]] == ["fill", "select", "click"]
        assert workflow["steps"][-1]["step_type"] == "wait_for_timeout_limited"

    def test_preview_executes_fixture_workflow_and_returns_sample(self, client: TestClient):
        workflow = self._create_mapped_workflow(client)

        resp = client.post(
            f"/api/workflows/{workflow['id']}/preview",
            json={"html_snapshot": self.SEARCH_HTML, "sample_limit": 5},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["preview_status"] == "succeeded"
        assert data["sample_rows"] == [{"title": "Laptop Pro", "price": "$1299"}]
        assert [event["action"] for event in data["timeline"][:4]] == ["goto", "fill", "select", "click"]
        assert data["page_title"] == "Search Fixture"

    def test_preview_missing_selector_returns_friendly_failure(self, client: TestClient):
        create_resp = client.post(
            "/api/workflows",
            json={
                "name": "Missing Selector Workflow",
                "start_url": "https://example.com/search",
                "steps": [
                    {"step_type": "goto", "value": "https://example.com/search"},
                    {"step_type": "fill", "selector": "#missing", "value": "laptops"},
                ],
            },
        )
        assert create_resp.status_code == 201
        workflow_id = create_resp.json()["id"]

        resp = client.post(
            f"/api/workflows/{workflow_id}/preview",
            json={"html_snapshot": self.SEARCH_HTML},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["preview_status"] == "failed"
        assert data["failure_type"] == "selector_missing"
        assert "Update the field mapping selector" in data["recommended_action"]
        assert data["timeline"][-1]["status"] == "failed"

    def test_preview_redacts_sensitive_step_values(self, client: TestClient):
        html = """
        <html><head><title>Login Fixture</title></head><body>
          <input id="password" name="password" value="">
          <div class="result"><span class="title">Private Search</span></div>
        </body></html>
        """
        create_resp = client.post(
            "/api/workflows",
            json={
                "name": "Redaction Workflow",
                "start_url": "https://example.com/search",
                "steps": [
                    {"step_type": "goto", "value": "https://example.com/search"},
                    {
                        "step_type": "fill",
                        "selector": "#password",
                        "value": "supersecret",
                        "description": "fill password",
                    },
                ],
                "extraction_schema": [
                    {"name": "title", "field_type": "string", "required": False},
                ],
            },
        )
        assert create_resp.status_code == 201

        resp = client.post(
            f"/api/workflows/{create_resp.json()['id']}/preview",
            json={"html_snapshot": html},
        )

        assert resp.status_code == 200
        body = str(resp.json())
        assert "supersecret" not in body
        assert "supe...cret" in body

    def test_unsafe_start_url_rejected_for_workflow_draft_mapping(self, client: TestClient):
        draft = self._create_draft(client)

        resp = client.post(
            f"/api/workflow-drafts/{draft['id']}/manual-mapping",
            json={
                "name": "Unsafe Start",
                "start_url": "http://127.0.0.1/admin",
                "fields": [],
                "submit_action": {"action": "click", "selector": "#submit"},
            },
        )

        assert resp.status_code == 400
        assert "Unsafe workflow start URL" in resp.json()["detail"]
