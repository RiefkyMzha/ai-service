import base64
import json
import logging
from typing import Any, Dict

import requests
from fastapi import HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.data_loader import DataLoader
from app.core.normalization import normalize_analysis_result
from app.core.prompts import EMERGENCY_PROMPT, REASONING_PROMPT, VISION_PROMPT

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 15 * 1024 * 1024


class AIService:
    def __init__(self, data_loader: DataLoader) -> None:
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = "nvidia/nemotron-3.5-super-vl:free"
        self.timeout = 60
        self.data_loader = data_loader

    async def _process_image_to_base64(self, file: UploadFile | None) -> str | None:
        if not file:
            return None

        content_type = (file.content_type or "").lower()
        if content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=400,
                detail="File harus berupa gambar (JPG, PNG, atau WEBP).",
            )

        chunks: list[bytes] = []
        total_bytes = 0
        chunk_size = 1024 * 1024

        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > MAX_IMAGE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail="Ukuran gambar maksimal 15MB.",
                )
            chunks.append(chunk)

        content = b"".join(chunks)

        encoded = base64.b64encode(content).decode("ascii")
        return f"data:{content_type};base64,{encoded}"

    def _post_openrouter(self, messages: list[dict[str, Any]]) -> str:
        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://cegahscam.local",
            "X-Title": "CegahScam AI",
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        resp = requests.post(
            self.api_url,
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def _call_openrouter(self, messages: list[dict[str, Any]]) -> str:
        if not settings.OPENROUTER_API_KEY:
            raise HTTPException(
                status_code=500,
                detail="Konfigurasi API AI tidak valid.",
            )

        try:
            return await run_in_threadpool(self._post_openrouter, messages)

        except requests.Timeout as err:
            raise HTTPException(
                status_code=408,
                detail="Request ke AI timeout.",
            ) from err

        except requests.HTTPError as err:
            status = err.response.status_code if err.response is not None else None
            if status in (401, 403):
                detail = "API key AI tidak valid atau tidak punya akses."
            elif status == 429:
                detail = "Kuota/laju layanan AI terlampaui, coba lagi nanti."
            else:
                detail = "Layanan AI menolak permintaan."
            raise HTTPException(status_code=502, detail=detail) from err

        except requests.RequestException as err:
            raise HTTPException(
                status_code=502,
                detail="Gagal terhubung ke layanan AI.",
            ) from err

        except (KeyError, IndexError, ValueError) as err:
            raise HTTPException(
                status_code=500,
                detail="Respons AI tidak valid.",
            ) from err

    async def analyze_text_and_image(
        self,
        user_text: str,
        image: UploadFile | None,
    ) -> dict[str, Any]:
        image_url = await self._process_image_to_base64(image)

        system_instruction = (
            f"{REASONING_PROMPT}\n\n{VISION_PROMPT}"
            if image_url
            else REASONING_PROMPT
        )

        user_content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": f"<untrusted_evidence>\n{user_text}\n</untrusted_evidence>",
            }
        ]

        if image_url:
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": image_url},
                }
            )

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_content},
        ]
        raw_result = await self._call_openrouter(messages)

        try:
            result = json.loads(raw_result)
            if not isinstance(result, dict):
                raise ValueError("Output AI bukan object JSON.")
        except (json.JSONDecodeError, ValueError) as err:
            raise HTTPException(
                status_code=500,
                detail="Format output AI cacat.",
            ) from err

        result = normalize_analysis_result(result)
        result["official_contact"] = self.data_loader.official_contact_for(user_text)
        return result

    async def process_emergency(
        self,
        incident_data: Dict[str, Any],
        image: UploadFile | None,
        is_financial: bool,
    ) -> dict[str, Any]:
        image_url = await self._process_image_to_base64(image)

        incident_text = "\n".join(
            f"- {key}: {value}"
            for key, value in incident_data.items()
            if value
        )

        incident_type = "FINANCIAL SCAM" if is_financial else "DATA BREACH"

        user_content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    f"INCIDENT TYPE: {incident_type}\n\n"
                    f"<untrusted_evidence>\n{incident_text}\n</untrusted_evidence>"
                ),
            }
        ]

        if image_url:
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": image_url},
                }
            )

        messages = [
            {"role": "system", "content": EMERGENCY_PROMPT},
            {"role": "user", "content": user_content},
        ]

        logger.info("Memproses laporan darurat (%s)...", incident_type)

        raw_result = await self._call_openrouter(messages)

        try:
            result = json.loads(raw_result)
            if not isinstance(result, dict):
                raise ValueError("Output AI bukan object JSON.")
        except (json.JSONDecodeError, ValueError) as err:
            logger.error("Gagal parse JSON darurat (panjang output: %d).", len(raw_result))
            raise HTTPException(
                status_code=500,
                detail="Format output AI cacat.",
            ) from err

        result = normalize_analysis_result(result)

        bank_hint = incident_data.get("bank_korban") if is_financial else None
        result["official_contact"] = (
            self.data_loader.official_contact_for(str(bank_hint))
            if bank_hint
            else None
        )
        return result
