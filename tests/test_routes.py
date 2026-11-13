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
    "kronologi_user": "Akun saya dihubungi pihak mengaku CS dan meminta OTP.",
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


def test_financial_emergency_requires_kronologi_user(client, fake_openrouter):
    form = {k: v for k, v in FINANCIAL_FORM.items() if k != "kronologi_user"}
    response = client.post(
        "/api/v1/emergency/financial",
        data=form,
        files={"bukti_transfer": ("bukti.png", make_png(), "image/png")},
    )
    assert response.status_code == 422


def test_data_breach_emergency_requires_kronologi_user(client, fake_openrouter):
    form = {k: v for k, v in BREACH_FORM.items() if k != "kronologi_user"}
    response = client.post(
        "/api/v1/emergency/data-breach",
        data=form,
        files={"bukti_percakapan": ("bukti.png", make_png(), "image/png")},
    )
    assert response.status_code == 422


def test_emergency_kronologi_user_length_limits(client, fake_openrouter):
    overlong_form = dict(FINANCIAL_FORM, kronologi_user="x" * 10_001)
    res_overlong = client.post(
        "/api/v1/emergency/financial",
        data=overlong_form,
        files={"bukti_transfer": ("bukti.png", make_png(), "image/png")},
    )
    assert res_overlong.status_code == 422

    max_len_form = dict(FINANCIAL_FORM, kronologi_user="x" * 10_000)
    res_max = client.post(
        "/api/v1/emergency/financial",
        data=max_len_form,
        files={"bukti_transfer": ("bukti.png", make_png(), "image/png")},
    )
    assert res_max.status_code == 200


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


def test_data_breach_emergency_extracts_bank_from_ai_kronologi(client, monkeypatch):
    import json
    from app.services.ai_service import AIService

    async def fake_call(self, messages):
        return json.dumps(
            {
                "ai_kronologi": (
                    "I. DATA PELAPOR (KORBAN)\n"
                    "III. RINCIAN KRONOLOGI KEJADIAN\n"
                    "1. Pelaku mengirim pesan WhatsApp mengatasnamakan BCA Official."
                ),
                "langkah_penanganan": [
                    {
                        "title": "Laporkan ke OJK",
                        "description": "Hubungi OJK 157 untuk pelaporan.",
                    }
                ],
            }
        )

    monkeypatch.setattr(AIService, "_call_openrouter", fake_call)
    form = dict(BREACH_FORM, jenis_data="Akun perbankan / finansial")
    response = client.post(
        "/api/v1/emergency/data-breach",
        data=form,
        files={"bukti_percakapan": ("bukti.png", make_png(), "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["official_contact"]["name"] == "Bank BCA (Bank Central Asia)"
    assert body["official_contact"]["phone"] == "1500888"


def test_data_breach_emergency_user_input_overrides_ai_kronologi(client, monkeypatch):
    import json
    from app.services.ai_service import AIService

    async def fake_call(self, messages):
        return json.dumps(
            {
                "ai_kronologi": "Pelaku menyamar sebagai petugas BCA di tangkapan layar.",
                "langkah_penanganan": [],
            }
        )

    monkeypatch.setattr(AIService, "_call_openrouter", fake_call)
    form = dict(
        BREACH_FORM,
        jenis_data="Akun perbankan / finansial",
        kronologi_user="Saya dihubungi penipu yang mengaku dari BRI.",
    )
    response = client.post(
        "/api/v1/emergency/data-breach",
        data=form,
        files={"bukti_percakapan": ("bukti.png", make_png(), "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["official_contact"]["name"] == "Bank BRI (Bank Rakyat Indonesia)"
    assert body["official_contact"]["phone"] == "1500017"


def test_data_breach_emergency_ignores_langkah_penanganan_for_bank_lookup(
    client, monkeypatch
):
    import json
    from app.services.ai_service import AIService

    async def fake_call(self, messages):
        return json.dumps(
            {
                "ai_kronologi": "Pelaku meminta kode OTP akun media sosial.",
                "langkah_penanganan": [
                    {
                        "title": "Hubungi OJK atau Bank",
                        "description": "Hubungi OJK 157 atau BCA jika terdampak.",
                    }
                ],
            }
        )

    monkeypatch.setattr(AIService, "_call_openrouter", fake_call)
    response = client.post(
        "/api/v1/emergency/data-breach",
        data=BREACH_FORM,
        files={"bukti_percakapan": ("bukti.png", make_png(), "image/png")},
    )
    assert response.status_code == 200
    assert response.json()["official_contact"] is None


def test_analyze_image_extracts_bank_from_reasons(client, monkeypatch):
    import json
    from app.services.ai_service import AIService

    async def fake_call(self, messages):
        return json.dumps(
            {
                "risk_score": 85,
                "risk_category": "Tinggi",
                "scam_type": "Phishing",
                "reasons": [
                    "Gambar menampilkan pesan palsu mengatasnamakan Bank Mandiri."
                ],
                "recommendations": [
                    "Jangan klik tautan dan hubungi OJK 157 atau BCA jika perlu."
                ],
            }
        )

    monkeypatch.setattr(AIService, "_call_openrouter", fake_call)
    response = client.post(
        "/api/v1/analyze/image",
        data={"platform": "WhatsApp"},
        files={"image": ("bukti.png", make_png(), "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["official_contact"]["name"] == "Bank Mandiri"
    assert body["official_contact"]["phone"] == "14000"
    assert [c["name"] for c in body["official_contacts"]] == ["Bank Mandiri"]


def test_financial_emergency_multi_bank_priority_and_cap(client, monkeypatch):
    import json
    from app.services.ai_service import AIService

    async def fake_call(self, messages):
        return json.dumps(
            {
                "ai_kronologi": (
                    "Korban mentransfer dari Bank BCA melalui Bank Mandiri lalu BNI, "
                    "dan diminta lapor ke OJK 157."
                ),
                "langkah_penanganan": [],
            }
        )

    monkeypatch.setattr(AIService, "_call_openrouter", fake_call)
    form = dict(
        FINANCIAL_FORM,
        bank_korban="BCA",
        nama_institusi_penipu="BRI",
        kronologi_user="Transfer ke rekening penipu.",
    )
    response = client.post(
        "/api/v1/emergency/financial",
        data=form,
        files={"bukti_transfer": ("bukti.png", make_png(), "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["official_contact"]["name"] == "Bank BCA (Bank Central Asia)"
    assert [c["name"] for c in body["official_contacts"]] == [
        "Bank BCA (Bank Central Asia)",
        "Bank BRI (Bank Rakyat Indonesia)",
        "Bank Mandiri",
    ]


def test_data_breach_multi_bank_form_and_image_excludes_ojk(client, monkeypatch):
    import json
    from app.services.ai_service import AIService

    async def fake_call(self, messages):
        return json.dumps(
            {
                "ai_kronologi": (
                    "Pelaku mengirim pesan dari BCA Official dan menyebut OJK 157."
                ),
                "langkah_penanganan": [],
            }
        )

    monkeypatch.setattr(AIService, "_call_openrouter", fake_call)
    form = dict(
        BREACH_FORM,
        jenis_data="Akun perbankan / finansial",
        kronologi_user="Saya dihubungi penipu yang mengaku dari BRI.",
    )
    response = client.post(
        "/api/v1/emergency/data-breach",
        data=form,
        files={"bukti_percakapan": ("bukti.png", make_png(), "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["official_contact"]["name"] == "Bank BRI (Bank Rakyat Indonesia)"
    assert [c["name"] for c in body["official_contacts"]] == [
        "Bank BRI (Bank Rakyat Indonesia)",
        "Bank BCA (Bank Central Asia)",
    ]


def test_analyze_text_with_image_multi_bank(client, monkeypatch):
    import json
    from app.services.ai_service import AIService

    async def fake_call(self, messages):
        return json.dumps(
            {
                "risk_score": 90,
                "risk_category": "Sangat Tinggi",
                "scam_type": "Phishing",
                "reasons": [
                    "Screenshot menampilkan logo Bank Mandiri dan rujukan OJK 157."
                ],
                "recommendations": ["Hubungi bank resmi."],
            }
        )

    monkeypatch.setattr(AIService, "_call_openrouter", fake_call)
    response = client.post(
        "/api/v1/analyze/text",
        data={"text_content": "Saya ditipu pelaku mengaku CS BCA."},
        files={"image": ("bukti.png", make_png(), "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["official_contact"]["name"] == "Bank BCA (Bank Central Asia)"
    assert [c["name"] for c in body["official_contacts"]] == [
        "Bank BCA (Bank Central Asia)",
        "Bank Mandiri",
    ]


def test_data_breach_accepts_long_json_tindakan_pelaku(client, fake_openrouter):
    import json

    long_actions = json.dumps(
        ["link", "data-pribadi", "otp", "menyamar", "x" * 300]
    )
    form = dict(BREACH_FORM, tindakan_pelaku=long_actions)
    response = client.post(
        "/api/v1/emergency/data-breach",
        data=form,
        files={"bukti_percakapan": ("bukti.png", make_png(), "image/png")},
    )
    assert response.status_code == 200


def test_routes_return_json_500_when_llm_violates_schema(client, monkeypatch):
    import json
    from app.services.ai_service import AIService

    async def fake_bad_analysis(self, messages):
        return json.dumps(
            {
                "risk_score": 150,
                "risk_category": "Tinggi",
                "reasons": "bukan-list",
                "recommendations": ["y"],
            }
        )

    monkeypatch.setattr(AIService, "_call_openrouter", fake_bad_analysis)
    res_text = client.post(
        "/api/v1/analyze/text",
        data={"text_content": "Cek pesan mencurigakan."},
    )
    assert res_text.status_code == 500
    assert res_text.json() == {"detail": "Format output AI cacat."}

    async def fake_bad_emergency(self, messages):
        return json.dumps(
            {
                "ai_kronologi": None,
                "langkah_penanganan": ["bukan-object"],
            }
        )

    monkeypatch.setattr(AIService, "_call_openrouter", fake_bad_emergency)
    res_emg = client.post(
        "/api/v1/emergency/financial",
        data=FINANCIAL_FORM,
        files={"bukti_transfer": ("bukti.png", make_png(), "image/png")},
    )
    assert res_emg.status_code == 500
    assert res_emg.json() == {"detail": "Format output AI cacat."}
