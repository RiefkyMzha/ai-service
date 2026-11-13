import asyncio
import json
import logging
import time

import pytest
from fastapi import HTTPException

from app.core.data_loader import DataLoader
from app.services.ai_service import AIService
from app.services.phone_service import (
    PHONE_CACHE_MAX_SIZE,
    PHONE_CACHE_TTL_SECONDS,
    PhoneService,
    _PHONE_CACHE,
)

VALID_CRED = {
    "token": "token-uji",
    "finalKey": "00" * 16,
    "clientDeviceId": "device-uji",
}

ANALYSIS_JSON = json.dumps(
    {
        "risk_score": 85,
        "risk_category": "Sangat Tinggi",
        "scam_type": "Penipuan Kurir / Marketplace",
        "reasons": ["Profil mencurigakan."],
        "recommendations": ["Blokir nomor."],
        "official_contact": {"name": "Bank Palsu", "phone": "000"},
    }
)


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def clear_phone_cache():
    _PHONE_CACHE.clear()
    yield
    _PHONE_CACHE.clear()


@pytest.fixture
def service() -> PhoneService:
    return PhoneService(AIService(DataLoader()))


def test_missing_credential_file_returns_500(service: PhoneService, tmp_path):
    service.cred_file = tmp_path / "tidak-ada.json"

    with pytest.raises(HTTPException) as exc:
        service._get_active_cred()

    assert exc.value.status_code == 500


def test_corrupt_credential_file_returns_500(service: PhoneService, tmp_path):
    cred_file = tmp_path / "gtc_credentials.json"
    cred_file.write_text("bukan json", encoding="utf-8")
    service.cred_file = cred_file

    with pytest.raises(HTTPException) as exc:
        service._get_active_cred()

    assert exc.value.status_code == 500


def test_incomplete_credentials_return_500(service: PhoneService, tmp_path):
    cred_file = tmp_path / "gtc_credentials.json"
    cred_file.write_text(
        json.dumps({"active": "a", "credentials": {"a": {"token": "x"}}}),
        encoding="utf-8",
    )
    service.cred_file = cred_file

    with pytest.raises(HTTPException) as exc:
        service._get_active_cred()

    assert exc.value.status_code == 500
    assert "tidak lengkap" in exc.value.detail


def test_analyze_phone_enriches_contact_from_profile(monkeypatch, service: PhoneService):
    monkeypatch.setattr(PhoneService, "_get_active_cred", lambda self: VALID_CRED)
    monkeypatch.setattr(
        PhoneService,
        "_gtc_call",
        lambda self, endpoint, payload, cred: (
            200,
            {
                "result": {
                    "profile": {"displayName": "CS Resmi Bank BCA"},
                    "tags": [{"tag": "penipuan"}],
                }
            },
        ),
    )

    async def fake_call(self, messages):
        return ANALYSIS_JSON

    monkeypatch.setattr(AIService, "_call_openrouter", fake_call)

    result = run(service.analyze_phone_number("0812-3456-7890"))

    assert result["official_contact"] == {
        "name": "Bank BCA (Bank Central Asia)",
        "phone": "1500888",
    }
    assert result["risk_score"] == 85


def test_analyze_phone_without_bank_has_no_contact(monkeypatch, service: PhoneService):
    monkeypatch.setattr(PhoneService, "_get_active_cred", lambda self: VALID_CRED)
    monkeypatch.setattr(
        PhoneService,
        "_gtc_call",
        lambda self, endpoint, payload, cred: (
            200,
            {
                "result": {
                    "profile": {"displayName": "Kak Depi"},
                    "tags": [],
                }
            },
        ),
    )

    async def fake_call(self, messages):
        return ANALYSIS_JSON

    monkeypatch.setattr(AIService, "_call_openrouter", fake_call)

    result = run(service.analyze_phone_number("081234567890"))

    assert result["official_contact"] is None


def test_analyze_phone_does_not_block_event_loop(monkeypatch, service: PhoneService):
    """Panggilan GetContact yang lambat tidak boleh membekukan event loop.

    Heartbeat mengukur jeda terbesar antar-tick. Jika `_gtc_call` (blocking)
    dipanggil langsung di coroutine, jeda mendekati durasi panggilan itu.
    """
    gtc_delay = 0.5

    def slow_gtc_call(self, endpoint, payload, cred):
        time.sleep(gtc_delay)
        return 200, {"result": {"profile": {"displayName": "Kak Depi"}, "tags": []}}

    monkeypatch.setattr(PhoneService, "_get_active_cred", lambda self: VALID_CRED)
    monkeypatch.setattr(PhoneService, "_gtc_call", slow_gtc_call)

    async def fake_call(self, messages):
        return ANALYSIS_JSON

    monkeypatch.setattr(AIService, "_call_openrouter", fake_call)

    async def scenario() -> float:
        max_gap = 0.0
        stop = False

        async def heartbeat():
            nonlocal max_gap
            last = time.perf_counter()
            while not stop:
                await asyncio.sleep(0.01)
                now = time.perf_counter()
                max_gap = max(max_gap, now - last)
                last = now

        beat = asyncio.create_task(heartbeat())
        await asyncio.sleep(0.05)
        await service.analyze_phone_number("081234567890")
        stop = True
        await beat
        return max_gap

    max_gap = run(scenario())

    assert max_gap < gtc_delay / 2, (
        f"Event loop membeku {max_gap:.2f}s saat GetContact dipanggil."
    )


def test_phone_number_is_masked_in_logs(monkeypatch, caplog, service: PhoneService):
    """Nomor lengkap tidak boleh muncul di log; hanya bentuk tersamar."""
    monkeypatch.setattr(PhoneService, "_get_active_cred", lambda self: VALID_CRED)
    monkeypatch.setattr(
        PhoneService,
        "_gtc_call",
        lambda self, endpoint, payload, cred: (
            200,
            {"result": {"profile": {"displayName": "Kak Depi"}, "tags": []}},
        ),
    )

    async def fake_call(self, messages):
        return ANALYSIS_JSON

    monkeypatch.setattr(AIService, "_call_openrouter", fake_call)
    caplog.set_level(logging.DEBUG)

    run(service.analyze_phone_number("081234567890"))

    assert "081234567890" not in caplog.text
    assert "6281234567890" not in caplog.text
    assert "+6281*******90" in caplog.text


def test_gtc_unexpected_error_does_not_log_exception_text(
    monkeypatch, caplog, service: PhoneService
):
    """Teks exception mentah bisa memuat URL/potongan respons; jangan di-log."""

    def boom(*args, **kwargs):
        raise RuntimeError("DETAIL-SENSITIF-DARI-UPSTREAM")

    monkeypatch.setattr("app.services.phone_service.requests.post", boom)
    caplog.set_level(logging.DEBUG)

    with pytest.raises(HTTPException) as exc:
        service._gtc_call("/v2.8/search", {}, VALID_CRED)

    assert exc.value.status_code == 502
    assert "DETAIL-SENSITIF-DARI-UPSTREAM" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_gtc_rejected_session_returns_502(monkeypatch, service: PhoneService):
    class FakeResponse:
        status_code = 401

    monkeypatch.setattr(
        "app.services.phone_service.requests.post",
        lambda *args, **kwargs: FakeResponse(),
    )

    with pytest.raises(HTTPException) as exc:
        service._gtc_call("/v2.8/search", {}, VALID_CRED)

    assert exc.value.status_code == 502
    assert "Sesi GetContact" in exc.value.detail


def test_analyze_phone_encapsulates_context_and_separates_roles(monkeypatch, service: PhoneService):
    monkeypatch.setattr(PhoneService, "_get_active_cred", lambda self: VALID_CRED)
    monkeypatch.setattr(
        PhoneService,
        "_gtc_call",
        lambda self, endpoint, payload, cred: (
            200,
            {"result": {"profile": {"displayName": "Akun Penipu"}, "tags": [{"tag": "injeksi"}]}},
        ),
    )

    captured = []

    async def fake_call(self, messages):
        nonlocal captured
        captured = messages
        return ANALYSIS_JSON

    monkeypatch.setattr(AIService, "_call_openrouter", fake_call)
    run(service.analyze_phone_number("081234567890"))

    assert len(captured) == 2
    assert captured[0]["role"] == "system"
    assert captured[1]["role"] == "user"
    assert "<untrusted_evidence>" in captured[1]["content"]
    assert "TARGET PHONE NUMBER: +6281234567890" in captured[1]["content"]


def test_analyze_phone_uses_cache_across_formats(monkeypatch, caplog, service: PhoneService):
    gtc_calls = 0
    llm_calls = 0

    def fake_gtc(self, endpoint, payload, cred):
        nonlocal gtc_calls
        gtc_calls += 1
        return 200, {"result": {"profile": {"displayName": "CS Bank BCA"}, "tags": []}}

    async def fake_llm(self, messages):
        nonlocal llm_calls
        llm_calls += 1
        return ANALYSIS_JSON

    monkeypatch.setattr(PhoneService, "_get_active_cred", lambda self: VALID_CRED)
    monkeypatch.setattr(PhoneService, "_gtc_call", fake_gtc)
    monkeypatch.setattr(AIService, "_call_openrouter", fake_llm)
    caplog.set_level(logging.INFO)

    first = run(service.analyze_phone_number("0812-3456-7890"))
    second = run(service.analyze_phone_number("+62 812 3456 7890"))

    assert gtc_calls == 1
    assert llm_calls == 1
    assert first == second
    assert "Cache hit analisis untuk nomor: +6281*******90" in caplog.text


def test_analyze_phone_cache_expires_after_24h(monkeypatch, service: PhoneService):
    gtc_calls = 0
    fake_now = 1000.0

    def fake_gtc(self, endpoint, payload, cred):
        nonlocal gtc_calls
        gtc_calls += 1
        return 200, {"result": {"profile": {"displayName": "Kak Depi"}, "tags": []}}

    async def fake_llm(self, messages):
        return ANALYSIS_JSON

    monkeypatch.setattr(PhoneService, "_get_active_cred", lambda self: VALID_CRED)
    monkeypatch.setattr(PhoneService, "_gtc_call", fake_gtc)
    monkeypatch.setattr(AIService, "_call_openrouter", fake_llm)
    monkeypatch.setattr("app.services.phone_service.time.monotonic", lambda: fake_now)

    run(service.analyze_phone_number("081234567890"))
    assert gtc_calls == 1

    fake_now += PHONE_CACHE_TTL_SECONDS + 1
    run(service.analyze_phone_number("081234567890"))
    assert gtc_calls == 2


def test_analyze_phone_cache_evicts_lru_above_100(monkeypatch, service: PhoneService):
    monkeypatch.setattr(PhoneService, "_get_active_cred", lambda self: VALID_CRED)
    monkeypatch.setattr(
        PhoneService,
        "_gtc_call",
        lambda self, endpoint, payload, cred: (
            200,
            {"result": {"profile": {"displayName": "User"}, "tags": []}},
        ),
    )

    async def fake_llm(self, messages):
        return ANALYSIS_JSON

    monkeypatch.setattr(AIService, "_call_openrouter", fake_llm)

    for i in range(PHONE_CACHE_MAX_SIZE + 5):
        run(service.analyze_phone_number(f"0812{i:08d}"))

    assert len(_PHONE_CACHE) == PHONE_CACHE_MAX_SIZE


def test_analyze_phone_does_not_cache_empty_gtc_result(monkeypatch, service: PhoneService):
    gtc_calls = 0

    def fake_empty_gtc(self, endpoint, payload, cred):
        nonlocal gtc_calls
        gtc_calls += 1
        return 200, {"result": {"profile": {}, "tags": []}}

    async def fake_llm(self, messages):
        return ANALYSIS_JSON

    monkeypatch.setattr(PhoneService, "_get_active_cred", lambda self: VALID_CRED)
    monkeypatch.setattr(PhoneService, "_gtc_call", fake_empty_gtc)
    monkeypatch.setattr(AIService, "_call_openrouter", fake_llm)

    run(service.analyze_phone_number("081234567890"))
    run(service.analyze_phone_number("081234567890"))

    assert gtc_calls == 2
    assert len(_PHONE_CACHE) == 0


def test_analyze_phone_multi_bank_from_profile_and_tags(
    monkeypatch, service: PhoneService
):
    monkeypatch.setattr(PhoneService, "_get_active_cred", lambda self: VALID_CRED)
    monkeypatch.setattr(
        PhoneService,
        "_gtc_call",
        lambda self, endpoint, payload, cred: (
            200,
            {
                "result": {
                    "profile": {"displayName": "CS BCA"},
                    "tags": [{"tag": "Penipu BRI"}, {"tag": "Penipu Bank Mandiri"}],
                }
            },
        ),
    )

    async def fake_llm(self, messages):
        return ANALYSIS_JSON

    monkeypatch.setattr(AIService, "_call_openrouter", fake_llm)

    result = run(service.analyze_phone_number("081234567890"))

    assert result["official_contact"]["name"] == "Bank BCA (Bank Central Asia)"
    assert [c["name"] for c in result["official_contacts"]] == [
        "Bank BCA (Bank Central Asia)",
        "Bank BRI (Bank Rakyat Indonesia)",
        "Bank Mandiri",
    ]


def test_analyze_phone_handles_null_gtc_result_and_malformed_tags(
    monkeypatch, service: PhoneService
):
    responses = iter(
        [
            {"result": None},
            {
                "result": {
                    "profile": None,
                    "tags": [None, {"tag": None}, {"tag": "  "}, {"tag": "Penipu BCA"}],
                }
            },
        ]
    )

    monkeypatch.setattr(PhoneService, "_get_active_cred", lambda self: VALID_CRED)
    monkeypatch.setattr(
        PhoneService,
        "_gtc_call",
        lambda self, endpoint, payload, cred: (200, next(responses)),
    )

    async def fake_llm(self, messages):
        return ANALYSIS_JSON

    monkeypatch.setattr(AIService, "_call_openrouter", fake_llm)

    first = run(service.analyze_phone_number("081234567890"))
    assert first["official_contact"] is None
    assert len(_PHONE_CACHE) == 0

    second = run(service.analyze_phone_number("081234567890"))
    assert second["official_contact"]["name"] == "Bank BCA (Bank Central Asia)"
    assert len(_PHONE_CACHE) == 1


def test_analyze_phone_schema_error_returns_500_without_poisoning_cache(
    monkeypatch, service: PhoneService
):
    monkeypatch.setattr(PhoneService, "_get_active_cred", lambda self: VALID_CRED)
    monkeypatch.setattr(
        PhoneService,
        "_gtc_call",
        lambda self, endpoint, payload, cred: (
            200,
            {"result": {"profile": {"displayName": "CS Bank BCA"}, "tags": [{"tag": "spam"}]}},
        ),
    )

    async def fake_bad_llm(self, messages):
        return '{"risk_score": 150, "risk_category": "Tinggi", "reasons": ["x"], "recommendations": ["y"]}'

    monkeypatch.setattr(AIService, "_call_openrouter", fake_bad_llm)

    with pytest.raises(HTTPException) as exc:
        run(service.analyze_phone_number("081234567890"))

    assert exc.value.status_code == 500
    assert exc.value.detail == "Format output AI cacat."
    assert len(_PHONE_CACHE) == 0

