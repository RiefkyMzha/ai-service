from tests.conftest import make_png

FINANCIAL_FORM = {
    "bank_korban": "BCA",
    "platform_kejadian": "WhatsApp",
    "tanggal_kejadian": "2026-10-27",
    "tujuan_transaksi": "Pembelian barang",
    "nomor_rekening_penipu": "1234567890",
    "nominal_kerugian": "1500000",
    "kronologi_user": "Transfer untuk barang yang tidak dikirim.",
}

BREACH_FORM = {
    "jenis_data": "Data pribadi (nama, email)",
    "tanggal_kejadian": "2026-10-27",
    "platform_kejadian": "Instagram",
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


def test_data_breach_emergency_extracts_bank_from_kronologi(client, fake_openrouter):
    form = dict(
        BREACH_FORM,
        jenis_data="Akun perbankan / finansial",
        kronologi_user="Pelaku meminta OTP BCA mobile saya melalui WhatsApp.",
    )
    response = client.post(
        "/api/v1/emergency/data-breach",
        data=form,
        files={"bukti_percakapan": ("bukti.png", make_png(), "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["official_contact"]["name"] == "Bank BCA (Bank Central Asia)"
    assert body["official_contact"]["phone"] == "1500888"


def test_data_breach_emergency_falls_back_to_ojk_for_banking_or_card(
    client, fake_openrouter
):
    form = dict(
        BREACH_FORM,
        jenis_data="Akun perbankan / finansial",
    )
    response = client.post(
        "/api/v1/emergency/data-breach",
        data=form,
        files={"bukti_percakapan": ("bukti.png", make_png(), "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["official_contact"]["name"] == "Otoritas Jasa Keuangan (OJK)"
    assert body["official_contact"]["phone"] == "157"


def test_financial_emergency_requires_evidence(client, fake_openrouter):
    response = client.post("/api/v1/emergency/financial", data=FINANCIAL_FORM)
    assert response.status_code == 422


def test_mock_mode_endpoints_work_without_upstream(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "MOCK_MODE", True)

    res_text = client.post(
        "/api/v1/analyze/text",
        data={"text_content": "Selamat anda pemenang hadiah undian Bank BCA"},
    )
    assert res_text.status_code == 200
    body_text = res_text.json()
    assert body_text["risk_score"] == 85
    assert body_text["official_contact"]["name"] == "Bank BCA (Bank Central Asia)"

    res_phone = client.post(
        "/api/v1/analyze/phone",
        json={"phone_number": "081234567890"},
    )
    assert res_phone.status_code == 200
    assert res_phone.json()["risk_score"] == 65

    res_emg = client.post(
        "/api/v1/emergency/financial",
        data=FINANCIAL_FORM,
        files={"bukti_transfer": ("bukti.png", make_png(), "image/png")},
    )
    assert res_emg.status_code == 200
    assert res_emg.json()["official_contact"]["phone"] == "1500888"
