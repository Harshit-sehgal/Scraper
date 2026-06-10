"""Extraction validation and quality gates.

Validates extraction results and applies quality gates
to ensure data quality and consistency.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ValidationSeverity(Enum):
    """Validation severity levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationResult:
    """Result of a validation check."""

    field_name: str
    severity: ValidationSeverity
    message: str
    value: Any = None
    expected: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_name": self.field_name,
            "severity": self.severity.value,
            "message": self.message,
            "value": self.value,
            "expected": self.expected,
        }


class ExtractionValidator:
    """Validates extraction results."""

    def __init__(self):
        self._rules: dict[str, list[Any]] = {}

    def add_rule(self, field_name: str, rule: Any) -> None:
        """Add validation rule for a field."""
        if field_name not in self._rules:
            self._rules[field_name] = []
        self._rules[field_name].append(rule)

    def validate_field(self, field_name: str, value: Any) -> list[ValidationResult]:
        """Validate a single field."""
        results = []
        rules = self._rules.get(field_name, [])

        for rule in rules:
            result = rule.validate(field_name, value)
            if result:
                results.append(result)

        return results

    def validate_record(self, record: dict[str, Any]) -> list[ValidationResult]:
        """Validate a complete record."""
        results = []

        # Validate each field
        for field_name, value in record.items():
            field_results = self.validate_field(field_name, value)
            results.extend(field_results)

        # Check required fields
        for field_name in self._rules:
            if field_name not in record:
                results.append(
                    ValidationResult(
                        field_name=field_name,
                        severity=ValidationSeverity.WARNING,
                        message=f"Missing required field: {field_name}",
                    ),
                )

        return results


@dataclass
class ValidationRule:
    """Base validation rule."""

    name: str = ""
    description: str = ""

    def validate(self, field_name: str, value: Any) -> ValidationResult | None:
        raise NotImplementedError


@dataclass
class RequiredRule(ValidationRule):
    """Rule that field is required and not empty."""

    def validate(self, field_name: str, value: Any) -> ValidationResult | None:
        if value is None or (isinstance(value, str) and not value.strip()):
            return ValidationResult(
                field_name=field_name,
                severity=ValidationSeverity.ERROR,
                message=f"Field {field_name} is required",
                value=value,
            )
        return None


@dataclass
class TypeRule(ValidationRule):
    """Rule that field must be of specific type."""

    expected_type: type | tuple[type, ...] = str

    def validate(self, field_name: str, value: Any) -> ValidationResult | None:
        if value is not None and not isinstance(value, self.expected_type):
            type_name = getattr(self.expected_type, "__name__", str(self.expected_type))
            return ValidationResult(
                field_name=field_name,
                severity=ValidationSeverity.ERROR,
                message=f"Field {field_name} must be {type_name}",
                value=value,
                expected=type_name,
            )
        return None


@dataclass
class LengthRule(ValidationRule):
    """Rule for string length constraints."""

    min_length: int = 0
    max_length: int = 1000

    def validate(self, field_name: str, value: Any) -> ValidationResult | None:
        if isinstance(value, str):
            if len(value) < self.min_length:
                return ValidationResult(
                    field_name=field_name,
                    severity=ValidationSeverity.ERROR,
                    message=f"Field {field_name} too short (min: {self.min_length})",
                    value=len(value),
                    expected=f">={self.min_length}",
                )
            if len(value) > self.max_length:
                return ValidationResult(
                    field_name=field_name,
                    severity=ValidationSeverity.WARNING,
                    message=f"Field {field_name} too long (max: {self.max_length})",
                    value=len(value),
                    expected=f"<={self.max_length}",
                )
        return None


@dataclass
class PatternRule(ValidationRule):
    """Rule for regex pattern matching."""

    pattern: str = ""

    def validate(self, field_name: str, value: Any) -> ValidationResult | None:
        if isinstance(value, str) and self.pattern and not re.match(self.pattern, value):
            return ValidationResult(
                field_name=field_name,
                severity=ValidationSeverity.WARNING,
                message=f"Field {field_name} doesn't match pattern {self.pattern}",
                value=value,
                expected=f"Pattern: {self.pattern}",
            )
        return None


@dataclass
class RangeRule(ValidationRule):
    """Rule for numeric range constraints."""

    min_value: float | None = None
    max_value: float | None = None

    def validate(self, field_name: str, value: Any) -> ValidationResult | None:
        if isinstance(value, (int, float)):
            if self.min_value is not None and value < self.min_value:
                return ValidationResult(
                    field_name=field_name,
                    severity=ValidationSeverity.ERROR,
                    message=f"Field {field_name} below minimum",
                    value=value,
                    expected=f">={self.min_value}",
                )
            if self.max_value is not None and value > self.max_value:
                return ValidationResult(
                    field_name=field_name,
                    severity=ValidationSeverity.WARNING,
                    message=f"Field {field_name} above maximum",
                    value=value,
                    expected=f"<={self.max_value}",
                )
        return None


class QualityGate:
    """Quality gate for extraction results."""

    def __init__(self, name: str = "default"):
        self.name = name
        self._validators: list[ExtractionValidator] = []
        self._thresholds: dict[str, float] = {}

    def add_validator(self, validator: ExtractionValidator) -> None:
        """Add a validator to the quality gate."""
        self._validators.append(validator)

    def set_threshold(self, metric: str, threshold: float) -> None:
        """Set quality threshold."""
        self._thresholds[metric] = threshold

    def evaluate(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        """Evaluate quality of extraction results."""
        all_results = []
        for record in records:
            for validator in self._validators:
                results = validator.validate_record(record)
                all_results.extend(results)

        # Calculate metrics
        total_fields = sum(len(r) for r in records)
        errors = [r for r in all_results if r.severity == ValidationSeverity.ERROR]
        warnings = [r for r in all_results if r.severity == ValidationSeverity.WARNING]

        error_rate = len(errors) / total_fields if total_fields > 0 else 0
        warning_rate = len(warnings) / total_fields if total_fields > 0 else 0

        # Check thresholds
        passed = True
        failures = []
        for metric, threshold in self._thresholds.items():
            if metric == "error_rate" and error_rate > threshold:
                passed = False
                failures.append(f"Error rate {error_rate:.2%} > {threshold:.2%}")
            elif metric == "warning_rate" and warning_rate > threshold:
                passed = False
                failures.append(f"Warning rate {warning_rate:.2%} > {threshold:.2%}")

        return {
            "gate": self.name,
            "passed": passed,
            "metrics": {
                "total_records": len(records),
                "total_fields": total_fields,
                "errors": len(errors),
                "warnings": len(warnings),
                "error_rate": error_rate,
                "warning_rate": warning_rate,
            },
            "failures": failures,
            "results": [r.to_dict() for r in all_results[:100]],  # Limit output
        }


# Pre-configured validators
def create_url_validator() -> ExtractionValidator:
    """Create validator for URL fields."""
    validator = ExtractionValidator()
    validator.add_rule("url", RequiredRule())
    validator.add_rule("url", PatternRule(pattern=r"^https?://"))
    validator.add_rule("url", LengthRule(min_length=10, max_length=2000))
    return validator


def create_price_validator() -> ExtractionValidator:
    """Create validator for price fields."""
    validator = ExtractionValidator()
    validator.add_rule("price", RequiredRule())
    validator.add_rule("price", TypeRule(expected_type=(int, float, str)))
    validator.add_rule("price", RangeRule(min_value=0))
    return validator


def create_email_validator() -> ExtractionValidator:
    """Create validator for email fields."""
    validator = ExtractionValidator()
    validator.add_rule("email", PatternRule(pattern=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"))
    return validator
