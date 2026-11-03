# Panduan Integrasi ("How-To") & Rekomendasi Teknologi Web — CegahScam AI Service

Dokumen ini disusun sebagai panduan rujukan teknis bagi tim pengembang **backend utama aplikasi web** dan **frontend aplikasi web** untuk mengintegrasikan **CegahScam AI Service**, lengkap dengan tata cara penggunaan **Mode Mock (`MOCK_MODE=true`)** serta kajian opsi teknologi yang dapat dipertimbangkan oleh tim.

---

## 1. Pemisahan Peran: Frontend, Backend Utama, dan AI Service

Sistem CegahScam memisahkan tanggung jawab ke dalam 3 komponen yang berkomunikasi melalui REST API:

```
+-------------------------------------------------------------------+
|                    1. FRONTEND APLIKASI WEB                       |
|  - Menampilkan form input (teks, gambar, nomor, laporan darurat)  |
|  - Validasi awal di sisi klien (ukuran file <= 15 MB, format)     |
|  - Menampilkan indikator loading & merender hasil analisis        |
|  - TIDAK PERNAH memanggil AI Service secara langsung              |
+---------------------------------+---------------------------------+
                                  | HTTP / HTTPS (Publik)
                                  v
+-------------------------------------------------------------------+
|                  2. BACKEND UTAMA APLIKASI WEB                    |
|  - Menerima request dari Frontend Aplikasi Web                    |
|  - Menyimpan hasil & riwayat pengecekan ke Database Utama         |
|  - Menambahkan header rahasia X-API-Token saat memanggil AI       |
|  - Mengatur timeout request >= 90 detik tanpa retry otomatis      |
+---------------------------------+---------------------------------+
                                  | HTTP Internal + Header X-API-Token
                                  v
+-------------------------------------------------------------------+
|                      3. CEGAHSCAM AI SERVICE                      |
|  - Microservice stateless (Python 3.12 + FastAPI)                 |
|  - Mengeksekusi analisis AI (OpenRouter), reputasi nomor          |
|    (GetContact), Knowledge Base RAG, & Whitelist Bank             |
+-------------------------------------------------------------------+
```

### Aturan Wajib Integrasi:
1. **Jangan Panggil AI Service dari Browser:** Header `X-API-Token` adalah rahasia antar-server. Jika dipanggil langsung dari kode frontend di browser, token akan terlihat di *Network Inspector* pengguna.
2. **AI Service Bersifat Stateless:** AI Service tidak menyimpan riwayat ke database dan tidak men-generate berkas PDF. Setelah **backend utama aplikasi web** menerima JSON dari AI Service, backend utama yang bertugas menyimpannya ke database utama.
3. **Timeout Minimal 90 Detik & Tanpa Auto-Retry:** Pada Mode Live, analisis gambar dan teks oleh LLM membutuhkan waktu rata-rata 14–30 detik (maksimal 60 detik di sisi AI Service). Backend utama wajib memasang *HTTP timeout* $\ge 90$ detik dan **tidak melakukan retry otomatis** pada kode `408`/`502` agar kuota API tidak terkuras dua kali.

---

## 2. Rekomendasi Opsi Teknologi untuk Tim Web (Bahan Pertimbangan)

Bagian ini menyajikan perbandingan objektif beberapa opsi teknologi untuk **backend utama aplikasi web** dan **frontend aplikasi web**. Tim web bebas memilih kombinasi yang paling dikuasai.

### 2.1. Opsi Teknologi Backend Utama Aplikasi Web

Backend utama bertugas menerima request dari frontend, meneruskan payload (JSON maupun `multipart/form-data`) ke AI Service, dan menyimpan riwayat ke database.

| Opsi Teknologi | Kelebihan | Kekurangan | Pertimbangan Penggunaan |
|---|---|---|---|
| **1. Node.js + Express.js** | - Penanganan I/O asinkron (*non-blocking*) sangat baik saat menunggu respons AI Service (14–30 detik).<br>- Ekosistem *middleware* populer (`multer` untuk meneruskan file gambar, `axios`/`undici` untuk HTTP client).<br>- Bahasa yang sama (JavaScript/TypeScript) dengan frontend. | - Tidak memiliki struktur folder baku dan ORM bawaan (perlu merangkai sendiri Prisma/Sequelize/Mongoose dan validasi). | Sangat cocok jika tim web sudah terbiasa dengan ekosistem JavaScript full-stack dan ingin membangun REST API ringan dengan cepat. |
| **2. Python + FastAPI atau Flask** | - **Satu bahasa pemrograman (Python)** dengan AI Service sehingga memudahkan kolaborasi dan *troubleshooting* lintas tim.<br>- **FastAPI:** Mendukung `async` penuh, validasi Pydantic, dan *proxy* `multipart` dengan `httpx`.<br>- **Flask:** Sangat sederhana dan mudah dipelajari untuk aplikasi CRUD skala kecil-menengah. | - **Flask** secara bawaan bersifat *synchronous* (WSGI); jika ada banyak pengguna bersamaan menunggu respons AI 20 detik, *worker thread* bisa cepat penuh kecuali dikonfigurasi dengan Gunicorn gevent/threads.<br>- Ekosistem *template* web full-stack tidak selengkap Laravel. | Pilih **FastAPI** jika menginginkan performa asinkron setara Node.js dengan bahasa Python; pilih **Flask** jika tim mengutamakan kesederhanaan kode. |
| **3. PHP + Laravel** | - *Batteries-included*: Autentikasi user, migrasi database (Eloquent ORM), validasi form, *queue*, dan keamanan CSRF sudah tersedia dari bawaan.<br>- `Http::timeout(90)->attach(...)` milik Laravel sangat ringkas untuk meneruskan gambar ke AI Service. | - Model eksekusi PHP tradisional menahan 1 proses PHP-FPM selama menunggu respons AI Service (14–30 detik), sehingga perlu penyesuaian `max_execution_time >= 120` di `php.ini` dan jumlah worker FPM yang memadai. | Sangat cocok jika tim backend paling produktif menggunakan PHP dan membutuhkan fitur manajemen user/riwayat database yang cepat jadi. |

---

### 2.2. Opsi Teknologi Frontend Aplikasi Web

Frontend bertugas menyajikan antarmuka pengguna untuk mengirim teks, mengunggah gambar bukti, memasukkan nomor telepon, dan menampilkan hasil analisis.

| Opsi Teknologi | Kelebihan | Kekurangan | Pertimbangan Penggunaan |
|---|---|---|---|
| **1. HTML, CSS, & Vanilla JavaScript** | - Tanpa proses *build/compile* yang rumit; sangat ringan dan langsung berjalan di semua browser.<br>- `fetch()` dan `FormData` bawaan browser sudah cukup untuk mengirim teks dan file gambar ke backend utama. | - Mengelola *state* tampilan yang kompleks (seperti perpindahan tab, *loading state*, form darurat multi-field, dan riwayat) secara manual di DOM menjadi lebih repot seiring bertambahnya halaman. | Cocok jika antarmuka web memiliki jumlah halaman sedikit atau jika frontend di-render langsung oleh backend (*Server-Side Rendering* seperti Blade/Jinja). |
| **2. React (JavaScript / TypeScript)** | - Arsitektur berbasis komponen memudahkan pembuatan ulang elemen UI (seperti kartu `risk_score`, badge `risk_category`, daftar `reasons`, dan tombol `official_contact`).<br>- Ekosistem pustaka UI (Tailwind, Shadcn, MUI) sangat luas. | - Membutuhkan setup *bundler* (Vite/Next.js) dan pemahaman manajemen *state* (`useState`, `useEffect`). | Cocok jika tim frontend ingin membangun *Single Page Application* (SPA) yang interaktif dan modular. |
| **3. Vue.js (JavaScript / TypeScript)** | - Kurva belajar (*learning curve*) lebih landai dibanding React karena pemisahan jelas antara `<template>`, `<script>`, dan `<style>`.<br>- Reaktivitas *state* untuk form dan *loading indicator* sangat intuitif. | - Ukuran komunitas sedikit di bawah React, meski sudah sangat matang untuk kebutuhan produksi. | Pilihan jalan tengah terbaik bila tim menginginkan kemudahan HTML/CSS namun dengan kekuatan komponen modern. |

> **Catatan tentang TypeScript:** Bila tim memilih React atau Vue, penggunaan **TypeScript** sangat membantu karena skema respons di [`api-contract.md`](api-contract.md) sudah memiliki tipe data yang pasti (`risk_score: number`, `reasons: string[]`, dll.), namun **JavaScript biasa** tetap sepenuhnya kompatibel dan lebih cepat ditulis bila waktu terbatas.

---

## 3. Cara Menjalankan AI Service: Mode Mock vs Mode Live

Untuk memudahkan pengembangan dan pengujian oleh tim web **tanpa menghabiskan kuota harian OpenRouter dan GetContact** serta **tanpa perlu meminta API Key rahasia**, AI Service menyediakan **Mode Mock (`MOCK_MODE=true`)**.

### Perbedaan Mode Mock dan Mode Live

| Aspek | Mode Mock (`MOCK_MODE=true`) | Mode Live (`MOCK_MODE=false`) |
|---|---|---|
| **Kapan Digunakan?** | Saat *coding* harian frontend & backend utama, uji UI, dan uji simpan database. | Saat uji integrasi akhir (UAT) dan saat rilis produksi. |
| **Butuh `OPENROUTER_API_KEY`?** | **Tidak perlu** (bisa dikosongkan). | **Wajib diisi.** |
| **Butuh `gtc_credentials.json`?** | **Tidak perlu.** | **Wajib ada** di `app/data/gtc_credentials.json`. |
| **Butuh `CEGAHSCAM_API_TOKEN`?** | **Tetap wajib** (agar autentikasi header `X-API-Token` teruji nyata). | **Wajib.** |
| **Validasi Input & Kontrak JSON** | **100% identik dengan asli** (cek batas gambar 15 MB, tipe MIME, regex nomor, dan whitelist bank tetap jalan). | **100% asli.** |
| **Kecepatan Respons** | Instan (**< 50 milidetik**). | **14 – 30 detik** (mengikuti inferensi LLM). |

### Langkah Menyalakan AI Service dalam Mode Mock (Untuk Tim Web)

1. Salin berkas [`.env.example`](.env.example) menjadi `.env` di folder root `cegahscam-ai`:
   ```env
   OPENROUTER_API_KEY=
   CEGAHSCAM_API_TOKEN=token-rahasia-integrasi-lokal-12345
   LOG_LEVEL=INFO
   MOCK_MODE=true
   ```
2. Jalankan server:
   - **Menggunakan Python venv lokal:**
     ```powershell
     venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
     ```
   - **Atau menggunakan Docker:**
     ```powershell
     docker build -t cegahscam-ai:latest .
     docker run --rm -p 8000:8000 --env-file .env cegahscam-ai:latest
     ```
3. Buka dokumentasi interaktif di `http://127.0.0.1:8000/docs`, klik tombol **Authorize**, lalu masukkan nilai `CEGAHSCAM_API_TOKEN` (`token-rahasia-integrasi-lokal-12345`).

---

## 4. Panduan "How-To" Memanggil Endpoint dari Backend Utama

Seluruh endpoint bisnis berada di bawah prefix `/api/v1` dan wajib menyertakan header:
```http
X-API-Token: <nilai CEGAHSCAM_API_TOKEN>
```

> Rincian skema lengkap dapat dilihat di [`api-contract.md`](api-contract.md). Berikut adalah ringkasan praktis cara pemanggilannya.

### 4.1. Ringkasan 5 Endpoint Bisnis + Healthcheck

| Endpoint | Method | Content-Type yang Dikirim Backend Utama | Field Input |
|---|---|---|---|
| `/health` | `GET` | - *(Tanpa Header Auth)* | - |
| `/api/v1/analyze/text` | `POST` | `application/x-www-form-urlencoded` atau `multipart/form-data` | `text_content` (wajib, 1–10.000 karakter), `image` (file JPG/PNG/WEBP $\le 15$ MB, **opsional** untuk analisis teks+gambar sekaligus) |
| `/api/v1/analyze/image` | `POST` | `multipart/form-data` | `platform` (wajib, 1–50 karakter, misal `"WhatsApp"`), `image` (file JPG/PNG/WEBP $\le 15$ MB, wajib) |
| `/api/v1/analyze/phone` | `POST` | `application/json` | `{"phone_number": "081234567890"}` |
| `/api/v1/emergency/financial` | `POST` | `multipart/form-data` | `bank_korban`, `kanal_media`, `tanggal_kejadian`, `tujuan_transaksi`, `nomor_rekening_penipu`, `nominal_kerugian`, `nama_institusi_penipu` (opsional), `nama_pemilik_penipu` (opsional), `kronologi_user` (opsional), `bukti_transfer` (file gambar wajib) |
| `/api/v1/emergency/data-breach` | `POST` | `multipart/form-data` | `jenis_data`, `tanggal_kejadian`, `kanal_media`, `tindakan_pelaku`, `status_akses`, `kronologi_user` (opsional), `bukti_percakapan` (file gambar wajib) |

---

### 4.2. Contoh Implementasi di Backend Utama Aplikasi Web

Berikut contoh kode di sisi **backend utama aplikasi web** untuk memanggil AI Service pada beberapa pilihan bahasa pemrograman:

#### Opsi A: Jika Backend Utama Menggunakan JavaScript / Node.js (`fetch` bawaan Node 18+)
```javascript
const AI_BASE_URL = process.env.AI_SERVICE_URL || "http://127.0.0.1:8000";
const AI_API_TOKEN = process.env.CEGAHSCAM_API_TOKEN;

// 1. Contoh Analisis Teks (Form Data)
async function analyzeText(textContent) {
  const form = new URLSearchParams();
  form.append("text_content", textContent);

  const response = await fetch(`${AI_BASE_URL}/api/v1/analyze/text`, {
    method: "POST",
    headers: {
      "X-API-Token": AI_API_TOKEN,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: form,
    signal: AbortSignal.timeout(90_000), // Timeout wajib >= 90 detik
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "Gagal menganalisis teks");
  }
  return data;
}

// 2. Contoh Analisis Nomor Telepon (JSON)
async function analyzePhone(phoneNumber) {
  const response = await fetch(`${AI_BASE_URL}/api/v1/analyze/phone`, {
    method: "POST",
    headers: {
      "X-API-Token": AI_API_TOKEN,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ phone_number: phoneNumber }),
    signal: AbortSignal.timeout(90_000),
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "Gagal menganalisis nomor telepon");
  }
  return data;
}
```

#### Opsi B: Jika Backend Utama Menggunakan Python (`requests` / `httpx`)
```python
import os
import requests

AI_BASE_URL = os.getenv("AI_SERVICE_URL", "http://127.0.0.1:8000")
AI_API_TOKEN = os.getenv("CEGAHSCAM_API_TOKEN", "")
HEADERS = {"X-API-Token": AI_API_TOKEN}

# 1. Contoh Analisis Teks + Gambar (Multipart ke /api/v1/analyze/text)
def analyze_text_and_image(text_content: str, image_bytes: bytes, filename: str, mime_type: str) -> dict:
    resp = requests.post(
        f"{AI_BASE_URL}/api/v1/analyze/text",
        headers=HEADERS,
        data={"text_content": text_content},
        files={"image": (filename, image_bytes, mime_type)},
        timeout=90,
    )
    resp.raise_for_status()
    return resp.json()

# 2. Contoh Analisis Nomor Telepon (JSON)
def analyze_phone(phone_number: str) -> dict:
    resp = requests.post(
        f"{AI_BASE_URL}/api/v1/analyze/phone",
        headers=HEADERS,
        json={"phone_number": phone_number},
        timeout=90,
    )
    resp.raise_for_status()
    return resp.json()
```

#### Opsi C: Jika Backend Utama Menggunakan PHP / Laravel (`Http` Client)
```php
use Illuminate\Support\Facades\Http;

// 1. Contoh Analisis Teks + Gambar (Multipart ke /api/v1/analyze/text)
$response = Http::withHeaders([
    'X-API-Token' => config('services.cegahscam_ai.token'),
])
->timeout(90)
->attach(
    'image',
    file_get_contents($request->file('image')->getRealPath()),
    $request->file('image')->getClientOriginalName()
)
->post(config('services.cegahscam_ai.url') . '/api/v1/analyze/text', [
    'text_content' => $request->input('text_content'),
]);

return $response->json();
```

---

## 5. Panduan "How-To" untuk Frontend Aplikasi Web

Ketika **frontend aplikasi web** menerima data hasil analisis yang diteruskan oleh backend utama, berikut adalah panduan penanganan UI/UX-nya:

### 5.1. Struktur JSON Hasil Analisis (`/analyze/*`)
```json
{
  "risk_score": 85,
  "risk_category": "Sangat Tinggi",
  "scam_type": "Undian Palsu (Fake Reward)",
  "reasons": [
    "Pesan mengklaim hadiah undian tanpa partisipasi sebelumnya.",
    "Terdapat instruksi menghubungi pihak tertentu atau klik tautan."
  ],
  "recommendations": [
    "Abaikan pesan. Jangan klik tautan dan jangan mentransfer biaya administrasi apa pun.",
    "Verifikasi informasi langsung melalui saluran resmi institusi terkait."
  ],
  "official_contact": {
    "name": "Bank BCA (Bank Central Asia)",
    "phone": "1500888",
    "whatsapp": null
  }
}
```

### 5.2. Aturan Tampilan di Frontend Aplikasi Web
1. **Pewarnaan Skor & Kategori Risiko (`risk_score` & `risk_category`):**
   - `0 – 19` (`Aman`): Hijau
   - `20 – 39` (`Rendah`): Biru / Kuning Muda
   - `40 – 59` (`Sedang`): Kuning / Oranye
   - `60 – 79` (`Tinggi`): Oranye Tua / Merah Muda
   - `80 – 100` (`Sangat Tinggi`): Merah
2. **Menampilkan Kontak Resmi Bank (`official_contact`):**
   - Field `official_contact` bisa bernilai **`null`** (jika pesan tidak menyebut bank resmi yang terdaftar di whitelist).
   - Gunakan pengecekan kondisional (`if (data.official_contact !== null)`) sebelum merender kartu *"Hubungi Call Center Resmi"*.
3. **Penanganan *Loading State*:**
   - Tampilkan *loading spinner* atau pesan progres (misalnya: *"Sedang menganalisis bukti pesan..."*) dan nonaktifkan tombol *Submit* selama request berlangsung agar pengguna tidak menekan tombol berkali-kali.
4. **Validasi Ukuran Gambar Sebelum Upload:**
   - Batasi input file di browser hanya menerima `.jpg`, `.jpeg`, `.png`, `.webp` dengan ukuran maksimal **15 MB** agar pengguna mendapat umpan balik instan sebelum file dikirim ke server.
