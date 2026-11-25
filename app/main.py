import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.core.config import settings
from app.core.security import api_key_header, require_api_token

logging.basicConfig(
    level=settings.LOG_LEVEL.upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

OPENAPI_TAGS = [
    {
        "name": "Analysis",
        "description": "Deteksi indikasi penipuan pada pesan teks, tangkapan layar bukti, dan nomor telepon.",
    },
    {
        "name": "Emergency",
        "description": "Penyusunan kronologi formal dan langkah penanganan darurat bagi korban penipuan.",
    },
    {
        "name": "Health",
        "description": "Pemantauan ketersediaan layanan dan status mode operasional.",
    },
]

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend API Service untuk deteksi penipuan CegahScam.",
    version="1.0.0",
    openapi_tags=OPENAPI_TAGS,
)

@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "ok",
        "message": "CegahScam AI Service is healthy",
        "mock_mode": settings.MOCK_MODE,
    }

app.include_router(
    router,
    prefix=settings.API_V1_STR,
    dependencies=[Depends(api_key_header)],
)

app.middleware("http")(require_api_token)

cors_origins = [
    origin.strip()
    for origin in settings.CORS_ORIGINS.split(",")
    if origin.strip()
] or ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)