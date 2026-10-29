from typing import Any, Dict

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
