"""Bounded Workflow Replay runner and field detector.

This module keeps Workflow Replay execution logic out of route handlers.
It supports deterministic local HTML snapshots for tests and a narrow
HTML-fetch path for product preview. Full Playwright automation can be
added behind this interface without changing API handlers.
"""

from __future__ import annotations

import datetime
from typing import Any

from bs4 import BeautifulSoup

from app.models import SchemaField, Workflow, WorkflowStep, WorkflowStepType

SENSITIVE_NAME_PARTS = ("password", "pass", "token", "secret", "session", "cookie", "auth")
MAX_WAIT_MS = 10_000


def _now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _is_sensitive_name(value: str) -> bool:
    lowered = str(value or "").lower()
    return any(part in lowered for part in SENSITIVE_NAME_PARTS)


def redact_step_value(value: str, *, label: str = "", selector: str = "") -> str:
    """Redact values that look like credentials/session material."""
    raw = str(value or "")
    if not raw:
        return ""
    if not (_is_sensitive_name(label) or _is_sensitive_name(selector)):
        return raw
    if len(raw) <= 4:
        return "..."
    if len(raw) <= 8:
        return f"{raw[:2]}...{raw[-2:]}"
    return f"{raw[:4]}...{raw[-4:]}"


def _css_selector_for_control(control) -> str:
    control_id = control.get("id")
    if control_id:
        return f"#{control_id}"
    name = control.get("name")
    if name:
        return f'{control.name}[name="{name}"]'
    control_type = control.get("type")
    if control_type:
        return f'{control.name}[type="{control_type}"]'
    return control.name


def _label_for_control(soup: BeautifulSoup, control) -> tuple[str, list[str]]:
    evidence: list[str] = []
    control_id = control.get("id")
    if control_id:
        label = soup.find("label", attrs={"for": control_id})
        if label and label.get_text(strip=True):
            evidence.append("label[for] text")
            return label.get_text(" ", strip=True), evidence
    aria = control.get("aria-label")
    if aria:
        evidence.append("aria-label")
        return str(aria), evidence
    placeholder = control.get("placeholder")
    if placeholder:
        evidence.append("placeholder")
        return str(placeholder), evidence
    name = control.get("name") or control_id or control.get("type") or control.name
    evidence.append("name/id fallback")
    return str(name), evidence


def detect_fields_from_html(html: str) -> list[dict[str, Any]]:
    """Detect form controls and submit actions from an HTML snapshot."""
    soup = BeautifulSoup(html or "", "html.parser")
    fields: list[dict[str, Any]] = []

    controls = soup.select("input, select, textarea, button")
    for control in controls:
        tag = control.name
        control_type = str(control.get("type") or ("select" if tag == "select" else tag)).lower()
        if tag == "button" and control_type not in {"submit", "button"}:
            continue
        if (
            tag == "input"
            and control_type in {"hidden", "submit", "button", "reset", "image"}
            and control_type not in {"submit", "button"}
        ):
            continue

        label, evidence = _label_for_control(soup, control)
        selector = _css_selector_for_control(control)
        possible_values: list[str] = []
        if tag == "select":
            possible_values = [opt.get_text(" ", strip=True) for opt in control.find_all("option")]

        is_submit = tag == "button" or control_type in {"submit", "button"}
        if is_submit:
            label = label if label not in {"submit", "button"} else control.get_text(" ", strip=True) or label
            evidence.append("submit control")

        confidence = 0.9 if "label[for] text" in evidence else 0.75 if possible_values or control.get("placeholder") else 0.6
        fields.append(
            {
                "label": label,
                "selector": selector,
                "type": "submit" if is_submit else control_type,
                "required_guess": bool(control.get("required")),
                "confidence": confidence,
                "evidence": evidence,
                "possible_values": possible_values,
            },
        )
    return fields


def steps_from_manual_mapping(
    *,
    start_url: str,
    fields: list[dict[str, Any]],
    submit_action: dict[str, Any] | None = None,
) -> list[WorkflowStep]:
    """Convert user-corrected field mapping into bounded workflow steps."""
    steps: list[WorkflowStep] = [
        WorkflowStep(
            step_type=WorkflowStepType.GOTO,
            value=start_url,
            description="Open stable workflow start URL",
            order=0,
        ),
    ]
    for field in fields:
        action = str(field.get("action") or "fill").lower()
        selector = str(field.get("selector") or "")
        label = str(field.get("label") or selector)
        value = str(field.get("value") or "")
        step_type = {
            "fill": WorkflowStepType.FILL,
            "select": WorkflowStepType.SELECT,
            "check": WorkflowStepType.CHECK,
            "uncheck": WorkflowStepType.UNCHECK,
            "press": WorkflowStepType.PRESS,
        }.get(action, WorkflowStepType.FILL)
        steps.append(
            WorkflowStep(
                step_type=step_type,
                selector=selector,
                value=value,
                description=f"{step_type.value} {label}",
                order=len(steps),
            ),
        )
    if submit_action:
        steps.append(
            WorkflowStep(
                step_type=WorkflowStepType(str(submit_action.get("action") or "click")),
                selector=str(submit_action.get("selector") or ""),
                value=str(submit_action.get("value") or ""),
                description="Submit workflow form",
                order=len(steps),
            ),
        )
    steps.append(
        WorkflowStep(
            step_type=WorkflowStepType.WAIT_FOR_TIMEOUT_LIMITED,
            value="1000",
            description="Bounded wait after submit",
            order=len(steps),
        ),
    )
    return steps


def _page_title(soup: BeautifulSoup) -> str:
    title = soup.find("title")
    return title.get_text(" ", strip=True) if title else ""


def _failure(
    *,
    workflow: Workflow,
    failure_type: str,
    user_message: str,
    recommended_action: str,
    timeline: list[dict[str, Any]],
    soup: BeautifulSoup | None = None,
) -> dict[str, Any]:
    return {
        "workflow_id": workflow.id,
        "preview_status": "failed",
        "failure_type": failure_type,
        "user_message": user_message,
        "recommended_action": recommended_action,
        "timeline": timeline,
        "last_url": workflow.start_url,
        "page_title": _page_title(soup) if soup is not None else "",
        "screenshot": None,
        "sample_rows": [],
        "warnings": [],
    }


def _extract_rows(soup: BeautifulSoup, schema_fields: list[SchemaField], *, limit: int = 5) -> list[dict[str, Any]]:
    if not schema_fields:
        table_rows: list[dict[str, Any]] = []
        for tr in soup.select("table tr"):
            cells = [cell.get_text(" ", strip=True) for cell in tr.select("th,td")]
            if cells:
                table_rows.append({"text": " | ".join(cells)})
        return table_rows[:limit]

    candidates = soup.select(".result, .item, article, tbody tr, tr")
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        row: dict[str, Any] = {}
        for field in schema_fields:
            name = field.name
            selectors = [
                f'[data-field="{name}"]',
                f".{name}",
                f'[itemprop="{name}"]',
                f'[name="{name}"]',
            ]
            value = ""
            for selector in selectors:
                found = candidate.select_one(selector)
                if found is not None:
                    value = found.get_text(" ", strip=True) or str(found.get("value") or "")
                    break
            row[name] = value
        if any(row.values()):
            rows.append(row)
        if len(rows) >= limit:
            break
    return rows


async def preview_workflow_snapshot(
    workflow: Workflow,
    *,
    html_snapshot: str,
    sample_limit: int = 5,
) -> dict[str, Any]:
    """Run a deterministic bounded preview against an HTML snapshot."""
    soup = BeautifulSoup(html_snapshot or "", "html.parser")
    timeline: list[dict[str, Any]] = []

    if not workflow.start_url:
        return _failure(
            workflow=workflow,
            failure_type="invalid_workflow",
            user_message="Workflow has no start URL.",
            recommended_action="Choose a stable public start URL.",
            timeline=timeline,
            soup=soup,
        )

    for step in sorted(workflow.steps, key=lambda item: item.order):
        step_type = step.step_type
        event = {
            "order": step.order,
            "action": step_type.value,
            "selector": step.selector,
            "value": redact_step_value(step.value, label=step.description, selector=step.selector),
            "status": "ok",
            "timestamp": _now_iso(),
        }
        if step_type in {WorkflowStepType.GOTO, WorkflowStepType.OPEN}:
            event["url"] = workflow.start_url
        elif step_type in {
            WorkflowStepType.FILL,
            WorkflowStepType.SELECT,
            WorkflowStepType.CHECK,
            WorkflowStepType.UNCHECK,
            WorkflowStepType.CLICK,
            WorkflowStepType.PRESS,
        }:
            if step.selector and soup.select_one(step.selector) is None:
                event["status"] = "failed"
                timeline.append(event)
                return _failure(
                    workflow=workflow,
                    failure_type="selector_missing",
                    user_message=f"Workflow step selector was not found: {step.selector}",
                    recommended_action="Update the field mapping selector and preview again.",
                    timeline=timeline,
                    soup=soup,
                )
        elif step_type == WorkflowStepType.WAIT_FOR_TIMEOUT_LIMITED:
            wait_ms = int(str(step.value or "0") or "0")
            if wait_ms > MAX_WAIT_MS:
                event["status"] = "capped"
                event["value"] = str(MAX_WAIT_MS)
        timeline.append(event)

    sample_rows = _extract_rows(soup, workflow.extraction_schema, limit=sample_limit)
    return {
        "workflow_id": workflow.id,
        "preview_status": "succeeded",
        "sample_rows": sample_rows,
        "timeline": timeline,
        "warnings": [] if sample_rows else ["No sample rows matched the extraction schema."],
        "last_url": workflow.start_url,
        "page_title": _page_title(soup),
        "screenshot": None,
        "record_count": len(sample_rows),
    }


async def run_workflow_snapshot(workflow: Workflow, *, html_snapshot: str) -> dict[str, Any]:
    """Run a workflow against an HTML snapshot and return preview-style rows."""
    result = await preview_workflow_snapshot(workflow, html_snapshot=html_snapshot, sample_limit=100)
    result["run_status"] = "succeeded" if result.get("preview_status") == "succeeded" else "failed"
    return result
