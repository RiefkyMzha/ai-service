# Panduan Implementasi untuk Pengembang Web — CegahScam AI Service

Dokumen ini disusun sebagai panduan dan rujukan teknis bagi tim pengembang **backend utama aplikasi web** dan **frontend aplikasi web** dalam mengimplementasikan koneksi ke **CegahScam AI Service**, lengkap dengan kajian opsi teknologi web yang dapat dipertimbangkan oleh tim.

---

## 1. Arsitektur Komunikasi Sistem Web dengan AI Service

**CegahScam AI Service** berjalan pada server terpisah yang dikelola oleh tim AI/MLOps dan diakses oleh sistem web melalui protokol HTTP/HTTPS (REST API):

```
+-------------------------------------------------------------------+
|                    1. FRONTEND APLIKASI WEB                       |
|  - Menampilkan form input (teks, gambar, nomor, laporan darurat)  |
|  - Validasi awal di sisi klien (ukuran file <= 15 MB, format)     |
|  - Menampilkan indikator loading & merender hasil analisis        |
+-----------------+-------------------------------+-----------------+
                  |                               |
   (Pola A: Lewat Backend Utama -                 | (Pola B: Langsung dari Frontend
    Direkomendasikan untuk Produksi)              |  saat Uji Coba / CORS Aktif)
                  v                               |
+-----------------------------------+             |
|   2. BACKEND UTAMA APLIKASI WEB   |             |
|  - Mengelola sesi & logika web    |             |
|  - Menyimpan riwayat ke Database  |             |
|  - Menambahkan X-API-Token        |             |
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
   - Seluruh pemanggilan ke endpoint `/api/v1/*` wajib menyertakan header `X-API-Token` yang nilainya diberikan oleh tim AI/MLOps.
   - **Rekomendasi Keamanan:** Meskipun AI Service telah mengaktifkan dukungan CORS (`CORSMiddleware`) sehingga dapat dipanggil dari browser saat tahap uji coba (Pola B), pada tahap produksi sangat disarankan agar pemanggilan ke AI Service dilakukan melalui **backend utama aplikasi web** (Pola A) supaya `X-API-Token` tetap tersimpan aman di sisi server backend utama dan tidak terlihat di *Network Inspector* browser pengguna.
2. **Penyimpanan Database & Pembuatan Laporan (Stateless API):**
   - AI Service bersifat murni *stateless* (hanya menerima input dan mengembalikan JSON hasil analisis, tanpa menyimpan riwayat ke database dan tanpa membuat file PDF).
   - Penyimpanan riwayat pengecekan pengguna ke database utama serta pembuatan file laporan/PDF merupakan tanggung jawab **backend utama aplikasi web**.
3. **Pengaturan Timeout ($\ge 90$ Detik) & Larangan Auto-Retry:**
   - Pada saat mode AI aktif (*Live Mode*), proses pembacaan gambar bukti dan penalaran model AI membutuhkan waktu rata-rata **14 hingga 30 detik** (dengan batas maksimal 60 detik).
   - Pengembang web **wajib mengatur batas waktu tunggu (*HTTP request timeout*) minimal 90 detik** pada klien HTTP yang memanggil AI Service, serta **tidak memasang fitur *auto-retry*** pada error `408`/`502` agar satu klik pengguna tidak memicu pemanggilan ganda.

---

## 2. Rekomendasi Opsi Teknologi untuk Tim Web (Bahan Pertimbangan)

Bagian ini menyajikan perbandingan objektif beberapa opsi teknologi untuk **backend utama aplikasi web** dan **frontend aplikasi web** sebagai bahan pertimbangan (bukan keputusan yang mengikat). Tim pengembang web bebas memilih teknologi yang paling dikuasai.

### 2.1. Opsi Teknologi Backend Utama Aplikasi Web

Backend utama bertugas menerima request dari pengguna, meneruskan data (JSON maupun `multipart/form-data` berisi gambar) ke URL AI Service, serta menyimpan hasilnya ke database utama.

| Opsi Teknologi | Kelebihan | Kekurangan | Pertimbangan Penggunaan |
|---|---|---|---|
| **1. Node.js + Express.js** | - Penanganan I/O asinkron (*non-blocking*) sangat baik saat menunggu respons AI Service (14–30 detik).<br>- Ekosistem *middleware* populer (`multer` untuk meneruskan file gambar, `fetch`/`axios` untuk HTTP client).<br>- Menggunakan bahasa yang sama (JavaScript/TypeScript) dengan frontend. | - Tidak memiliki struktur folder baku dan ORM bawaan (perlu merangkai sendiri Prisma/Sequelize/Mongoose dan validasi). | Sangat cocok jika tim web sudah terbiasa dengan ekosistem JavaScript full-stack dan ingin membangun REST API ringan dengan cepat. |
| **2. Python + FastAPI atau Flask** | - **Satu bahasa pemrograman (Python)** dengan AI Service sehingga memudahkan kolaborasi lintas tim.<br>- **FastAPI:** Mendukung `async` penuh dan validasi skema otomatis.<br>- **Flask:** Sangat sederhana dan mudah dipelajari untuk aplikasi skala kecil-menengah. | - **Flask** secara bawaan bersifat *synchronous* (WSGI); jika ada banyak pengguna bersamaan menunggu respons AI 20 detik, *worker thread* perlu dikonfigurasi lebih banyak.<br>- Fitur bawaan full-stack tidak selengkap Laravel. | Pilih **FastAPI** jika menginginkan performa asinkron tinggi dengan bahasa Python; pilih **Flask** jika tim mengutamakan kesederhanaan kode. |
| **3. PHP + Laravel** | - *Batteries-included*: Autentikasi user, migrasi database (Eloquent ORM), validasi form, dan keamanan sudah tersedia dari bawaan.<br>- HTTP Client bawaan (`Http::timeout(90)->attach(...)`) sangat ringkas untuk meneruskan gambar ke AI Service. | - Model eksekusi PHP menahan proses selama menunggu respons AI Service (14–30 detik), sehingga perlu memastikan `max_execution_time >= 120` di konfigurasi PHP. | Sangat cocok jika tim backend paling produktif menggunakan PHP dan membutuhkan fitur manajemen user serta riwayat database yang cepat selesai. |

---

### 2.2. Opsi Teknologi Frontend Aplikasi Web

Frontend bertugas menyajikan antarmuka pengguna untuk mengirim teks, mengunggah gambar bukti, memasukkan nomor telepon, mengisi form darurat, dan menampilkan hasil analisis.

| Opsi Teknologi | Kelebihan | Kekurangan | Pertimbangan Penggunaan |
|---|---|---|---|
| **1. HTML, CSS, & Vanilla JavaScript** | - Tanpa proses *build/compile* yang rumit; sangat ringan dan langsung berjalan di semua browser.<br>- `fetch()` dan `FormData` bawaan browser sudah cukup untuk mengirim teks dan file gambar. | - Mengelola *state* tampilan yang kompleks (perpindahan tab, *loading state*, form darurat multi-field, dan riwayat) secara manual di DOM menjadi lebih repot seiring bertambahnya halaman. | Cocok jika antarmuka web memiliki jumlah halaman sedikit atau jika halaman di-render langsung oleh backend (*Server-Side Rendering* seperti Blade/Jinja). |
| **2. React (JavaScript / TypeScript)** | - Arsitektur berbasis komponen memudahkan pembuatan ulang elemen UI (seperti kartu `risk_score`, badge `risk_category`, daftar `reasons`, dan tombol `official_contact`).<br>- Ekosistem pustaka UI (Tailwind, Shadcn, MUI) sangat luas. | - Membutuhkan setup *bundler* (Vite/Next.js) dan pemahaman manajemen *state* (`useState`, `useEffect`). | Cocok jika tim frontend ingin membangun *Single Page Application* (SPA) yang interaktif dan modular. |
| **3. Vue.js (JavaScript / TypeScript)** | - Kurva belajar (*learning curve*) lebih landai dibanding React karena pemisahan jelas antara `<template>`, `<script>`, dan `<style>`.<br>- Reaktivitas *state* untuk form dan *loading indicator* sangat intuitif. | - Ukuran komunitas sedikit di bawah React, meski sudah sangat matang untuk kebutuhan produksi. | Pilihan jalan tengah terbaik bila tim menginginkan kemudahan penulisan HTML/CSS namun dengan kekuatan komponen modern. |

> **Catatan tentang TypeScript:** Bila tim memilih React atau Vue, penggunaan **TypeScript** sangat membantu karena skema respons di [`api-contract.md`](api-contract.md) sudah memiliki tipe data yang pasti (`risk_score: number`, `reasons: string[]`, dll.), namun **JavaScript biasa** tetap sepenuhnya kompatibel dan lebih cepat ditulis bila waktu terbatas.

---

## 3. Mode Pengujian bagi Tim Web (Mode Mock vs Mode Live)

Untuk mendukung kelancaran pengembangan oleh tim web tanpa terkendala batas kuota harian API eksternal, server AI Service menyediakan dua mode operasional yang dikendalikan oleh tim AI/MLOps:

| Aspek dari Sisi Tim Web | Saat Server AI dalam **Mode Mock** | Saat Server AI dalam **Mode Live** |
|---|---|---|
| **Tujuan Penggunaan** | Untuk tahap *coding* tampilan UI, pengujian kirim form/gambar, dan pengujian simpan ke database. | Untuk tahap uji integrasi akhir (*End-to-End Testing*) dan demo/produksi. |
| **Batas Pemanggilan (Kuota)** | **Bebas tanpa batas** (tim web dapat memanggil endpoint ribuan kali untuk uji coba). | Menggunakan kuota nyata model AI dan pencarian reputasi nomor. |
| **Kecepatan Respons** | Instan (**< 50 milidetik**). | **14 – 30 detik** (mengikuti proses inferensi AI sesungguhnya). |
| **Aturan Validasi & Format JSON** | **100% sama persis dengan Mode Live** (validasi `X-API-Token`, batas ukuran gambar 15 MB, format nomor telepon, format field darurat, dan pencocokan kontak resmi bank tetap berjalan nyata). | **100% asli.** |

### Cara Mengecek Status Mode Server AI Service Saat Ini
Tim web dapat memeriksa kapan saja apakah server AI Service sedang berada dalam **Mode Mock** atau **Mode Live** dengan memanggil endpoint `GET /health` (tanpa memerlukan token):
```json
{
  "status": "ok",
  "message": "CegahScam AI Service is healthy",
  "mock_mode": true
}
```
- Jika `"mock_mode": true` $\rightarrow$ Server sedang dalam **Mode Mock** (aman untuk *testing* berulang kali).
- Jika `"mock_mode": false` $\rightarrow$ Server sedang dalam **Mode Live** (terhubung penuh ke mesin AI).
- Apabila tim web telah menyelesaikan pengembangan dan ingin beralih dari Mode Mock ke Mode Live (atau sebaliknya), cukup informasikan kepada tim AI/MLOps tanpa perlu mengubah kode atau URL di sisi aplikasi web.

---

## 4. Rujukan Kontrak Endpoint & Skema Data

Seluruh rincian teknis mengenai daftar endpoint (`/api/v1/analyze/text`, `/api/v1/analyze/image`, `/api/v1/analyze/phone`, `/api/v1/emergency/financial`, `/api/v1/emergency/data-breach`), nama dan batas ukuran field, kode status error (`400`, `401`, `408`, `413`, `422`, `500`, `502`), serta struktur JSON respons dapat dilihat secara lengkap pada dokumen **[`api-contract.md`](api-contract.md)**.
