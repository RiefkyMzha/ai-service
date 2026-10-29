import hmac
import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

from app.core.config import settings

logger = logging.getLogger(__name__)

TOKEN_HEADER = "x-api-token"

api_key_header = APIKeyHeader(
    name="X-API-Token",
    auto_error=False,
)


def _token_error(provided: str | None) -> tuple[int, str] | None:
    expected = settings.CEGAHSCAM_API_TOKEN
    if not expected:
        logger.error("CEGAHSCAM_API_TOKEN belum diatur; semua request API ditolak.")
        return 500, "Konfigurasi token API belum diatur."

    if not hmac.compare_digest(
        (provided or "").encode("utf-8"), expected.encode("utf-8")
    ):
        logger.warning("Request ditolak: token API tidak valid atau tidak ada.")
        return 401, "Token API tidak valid atau tidak ada."
    return None


def _is_protected(path: str) -> bool:
    prefix = settings.API_V1_STR
    return path == prefix or path.startswith(prefix + "/")


async def require_api_token(request: Request, call_next):
    if _is_protected(request.url.path):
        error = _token_error(request.headers.get(TOKEN_HEADER))
        if error:
            status_code, detail = error
            return JSONResponse(status_code=status_code, content={"detail": detail})
    return await call_next(request)
