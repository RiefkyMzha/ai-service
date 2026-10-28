from tests.conftest import make_png

FINANCIAL_FORM = {
    "bank_korban": "BCA",
    "kanal_media": "WhatsApp",
    "tanggal_kejadian": "2026-10-27",
    "tujuan_transaksi": "Pembelian barang",
    "nomor_rekening_penipu": "1234567890",
    "nominal_kerugian": "1500000",
    "kronologi_user": "Transfer untuk barang yang tidak dikirim.",
}

BREACH_FORM = {
    "jenis_data": "Data pribadi (nama, email)",
    "tanggal_kejadian": "2026-10-27",
    "kanal_media": "Instagram",
    "tindakan_pelaku": "Meminta OTP",
    "status_akses": "Masih bisa diakses",
}


def test_analyze_text_attaches_official_contact_from_whitelist(
    client, fake_openrouter
):
    response = client.post(
        "/api/v1/analyze/text",
        data={"text_content": "Halo, ini BCA. Akun Anda diblokir, kirim OTP."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["official_contact"]["name"] == "Bank BCA (Bank Central Asia)"
    assert body["official_contact"]["phone"] == "1500888"
    # Label Inggris dari LLM dinormalisasi ke Bahasa Indonesia.
    assert body["scam_type"] == "Tidak Ada Indikator Penipuan"


def test_analyze_text_without_bank_has_no_contact(client, fake_openrouter):
    response = client.post(
        "/api/v1/analyze/text",
        data={"text_content": "Ada promo mencurigakan dari akun tak dikenal."},
    )

    assert response.status_code == 200
    assert response.json()["official_contact"] is None


def test_analyze_text_requires_content(client, fake_openrouter):
    response = client.post("/api/v1/analyze/text", data={})
    assert response.status_code == 422


def test_analyze_text_rejects_overlong_content(client, fake_openrouter):
    response = client.post(
        "/api/v1/analyze/text",
        data={"text_content": "a" * 10_001},
    )
    assert response.status_code == 422


def test_analyze_image_returns_analysis_without_contact(client, fake_openrouter):
    response = client.post(
        "/api/v1/analyze/image",
        data={"platform": "WhatsApp"},
        files={"image": ("bukti.png", make_png(), "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["risk_score"] == 80
    assert body["official_contact"] is None


def test_analyze_image_rejects_non_image(client, fake_openrouter):
    response = client.post(
        "/api/v1/analyze/image",
        data={"platform": "WhatsApp"},
        files={"image": ("bukti.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400


def test_analyze_image_rejects_oversized_file(client, fake_openrouter):
    oversized = b"\x00" * (15 * 1024 * 1024 + 1)
    response = client.post(
        "/api/v1/analyze/image",
        data={"platform": "WhatsApp"},
        files={"image": ("besar.png", oversized, "image/png")},
    )
    assert response.status_code == 413


def test_financial_emergency_uses_bank_korban_whitelist(client, fake_openrouter):
    response = client.post(
        "/api/v1/emergency/financial",
        data=FINANCIAL_FORM,
        files={"bukti_transfer": ("bukti.png", make_png(), "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["official_contact"]["name"] == "Bank BCA (Bank Central Asia)"
    assert body["official_contact"]["phone"] == "1500888"
    assert body["langkah_penanganan"]


def test_financial_emergency_unknown_bank_has_no_contact(client, fake_openrouter):
    form = dict(FINANCIAL_FORM, bank_korban="Bank Gaib")
    response = client.post(
        "/api/v1/emergency/financial",
        data=form,
        files={"bukti_transfer": ("bukti.png", make_png(), "image/png")},
    )

    assert response.status_code == 200
    # Model mengembalikan kontak palsu, tapi harus ditimpa menjadi null.
    assert response.json()["official_contact"] is None


def test_data_breach_emergency_has_no_contact(client, fake_openrouter):
    response = client.post(
        "/api/v1/emergency/data-breach",
        data=BREACH_FORM,
        files={"bukti_percakapan": ("bukti.png", make_png(), "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["official_contact"] is None
    assert body["ai_kronologi"].startswith("I. DATA PELAPOR")


def test_financial_emergency_requires_evidence(client, fake_openrouter):
    response = client.post("/api/v1/emergency/financial", data=FINANCIAL_FORM)
    assert response.status_code == 422
