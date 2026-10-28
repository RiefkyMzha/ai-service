import logging

from fastapi import FastAPI
from app.api.routes import router
from app.core.config import settings

logging.basicConfig(
    level=settings.LOG_LEVEL.upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend API Service untuk deteksi penipuan CegahScam.",
    version="1.0.0"
)

# Endpoint kesehatan untuk monitoring server
@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "message": "CegahScam AI Service is healthy"}

# Mendaftarkan rute yang sudah kita buat
app.include_router(router, prefix=settings.API_V1_STR)