import logging

from fastapi import Depends, FastAPI
from app.api.routes import router
from app.core.config import settings
from app.core.security import api_key_header, require_api_token

logging.basicConfig(
    level=settings.LOG_LEVEL.upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend API Service untuk deteksi penipuan CegahScam.",
    version="1.0.0"
)

@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "message": "CegahScam AI Service is healthy"}

app.include_router(
    router,
    prefix=settings.API_V1_STR,
    dependencies=[Depends(api_key_header)],
)

app.middleware("http")(require_api_token)