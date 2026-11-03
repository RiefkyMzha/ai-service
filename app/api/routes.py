from fastapi import APIRouter, File, Form, UploadFile, Depends
from typing import Optional

from app.schemas.payload import (
    AnalysisResponse,
    PhoneAnalysisRequest,
    EmergencyResponse,
    OfficialContact,
    ActionStep,
)
from app.services.ai_service import AIService
from app.services.phone_service import PhoneService
from app.core.data_loader import DataLoader

router = APIRouter()

_data_loader = DataLoader()

def get_ai_service() -> AIService:
    return AIService(data_loader=_data_loader)

def get_phone_service(ai_service: AIService = Depends(get_ai_service)) -> PhoneService:
    return PhoneService(ai_service=ai_service)


# --- ROUTES ---

@router.post("/analyze/text", response_model=AnalysisResponse)
async def analyze_text(
    text_content: str = Form(..., min_length=1, max_length=10_000),
    image: Optional[UploadFile] = File(None),
    ai_service: AIService = Depends(get_ai_service)
):
    raw_dict = await ai_service.analyze_text_and_image(text_content, image)
    return AnalysisResponse(**raw_dict)

@router.post("/analyze/image", response_model=AnalysisResponse)
async def analyze_image(
    platform: str = Form(..., min_length=1, max_length=50),
    image: UploadFile = File(...),
    ai_service: AIService = Depends(get_ai_service)
):
    raw_dict = await ai_service.analyze_text_and_image(f"Platform: {platform}", image)
    return AnalysisResponse(**raw_dict)

@router.post("/analyze/phone", response_model=AnalysisResponse)
async def analyze_phone(
    request: PhoneAnalysisRequest,
    phone_service: PhoneService = Depends(get_phone_service)
):
    raw_dict = await phone_service.analyze_phone_number(request.phone_number)
    return AnalysisResponse(**raw_dict)

@router.post("/emergency/financial", response_model=EmergencyResponse)
async def emergency_financial(
    bank_korban: str = Form(..., min_length=1, max_length=100),
    platform_kejadian: str = Form(..., min_length=1, max_length=100),
    tanggal_kejadian: str = Form(..., min_length=1, max_length=10),
    tujuan_transaksi: str = Form(..., min_length=1, max_length=200),
    nomor_rekening_penipu: str = Form(..., min_length=1, max_length=50),
    nominal_kerugian: float = Form(..., ge=0),
    nama_institusi_penipu: Optional[str] = Form(None, max_length=200),
    nama_pemilik_penipu: Optional[str] = Form(None, max_length=200),
    kronologi_user: Optional[str] = Form(None, max_length=5_000),
    bukti_transfer: UploadFile = File(...),
    ai_service: AIService = Depends(get_ai_service)
):
    incident_data = {
        "bank_korban": bank_korban,
        "platform_kejadian": platform_kejadian,
        "tanggal_kejadian": tanggal_kejadian,
        "tujuan_transaksi": tujuan_transaksi,
        "nomor_rekening_penipu": nomor_rekening_penipu,
        "nominal_kerugian": nominal_kerugian,
        "nama_institusi_penipu": nama_institusi_penipu,
        "nama_pemilik_penipu": nama_pemilik_penipu,
        "kronologi_user": kronologi_user
    }
    raw_dict = await ai_service.process_emergency(incident_data, bukti_transfer, is_financial=True)
    return EmergencyResponse(**raw_dict)

@router.post("/emergency/data-breach", response_model=EmergencyResponse)
async def emergency_data_breach(
    jenis_data: str = Form(..., min_length=1, max_length=200),
    tanggal_kejadian: str = Form(..., min_length=1, max_length=10),
    platform_kejadian: str = Form(..., min_length=1, max_length=100),
    tindakan_pelaku: str = Form(..., min_length=1, max_length=200),
    status_akses: str = Form(..., min_length=1, max_length=100),
    kronologi_user: Optional[str] = Form(None, max_length=5_000),
    bukti_percakapan: UploadFile = File(...),
    ai_service: AIService = Depends(get_ai_service)
):
    incident_data = {
        "jenis_data": jenis_data,
        "tanggal_kejadian": tanggal_kejadian,
        "platform_kejadian": platform_kejadian,
        "tindakan_pelaku": tindakan_pelaku,
        "status_akses": status_akses,
        "kronologi_user": kronologi_user
    }
    raw_dict = await ai_service.process_emergency(incident_data, bukti_percakapan, is_financial=False)
    return EmergencyResponse(**raw_dict)
