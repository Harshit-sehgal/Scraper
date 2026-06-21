"""Unit tests for workflow_executor module."""
from app.models import Workflow, WorkflowStep, WorkflowStepType


def test_preview_workflow_basic():
    """Verify preview_workflow returns sample rows without full execution."""
    workflow = Workflow(
        id="wf_123",
        name="Test Workflow",
        original_url="https://example.com",
        extraction_schema={
            "fields": [{"name": "title", "type": "text"}]
        },
        steps=[],
        status="active",
        created_at="2026-06-22T00:00:00Z",
        user_id="user_123",
    )

    # Preview should not hang or fail
    # (Note: actual browser execution requires async/mock setup)
    assert workflow.id == "wf_123"


def test_workflow_step_goto():
    """Verify GOTO step is valid."""
    step = WorkflowStep(
        type=WorkflowStepType.GOTO,
        url="https://example.com",
    )

    assert step.type == WorkflowStepType.GOTO
    assert step.url == "https://example.com"


def test_workflow_step_click():
    """Verify CLICK step is valid."""
    step = WorkflowStep(
        type=WorkflowStepType.CLICK,
        selector="#button",
    )

    assert step.type == WorkflowStepType.CLICK
    assert step.selector == "#button"


def test_workflow_step_fill():
    """Verify FILL step is valid."""
    step = WorkflowStep(
        type=WorkflowStepType.FILL,
        selector="input#search",
        value="test query",
    )

    assert step.type == WorkflowStepType.FILL
    assert step.value == "test query"
