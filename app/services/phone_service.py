import copy
import json
import logging
import base64
import hashlib
import hmac
import re
import time
from collections import OrderedDict
import requests
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from pathlib import Path
from typing import Any, Tuple

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from app.core.config import settings
from app.core.normalization import normalize_analysis_result
from app.schemas.payload import AnalysisResponse
from app.services.ai_service import AIService, finalize_ai_result, parse_ai_json

logger = logging.getLogger(__name__)

GTC_BASE = "https://pbssrv-centralevents.com"
HMAC_KEY = "31426764382a642f3a6665497235466f3d236d5d785b722b4c657457442a495b494524324866782a2364292478587a78662d7a7b7578593f71703e2b7e365762"
APP_VERSION = "8.4.0"
ANDROID_OS = "android 9"
LANG = "en_US"
COUNTRY = "id"

PHONE_CACHE_MAX_SIZE = 100
PHONE_CACHE_TTL_SECONDS = 86400
_PHONE_CACHE: OrderedDict[str, Tuple[float, dict[str, Any]]] = OrderedDict()

def _mask_phone(number: str) -> str:
    if len(number) <= 7:
        return "*" * len(number)
    return number[:5] + "*" * (len(number) - 7) + number[-2:]


def _get_cached_phone_result(cache_key: str) -> dict[str, Any] | None:
    if cache_key not in _PHONE_CACHE:
        return None
    ts, val = _PHONE_CACHE[cache_key]
    if time.monotonic() - ts > PHONE_CACHE_TTL_SECONDS:
        del _PHONE_CACHE[cache_key]
        return None
    _PHONE_CACHE.move_to_end(cache_key)
    return copy.deepcopy(val)


def _set_cached_phone_result(cache_key: str, val: dict[str, Any]) -> None:
    _PHONE_CACHE[cache_key] = (time.monotonic(), copy.deepcopy(val))
    _PHONE_CACHE.move_to_end(cache_key)
    if len(_PHONE_CACHE) > PHONE_CACHE_MAX_SIZE:
        _PHONE_CACHE.popitem(last=False)


class PhoneService:
    def __init__(self, ai_service: AIService):
        self.ai_service = ai_service
        self.cred_file = Path("app/data/gtc_credentials.json")
        self.timeout = 25

    def _sig(self, ts: str, message: str, key_hex: str) -> str:
        mac = hmac.new(bytes.fromhex(key_hex), f"{ts}-{message}".encode(), hashlib.sha256)
        return base64.b64encode(mac.digest()).decode()

    def _pad(self, b: bytes) -> bytes:
        n = 16 - len(b) % 16
        return b + bytes([n]) * n

    def _encrypt(self, data: str, key_hex: str) -> str:
        enc = Cipher(algorithms.AES(bytes.fromhex(key_hex)), modes.ECB()).encryptor()
        return base64.b64encode(enc.update(self._pad(data.encode())) + enc.finalize()).decode()

    def _decrypt(self, data: str, key_hex: str) -> str:
        dec = Cipher(algorithms.AES(bytes.fromhex(key_hex)), modes.ECB()).decryptor()
        out = dec.update(base64.b64decode(data)) + dec.finalize()
        return out[: -out[-1]].decode()

    def _ts(self) -> str:
        return str(int(time.time() * 1000))

    def _get_active_cred(self) -> dict:
        if not self.cred_file.exists():
            logger.error("File kredensial GetContact tidak ditemukan.")
            raise HTTPException(status_code=500, detail="Konfigurasi layanan nomor (GetContact) belum diatur.")
        
        try:
            store = json.loads(self.cred_file.read_text("utf-8"))
            active_name = store.get("active")
            creds = store.get("credentials", {})
            if not active_name or active_name not in creds:
                raise HTTPException(status_code=500, detail="Akun aktif GetContact tidak ditemukan.")
            cred = creds[active_name]
        except json.JSONDecodeError:
            logger.error("File kredensial GetContact cacat/tidak valid JSON.")
            raise HTTPException(status_code=500, detail="Konfigurasi GetContact cacat.")

        missing = [
            key for key in ("token", "finalKey", "clientDeviceId") if not cred.get(key)
        ]
        if missing:
            logger.error("Kredensial GetContact tidak lengkap: %s", ", ".join(missing))
            raise HTTPException(status_code=500, detail="Konfigurasi GetContact tidak lengkap.")
        return cred

    def _gtc_call(self, endpoint: str, payload: dict, cred: dict) -> Tuple[int, dict]:
        raw = json.dumps(payload, ensure_ascii=False)
        ts = self._ts()
        headers = {
            "Content-Type": "application/json",
            "x-os": ANDROID_OS,
            "x-app-version": APP_VERSION,
            "x-client-device-id": cred["clientDeviceId"],
            "x-lang": LANG,
            "x-req-timestamp": ts,
            "x-country-code": COUNTRY,
            "x-encrypted": "1",
            "x-req-signature": self._sig(ts, raw, HMAC_KEY),
            "x-token": cred["token"]
        }
        
        body = json.dumps({"data": self._encrypt(raw, cred["finalKey"])})
        
        try:
            r = requests.post(GTC_BASE + endpoint, data=body, headers=headers, timeout=self.timeout)
            if r.status_code in (401, 403):
                logger.error("GetContact menolak sesi (HTTP %s).", r.status_code)
                raise HTTPException(
                    status_code=502,
                    detail="Sesi GetContact tidak valid atau kedaluwarsa.",
                )
            if r.status_code >= 400:
                logger.error("GetContact mengembalikan HTTP %s.", r.status_code)
                raise HTTPException(
                    status_code=502,
                    detail="Layanan pencarian nomor sedang gangguan.",
                )

            parsed = r.json()

            if "data" in parsed:
                parsed = json.loads(self._decrypt(parsed["data"], cred["finalKey"]))
            return r.status_code, parsed
        except HTTPException:
            raise
        except requests.Timeout:
            raise HTTPException(status_code=408, detail="Layanan pencarian nomor timeout.")
        except Exception as e:
            logger.error("Gagal memanggil API GetContact (%s).", type(e).__name__)
            raise HTTPException(status_code=502, detail="Layanan pencarian nomor sedang gangguan.")

    async def analyze_phone_number(self, phone_number: str) -> dict[str, Any]:
        """Alur utama analisis nomor: GetContact -> LLM"""

        normalized_phone = re.sub(r"[^\d+]", "", phone_number.strip())
        if normalized_phone.startswith("0"):
            normalized_phone = "+62" + normalized_phone[1:]
        elif normalized_phone.startswith("62"):
            normalized_phone = "+" + normalized_phone

        if settings.MOCK_MODE:
            logger.info("Simulasi MOCK_MODE pencarian nomor: %s", _mask_phone(normalized_phone))
            mock_phone_result: dict[str, Any] = {
                "risk_score": 65,
                "risk_category": "Tinggi",
                "scam_type": "Peniruan Identitas / Pengambilalihan Akun",
                "reasons": [
                    f"[MOCK MODE] Simulasi pemeriksaan reputasi untuk nomor {_mask_phone(normalized_phone)}.",
                    "Nomor tidak terdaftar sebagai call center resmi institusi perbankan.",
                ],
                "recommendations": [
                    "Jangan berikan kode OTP, PIN, atau password kepada penelepon.",
                    "Blokir nomor apabila meminta transfer dana atau data rahasia.",
                ],
                "official_contact": None,
                "official_contacts": [],
            }
            return normalize_analysis_result(mock_phone_result)

        cache_key = hashlib.sha256(normalized_phone.encode("utf-8")).hexdigest()
        cached_result = _get_cached_phone_result(cache_key)
        if cached_result is not None:
            logger.info("Cache hit analisis untuk nomor: %s", _mask_phone(normalized_phone))
            return cached_result

        cred = self._get_active_cred()
        payload = {
            "countryCode": COUNTRY,
            "phoneNumber": normalized_phone,
            "source": "search",
            "token": cred["token"],
        }
        
        logger.info("Mencari informasi GetContact untuk nomor: %s", _mask_phone(normalized_phone))
        code, body = await run_in_threadpool(self._gtc_call, "/v2.8/search", payload, cred)

        if not isinstance(body, dict):
            logger.error("Respons GetContact bukan object JSON.")
            raise HTTPException(
                status_code=502,
                detail="Respons layanan pencarian nomor tidak valid.",
            )

        gtc_result = body.get("result")
        if not isinstance(gtc_result, dict):
            gtc_result = {}

        raw_profile = gtc_result.get("profile")
        gtc_profile = raw_profile if isinstance(raw_profile, dict) else {}

        raw_tags = gtc_result.get("tags")
        gtc_tags = raw_tags if isinstance(raw_tags, list) else []

        clean_tags = [
            tag.strip()
            for item in gtc_tags
            if isinstance(item, dict)
            and isinstance((tag := item.get("tag")), str)
            and tag.strip()
        ]
        display_name = gtc_profile.get("displayName")
        profile_name = (
            display_name.strip()
            if isinstance(display_name, str) and display_name.strip()
            else "Unknown"
        )

        from app.core.prompts import REASONING_PROMPT

        gtc_context = (
            f"TARGET PHONE NUMBER: {normalized_phone}\n"
            f"GETCONTACT PROFILE NAME: {profile_name}\n"
            f"GETCONTACT TAGS: {', '.join(clean_tags) if clean_tags else 'No tags found'}\n"
        )
        
        messages = [
            {"role": "system", "content": REASONING_PROMPT},
            {
                "role": "user",
                "content": f"<untrusted_evidence>\n{gtc_context}</untrusted_evidence>",
            },
        ]
        
        logger.info("Mengirim data GetContact ke LLM untuk analisis risiko...")
        raw_result = await self.ai_service._call_openrouter(messages)
        result = parse_ai_json(raw_result, "nomor")
        result = normalize_analysis_result(result)
        contacts = self.ai_service.data_loader.official_contacts_for(
            gtc_context, limit=3
        )
        result = finalize_ai_result(result, contacts, AnalysisResponse, "nomor")

        has_profile_name = isinstance(display_name, str) and bool(display_name.strip())
        has_tags = len(clean_tags) > 0
        if has_profile_name or has_tags:
            _set_cached_phone_result(cache_key, result)

        return result