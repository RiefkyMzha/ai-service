import asyncio

import pytest
import requests
from fastapi import HTTPException

from app.core.config import settings
from app.core.data_loader import DataLoader
from app.services.ai_service import AIService
from tests.conftest import make_png, make_upload


@pytest.fixture
def service() -> AIService:
    return AIService(DataLoader())


def run(coro):
    return asyncio.run(coro)


def test_missing_api_key_returns_500(monkeypatch, service: AIService):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")

    with pytest.raises(HTTPException) as exc:
        run(service._call_openrouter([]))

    assert exc.value.status_code == 500
    assert "Konfigurasi API AI" in exc.value.detail


def test_timeout_maps_to_408(monkeypatch, service: AIService):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "test-key")

    def raise_timeout(*args, **kwargs):
        raise requests.Timeout()

    monkeypatch.setattr("app.services.ai_service.requests.post", raise_timeout)

    with pytest.raises(HTTPException) as exc:
        run(service._call_openrouter([]))

    assert exc.value.status_code == 408


def test_unauthorized_maps_to_502(monkeypatch, service: AIService):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "test-key")

    def raise_unauthorized(*args, **kwargs):
        response = requests.Response()
        response.status_code = 401
        raise requests.HTTPError(response=response)

    monkeypatch.setattr(
        "app.services.ai_service.requests.post", raise_unauthorized
    )

    with pytest.raises(HTTPException) as exc:
        run(service._call_openrouter([]))

    assert exc.value.status_code == 502
    assert "API key AI" in exc.value.detail


def test_invalid_json_output_returns_500(monkeypatch, service: AIService):
    async def fake_call(self, messages):
        return "bukan json"

    monkeypatch.setattr(AIService, "_call_openrouter", fake_call)

    with pytest.raises(HTTPException) as exc:
        run(service.analyze_text_and_image("tes", None))

    assert exc.value.status_code == 500
    assert "Format output AI" in exc.value.detail


def test_analyze_attaches_whitelisted_contact(monkeypatch, service: AIService):
    async def fake_call(self, messages):
        return (
            '{"risk_score": 75, "risk_category": "high",'
            ' "scam_type": "Phishing / Smishing / Vishing",'
            ' "reasons": ["x"], "recommendations": ["y"],'
            ' "official_contact": {"name": "Bank Palsu", "phone": "000"}}'
        )

    monkeypatch.setattr(AIService, "_call_openrouter", fake_call)
    result = run(service.analyze_text_and_image("Ini BCA, kirim OTP", None))

    assert result["risk_category"] == "Tinggi"
    assert result["official_contact"]["name"] == "Bank BCA (Bank Central Asia)"


def test_image_mime_whitelist(service: AIService):
    upload = make_upload(b"hello", content_type="application/pdf")

    with pytest.raises(HTTPException) as exc:
        run(service._process_image_to_base64(upload))

    assert exc.value.status_code == 400


def test_image_size_limit(service: AIService):
    upload = make_upload(b"\x00" * (15 * 1024 * 1024 + 1))

    with pytest.raises(HTTPException) as exc:
        run(service._process_image_to_base64(upload))

    assert exc.value.status_code == 413


def test_valid_image_becomes_data_uri(service: AIService):
    upload = make_upload(make_png())
    encoded = run(service._process_image_to_base64(upload))

    assert encoded.startswith("data:image/png;base64,")


def test_no_image_returns_none(service: AIService):
    assert run(service._process_image_to_base64(None)) is None
