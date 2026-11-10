# API Contract — CegahScam AI Service

Kontrak implementasi untuk microservice AI CegahScam. Dokumen ini adalah acuan teknis untuk backend utama aplikasi web. Teknologi backend utama dan frontend belum ditetapkan; kontrak ini hanya bergantung pada HTTP REST.

| Item | Nilai |
|---|---|
| Versi service | `1.0.0` |
| Base URL (lokal) | `http://127.0.0.1:8000` |
| Prefix API | `/api/v1` |
| Format | JSON UTF-8 (`application/json`) |
| OpenAPI/Swagger | `/docs`, `/redoc`, `/openapi.json` |

## 1. Konvensi umum

- Semua endpoint bisnis menerima `POST`. Hanya `GET /health` yang tersedia di luar prefix.
- Respons sukses selalu `application/json`; tidak ada streaming.
- Service ini **tidak** membuat PDF, tidak menyimpan riwayat, dan tidak menulis ke database. Itu tanggung jawab backend utama aplikasi web.
- **Autentikasi:** semua endpoint di bawah `/api/v1` wajib mengirim header `X-API-Token: <CEGAHSCAM_API_TOKEN>`. Token dicek sebelum body dibaca. Tanpa/salah token → `401`; token server belum dikonfigurasi → `500` (fail closed). `GET /health`, `/docs`, `/redoc`, dan `/openapi.json` tetap terbuka tanpa token.
- **CORS:** `CORSMiddleware` aktif secara bawaan (`CORS_ORIGINS=*` di `.env`, dapat dibatasi ke domain tertentu). Untuk keamanan token pada produksi, pemanggilan melalui backend utama aplikasi web tetap paling direkomendasikan.
- Field opsional yang tidak diisi dikembalikan sebagai `null` (mis. `scam_type`, `official_contact`, `official_contact.whatsapp`).

### 1.1 Bentuk error

Error dari `HTTPException`:

```json
{ "detail": "Pesan error dalam Bahasa Indonesia." }
```

Error validasi (422) mengikuti format Pydantic:

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "text_content"],
      "msg": "Field required",
      "input": null
    }
  ]
}
```

### 1.2 Batas input

| Item | Batas |
|---|---|
| `text_content` | 1–10.000 karakter |
| `platform` | 1–50 karakter |
| `kronologi_user` | ≤ 5.000 karakter |
| Gambar | `image/jpeg`, `image/jpg`, `image/png`, `image/webp`; ≤ 15 MB |
| `phone_number` | `08…`, `628…`, atau `+628…`; total 8–15 digit |

## 2. Skema respons

### 2.1 `OfficialContact`

| Field | Tipe | Wajib | Keterangan |
|---|---|---|---|
| `name` | string | ya | Nama bank/institusi dari whitelist |
| `phone` | string | ya | Nomor call center (selalu string) |
| `whatsapp` | string \| null | tidak | Umumnya `null` saat ini |

### 2.2 `AnalysisResponse`

Dipakai oleh `/analyze/text`, `/analyze/image`, `/analyze/phone`.

| Field | Tipe | Wajib | Keterangan |
|---|---|---|---|
| `risk_score` | integer | ya | 0–100 |
| `risk_category` | string | ya | `Rendah`, `Sedang`, `Tinggi`, `Sangat Tinggi`, dst. |
| `scam_type` | string \| null | tidak | Label dinormalisasi ke Bahasa Indonesia |
| `reasons` | string[] | ya | Alasan berbasis bukti |
| `recommendations` | string[] | ya | Langkah pencegahan |
| `official_contact` | `OfficialContact` \| null | tidak | Lihat §4 |

### 2.3 `EmergencyResponse`

Dipakai oleh `/emergency/financial` dan `/emergency/data-breach`.

| Field | Tipe | Wajib | Keterangan |
|---|---|---|---|
| `ai_kronologi` | string | ya | Format I/II/III, dipisah `\n` |
| `langkah_penanganan` | array `{title, description}` | ya | Minimal satu langkah |
| `official_contact` | `OfficialContact` \| null | tidak | Lihat §4 |

## 3. Endpoint

> Contoh request/response di bagian ini bersifat **ilustratif dan diringkas** — array `reasons`/`recommendations` serta `ai_kronologi` dipotong agar ringkas. Respons HTTP nyata apa adanya (verbatim, termasuk latensi) ada di [`README.md`](README.md).

### 3.1 `POST /api/v1/analyze/text`

Menganalisis teks indikasi penipuan, opsional dengan satu gambar bukti.

`Content-Type: multipart/form-data`

| Field | Tipe | Wajib | Batasan |
|---|---|---|---|
| `text_content` | string | ya | 1–10.000 karakter |
| `image` | file | tidak | JPG/PNG/WEBP, ≤ 15 MB |

```bash
curl -X POST http://127.0.0.1:8000/api/v1/analyze/text \
  -H "X-API-Token: <CEGAHSCAM_API_TOKEN>" \
  -F "text_content=Halo, ini BCA. Kirim OTP ke http://bca-verifikasi.xyz" \
  -F "image=@bukti.png;type=image/png"
```

Respons `200`:

```json
{
  "risk_score": 90,
  "risk_category": "Sangat Tinggi",
  "scam_type": "Phishing / Smishing / Vishing",
  "reasons": ["Pesan meminta OTP melalui tautan tidak resmi."],
  "recommendations": ["Jangan klik tautan dan jangan bagikan OTP."],
  "official_contact": {
    "name": "Bank BCA (Bank Central Asia)",
    "phone": "1500888",
    "whatsapp": null
  }
}
```

Error: `400` MIME tidak didukung, `408` timeout AI, `413` gambar > 15 MB, `422` validasi, `500` key/JSON AI, `502` upstream AI.

### 3.2 `POST /api/v1/analyze/image`

Menganalisis satu tangkapan layar.

| Field | Tipe | Wajib | Batasan |
|---|---|---|---|
| `platform` | string | ya | 1–50 karakter |
| `image` | file | ya | JPG/PNG/WEBP, ≤ 15 MB |

```bash
curl -X POST http://127.0.0.1:8000/api/v1/analyze/image \
  -H "X-API-Token: <CEGAHSCAM_API_TOKEN>" \
  -F "platform=WhatsApp" -F "image=@bukti.png;type=image/png"
```

Respons `200`: bentuk `AnalysisResponse`. Karena tidak ada OCR di server, `official_contact` selalu `null`.

### 3.3 `POST /api/v1/analyze/phone`

Menggabungkan data GetContact dengan analisis LLM.

`Content-Type: application/json`

| Field | Tipe | Wajib | Batasan |
|---|---|---|---|
| `phone_number` | string | ya | Format Indonesia, 8–15 digit |

```bash
curl -X POST http://127.0.0.1:8000/api/v1/analyze/phone \
  -H "Content-Type: application/json" \
  -H "X-API-Token: <CEGAHSCAM_API_TOKEN>" \
  -d '{"phone_number":"081234567890"}'
```

Respons `200`:

```json
{
  "risk_score": 85,
  "risk_category": "Tinggi",
  "scam_type": "Penipuan Kurir / Marketplace",
  "reasons": ["Profil GetContact menandai nomor ini sebagai penipuan."],
  "recommendations": ["Blokir nomor dan jangan bertransaksi."],
  "official_contact": null
}
```

Error: `422` format nomor, `500` kredensial GetContact hilang/rusak, `502` sesi GetContact kedaluwarsa/upstream gagal, `408` timeout, `500` JSON AI cacat.

### 3.4 `POST /api/v1/emergency/financial`

Menyusun kronologi dan langkah penanganan kasus penipuan finansial.

| Field | Tipe | Wajib | Batasan |
|---|---|---|---|
| `bank_korban` | string | ya | 1–100 |
| `platform_kejadian` | string | ya | 1–100 (misal `"WhatsApp"`, `"Telegram"`, `"Instagram"`) |
| `tanggal_kejadian` | string | ya | maks. 10 (`YYYY-MM-DD`, contoh: `"2026-11-03"`) |
| `tujuan_transaksi` | string | ya | 1–200 |
| `nomor_rekening_penipu` | string | ya | 1–50 |
| `nominal_kerugian` | number | ya | ≥ 0 |
| `nama_institusi_penipu` | string | tidak | ≤ 200 |
| `nama_pemilik_penipu` | string | tidak | ≤ 200 |
| `kronologi_user` | string | tidak | ≤ 5.000 |
| `bukti_transfer` | file | ya | JPG/PNG/WEBP, ≤ 15 MB |

```bash
curl -X POST http://127.0.0.1:8000/api/v1/emergency/financial \
  -H "X-API-Token: <CEGAHSCAM_API_TOKEN>" \
  -F "bank_korban=BCA" -F "platform_kejadian=WhatsApp" \
  -F "tanggal_kejadian=2026-10-27" -F "tujuan_transaksi=Pembelian barang" \
  -F "nomor_rekening_penipu=1234567890" -F "nominal_kerugian=1500000" \
  -F "bukti_transfer=@bukti.png;type=image/png"
```

Respons `200`:

```json
{
  "ai_kronologi": "I. DATA PELAPOR (KORBAN)\n- Platform / Kanal Kejadian: WhatsApp\n- Waktu Kejadian: 2026-10-27\n\nII. DATA TERLAPOR (PELAKU)\n- Nama Institusi / Pengakuan Pelaku: Tidak disebutkan\n- Rekening / Kontak Pelaku: 1234567890\n\nIII. RINCIAN KRONOLOGI KEJADIAN\n1. Korban mentransfer dana.\n2. Barang tidak dikirim.",
  "langkah_penanganan": [
    { "title": "Hubungi Call Center Bank", "description": "Minta pembekuan transaksi." }
  ],
  "official_contact": {
    "name": "Bank BCA (Bank Central Asia)",
    "phone": "1500888",
    "whatsapp": null
  }
}
```

`official_contact` hanya diisi dari `bank_korban`; bank di luar whitelist → `null`.

### 3.5 `POST /api/v1/emergency/data-breach`

| Field | Tipe | Wajib | Batasan |
|---|---|---|---|
| `jenis_data` | string | ya | 1–200 |
| `tanggal_kejadian` | string | ya | maks. 10 (`YYYY-MM-DD`, contoh: `"2026-11-03"`) |
| `platform_kejadian` | string | ya | 1–100 (misal `"Instagram"`, `"Telegram"`, `"Facebook"`) |
| `tindakan_pelaku` | string | ya | 1–200 |
| `status_akses` | string | ya | 1–100 |
| `kronologi_user` | string | tidak | ≤ 5.000 |
| `bukti_percakapan` | file | ya | JPG/PNG/WEBP, ≤ 15 MB |

```bash
curl -X POST http://127.0.0.1:8000/api/v1/emergency/data-breach \
  -H "X-API-Token: <CEGAHSCAM_API_TOKEN>" \
  -F "jenis_data=Data pribadi (nama, email)" -F "tanggal_kejadian=2026-10-27" \
  -F "platform_kejadian=Instagram" -F "tindakan_pelaku=Meminta OTP" \
  -F "status_akses=Masih bisa diakses" \
  -F "bukti_percakapan=@bukti.png;type=image/png"
```

Respons `200`: bentuk `EmergencyResponse`. `official_contact` diisi dari pencocokan nama bank pada `kronologi_user`/`tindakan_pelaku`/`jenis_data`, atau fallback ke `Otoritas Jasa Keuangan (OJK)` (`157`) bila `jenis_data` berkaitan dengan akun perbankan/finansial atau kartu kredit/debit (selain itu `null`).

### 3.6 `GET /health`

```json
{ "status": "ok", "message": "CegahScam AI Service is healthy", "mock_mode": false }
```

Dipakai untuk memantau status layanan dan mengetahui apakah server sedang berjalan dalam Mode Mock (`"mock_mode": true`) atau Mode Live (`"mock_mode": false`). Tidak mengecek dependensi eksternal.

## 4. Aturan `official_contact`

- Field opsional, tetapi **wajib terisi** bila bank terdeteksi ada di `app/data/Bank_Call_Senter_Final.json` (100 entri, bentuk `{name, call, aliases?}`).
- Sumber bukti: `text_content` (text), `bank_korban` (financial), `kronologi_user`/`tindakan_pelaku`/`jenis_data` dengan fallback OJK `157` untuk kategori perbankan/kartu (data-breach), serta profil/tag GetContact (phone). Endpoint image tidak punya bukti deterministik → `null`.
- Nilai `official_contact` dari LLM selalu ditimpa; bank di luar whitelist menghasilkan `null`.
- Jika beberapa bank terdeteksi, dipilih yang paling cocok: alias sama persis → alias paling spesifik → alias terpanjang → kemunculan paling awal → nama terpendek.
- `phone` selalu dikembalikan sebagai string.

Contoh:

| Input | Hasil |
|---|---|
| `bank mandiri` | Bank Mandiri |
| `mandiri taspen` | Bank Mandiri Taspen |
| `bca` | Bank BCA (Bank Central Asia) |
| `bca syariah` | Bank BCA Syariah |
| `bca dan bri` | Bank BCA (kemunculan paling awal) |
| `bank gaib` | `null` |

## 5. Ringkasan status

| Status | Arti |
|---|---|
| 200 | Sukses |
| 400 | MIME gambar tidak didukung |
| 408 | Timeout OpenRouter/GetContact |
| 413 | Gambar > 15 MB |
| 401 | Header `X-API-Token` tidak ada atau salah |
| 422 | Validasi field gagal |
| 500 | API key kosong, `CEGAHSCAM_API_TOKEN` belum diatur, kredensial hilang/rusak, output AI bukan JSON |
| 502 | Upstream AI menolak/limit, sesi GetContact kedaluwarsa |

## 6. Catatan integrasi klien

- **Panduan implementasi tim web:** lihat [`panduan_implementasi.md`](panduan_implementasi.md) untuk arsitektur komunikasi dengan tim web dan kajian opsi teknologi web.
- **Mode Mock (`MOCK_MODE=true`):** saat mengembangkan dan menguji integrasi di lokal, backend utama dapat menyalakan `MOCK_MODE=true` di `.env` AI Service agar seluruh endpoint mengembalikan respons simulasi sesuai skema dalam < 50 ms tanpa memerlukan `OPENROUTER_API_KEY` maupun `gtc_credentials.json` (autentikasi `X-API-Token`, validasi input, dan `official_contact` tetap aktif 100%).
- **Timeout:** siapkan timeout ≥ 90 detik pada Mode Live (`MOCK_MODE=false`). Server memakai 25 detik untuk GetContact dan 60 detik untuk AI.
- **Retry:** jangan retry otomatis pada `408`/`502`; setiap POST memanggil LLM dan mengonsumsi kuota.
- **Null handling:** perlakukan `scam_type`, `official_contact`, dan `official_contact.whatsapp` sebagai opsional.
- **Non-determinisme:** skor dan redaksi dapat berbeda antar pemanggilan meski input sama.
- **Idempotensi:** endpoint bukan idempotent; tidak ada cache atau penyimpanan hasil.
- **Privasi:** gambar dan teks dikirim ke OpenRouter (pihak ketiga) untuk analisis pada Mode Live.
