# CegahScam AI Service

Microservice FastAPI yang menganalisis indikasi penipuan (teks, gambar, nomor telepon) dan menyusun draf penanganan darurat. Service ini **hanya mengembalikan JSON**; pembuatan PDF dan penyimpanan riwayat menjadi tanggung jawab backend utama aplikasi web.

## Setup

```powershell
git clone <url-repo> ai-service
cd ai service
python -m venv venv
venv\Scripts\pip.exe install -r requirements.txt
copy .env.example .env      # isi OPENROUTER_API_KEY dan CEGAHSCAM_API_TOKEN
```

Lalu pilih salah satu mode di `.env`:

### Opsi A: Mode Mock (Untuk Integrasi Tim Web — Tanpa Kuota & Tanpa Kredensial Eksternal)
Cocok untuk menguji integrasi backend utama dan frontend tanpa memerlukan `OPENROUTER_API_KEY` maupun `gtc_credentials.json`:
```env
OPENROUTER_API_KEY=
CEGAHSCAM_API_TOKEN=token-rahasia-lokal-12345
LOG_LEVEL=INFO
MOCK_MODE=true
```

### Opsi B: Mode Live (Koneksi Penuh ke OpenRouter & GetContact)
1. Set `MOCK_MODE=false` di `.env`, lalu isi `OPENROUTER_API_KEY` dan `CEGAHSCAM_API_TOKEN`.
2. Minta `app/data/gtc_credentials.json` ke maintainer lewat jalur aman. File ini **tidak** ada di repo karena berisi token sesi GetContact; tanpa file ini semua endpoint selain `/analyze/phone` tetap berjalan normal.

## Menjalankan

```powershell
venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

- Swagger: http://127.0.0.1:8000/docs
- Redoc: http://127.0.0.1:8000/redoc
- Health: http://127.0.0.1:8000/health

## Konfigurasi

| Kebutuhan | Lokasi | Catatan |
|---|---|---|
| `OPENROUTER_API_KEY` | `.env` (contoh di `.env.example`) | Wajib pada Mode Live (`MOCK_MODE=false`); kalau kosong semua endpoint analisis → 500 |
| `LOG_LEVEL` | `.env` | `DEBUG`/`INFO`/`WARNING`/`ERROR`, default `INFO` |
| `CEGAHSCAM_API_TOKEN` | `.env` (contoh di `.env.example`) | Wajib; token rahasia antar-service, dikirim backend utama aplikasi web lewat header `X-API-Token`. Di Swagger (`/docs`), masukkan via tombol hijau **Authorize**. Kosong → semua `/api/v1` ditolak (500). `/health` tetap terbuka |
| `MOCK_MODE` | `.env` (contoh di `.env.example`) | Opsional (`true`/`false`, default `false`). Bila `true`, server mengembalikan respons simulasi sesuai kontrak (< 50 ms) tanpa memanggil OpenRouter/GetContact dan tanpa memerlukan `OPENROUTER_API_KEY` maupun `gtc_credentials.json` |
| `CORS_ORIGINS` | `.env` (contoh di `.env.example`) | Opsional (default `*`). Daftar origin CORS dipisahkan koma agar endpoint dapat dipanggil dari frontend browser maupun backend utama aplikasi web |
| Kredensial GetContact | `app/data/gtc_credentials.json` | Hanya untuk `/analyze/phone` pada Mode Live; tidak bisa di-override env |
| Whitelist call center | `app/data/Bank_Call_Senter_Final.json` | 100 entri `{name, call, aliases?}` |
| Knowledge base scam | `app/data/knowledge_base_cegahscam.json` | Basis pengetahuan pola kata kunci & SOP mitigasi (aktif otomatis bila cocok $\ge 3$ kata kunci) |

Model dan URL OpenRouter di-hardcode di `app/services/ai_service.py`, bukan lewat env.

## Endpoint

Semua endpoint bisnis di bawah `/api/v1` wajib menyertakan header `X-API-Token`. Hanya `GET /health` yang terbuka tanpa autentikasi.

| Method | Path | Content-Type | Autentikasi |
|---|---|---|---|
| POST | `/api/v1/analyze/text` | `multipart/form-data` (`text_content`, `image` opsional) | `X-API-Token` |
| POST | `/api/v1/analyze/image` | `multipart/form-data` (`platform`, `image`) | `X-API-Token` |
| POST | `/api/v1/analyze/phone` | `application/json` (`phone_number`) | `X-API-Token` |
| POST | `/api/v1/emergency/financial` | `multipart/form-data` | `X-API-Token` |
| POST | `/api/v1/emergency/data-breach` | `multipart/form-data` | `X-API-Token` |
| GET | `/health` | — | Bebas |

Kontrak implementasi lengkap (field, batasan, contoh request, kontrak error): [`api-contract.md`](api-contract.md). Panduan implementasi untuk tim web & opsi teknologi: [`panduan_implementasi.md`](panduan_implementasi.md). Bukti pengujian & evaluasi metrik Fase 2: [`PENGUJIAN.md`](PENGUJIAN.md).

## Kebijakan `official_contact`

- Field ini **opsional**, tetapi wajib terisi bila bank yang terdeteksi ada di whitelist `Bank_Call_Senter_Final.json`.
- Sumber bukti: `text_content` (analisis teks), `bank_korban` (emergency finansial), profil/tag GetContact (analisis nomor). Analisis gambar murni tidak punya bukti deterministik → `null`.
- Bila beberapa bank terdeteksi, dipilih yang paling cocok (alias paling spesifik, lalu kemunculan paling awal): `bank mandiri` → **Bank Mandiri**, `mandiri taspen` → **Bank Mandiri Taspen**.
- Nilai `official_contact` dari LLM selalu ditimpa; bank di luar whitelist menghasilkan `null`.

## Test

```powershell
venv\Scripts\pip.exe install -r requirements-dev.txt
venv\Scripts\python.exe -m pytest
```

Harapan: **65 passed**. Semua akses jaringan di-mock (`OpenRouter` dan `GetContact`), jadi test bisa dijalankan offline.

## Struktur proyek

```
app/
  main.py            # entrypoint FastAPI + logging + CORSMiddleware
  api/routes.py      # 5 endpoint bisnis + dependency factory
  core/
    config.py        # Settings (.env, termasuk MOCK_MODE & CORS_ORIGINS)
    data_loader.py   # whitelist bank + indeks knowledge base (min_keywords=3)
    normalization.py # label LLM -> Bahasa Indonesia
    prompts.py       # prompt Vision/Reasoning/Emergency + guardrails
    security.py      # middleware & schema auth X-API-Token
  schemas/payload.py # response model + validasi nomor telepon
  services/
    ai_service.py    # OpenRouter (threadpool), KB injection, chunked streaming gambar, MOCK_MODE
    phone_service.py # GetContact (threadpool) + enrichment + MOCK_MODE
  data/              # JSON bank, knowledge base, kredensial (lokal)
tests/               # 65 test, tanpa jaringan (unit, route, auth, CORS, log, stream, KB, mock mode)
eval/                # skrip evaluasi Fase 2 (evaluate_phase2.py); eval/data/ di-ignore Git
```

## Pemetaan error

| Status | Arti |
|---|---|
| 400 | File bukan gambar yang didukung (JPG/PNG/WEBP) |
| 401 | Header `X-API-Token` tidak ada atau salah |
| 408 | Timeout ke OpenRouter / GetContact |
| 413 | Gambar > 15 MB |
| 422 | Validasi input gagal (field wajib, panjang, format nomor) |
| 500 | API key kosong, `CEGAHSCAM_API_TOKEN` belum diatur, kredensial hilang/rusak, output AI bukan JSON |
| 502 | OpenRouter menolak/limit, sesi GetContact kedaluwarsa, gangguan upstream |

## Troubleshooting

| Gejala | Sebab | Solusi |
|---|---|---|
| `401 Token API tidak valid atau tidak ada.` | Header `X-API-Token` tidak disertakan atau salah | Sertakan header `X-API-Token: <token>` pada request, atau klik tombol **Authorize** di `/docs` |
| `500 Konfigurasi token API belum diatur.` | `CEGAHSCAM_API_TOKEN` di `.env` kosong | Isi `CEGAHSCAM_API_TOKEN` di `.env` dengan token rahasia acak, lalu restart server |
| `500 Konfigurasi API AI tidak valid.` | `OPENROUTER_API_KEY` kosong | isi `.env`, lalu restart proses server |
| `500 Konfigurasi GetContact ...` | `gtc_credentials.json` tidak ada/tidak lengkap | minta file ke maintainer, taruh di `app/data/` |
| `502 Sesi GetContact tidak valid atau kedaluwarsa.` | token sesi kedaluwarsa | perbarui file kredensial (dibaca per request, tidak perlu restart) |
| `ModuleNotFoundError: app` | CWD bukan root repo | `cd` ke root lalu jalankan ulang |
| `.env` tidak terbaca / data JSON gagal dimuat | CWD bukan root repo | sama seperti di atas |
| `Address already in use` di port 8000 | ada proses lain yang memakai port 8000 | hentikan proses lama atau gunakan `--port` lain |
| `/docs` kosong di browser | aset Swagger dari CDN diblokir | gunakan `/redoc`, atau izinkan akses jsdelivr |

## Catatan operasional

- Kredensial GetContact adalah snapshot sesi; tidak ada login/refresh otomatis. Jika muncul 502, perbarui `app/data/gtc_credentials.json` (perubahan langsung aktif tanpa restart).
- Pemanggilan HTTP keluar berjalan di threadpool sehingga event loop tidak tersandera, tetapi service tetap satu proses — latensi 4–24 detik per request adalah normal.
- Service stateless: tidak menyimpan riwayat, tidak menulis database, tidak membuat PDF.
