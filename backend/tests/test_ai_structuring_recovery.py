import asyncio

from app import scraper as scraper_mod
from app.models import FieldType, SchemaField


def test_ai_clean_and_align_records_recovers_after_fast_empty(monkeypatch):
    schema = [
        SchemaField(name="company_name", field_type=FieldType.STRING, required=True),
        SchemaField(name="phone", field_type=FieldType.PHONE, required=False),
    ]
    records = [{"company_name": "Acme Interiors", "phone": None}]

    monkeypatch.setattr(scraper_mod, "_llm_json_fast", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        scraper_mod,
        "_llm_json",
        lambda *args, **kwargs: {"records": [{"company_name": "Acme Interiors", "phone": "+91 90000 11111"}]},
    )

    output, report = asyncio.run(
        scraper_mod.ai_clean_and_align_records(records, schema_fields=schema, min_record_score=0.0)
    )

    assert report["ai_chunks"] == 1
    assert report["fallback_chunks"] == 0
    assert output
    assert output[0]["company_name"] == "Acme Interiors"


def test_ai_clean_and_align_records_honors_consecutive_failure_threshold(monkeypatch):
    schema = [SchemaField(name="company_name", field_type=FieldType.STRING, required=True)]
    records = [
        {"company_name": "A"},
        {"company_name": "B"},
        {"company_name": "C"},
    ]

    monkeypatch.setattr(scraper_mod, "AI_STRUCTURING_CHUNK_SIZE", 1)
    monkeypatch.setattr(scraper_mod, "AI_STRUCTURING_MAX_CONSECUTIVE_MODEL_FAILURES", 2)
    monkeypatch.setattr(scraper_mod, "_llm_json_fast", lambda *args, **kwargs: {})
    monkeypatch.setattr(scraper_mod, "_llm_json", lambda *args, **kwargs: {})

    output, report = asyncio.run(
        scraper_mod.ai_clean_and_align_records(records, schema_fields=schema, min_record_score=0.0)
    )

    assert len(output) == 3
    assert report["fallback_chunks"] == 3
    assert report["model_fallback_mode"] is True


def test_llm_json_fast_uses_groq_fallback_model(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_MODEL", "primary-model")
    monkeypatch.setenv("GROQ_FALLBACK_MODEL", "fallback-model")

    calls: list[str] = []

    def fake_openai_json(endpoint, payload, headers=None, timeout=45, max_attempts=2, backoff_seconds=0.8):
        model = payload.get("model")
        calls.append(model)
        if model == "primary-model":
            raise RuntimeError("429 throttled")
        if model == "fallback-model":
            return {"records": [{"company_name": "Fallback Row"}]}
        return {}

    monkeypatch.setattr(scraper_mod, "_call_openai_compatible_json", fake_openai_json)

    out = scraper_mod._llm_json_fast(
        messages=[{"role": "user", "content": "test"}],
        temperature=0.0,
        timeout=3,
    )

    assert out == {"records": [{"company_name": "Fallback Row"}]}
    assert calls[:2] == ["primary-model", "fallback-model"]
