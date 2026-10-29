import io
import json
import struct
import zlib

import pytest
from fastapi.testclient import TestClient
from starlette.datastructures import Headers, UploadFile

from app.core.config import settings
from app.main import app
from app.services.ai_service import AIService

TEST_API_TOKEN = "token-uji-bukan-rahasia"

ANALYSIS_RESULT = {
    "risk_score": 80,
    "risk_category": "Tinggi",
    "scam_type": "No Scam Indicators",
    "reasons": ["Ada permintaan OTP."],
    "recommendations": ["Jangan berikan OTP."],
    "official_contact": {"name": "Bank Palsu", "phone": "000"},
}

EMERGENCY_RESULT = {
    "ai_kronologi": "I. DATA PELAPOR (KORBAN)\n- Platform / Kanal Kejadian: WhatsApp",
    "langkah_penanganan": [
        {"title": "Hubungi bank", "description": "Telepon call center resmi."}
    ],
    "official_contact": {"name": "Bank Palsu", "phone": "000"},
}


def make_png(width: int = 8, height: int = 8) -> bytes:
    raw = b"".join(b"\x00" + bytes([30, 60, 90]) * width for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        payload = kind + data
        return (
            struct.pack(">I", len(data))
            + payload
            + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def make_upload(
    content: bytes,
    content_type: str = "image/png",
    filename: str = "bukti.png",
) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(settings, "CEGAHSCAM_API_TOKEN", TEST_API_TOKEN)
    with TestClient(app, headers={"X-API-Token": TEST_API_TOKEN}) as test_client:
        yield test_client


@pytest.fixture
def fake_openrouter(monkeypatch):
    """Ganti panggilan jaringan OpenRouter dengan payload deterministik."""

    async def fake_call(self, messages):
        serialized = json.dumps(messages, ensure_ascii=False)
        if "Emergency Response Coordinator" in serialized:
            return json.dumps(EMERGENCY_RESULT)
        return json.dumps(ANALYSIS_RESULT)

    monkeypatch.setattr(AIService, "_call_openrouter", fake_call)
    return fake_call
