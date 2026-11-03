import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from tests.conftest import TEST_API_TOKEN

PROTECTED_URL = "/api/v1/analyze/text"
VALID_FORM = {"text_content": "Halo, ini BCA. Kirim OTP sekarang."}


@pytest.fixture
def raw_client(monkeypatch) -> TestClient:
    """Client tanpa header token bawaan, dengan token server terkonfigurasi."""
    monkeypatch.setattr(settings, "CEGAHSCAM_API_TOKEN", TEST_API_TOKEN)
    with TestClient(app) as test_client:
        yield test_client


def test_missing_token_returns_401(raw_client: TestClient, fake_openrouter):
    response = raw_client.post(PROTECTED_URL, data=VALID_FORM)

    assert response.status_code == 401
    assert response.json() == {"detail": "Token API tidak valid atau tidak ada."}


def test_wrong_token_returns_401(raw_client: TestClient, fake_openrouter):
    response = raw_client.post(
        PROTECTED_URL, data=VALID_FORM, headers={"X-API-Token": "salah"}
    )

    assert response.status_code == 401


def test_non_ascii_token_returns_401_not_500(raw_client: TestClient, fake_openrouter):
    response = raw_client.post(
        PROTECTED_URL,
        data=VALID_FORM,
        headers={"X-API-Token": "tokén-ñ".encode("utf-8")},
    )

    assert response.status_code == 401


def test_correct_token_allows_request(raw_client: TestClient, fake_openrouter):
    response = raw_client.post(
        PROTECTED_URL, data=VALID_FORM, headers={"X-API-Token": TEST_API_TOKEN}
    )

    assert response.status_code == 200
    assert response.json()["risk_score"] == 80


def test_unconfigured_token_fails_closed_with_500(monkeypatch, fake_openrouter):
    """Token server kosong tidak boleh berarti 'tanpa auth'."""
    monkeypatch.setattr(settings, "CEGAHSCAM_API_TOKEN", "")

    with TestClient(app) as test_client:
        for headers in ({}, {"X-API-Token": ""}, {"X-API-Token": "apa-saja"}):
            response = test_client.post(PROTECTED_URL, data=VALID_FORM, headers=headers)

            assert response.status_code == 500
            assert response.json() == {
                "detail": "Konfigurasi token API belum diatur."
            }


def test_health_is_open_without_token(monkeypatch):
    monkeypatch.setattr(settings, "CEGAHSCAM_API_TOKEN", TEST_API_TOKEN)
    monkeypatch.setattr(settings, "MOCK_MODE", True)

    with TestClient(app) as test_client:
        response = test_client.get("/health")

    assert response.status_code == 200
    assert response.json()["mock_mode"] is True


def test_cors_preflight_and_headers_on_protected_endpoint(raw_client: TestClient):
    preflight = raw_client.options(
        PROTECTED_URL,
        headers={
            "Origin": "https://cegahscam.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-API-Token, Content-Type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers.get("access-control-allow-origin") == "*"


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/analyze/text",
        "/api/v1/analyze/image",
        "/api/v1/analyze/phone",
        "/api/v1/emergency/financial",
        "/api/v1/emergency/data-breach",
    ],
)
def test_every_business_endpoint_requires_token(raw_client: TestClient, path: str):
    """Auth harus dicek sebelum validasi body (401, bukan 422)."""
    response = raw_client.post(path)

    assert response.status_code == 401
