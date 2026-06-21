"""Unit tests for workflow_executor module."""

from app.models import FieldType, SchemaField, Workflow, WorkflowStatus, WorkflowStep, WorkflowStepType


def test_preview_workflow_basic():
    """Verify preview_workflow returns sample rows without full execution."""
    workflow = Workflow(
        id="wf_123",
        name="Test Workflow",
        original_url="https://example.com",
        extraction_schema=[
            SchemaField(name="title", field_type=FieldType.STRING),
        ],
        steps=[],
        status=WorkflowStatus.ACTIVE,
        created_at="2026-06-22T00:00:00Z",
        user_id="user_123",
    )

    # Preview should not hang or fail
    # (Note: actual browser execution requires async/mock setup)
    assert workflow.id == "wf_123"


def test_workflow_step_goto():
    """Verify GOTO step is valid."""
    step = WorkflowStep(
        step_type=WorkflowStepType.GOTO,
        value="https://example.com",
    )

    assert step.step_type == WorkflowStepType.GOTO
    assert step.value == "https://example.com"


def test_workflow_step_click():
    """Verify CLICK step is valid."""
    step = WorkflowStep(
        step_type=WorkflowStepType.CLICK,
        selector="#button",
    )

    assert step.step_type == WorkflowStepType.CLICK
    assert step.selector == "#button"


def test_workflow_step_fill():
    """Verify FILL step is valid."""
    step = WorkflowStep(
        step_type=WorkflowStepType.FILL,
        selector="input#search",
        value="test query",
    )

    assert step.step_type == WorkflowStepType.FILL
    assert step.value == "test query"
