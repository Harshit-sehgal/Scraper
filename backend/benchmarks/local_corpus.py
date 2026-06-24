"""Local benchmark corpus scoring with versioned expected outputs.

The corpus runner is intentionally deterministic: it uses checked-in fixtures,
does not open the network, and does not require a browser or LLM call.
"""

from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.empty_response_detector import detect_empty_response
from app.models import FieldType, SchemaField
from app.selector_engine import extract_with_regex
from app.zero_result_classifier import classify_zero_result
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = REPO_ROOT / "backend" / "tests" / "fixtures" / "pages"
MANIFEST_PATH = Path(__file__).with_name("local_corpus_expected.json")
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "benchmarks"
LOCAL_CORPUS_JSON = "latest_local_corpus.json"
LOCAL_CORPUS_MD = "latest_local_corpus.md"

REQUIRED_METRICS = {
    "field_precision",
    "field_recall",
    "field_f1",
    "row_precision",
    "row_recall",
    "row_f1",
    "records_found",
    "missing_required_fields",
    "invalid_types",
    "duplicates",
    "timeout_rate",
    "runtime_seconds",
    "browser_failures",
}


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    status: str
    categories: list[str]
    fixture: str
    extractor: str
    metrics: dict[str, int | float]
    failures: list[str]
    failure_class: str | None = None


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_local_corpus(
    *,
    manifest_path: Path = MANIFEST_PATH,
    output_dir: Path = DEFAULT_ARTIFACT_DIR,
    write_artifacts: bool = True,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    started = datetime.now(UTC)
    start = time.monotonic()
    case_results = [_run_case(case) for case in manifest["cases"]]
    aggregate = _aggregate_results(case_results)
    aggregate_failures = _aggregate_failures(manifest, aggregate)
    status = "passed" if not aggregate_failures and all(result.status == "passed" for result in case_results) else "failed"
    ended = datetime.now(UTC)
    report: dict[str, Any] = {
        "version": manifest["version"],
        "generated_at": ended.isoformat(),
        "started_at": started.isoformat(),
        "ended_at": ended.isoformat(),
        "duration_seconds": round(time.monotonic() - start, 3),
        "status": status,
        "live_sites_used": False,
        "browser_required": False,
        "manifest": str(manifest_path.relative_to(REPO_ROOT)),
        "required_categories": manifest["required_categories"],
        "aggregate_thresholds": manifest["aggregate_thresholds"],
        "aggregate": aggregate,
        "failures": aggregate_failures,
        "cases": [_case_result_to_dict(result) for result in case_results],
    }
    if write_artifacts:
        _write_artifacts(report, output_dir)
    return report


def _run_case(case: dict[str, Any]) -> CaseResult:
    start = time.monotonic()
    extracted = _extract_case_records(case)
    runtime_seconds = round(time.monotonic() - start, 6)
    expected = case.get("expected_records", [])
    required_fields = case.get("required_fields", [])
    schema = case.get("schema", [])
    matched_pairs = _match_expected_rows(expected, extracted, required_fields)
    metrics = _score_records(
        extracted=extracted,
        expected=expected,
        required_fields=required_fields,
        schema=schema,
        matched_pairs=matched_pairs,
        runtime_seconds=runtime_seconds,
    )

    failure_class = None
    if case["extractor"] == "negative_html":
        failure_class = _classify_negative_fixture(case["fixture"], required_fields)
        metrics["false_positive_records"] = len(extracted)

    failures = _case_failures(case, metrics, failure_class)
    return CaseResult(
        case_id=case["id"],
        status="passed" if not failures else "failed",
        categories=list(case["categories"]),
        fixture=case["fixture"],
        extractor=case["extractor"],
        metrics=metrics,
        failures=failures,
        failure_class=failure_class,
    )


def _extract_case_records(case: dict[str, Any]) -> list[dict[str, Any]]:
    fixture_path = FIXTURES_DIR / case["fixture"]
    if case["extractor"] in {"html_regex", "negative_html"}:
        schema_fields = [
            SchemaField(
                name=field["name"],
                field_type=FieldType(field["type"]),
                required=bool(field.get("required", False)),
                description="",
            )
            for field in case["schema"]
        ]
        html = fixture_path.read_text(encoding="utf-8")
        return [
            _strip_record_metadata(record)
            for record in extract_with_regex(
                html,
                schema_fields,
                base_url=f"https://fixtures.local/{case['fixture']}",
            )
        ]
    if case["extractor"] == "json_items":
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        return [dict(item) for item in payload["items"]]
    message = f"Unsupported local corpus extractor: {case['extractor']}"
    raise ValueError(message)


def _strip_record_metadata(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != "record_score"}


def _classify_negative_fixture(fixture_name: str, schema_fields: list[str]) -> str:
    html = (FIXTURES_DIR / fixture_name).read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "link"]):
        tag.decompose()
    visible_text = soup.get_text(separator=" ", strip=True)
    forms = [{"action": form.get("action", ""), "method": form.get("method", "")} for form in soup.find_all("form")]
    empty_check = detect_empty_response(html)
    classification = classify_zero_result(
        acquisition_lineage={"state": "direct"},
        session_detection=None,
        empty_check=vars(empty_check),
        anti_bot_score=0.0,
        final_url=f"https://fixtures.local/{fixture_name}",
        html=html,
        visible_text=visible_text,
        detected_forms=forms,
        detected_containers=0,
        raw_candidate_count=0,
        schema_fields=schema_fields,
    )
    return classification.failure_class


def _score_records(
    *,
    extracted: list[dict[str, Any]],
    expected: list[dict[str, Any]],
    required_fields: list[str],
    schema: list[dict[str, Any]],
    matched_pairs: list[tuple[int, int]],
    runtime_seconds: float,
) -> dict[str, int | float]:
    true_positive_rows = len(matched_pairs)
    row_precision = _ratio(true_positive_rows, len(extracted), empty_value=1.0 if not expected else 0.0)
    row_recall = _ratio(true_positive_rows, len(expected), empty_value=1.0)

    expected_cells = len(expected) * len(required_fields)
    actual_cells = sum(1 for record in extracted for field in required_fields if _has_value(record.get(field)))
    matched_cells = sum(
        1
        for expected_idx, actual_idx in matched_pairs
        for field in required_fields
        if _field_matches(expected[expected_idx].get(field), extracted[actual_idx].get(field))
    )
    field_precision = _ratio(matched_cells, actual_cells, empty_value=1.0 if expected_cells == 0 else 0.0)
    field_recall = _ratio(matched_cells, expected_cells, empty_value=1.0)

    return {
        "field_precision": field_precision,
        "field_recall": field_recall,
        "field_f1": _f1(field_precision, field_recall),
        "row_precision": row_precision,
        "row_recall": row_recall,
        "row_f1": _f1(row_precision, row_recall),
        "records_found": len(extracted),
        "missing_required_fields": _missing_required_fields(extracted, required_fields),
        "invalid_types": _invalid_type_count(extracted, schema),
        "duplicates": _duplicate_count(extracted, required_fields),
        "timeout_rate": 0.0,
        "runtime_seconds": runtime_seconds,
        "browser_failures": 0,
    }


def _match_expected_rows(
    expected: list[dict[str, Any]],
    extracted: list[dict[str, Any]],
    required_fields: list[str],
) -> list[tuple[int, int]]:
    matched: list[tuple[int, int]] = []
    used_actual: set[int] = set()
    for expected_idx, expected_record in enumerate(expected):
        for actual_idx, actual_record in enumerate(extracted):
            if actual_idx in used_actual:
                continue
            if all(_field_matches(expected_record.get(field), actual_record.get(field)) for field in required_fields):
                matched.append((expected_idx, actual_idx))
                used_actual.add(actual_idx)
                break
    return matched


def _field_matches(expected: Any, actual: Any) -> bool:
    expected_norm = _normalize_value(expected)
    actual_norm = _normalize_value(actual)
    if expected_norm == actual_norm:
        return True
    if not expected_norm or not actual_norm:
        return False
    return len(expected_norm) >= 4 and expected_norm in actual_norm


def _normalize_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:g}"
    text = str(value).strip().lower()
    text = text.replace("\u2014", "-").replace("\u2013", "-")
    return re.sub(r"\s+", " ", text)


def _has_value(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _missing_required_fields(records: list[dict[str, Any]], required_fields: list[str]) -> int:
    return sum(1 for record in records for field in required_fields if not _has_value(record.get(field)))


def _duplicate_count(records: list[dict[str, Any]], required_fields: list[str]) -> int:
    signatures = [
        json.dumps({field: _normalize_value(record.get(field)) for field in required_fields}, sort_keys=True)
        for record in records
    ]
    return len(signatures) - len(set(signatures))


def _invalid_type_count(records: list[dict[str, Any]], schema: list[dict[str, Any]]) -> int:
    schema_by_name = {field["name"]: FieldType(field["type"]) for field in schema}
    invalid = 0
    for record in records:
        for field_name, field_type in schema_by_name.items():
            value = record.get(field_name)
            if _has_value(value) and not _value_matches_type(value, field_type):
                invalid += 1
    return invalid


def _value_matches_type(value: Any, field_type: FieldType) -> bool:
    text = str(value).strip()
    if field_type == FieldType.URL:
        return text.startswith(("http://", "https://"))
    if field_type == FieldType.PHONE:
        return len(re.sub(r"\D", "", text)) >= 7
    if field_type == FieldType.CURRENCY:
        return bool(re.search(r"([$£€¥₹]\s*\d|\d+[\d,.]*\s*[$£€¥₹]|^Rs\.?\s*\d)", text))
    if field_type in (FieldType.NUMBER, FieldType.INTEGER, FieldType.FLOAT):
        try:
            float(text)
        except ValueError:
            return False
    return True


def _case_failures(case: dict[str, Any], metrics: dict[str, int | float], failure_class: str | None) -> list[str]:
    thresholds = case.get("thresholds", {})
    failures = []
    if metrics["row_f1"] < thresholds.get("min_row_f1", 0.0):
        failures.append(f"row_f1 {metrics['row_f1']} below {thresholds['min_row_f1']}")
    if metrics["field_f1"] < thresholds.get("min_field_f1", 0.0):
        failures.append(f"field_f1 {metrics['field_f1']} below {thresholds['min_field_f1']}")
    if metrics["duplicates"] > thresholds.get("max_duplicates", 999999):
        failures.append(f"duplicates {metrics['duplicates']} above {thresholds['max_duplicates']}")
    if metrics.get("false_positive_records", 0) > thresholds.get("max_false_positive_records", 999999):
        failures.append(
            f"false_positive_records {metrics['false_positive_records']} above {thresholds['max_false_positive_records']}",
        )
    expected_failure_classes = set(case.get("expected_failure_classes", []))
    if expected_failure_classes and failure_class not in expected_failure_classes:
        failures.append(f"failure_class {failure_class!r} not in {sorted(expected_failure_classes)}")
    return failures


def _aggregate_results(results: list[CaseResult]) -> dict[str, int | float]:
    metrics = [result.metrics for result in results]
    positive_metrics = [metric for metric in metrics if "false_positive_records" not in metric]
    return {
        "case_count": len(results),
        "passed_cases": sum(1 for result in results if result.status == "passed"),
        "failed_cases": sum(1 for result in results if result.status != "passed"),
        "row_precision": _average_metric(positive_metrics, "row_precision"),
        "row_recall": _average_metric(positive_metrics, "row_recall"),
        "row_f1": _average_metric(positive_metrics, "row_f1"),
        "field_precision": _average_metric(positive_metrics, "field_precision"),
        "field_recall": _average_metric(positive_metrics, "field_recall"),
        "field_f1": _average_metric(positive_metrics, "field_f1"),
        "records_found": sum(int(metric["records_found"]) for metric in metrics),
        "missing_required_fields": sum(int(metric["missing_required_fields"]) for metric in metrics),
        "invalid_types": sum(int(metric["invalid_types"]) for metric in metrics),
        "duplicates": sum(int(metric["duplicates"]) for metric in metrics),
        "timeout_rate": _average_metric(metrics, "timeout_rate"),
        "runtime_seconds": round(sum(float(metric["runtime_seconds"]) for metric in metrics), 6),
        "browser_failures": sum(int(metric["browser_failures"]) for metric in metrics),
        "false_positive_records": sum(int(metric.get("false_positive_records", 0)) for metric in metrics),
    }


def _aggregate_failures(manifest: dict[str, Any], aggregate: dict[str, int | float]) -> list[str]:
    thresholds = manifest["aggregate_thresholds"]
    failures = []
    if aggregate["row_f1"] < thresholds["min_row_f1"]:
        failures.append(f"aggregate row_f1 {aggregate['row_f1']} below {thresholds['min_row_f1']}")
    if aggregate["field_f1"] < thresholds["min_field_f1"]:
        failures.append(f"aggregate field_f1 {aggregate['field_f1']} below {thresholds['min_field_f1']}")
    if aggregate["timeout_rate"] > thresholds["max_timeout_rate"]:
        failures.append(f"aggregate timeout_rate {aggregate['timeout_rate']} above {thresholds['max_timeout_rate']}")
    if aggregate["browser_failures"] > thresholds["max_browser_failures"]:
        failures.append(f"aggregate browser_failures {aggregate['browser_failures']} above {thresholds['max_browser_failures']}")
    return failures


def _average_metric(metrics: list[dict[str, int | float]], key: str) -> float:
    if not metrics:
        return 1.0
    return round(sum(float(metric[key]) for metric in metrics) / len(metrics), 6)


def _ratio(numerator: int, denominator: int, *, empty_value: float = 0.0) -> float:
    if denominator == 0:
        return empty_value
    return round(numerator / denominator, 6)


def _f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return round((2 * precision * recall) / (precision + recall), 6)


def _case_result_to_dict(result: CaseResult) -> dict[str, Any]:
    return {
        "id": result.case_id,
        "status": result.status,
        "categories": result.categories,
        "fixture": result.fixture,
        "extractor": result.extractor,
        "failure_class": result.failure_class,
        "metrics": result.metrics,
        "failures": result.failures,
    }


def _write_artifacts(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / LOCAL_CORPUS_JSON
    md_path = output_dir / LOCAL_CORPUS_MD
    report.setdefault("artifacts", {})
    report["artifacts"].update(
        {
            "json": _display_path(json_path),
            "markdown": _display_path(md_path),
        },
    )
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Local Benchmark Corpus Result",
        "",
        f"- generated_at: {report['generated_at']}",
        f"- version: {report['version']}",
        f"- status: {report['status']}",
        "- live_sites_used: false",
        "- browser_required: false",
        f"- case_count: {report['aggregate']['case_count']}",
        f"- row_f1: {report['aggregate']['row_f1']}",
        f"- field_f1: {report['aggregate']['field_f1']}",
        f"- false_positive_records: {report['aggregate']['false_positive_records']}",
        "",
        "## Cases",
        "",
        "| Case | Status | Row F1 | Field F1 | Records | Failure class |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for case in report["cases"]:
        metrics = case["metrics"]
        lines.append(
            f"| `{case['id']}` | {case['status']} | {metrics['row_f1']} | "
            f"{metrics['field_f1']} | {metrics['records_found']} | {case.get('failure_class') or ''} |",
        )
    if report["failures"]:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {failure}" for failure in report["failures"])
    return "\n".join(lines) + "\n"


def main() -> int:
    report = run_local_corpus()
    sys.stdout.write(f"Local corpus status: {report['status']}\n")
    sys.stdout.write(f"Wrote artifacts/benchmarks/{LOCAL_CORPUS_JSON}\n")
    sys.stdout.write(f"Wrote artifacts/benchmarks/{LOCAL_CORPUS_MD}\n")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
