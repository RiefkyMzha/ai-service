import json
from typing import Any, Dict

# --- Analysis Result Normalization ---

SCAM_TYPE_TRANSLATIONS = {
    "no scam indicators": "Tidak Ada Indikator Penipuan",
    "phishing / smishing / vishing": "Phishing / Smishing / Vishing",
    "impersonation / account takeover": "Peniruan Identitas / Pengambilalihan Akun",
    "fake customer support / fake bank notification": "CS Palsu / Notifikasi Bank Palsu",
    "investment scam / job scam": "Investasi Palsu / Lowongan Kerja Palsu",
    "courier/delivery scam / marketplace scam": "Penipuan Kurir / Marketplace",
    "romance scam / giveaway/prize scam": "Penipuan Romantis / Undian Berhadiah",
    "qr/payment scam / malware-related scam": "Penipuan QR/Pembayaran / Malware",
}

RISK_CATEGORY_TRANSLATIONS = {
    "very high": "Sangat Tinggi",
    "high": "Tinggi",
    "moderate": "Sedang",
    "medium": "Sedang",
    "low": "Rendah",
    "no scam indicators": "Tidak Ada Indikasi",
}


def _normalize_key(value: str) -> str:
    return " ".join(value.strip().lower().split())


def normalize_analysis_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Samakan label kategori agar konsisten Bahasa Indonesia."""
    scam_type = result.get("scam_type")
    if isinstance(scam_type, str):
        key = _normalize_key(scam_type)
        result["scam_type"] = SCAM_TYPE_TRANSLATIONS.get(key, scam_type.strip())

    risk_category = result.get("risk_category")
    if isinstance(risk_category, str):
        key = _normalize_key(risk_category)
        result["risk_category"] = RISK_CATEGORY_TRANSLATIONS.get(
            key, risk_category.strip()
        )

    return result


# --- Emergency Incident Normalization ---

PLATFORM_LABELS = {
    "whatsapp": "WhatsApp",
    "wa": "WhatsApp",
    "instagram": "Instagram",
    "ig": "Instagram",
}

BANK_CODE_LABELS = {
    "bca": "BCA",
    "bri": "BRI",
    "bni": "BNI",
    "mandiri": "Mandiri",
    "dana": "DANA",
    "ovo": "OVO",
    "gopay": "GOPAY",
}

FINANCIAL_PURPOSE_LABELS = {
    "link": "Pembelian barang/jasa",
    "pembelian": "Pembelian barang/jasa",
    "pembelian-barang": "Pembelian barang/jasa",
    "barang-jasa": "Pembelian barang/jasa",
    "data-pribadi": "Biaya administrasi",
    "administrasi": "Biaya administrasi",
    "biaya-admin": "Biaya administrasi",
    "biaya-administrasi": "Biaya administrasi",
    "otp": "Hadiah/promo",
    "hadiah": "Hadiah/promo",
    "promo": "Hadiah/promo",
    "hadiah-promo": "Hadiah/promo",
    "menyamar": "Pinjaman",
    "pinjaman": "Pinjaman",
    "lainnya": "Lainnya",
}

BREACH_DATA_TYPE_LABELS = {
    "data-pribadi": "Data pribadi",
    "media-sosial": "Akun media sosial",
    "perbankan": "Akun perbankan/finansial",
    "kartu": "Data kartu kredit/debit",
    "email": "Akun email",
}

BREACH_ACTION_LABELS = {
    "link": "Mengirim tautan mencurigakan",
    "data-pribadi": "Meminta data pribadi",
    "otp": "Meminta OTP/PIN/kata sandi",
    "menyamar": "Mengaku sebagai pihak tertentu",
    "lainnya": "Lainnya",
}

ACCESS_STATUS_LABELS = {
    "bisaakses": "Masih bisa diakses",
    "masih-bisa-diakses": "Masih bisa diakses",
    "tidakbisaakses": "Tidak bisa diakses",
    "tidak-bisa-diakses": "Tidak bisa diakses",
    "diketahuilain": "Diketahui pihak lain",
    "diketahui-pihak-lain": "Diketahui pihak lain",
    "diketahuipihaklain": "Diketahui pihak lain",
    "tidaktahu": "Tidak tahu",
    "tidak-tahu": "Tidak tahu",
}

_EMERGENCY_SINGLE_FIELD_MAPPINGS = (
    ("platform_kejadian", PLATFORM_LABELS),
    ("bank_korban", BANK_CODE_LABELS),
    ("status_akses", ACCESS_STATUS_LABELS),
)

_EMERGENCY_MULTI_FIELD_MAPPINGS = (
    ("tujuan_transaksi", FINANCIAL_PURPOSE_LABELS),
    ("jenis_data", BREACH_DATA_TYPE_LABELS),
    ("tindakan_pelaku", BREACH_ACTION_LABELS),
)


def _normalize_single_value(raw_value: Any, mapping: Dict[str, str]) -> str:
    if not isinstance(raw_value, str) or not raw_value.strip():
        return str(raw_value or "")
    return mapping.get(_normalize_key(raw_value), raw_value.strip())


def _normalize_multi_value(raw_value: Any, mapping: Dict[str, str]) -> str:
    if not isinstance(raw_value, str) or not raw_value.strip():
        return str(raw_value or "")

    text = raw_value.strip()
    items: list[str]
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                items = [str(item) for item in parsed]
            else:
                items = text.split(",")
        except json.JSONDecodeError:
            items = text.split(",")
    else:
        items = text.split(",")

    normalized_items = [
        mapping.get(_normalize_key(item), item.strip())
        for item in items
        if item and item.strip()
    ]
    return ", ".join(normalized_items)


def normalize_emergency_incident_data(incident_data: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(incident_data)
    for field, mapping in _EMERGENCY_SINGLE_FIELD_MAPPINGS:
        if normalized.get(field):
            normalized[field] = _normalize_single_value(normalized[field], mapping)
    for field, mapping in _EMERGENCY_MULTI_FIELD_MAPPINGS:
        if normalized.get(field):
            normalized[field] = _normalize_multi_value(normalized[field], mapping)
    return normalized

