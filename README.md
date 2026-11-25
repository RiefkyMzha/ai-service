# CegahScam AI Service

Microservice FastAPI yang menganalisis indikasi penipuan (teks, gambar, nomor telepon) dan menyusun draf penanganan darurat. Service ini **hanya mengembalikan JSON**; pembuatan PDF dan penyimpanan riwayat menjadi tanggung jawab backend utama aplikasi web. Baca [api-contract.md](api-contract.md) untuk informasi Implementasi.

## Setup

```powershell
git clone <url-repo> ai-service
cd ai-service
python -m venv venv
venv\Scripts\pip.exe install -r requirements.txt
copy .env.example .env      # isi OPENROUTER_API_KEY dan CEGAHSCAM_API_TOKEN
```

Lalu pilih salah satu mode di `.env`:

### Opsi A: Mode Mock (Untuk Integrasi Tim Web — Tanpa Kuota & Tanpa Kredensial Eksternal)
Cocok untuk menguji integrasi backend utama dan frontend tanpa memerlukan `OPENROUTER_API_KEY` maupun `gtc_credentials.json`:
```env
OPENROUTER_API_KEY=
OPENROUTER_MODEL=
CEGAHSCAM_API_TOKEN=token-rahasia-lokal-12345
LOG_LEVEL=INFO
MOCK_MODE=true
```

### Opsi B: Mode Live (Koneksi Penuh ke OpenRouter & GetContact)
1. Set `MOCK_MODE=false` di `.env`, lalu isi `OPENROUTER_API_KEY` dan `CEGAHSCAM_API_TOKEN`.
2. Minta `app/data/gtc_credentials.json` ke maintainer lewat jalur aman. File ini **tidak** ada di repo karena berisi token sesi GetContact; tanpa file ini semua endpoint selain `/analyze/phone` tetap berjalan normal.

## Run

```powershell
venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

- Swagger: http://127.0.0.1:8000/docs
- Redoc: http://127.0.0.1:8000/redoc
- Health: http://127.0.0.1:8000/health



## Endpoint

Semua endpoint bisnis di bawah `/api/v1` wajib menyertakan header `X-API-Token`. Hanya `GET /health` yang terbuka tanpa autentikasi.

| Method | Path | Fungsi Endpoint |
|---|---|---|
| `POST` | `/api/v1/analyze/text` | Menganalisis indikasi penipuan pada pesan teks (mendukung lampiran gambar bukti opsional) |
| `POST` | `/api/v1/analyze/image` | Mengekstraksi dan menganalisis indikasi penipuan dari tangkapan layar (*screenshot*) bukti |
| `POST` | `/api/v1/analyze/phone` | Memeriksa reputasi dan skor risiko nomor telepon target (integrasi GetContact + LLM) |
| `POST` | `/api/v1/emergency/financial` | Menyusun draf kronologi dan langkah mitigasi darurat untuk korban penipuan finansial |
| `POST` | `/api/v1/emergency/data-breach` | Menyusun draf kronologi dan langkah pengamanan darurat untuk korban kebocoran data pribadi |
| `GET` | `/health` | Memantau ketersediaan layanan (*healthcheck*) dan status operasional (`mock_mode`) |



## Test

```powershell
venv\Scripts\pip.exe install -r requirements-dev.txt
venv\Scripts\python.exe -m pytest
```



## Struktur proyek

```
app/
├── main.py                  # Entry point FastAPI, logging, dan CORS middleware
│
├── api/
│   └── routes.py            # 5 business endpoints dan dependency factory
│
├── core/
│   ├── config.py            # Application settings (.env, OpenRouter, MOCK_MODE, CORS)
│   ├── data_loader.py       # Whitelist bank dan indeks knowledge base (min_keywords=3)
│   ├── normalization.py     # Normalisasi label LLM ke Bahasa Indonesia
│   ├── prompts.py           # Prompt Vision, Reasoning, Emergency, dan guardrails
│   └── security.py          # Middleware keamanan dan validasi X-API-Token
│
├── schemas/
│   └── payload.py           # Response model dan validasi nomor telepon
│
├── services/
│   ├── ai_service.py        # OpenRouter, threadpool, KB injection, chunked image streaming, MOCK_MODE
│   └── phone_service.py     # GetContact, threadpool, cache in-memory, enrichment, MOCK_MODE
│
└── data/
    ├── Bank_Call_Center.json          # Data JSON whitelist bank & OJK
    ├── knowledge_base_cegahscam.json  # Data knowledge base pola penipuan
    └── gtc_credentials.json           # Kredensial lokal GetContact (git-ignored)
│
└── tests/                   # 140 automated tests (tanpa akses jaringan)
```

## Pemetaan error

| Status | Arti |
|---|---|
| 400 | File bukan gambar yang didukung (JPG/PNG/WEBP), gambar rusak/format palsu, atau melebihi batas piksel aman |
| 401 | Header `X-API-Token` tidak ada atau salah |
| 408 | Timeout ke OpenRouter / GetContact |
| 413 | Gambar > 15 MB |
| 422 | Validasi input gagal (field wajib, panjang, format nomor) |
| 500 | API key kosong, `CEGAHSCAM_API_TOKEN` belum diatur, kredensial hilang/rusak, output AI bukan JSON |
| 502 | OpenRouter menolak/limit, sesi GetContact kedaluwarsa, gangguan upstream |

#### Untuk Pengujian Manual melalui Swagger UI (`/docs`):
1. Buka browser pada URL Swagger: `http://127.0.0.1:8000/docs`.
2. Klik tombol hijau **Authorize** di pojok kanan atas.
3. Masukkan nilai `CEGAHSCAM_API_TOKEN` Anda, lalu klik **Authorize** dan **Close**.
4. Semua pengujian via tombol *Execute* akan otomatis menyertakan header keamanan tanpa tertolak 401.

