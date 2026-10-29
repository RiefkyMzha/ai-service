import re

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional

_PHONE_PATTERN = re.compile(r"^(?:\+62|62|0)\d{7,13}$")

# --- Sub-schemas ---
class OfficialContact(BaseModel):
    name: str
    phone: str
    whatsapp: Optional[str] = None

class ActionStep(BaseModel):
    title: str
    description: str

# --- Requests ---
class PhoneAnalysisRequest(BaseModel):
    phone_number: str = Field(..., description="Nomor telepon yang akan dianalisis", examples=["081234567890"])

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str) -> str:
        cleaned = re.sub(r"[^\d+]", "", value.strip())
        if not _PHONE_PATTERN.match(cleaned):
            raise ValueError(
                "Format nomor telepon tidak valid (contoh: 081234567890)."
            )
        return cleaned

# --- Responses ---
class AnalysisResponse(BaseModel):
    risk_score: int = Field(..., ge=0, le=100)
    risk_category: str = Field(..., examples=["Tinggi"])
    scam_type: Optional[str] = Field(None, examples=["Phishing Kredensial"])
    reasons: List[str]
    recommendations: List[str]
    official_contact: Optional[OfficialContact] = None

class EmergencyResponse(BaseModel):
    ai_kronologi: str
    langkah_penanganan: List[ActionStep]
    official_contact: Optional[OfficialContact] = None