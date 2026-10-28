# CegahScam AI Service

Microservice FastAPI yang menganalisis indikasi penipuan (teks, gambar, nomor telepon) dan menyusun draf penanganan darurat. Service ini **hanya mengembalikan JSON**; pembuatan PDF dan penyimpanan riwayat dilakukan backend Node.js.

## Quick start

```powershell
git clone <url-repo> cegahscam-ai
cd cegahscam-ai
python -m venv venv
venv\Scripts\pip.exe install -r requirements.txt
copy .env.example .env      # lalu isi OPENROUTER_API_KEY
venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Swagger: http://127.0.0.1:8000/docs · Health: http://127.0.0.1:8000/health

## Prasyarat

| Kebutuhan | Versi | Catatan |
|---|---|---|
| Python | 3.12 (minimum 3.10) | kode memakai sintaks `Path \| str` |
| Git | terbaru | untuk clone |
| Docker Desktop | opsional | hanya jika ingin menjalankan via container |
| Akses internet | — | service memanggil OpenRouter |

## Setup

Jalankan dari **root repo** — path `.env` dan `app/data/*.json` relatif terhadap CWD.

```powershell
python -m venv venv
venv\Scripts\pip.exe install -r requirements.txt
copy .env.example .env
```

Lalu:

1. Isi `OPENROUTER_API_KEY` di `.env` (ambil dari OpenRouter, jangan di-commit).
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
| `OPENROUTER_API_KEY` | `.env` (contoh di `.env.example`) | Wajib; kalau kosong semua endpoint analisis → 500 |
| `LOG_LEVEL` | `.env` | `DEBUG`/`INFO`/`WARNING`/`ERROR`, default `INFO` |
| Kredensial GetContact | `app/data/gtc_credentials.json` | Hanya untuk `/analyze/phone`; tidak bisa di-override env |
| Whitelist call center | `app/data/Bank_Call_Senter_Final.json` | 100 entri `{name, call, aliases?}` |

Model dan URL OpenRouter di-hardcode di `app/services/ai_service.py`, bukan lewat env.

## Endpoint

| Method | Path | Content-Type |
|---|---|---|
| POST | `/api/v1/analyze/text` | `multipart/form-data` (`text_content`, `image` opsional) |
| POST | `/api/v1/analyze/image` | `multipart/form-data` (`platform`, `image`) |
| POST | `/api/v1/analyze/phone` | `application/json` (`phone_number`) |
| POST | `/api/v1/emergency/financial` | `multipart/form-data` |
| POST | `/api/v1/emergency/data-breach` | `multipart/form-data` |
| GET | `/health` | — |

Kontrak implementasi lengkap (field, batasan, contoh request, kontrak error): [`api-contract.md`](api-contract.md). Bukti pengujian input/output nyata: [`PENGUJIAN.md`](PENGUJIAN.md).

## Kebijakan `official_contact`

- Field ini **opsional**, tetapi wajib terisi bila bank yang terdeteksi ada di whitelist `Bank_Call_Senter_Final.json`.
- Sumber bukti: `text_content` (analisis teks), `bank_korban` (emergency finansial), profil/tag GetContact (analisis nomor). Analisis gambar murni tidak punya bukti deterministik → `null`.
- Bila beberapa bank terdeteksi, dipilih yang paling cocok (alias paling spesifik, lalu kemunculan paling awal): `bank mandiri` → **Bank Mandiri**, `mandiri taspen` → **Bank Mandiri Taspen**.
- Nilai `official_contact` dari LLM selalu ditimpa; bank di luar whitelist menghasilkan `null`.

## Docker

```powershell
docker build -t cegahscam-ai:latest .
docker run -d --name cegahscam-ai -p 8000:8000 `
  --env-file .env `
  -v "${PWD}\app\data\gtc_credentials.json:/app/app/data/gtc_credentials.json:ro" `
  cegahscam-ai:latest
```

Image memakai `python:3.12-slim`, `WORKDIR /app`, dan punya `HEALTHCHECK` ke `/health`. `.env` dan kredensial GetContact tidak masuk image. Env direkam saat container **dibuat**, jadi setelah mengubah `.env` container harus dibuat ulang (`docker rm -f cegahscam-ai` lalu `docker run` lagi), bukan sekadar `restart`.

## Test

```powershell
venv\Scripts\pip.exe install -r requirements-dev.txt
venv\Scripts\python.exe -m pytest
```

Harapan: **42 passed**. Semua akses jaringan di-mock (`OpenRouter` dan `GetContact`), jadi test bisa dijalankan offline.

## Struktur proyek

```
app/
  main.py            # entrypoint FastAPI + logging
  api/routes.py      # 5 endpoint bisnis + dependency factory
  core/
    config.py        # Settings (.env)
    data_loader.py   # whitelist bank + ranking alias
    normalization.py # label LLM -> Bahasa Indonesia
    prompts.py       # prompt Vision/Reasoning/Emergency
  schemas/payload.py # response model + validasi nomor telepon
  services/
    ai_service.py    # OpenRouter (threadpool), validasi gambar
    phone_service.py # GetContact (token statis) + enrichment
  data/              # JSON bank, knowledge base, kredensial (lokal)
tests/               # 42 test, tanpa jaringan
```

## Pemetaan error

| Status | Arti |
|---|---|
| 400 | File bukan gambar yang didukung (JPG/PNG/WEBP) |
| 408 | Timeout ke OpenRouter / GetContact |
| 413 | Gambar > 15 MB |
| 422 | Validasi input gagal (field wajib, panjang, format nomor) |
| 500 | API key kosong, kredensial hilang/rusak, output AI bukan JSON |
| 502 | OpenRouter menolak/limit, sesi GetContact kedaluwarsa, gangguan upstream |

## Troubleshooting

| Gejala | Sebab | Solusi |
|---|---|---|
| `500 Konfigurasi API AI tidak valid.` | `OPENROUTER_API_KEY` kosong | isi `.env`, restart proses; untuk Docker, buat ulang container |
| `500 Konfigurasi GetContact ...` | `gtc_credentials.json` tidak ada/tidak lengkap | minta file ke maintainer, taruh di `app/data/` |
| `502 Sesi GetContact tidak valid atau kedaluwarsa.` | token sesi kedaluwarsa | perbarui file kredensial (dibaca per request, tidak perlu restart) |
| `ModuleNotFoundError: app` | CWD bukan root repo | `cd` ke root lalu jalankan ulang |
| `.env` tidak terbaca / data JSON gagal dimuat | CWD bukan root repo | sama seperti di atas |
| `Address already in use` di port 8000 | ada proses/container lain | `docker stop cegahscam-ai` atau hentikan proses lama |
| Perubahan `.env` tidak berefek di Docker | env dibekukan saat create | `docker rm -f cegahscam-ai` lalu `docker run` ulang |
| `/docs` kosong di browser | aset Swagger dari CDN diblokir | gunakan `/redoc`, atau izinkan akses jsdelivr |

## Catatan operasional

- Kredensial GetContact adalah snapshot sesi; tidak ada login/refresh otomatis. Jika muncul 502, perbarui `app/data/gtc_credentials.json` lalu buat ulang container (khusus Docker).
- Pemanggilan HTTP keluar berjalan di threadpool sehingga event loop tidak tersandera, tetapi service tetap satu proses — latensi 4–24 detik per request adalah normal.
- Service stateless: tidak menyimpan riwayat, tidak menulis database, tidak membuat PDF.
