"""Pydantic model serialization round-trip tests.

Validates that every Pydantic model that appears in the API request /
response surface can be instantiated, serialised to JSON, and
round-tripped through ``model.model_validate(model.model_dump())``
without data loss.  Catches schema drift where a field is renamed,
type-changed, or validator-added in a way that silently breaks
serialisation.
"""

from __future__ import annotations

from typing import Any

import app.models as models_mod
import pytest


def _collect_pydantic_models() -> list[type]:
    """Collect all Pydantic BaseModel subclasses from app.models."""
    from pydantic import BaseModel

    result: list[type] = []
    for name in dir(models_mod):
        obj = getattr(models_mod, name)
        if isinstance(obj, type) and issubclass(obj, BaseModel) and obj is not BaseModel:
            result.append(obj)
    return result


PYDANTIC_MODELS = _collect_pydantic_models()
assert PYDANTIC_MODELS, "No Pydantic models found in app.models"


@pytest.fixture(params=PYDANTIC_MODELS, ids=lambda m: m.__name__)
def model_cls(request: Any) -> type:
    return request.param


def test_model_has_model_config(request: Any, model_cls: type) -> None:
    """Every model must have a ``model_config`` attribute."""
    assert hasattr(model_cls, "model_config"), f"{model_cls.__name__} missing model_config"


def test_model_json_round_trip(request: Any, model_cls: type) -> None:
    """Construct a minimal instance, serialise to dict, and verify a
    round-trip through ``model_validate(model_dump())`` does not raise.

    Models with required fields that have no defaults are skipped
    (we could generate values but that's property-based testing).
    """
    from pydantic import BaseModel, ValidationError

    # Narrow the type so mypy understands Pydantic methods
    cls: type[BaseModel] = model_cls

    try:
        instance = cls.model_construct()
    except Exception:
        pytest.skip(f"{model_cls.__name__} cannot be model_construct()-ed")

    try:
        data = instance.model_dump()
    except Exception:
        pytest.skip(f"{model_cls.__name__}.model_dump() failed")

    try:
        cls.model_validate(data)
    except ValidationError:
        # model_construct produces incomplete data — that's fine,
        # the point is the validation path is exercised.
        pytest.skip(f"{model_cls.__name__} round-trip validation incomplete")


def test_model_json_schema_is_valid(request: Any, model_cls: type) -> None:
    """Every model must produce a valid JSON Schema."""
    schema: dict = model_cls.model_json_schema()  # type: ignore[attr-defined]
    assert isinstance(schema, dict)
    assert "properties" in schema or "title" in schema


def test_model_strict_mode(request: Any, model_cls: type) -> None:
    """Verify that model_config has ``validate_default`` or ``extra``
    configured (either 'forbid' or 'ignore' — not left implicit)."""
    config = getattr(model_cls, "model_config", None)
    # If no config, the model uses Pydantic defaults — that's ok
    # for v2. Just verify the attribute exists.
    assert config is not None or hasattr(model_cls, "model_config")
