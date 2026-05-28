import pytest
from fastapi import FastAPI
from app.config import settings
from app.main import lifespan

@pytest.mark.asyncio
async def test_production_security_enforcement_wildcard_cors(monkeypatch):
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(settings, "CORS_ORIGINS", ["*"])
    monkeypatch.setattr(settings, "API_KEY", "secure_key")

    app = FastAPI()
    
    with pytest.raises(ValueError) as exc:
        async with lifespan(app):
            pass
    assert "CORS_ORIGINS contains wildcard" in str(exc.value)


@pytest.mark.asyncio
async def test_production_security_enforcement_empty_api_key(monkeypatch):
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(settings, "CORS_ORIGINS", ["https://trusted.com"])
    monkeypatch.setattr(settings, "API_KEY", "")

    app = FastAPI()
    
    with pytest.raises(ValueError) as exc:
        async with lifespan(app):
            pass
    assert "API_KEY is empty or not configured" in str(exc.value)


@pytest.mark.asyncio
async def test_production_security_enforcement_placeholder_secrets(monkeypatch):
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(settings, "CORS_ORIGINS", ["https://trusted.com"])
    monkeypatch.setattr(settings, "API_KEY", "change-me")

    app = FastAPI()
    
    with pytest.raises(SystemExit) as exc:
        async with lifespan(app):
            pass
    assert "contains a known placeholder/default value" in str(exc.value)

