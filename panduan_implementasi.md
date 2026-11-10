# Panduan Implementasi untuk Pengembang Web — CegahScam AI Service

Dokumen ini disusun sebagai panduan dan rujukan teknis operasional (*runbook & integration guide*) bagi tim pengembang **backend utama aplikasi web** dan **frontend aplikasi web** dalam mengintegrasikan antarmuka web dengan **CegahScam AI Service**.

---

## 1. Arsitektur Komunikasi Sistem Web dengan AI Service

**CegahScam AI Service** berjalan pada server mandiri dan diakses oleh sistem web melalui protokol REST API (HTTPS):

```
+-------------------------------------------------------------------+
|                    1. FRONTEND APLIKASI WEB                       |
|  - Menampilkan form input (teks, gambar, nomor, laporan darurat)  |
|  - Validasi awal di browser (format JPG/PNG/WEBP, ukuran <= 15MB) |
|  - Menampilkan loading spinner & merender kartu hasil analisis    |
+-----------------+-------------------------------+-----------------+
                  |                               |
   (Pola A: Lewat Backend Utama -                 | (Pola B: Langsung dari Frontend
    Direkomendasikan untuk Produksi)              |  saat Uji Coba / CORS Aktif)
                  v                               |
+-----------------------------------+             |
|   2. BACKEND UTAMA APLIKASI WEB   |             |
|  - Mengelola sesi & autentikasi   |             |
|  - Menyimpan riwayat ke Database  |             |
|  - Menambahkan header X-API-Token |             |
+-----------------+-----------------+             |
                  |                               |
                  +---------------+---------------+
                                  | HTTPS REST API + Header X-API-Token
                                  v
+-------------------------------------------------------------------+
|              3. CEGAHSCAM AI SERVICE (Server Mandiri)             |
|  - Menerima request analisis teks, gambar, nomor, & darurat       |
|  - Mengembalikan hasil analisis dalam format JSON baku            |
+-------------------------------------------------------------------+
```

### Ketentuan Penting bagi Pengembang Web:
1. **Autentikasi Header `X-API-Token`:**
   - Seluruh pemanggilan ke endpoint `/api/v1/*` wajib menyertakan header `X-API-Token` yang nilainya dikonfigurasi oleh tim AI/MLOps.
   - **Rekomendasi Keamanan:** Meskipun AI Service telah mengaktifkan dukungan CORS (`CORSMiddleware`) sehingga dapat dipanggil dari browser saat tahap uji coba (Pola B), pada tahap produksi sangat disarankan pemanggilan dilakukan melalui **backend utama aplikasi web** (Pola A) supaya `X-API-Token` tetap aman di server backend dan tidak terlihat di *Network Inspector* browser pengguna.
2. **Penyimpanan Database & Laporan (Stateless API):**
   - AI Service bersifat murni *stateless* (tidak memiliki tabel database dan tidak membuat file PDF).
   - Penyimpanan riwayat pengecekan pengguna ke database utama serta pembuatan dokumen/sertifikat laporan merupakan tanggung jawab **backend utama aplikasi web**.
3. **Pengaturan Timeout ($\ge 90$ Detik) & Larangan Auto-Retry:**
   - Pada saat mode AI aktif (*Live Mode*), proses inferensi multimodal LLM membutuhkan waktu rata-rata **14 hingga 35 detik** (dengan batas maksimal 85 detik di server AI).
   - Pengembang web **wajib mengatur batas waktu tunggu (*HTTP request timeout*) minimal 90 detik** pada klien HTTP, serta **tidak memasang fitur *auto-retry*** pada error `408`/`502` agar satu klik pengguna tidak memicu pemanggilan ganda ke mesin AI.

---

## 2. Rekomendasi Opsi Teknologi untuk Tim Web (Bahan Pertimbangan)

Bagian ini menyajikan perbandingan objektif beberapa opsi teknologi sebagai bahan pertimbangan (bukan keputusan mengikat). Tim pengembang web bebas memilih kombinasi teknologi yang paling dikuasai.

### 2.1. Opsi Teknologi Backend Utama Aplikasi Web
| Opsi Teknologi | Kelebihan | Kekurangan | Pertimbangan Penggunaan |
|---|---|---|---|
| **1. Node.js + Express.js** | - Penanganan I/O asinkron (*non-blocking*) sangat baik saat menunggu respons AI Service (14–30 detik).<br>- Ekosistem *middleware* populer (`multer` untuk meneruskan file gambar, `fetch`/`axios` untuk HTTP client).<br>- Menggunakan bahasa yang sama (JavaScript/TypeScript) dengan frontend. | - Tidak memiliki struktur folder baku dan ORM bawaan (perlu merangkai sendiri Prisma/Sequelize dan validasi). | Sangat cocok jika tim web sudah terbiasa dengan ekosistem JavaScript full-stack dan ingin membangun REST API ringan dengan cepat. |
| **2. Python + FastAPI atau Flask** | - **Satu bahasa pemrograman (Python)** dengan AI Service sehingga memudahkan kolaborasi lintas tim.<br>- **FastAPI:** Mendukung `async` penuh dan validasi skema otomatis.<br>- **Flask:** Sangat sederhana dan mudah dipelajari untuk aplikasi skala kecil-menengah. | - **Flask** secara bawaan bersifat *synchronous* (WSGI); butuh worker thread lebih banyak saat menunggu respons AI.<br>- Fitur bawaan full-stack tidak selengkap Laravel. | Pilih **FastAPI** jika menginginkan performa asinkron tinggi dengan bahasa Python; pilih **Flask** jika tim mengutamakan kesederhanaan kode. |
| **3. PHP + Laravel** | - *Batteries-included*: Autentikasi user, migrasi database (Eloquent ORM), validasi form, dan keamanan sudah tersedia bawaan.<br>- HTTP Client bawaan (`Http::timeout(90)->attach(...)`) sangat ringkas untuk meneruskan gambar ke AI Service. | - Model eksekusi PHP menahan proses selama menunggu respons AI, sehingga perlu memastikan `max_execution_time >= 120` di konfigurasi PHP. | Sangat cocok jika tim backend paling produktif menggunakan PHP dan membutuhkan fitur manajemen user serta riwayat database yang cepat selesai. |

### 2.2. Opsi Teknologi Frontend Aplikasi Web
| Opsi Teknologi | Kelebihan | Kekurangan | Pertimbangan Penggunaan |
|---|---|---|---|
| **1. HTML, CSS, & Vanilla JS** | - Sangat ringan, tanpa proses *build/compile* yang rumit, dan langsung berjalan di semua browser.<br>- `fetch()` dan `FormData` bawaan browser sudah cukup untuk mengirim teks dan file gambar. | - Mengelola *state* tampilan yang kompleks (perpindahan tab, form multi-field, dan riwayat) secara manual di DOM menjadi lebih repot seiring bertambahnya halaman. | Cocok jika antarmuka web memiliki jumlah halaman sedikit atau jika halaman di-render langsung oleh backend (*Server-Side Rendering* seperti Blade/Jinja). |
| **2. React (JS / TS)** | - Arsitektur berbasis komponen memudahkan pembuatan ulang elemen UI (kartu skor risiko, badge kategori, daftar alasan, dan tombol kontak resmi).<br>- Ekosistem pustaka UI (Tailwind, Shadcn, MUI) sangat luas. | - Membutuhkan setup *bundler* (Vite/Next.js) dan pemahaman manajemen *state* (`useState`, `useEffect`). | Cocok jika tim frontend ingin membangun *Single Page Application* (SPA) yang interaktif dan modular. |
| **3. Vue.js (JS / TS)** | - Kurva belajar lebih landai dibanding React karena pemisahan jelas antara `<template>`, `<script>`, dan `<style>`.<br>- Reaktivitas *state* untuk form dan *loading indicator* sangat intuitif. | - Ekosistem komunitas sedikit di bawah React, meski sudah sangat matang untuk produksi. | Pilihan jalan tengah terbaik bila tim menginginkan kemudahan penulisan HTML/CSS namun dengan kekuatan komponen modern. |

---

## 3. Mode Pengujian bagi Tim Web (Mode Mock vs Mode Live)

Untuk mendukung kelancaran pengembangan tanpa khawatir kehabisan kuota harian API eksternal, server AI Service menyediakan dua mode operasional:

| Aspek dari Sisi Tim Web | Saat Server AI dalam **Mode Mock** | Saat Server AI dalam **Mode Live** |
|---|---|---|
| **Tujuan Penggunaan** | Tahap *coding* tampilan UI, pengujian form/upload gambar, dan uji simpan DB. | Uji integrasi akhir (*End-to-End Testing*) dan demo/produksi. |
| **Batas Kuota Pemanggilan** | **Bebas tanpa batas** (aman dipanggil ribuan kali saat uji coba). | Menggunakan kuota nyata model AI dan GetContact. |
| **Kecepatan Respons** | Instan (**< 50 milidetik**). | **14 – 30 detik** (mengikuti proses inferensi AI sesungguhnya). |
| **Aturan Validasi & Format JSON** | **100% sama persis dengan Mode Live** (validasi token, batas file 15 MB, format nomor telepon, format form darurat, dan kontak resmi bank tetap aktif). | **100% asli.** |

### Cara Mengecek Status Mode Server AI Service
Tim web dapat memeriksa kapan saja apakah server AI Service sedang berada dalam **Mode Mock** atau **Mode Live** dengan memanggil endpoint `GET /health` (tanpa memerlukan token):
```json
{
  "status": "ok",
  "message": "CegahScam AI Service is healthy",
  "mock_mode": true
}
```
- `"mock_mode": true` $\rightarrow$ Server sedang dalam **Mode Mock** (aman untuk pengujian berulang kali).
- `"mock_mode": false` $\rightarrow$ Server sedang dalam **Mode Live** (terhubung ke mesin AI).

---

## 4. Ringkasan Endpoint & Format Payload (Cheatsheet)

Perhatikan tipe data yang diterima setiap endpoint agar tidak mengalami error validasi (`422 Unprocessable Entity`):

| Endpoint | Method | Format Input yang Diterima | Parameter Wajib & Opsional |
|---|---|---|---|
| `/api/v1/analyze/text` | `POST` | `multipart/form-data` / `urlencoded` | **`text_content`** (wajib, 1–10.000 karakter)<br>**`image`** (opsional, file JPG/PNG/WEBP $\le 15$ MB) |
| `/api/v1/analyze/image` | `POST` | `multipart/form-data` | **`platform`** (wajib, misal `"WhatsApp"`, `"Telegram"`)<br>**`image`** (wajib, file bukti gambar $\le 15$ MB) |
| `/api/v1/analyze/phone` | `POST` | `application/json` | **`phone_number`** (wajib, format Indonesia: `08...`, `628...`, atau `+628...`, panjang 8–15 digit) |
| `/api/v1/emergency/financial` | `POST` | `multipart/form-data` | **`bank_korban`**, **`platform_kejadian`**, **`tanggal_kejadian`** (`YYYY-MM-DD`), **`tujuan_transaksi`**, **`nomor_rekening_penipu`**, **`nominal_kerugian`** (angka $\ge 0$), **`bukti_transfer`** (file gambar wajib)<br>*Opsional:* `nama_institusi_penipu`, `nama_pemilik_penipu`, `kronologi_user` |
| `/api/v1/emergency/data-breach` | `POST` | `multipart/form-data` | **`jenis_data`**, **`tanggal_kejadian`** (`YYYY-MM-DD`), **`platform_kejadian`**, **`tindakan_pelaku`**, **`status_akses`**, **`bukti_percakapan`** (file gambar wajib)<br>*Opsional:* `kronologi_user` |

---

## 5. Contoh Implementasi Pemanggilan API (Code Snippets)

Berikut contoh kode pemanggilan yang dapat langsung digunakan pada backend utama aplikasi web:

### Opsi A: Node.js (Express / Fetch bawaan Node 18+)
```javascript
const AI_BASE_URL = process.env.AI_SERVICE_URL || "http://127.0.0.1:8000";
const AI_TOKEN = process.env.CEGAHSCAM_API_TOKEN;

// 1. Analisis Pesan Teks + Gambar Bukti (Multipart)
async function analyzeTextAndImage(textContent, imageBuffer, imageName, mimeType) {
  const formData = new FormData();
  formData.append("text_content", textContent);
  if (imageBuffer) {
    formData.append("image", new Blob([imageBuffer], { type: mimeType }), imageName);
  }

  const response = await fetch(`${AI_BASE_URL}/api/v1/analyze/text`, {
    method: "POST",
    headers: { "X-API-Token": AI_TOKEN },
    body: formData,
    signal: AbortSignal.timeout(90000), // Timeout 90 detik
  });

  if (!response.ok) {
    const errorBody = await response.json();
    throw new Error(errorBody.detail || "Gagal melakukan analisis teks.");
  }
  return await response.json();
}

// 2. Analisis Nomor Telepon (JSON)
async function analyzePhoneNumber(phoneNumber) {
  const response = await fetch(`${AI_BASE_URL}/api/v1/analyze/phone`, {
    method: "POST",
    headers: {
      "X-API-Token": AI_TOKEN,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ phone_number: phoneNumber }),
    signal: AbortSignal.timeout(90000),
  });

  if (!response.ok) {
    const errorBody = await response.json();
    throw new Error(errorBody.detail || "Gagal menganalisis nomor telepon.");
  }
  return await response.json();
}
```

### Opsi B: PHP (Laravel HTTP Client)
```php
use Illuminate\Support\Facades\Http;

// 1. Analisis Teks + Upload Gambar
$response = Http::withHeaders([
    'X-API-Token' => config('services.cegahscam.token'),
])
->timeout(90)
->attach(
    'image',
    file_get_contents($request->file('image')->getRealPath()),
    $request->file('image')->getClientOriginalName()
)
->post(config('services.cegahscam.url') . '/api/v1/analyze/text', [
    'text_content' => $request->input('text_content'),
]);

if ($response->failed()) {
    abort($response->status(), $response->json('detail') ?? 'Terjadi kesalahan sistem.');
}
return $response->json();

// 2. Analisis Nomor Telepon
$phoneResponse = Http::withHeaders([
    'X-API-Token' => config('services.cegahscam.token'),
])
->timeout(90)
->post(config('services.cegahscam.url') . '/api/v1/analyze/phone', [
    'phone_number' => $request->input('phone_number'),
]);
return $phoneResponse->json();
```

### Opsi C: JavaScript di Frontend Browser (Pola B / Saat Uji Coba CORS)
```javascript
// Contoh pemanggilan langsung dari frontend (saat uji coba dengan backend AI Service)
async function submitTextProof(text, file) {
  const formData = new FormData();
  formData.append("text_content", text);
  if (file) {
    formData.append("image", file);
  }

  const res = await fetch("https://ai.domainanda.com/api/v1/analyze/text", {
    method: "POST",
    headers: {
      "X-API-Token": "TOKEN_RAHASIA",
    },
    body: formData,
  });

  return await res.json();
}
```

---

## 6. Panduan UI/UX & Penanganan Respons di Frontend

Ketika frontend menerima payload respons analisis:

```json
{
  "risk_score": 85,
  "risk_category": "Sangat Tinggi",
  "scam_type": "Undian Palsu (Fake Reward)",
  "reasons": [
    "Pesan mengklaim hadiah undian tanpa partisipasi sebelumnya.",
    "Terdapat desakan mentransfer biaya administrasi ke rekening pribadi."
  ],
  "recommendations": [
    "Abaikan pesan dan jangan pernah mentransfer biaya apa pun.",
    "Konfirmasi kebenaran informasi melalui kanal resmi institusi terkait."
  ],
  "official_contact": {
    "name": "Bank BCA (Bank Central Asia)",
    "phone": "1500888",
    "whatsapp": null
  }
}
```

### 1. Skema Pewarnaan Skor Risiko (`risk_score` 0–100):
| Rentang Skor | Kategori | Warna Rekomendasi UI | Makna Tampilan |
|---|---|---|---|
| `0 – 19` | **Aman** | Hijau (`#10B981`) | Tidak ditemukan indikasi penipuan |
| `20 – 39` | **Rendah** | Biru (`#3B82F6`) | Waspada standar, indikasi penipuan minimal |
| `40 – 59` | **Sedang** | Kuning / Oranye Muda (`#F59E0B`) | Mencurigakan, perlu verifikasi lanjut |
| `60 – 79` | **Tinggi** | Oranye Tua (`#EA580C`) | Sangat mencurigakan, terdapat pola penipuan aktif |
| `80 – 100` | **Sangat Tinggi** | Merah (`#EF4444`) | Terkonfirmasi kuat sebagai modus kejahatan penipuan |

### 2. Penanganan Aman Field `official_contact` (`null-check`):
- Field `official_contact` akan bernilai **`null`** apabila bukti tidak menyebutkan nama bank yang terdaftar di whitelist resmi.
- **Penting:** Pastikan kode frontend melakukan pengecekan kondisi sebelum merender:
  ```javascript
  // Contoh penanganan aman di React / Vue / JS
  if (data.official_contact) {
    renderOfficialContactCard(data.official_contact.name, data.official_contact.phone);
  } else {
    // Sembunyikan kartu kontak bank atau tampilkan saran umum
  }
  ```

### 3. Loading Indicator & Tombol Form:
- Karena analisis visual LLM membutuhkan waktu **14 hingga 25 detik**, frontend **wajib** menampilkan status memuat (*loading spinner*) dan mendisable tombol *Kirim / Submit* segera setelah tombol ditekan agar pengguna tidak mengklik berulang kali.
- **Saran UX:** Tampilkan pesan progres berganti, misalnya: *"Sedang menganalisis bukti pesan..."* lalu *"Mengecek indikasi pola penipuan..."*.

### 4. Validasi Sisi Klien (Pre-Validation):
Sebelum mengirim data ke server, lakukan validasi awal di browser:
- Pastikan ukuran file gambar **tidak melebihi 15 MB** (`file.size <= 15 * 1024 * 1024`).
- Pastikan ekstensi file hanya `.jpg`, `.jpeg`, `.png`, atau `.webp`.

---

## 7. Panduan Penanganan Error (Error Handling & User Messaging)

Jika pemanggilan API menghasilkan kode status HTTP bukan `200`, tangani dan sampaikan pesan yang informatif kepada pengguna:

| HTTP Status | Penyebab Masalah | Rekomendasi Pesan untuk Pengguna |
|---|---|---|
| **`400 Bad Request`** | Format file bukan gambar yang didukung | *"File yang diunggah harus berformat gambar (JPG, PNG, atau WEBP)."* |
| **`401 Unauthorized`** | Header `X-API-Token` salah atau tidak dikirim | *(Internal error / laporkan ke tim teknis)* *"Autentikasi layanan gagal."* |
| **`408 Request Timeout`** | Pemrosesan AI melebihi batas waktu 85 detik | *"Waktu pemrosesan habis. Silakan periksa koneksi dan coba beberapa saat lagi."* |
| **`413 Payload Too Large`** | Ukuran file gambar melebihi batas 15 MB | *"Ukuran gambar terlalu besar. Maksimal ukuran gambar adalah 15 MB."* |
| **`422 Unprocessable Entity`** | Field wajib kosong atau format nomor salah | Tampilkan detail validasi, misal: *"Nomor telepon tidak valid (contoh: 081234567890)."* |
| **`500 Internal Error`** | Kesalahan konfigurasi server AI | *"Terjadi gangguan internal pada sistem AI. Silakan hubungi admin."* |
| **`502 Bad Gateway`** | Upstream AI sedang padat / kuota GetContact habis | *"Layanan AI sedang mengalami kepadatan antrean. Silakan coba kembali sesaat lagi."* |

---

## 8. Rujukan Kontrak Lengkap

Spesifikasi teknis mendalam mengenai skema Pydantic, kontrak JSON per endpoint, serta format formulir darurat tersedia pada dokumen **[`api-contract.md`](api-contract.md)**.
