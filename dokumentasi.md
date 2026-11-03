# Dokumentasi Laporan Peran & Implementasi MLOps — CegahScam AI Service

Dokumen ini merupakan laporan teknis komprehensif mengenai pelaksanaan tanggung jawab **MLOps (Machine Learning Operations)** pada proyek **CegahScam**, mencakup arsitektur layanan AI, keamanan, pengujian kontrak API, optimasi model, evaluasi kuantitatif, hingga **siklus hidup pemeliharaan dan pembaruan model (*Model Lifecycle Management*)**.

---

## 1. Profil Peran & Ruang Lingkup Tanggung Jawab MLOps

Sebagai **MLOps Engineer** sekaligus penanggung jawab DevOps untuk sistem kecerdasan buatan CegahScam, fokus utama peran ini adalah menjembatani aset data dan model AI agar menjadi layanan produksi (*production-grade microservice*) yang aman, terukur, memiliki ketersediaan tinggi (*high availability*), dan mudah dipelihara.

### 1.1. Rincian 10 Area Jobdesk MLOps di Proyek CegahScam

| No | Area Jobdesk | Implementasi Nyata pada CegahScam AI Service |
|---|---|---|
| **1** | **Manajemen Deploy Model** | Menyiapkan dan men-deploy layanan inferensi AI menggunakan **FastAPI (Python 3.12)** pada server **VPS Ubuntu** mandiri menggunakan **`.venv` + `systemd` + `Nginx Reverse Proxy` + `Certbot (HTTPS)`**. |
| **2** | **Pemantauan Kinerja Model** | Membangun pipeline evaluasi kuantitatif (`eval/evaluate_phase2.py`) untuk mengukur *Precision*, *Recall*, *F1-Score*, *Accuracy*, *Confusion Matrix*, dan distribusi latensi (*mean*, *p50/median*, *max*). |
| **3** | **Skalabilitas & Ketersediaan** | Menerapkan arsitektur *stateless* dan eksekusi *non-blocking I/O* (`run_in_threadpool`) pada pemanggilan eksternal (OpenRouter & GetContact) agar *event loop* dan endpoint `/health` tidak pernah membeku saat trafik padat. |
| **4** | **Manajemen Versi Model** | Mengelola versi konfigurasi model LLM (`nvidia/nemotron-3.5-super-vl:free`), versi prompt sistem, serta versi basis pengetahuan statis via Git. |
| **5** | **Keamanan (*Security*)** | Menerapkan autentikasi (`X-API-Token` *fail-closed* dengan `hmac.compare_digest`), `CORSMiddleware` terkonfigurasi (`CORS_ORIGINS`), penyamaran data pribadi/PII di log (`+6281*******90`), pembatasan streaming upload gambar (maksimal 15 MB per *chunk* 1 MB), pertahanan *anti-prompt injection* (`<untrusted_evidence>`), dan audit dependensi (**0 CVE** via `pip-audit`). |
| **6** | **Monitoring & Debugging** | Menyediakan endpoint `/health` (dilengkapi indikator status `mock_mode`), pencatatan log terstruktur via `journalctl` yang aman dari kebocoran *raw payload*, dan pemetaan kode status HTTP yang presisi (`400`, `401`, `408`, `413`, `422`, `500`, `502`). |
| **7** | **Manajemen Data & Feature** | Mengelola indeks pencarian cepat di memori (*in-memory indexing*) untuk 2 aset data utama: whitelist kontak resmi bank (`Bank_Call_Senter_Final.json`) dan basis pengetahuan pola penipuan (`knowledge_base_cegahscam.json`). |
| **8** | **Dependency & Integrasi** | Mengunci versi pustaka produksi di `requirements.txt`, mengaktifkan dukungan lintas domain (`CORSMiddleware`), dan menyusun kontrak integrasi baku (`api-contract.md`) agar dapat diakses secara online oleh **frontend aplikasi web** maupun **backend utama aplikasi web**. |
| **9** | **Kolaborasi Antar-Tim** | Menyediakan dokumentasi teknis lengkap (`README.md`, `api-contract.md`, `panduan_implementasi.md`, `PENGUJIAN.md`, `SECURITY.md`, serta Swagger UI `/docs`) dan fitur **`MOCK_MODE`** agar tim web dapat menguji integrasi online tanpa khawatir kehabisan kuota API. |
| **10** | **Pengelolaan Sumber Daya** | Mengatur strategi peralihan `MOCK_MODE=true` (saat testing integrasi) ke `MOCK_MODE=false` (saat live produksi) untuk menghemat kuota pencarian GetContact (200/periode) dan rate limit OpenRouter, serta menjaga penggunaan RAM di VPS tetap sangat ringan. |

---

## 2. Arsitektur Integrasi Online & Deployment VPS Mandiri (Metode A: `systemd` + `.venv` + Nginx + Certbot)

Sesuai arahan arsitektur deployment proyek, **CegahScam AI Service** di-deploy pada server **VPS Ubuntu tersendiri** menggunakan subdomain HTTPS publik sehingga dapat diakses secara online oleh sistem web (baik dipanggil melalui **backend utama aplikasi web** maupun langsung dari **frontend aplikasi web**):

```
+-------------------------------------------------------------------+
|            TIM WEB (FRONTEND / BACKEND UTAMA APLIKASI WEB)        |
|  - Memanggil endpoint https://ai.<domain>/api/v1/...              |
|  - Menyertakan Header X-API-Token                                 |
+---------------------------------+---------------------------------+
                                  | HTTPS (Port 443, Terenkripsi TLS)
                                  v
+-------------------------------------------------------------------+
|               SERVER VPS UBUNTU — CEGAHSCAM AI SERVICE            |
|                                                                   |
|  [1] UFW Firewall (Hanya membuka Port 22/SSH, 80/HTTP, 443/HTTPS) |
|                                 |                                 |
|  [2] Nginx Reverse Proxy + Certbot Let's Encrypt SSL              |
|      - client_max_body_size 20M; (mendukung gambar hingga 15 MB)  |
|      - proxy_read_timeout 90s;   (mendukung inferensi LLM <= 60s) |
|                                 |                                 |
|                                 v (http://127.0.0.1:8000 lokal)   |
|  [3] Systemd Service (cegahscam-ai.service) + Python 3.12 .venv   |
|      - FastAPI + Uvicorn (--proxy-headers)                        |
|      - CORSMiddleware + X-API-Token Auth Middleware               |
|      - In-Memory Knowledge Base (RAG) & Bank Whitelist            |
|      - Mode Sakelar: MOCK_MODE=true (Testing) <-> false (Live)    |
+-------------------------------------------------------------------+
```

### Keputusan Arsitektural & Perencanaan Deployment MLOps:
1. **Mengapa Memilih FastAPI dibanding Flask?**
   FastAPI mendukung pemrograman asinkron (*native async/await*) secara bawaan yang sangat krusial untuk beban kerja berbasis jaringan (*I/O-bound*) seperti pemanggilan LLM dan API pihak ketiga. Selain itu, FastAPI memvalidasi skema input-output secara ketat menggunakan **Pydantic v2** dan menghasilkan dokumentasi OpenAPI/Swagger secara otomatis.
2. **Mengapa Menggunakan Metode A (`.venv` + `systemd` + Nginx + Certbot) di VPS?**
   - **Kelebihan:**
     - **Sangat ringan di RAM & CPU:** Tidak membutuhkan beban tambahan daemon kontainer di VPS, sehingga seluruh memori server dapat difokuskan untuk proses Python/Uvicorn dan Nginx.
     - **Isolasi Port Lokal (`127.0.0.1:8000`):** Uvicorn hanya mendengarkan di `localhost` (`127.0.0.1`), bukan `0.0.0.0`. Dunia luar hanya bisa masuk melalui Nginx pada port `443` (HTTPS).
     - **Kemudahan Operasional (Update Kredensial & Sakelar Mock/Live Instan):** Mengganti `OPENROUTER_API_KEY` atau mengubah `MOCK_MODE=true` ke `MOCK_MODE=false` di `/var/www/cegahscam-ai/.env` cukup diikuti perintah `sudo systemctl restart cegahscam-ai` yang selesai dalam ~1 detik. Bahkan pembaruan `app/data/gtc_credentials.json` langsung terbaca di setiap request tanpa perlu me-restart service.
   - **Kekurangan & Mitigasinya:**
     - Bergantung pada versi Python OS di VPS $\rightarrow$ dimitigasi dengan menggunakan **Ubuntu 24.04 LTS** yang sudah menyertakan **Python 3.12** secara bawaan dan mengisolasi paket di dalam `.venv`.
3. **Penyesuaian Konfigurasi Nginx Khusus Karakteristik CegahScam:**
   - **`client_max_body_size 20M;`:** Secara bawaan Nginx menolak upload > 1 MB (`413 Request Entity Too Large`). Karena CegahScam menerima gambar bukti hingga **15 MB**, batas body Nginx dinaikkan menjadi 20 MB.
   - **`proxy_read_timeout 90s;` & `proxy_connect_timeout 60s;`:** Karena analisis multimodal LLM membutuhkan waktu median 14 detik (dan maksimal 60 detik), timeout baca Nginx dinaikkan menjadi 90 detik agar tidak memutus koneksi lebih awal (`504 Gateway Timeout`).
4. **Strategi Manajemen Kuota: Mode Mock Online (`MOCK_MODE=true`) $\rightarrow$ Mode Live (`MOCK_MODE=false`):**
   - Saat AI Service pertama kali live di VPS dan tim web sedang menguji integrasi antarmuka mereka, `.env` di VPS disetel ke `MOCK_MODE=true`. Tim web dapat menembak endpoint online sepuasnya dengan waktu respons < 50 ms, validasi input & kontak bank tetap berjalan 100% nyata, namun **kuota OpenRouter dan GetContact (200/periode) terpakai 0**.
   - Status mode server setiap saat dapat diperiksa secara transparan melalui `GET /health` (`{"status": "ok", "message": "CegahScam AI Service is healthy", "mock_mode": true}`).
   - Ketika integrasi tim web sudah tuntas, MLOps mengubah `.env` menjadi `MOCK_MODE=false` dan menjalankan `sudo systemctl restart cegahscam-ai` untuk beralih ke **Mode Live** tanpa mengubah URL maupun kode di sisi tim web.

---

## 3. Siklus Hidup Pemeliharaan & Pembaruan Model (*LLMOps Model Lifecycle*)

Salah satu tantangan terbesar dalam sistem deteksi penipuan siber adalah **Concept Drift**—yaitu perubahan pola dan modus kejahatan seiring waktu (contoh: pergeseran dari modus *SMS Undian Palsu* ke modus *File APK Kurir/Surat Tilang*, *QRIS Palsu*, hingga *Task Scam / Pekerjaan Paruh Waktu*).

Meskipun inferensi utama menggunakan Foundation Model melalui OpenRouter (`nvidia/nemotron-3.5-super-vl:free`), kecerdasan kontekstual dan akurasi CegahScam AI Service dikendalikan oleh **4 aset lokal** yang dikelola secara berkelanjutan oleh MLOps.

### 3.1. Empat Komponen Model yang Diperbarui secara Berkala

1. **Basis Pengetahuan Pola Penipuan (`app/data/knowledge_base_cegahscam.json`) — *Lightweight In-Memory RAG***
   - Berisi pemetaan `kategori_pola`, `keywords_terkait`, dan `sop_mitigasi` hasil kurasi data penipuan di Indonesia.
   - Diindeks ke memori RAM saat startup oleh `DataLoader._build_kb_index()`.
   - Ketika teks pengguna memiliki kecocokan **minimal 3 kata kunci unik** (`min_keywords=3`) pada suatu kategori penipuan, sistem secara otomatis menyuntikkan pola dan SOP mitigasi tersebut ke dalam instruksi sistem LLM sebagai konteks referensi (*Knowledge Injection*).
2. **Whitelist Kontak Resmi Bank (`app/data/Bank_Call_Senter_Final.json`) — *Deterministic Grounding***
   - Mencegah LLM berhalusinasi saat memberikan nomor telepon bank.
   - Setiap kali bank disebut di dalam bukti pesan, profil nomor telepon, atau laporan darurat, `DataLoader.official_contact_for()` menimpa field `official_contact` secara deterministik menggunakan nomor call center resmi dari berkas ini.
3. **Instruksi Sistem & Normalisasi Taksonomi (`app/core/prompts.py` & `app/core/normalization.py`) — *Prompt Versioning***
   - Mengatur batas skor risiko (`0–100`), aturan anti-halusinasi, enkapsulasi `<untrusted_evidence>`, dan pemetaan nama kategori penipuan ke Bahasa Indonesia yang baku.
4. **Dataset Evaluasi Acuan / *Golden Dataset* (`eval/data/dataset_cegahscam_master.xlsx`) & Konfigurasi Model LLM (`app/services/ai_service.py`)**
   - Digunakan sebagai tolok ukur (*benchmark*) objektif setiap kali ada penambahan pengetahuan baru, perubahan prompt, maupun pergantian model LLM upstream.

---

### 3.2. Diagram Alur 5 Tahap Siklus Hidup Model (*Closed-Loop Lifecycle*)

```
+-------------------------------------------------------------------------+
| TAHAP 1: Pengumpulan & Sanitasi Data Kasus Baru (Data Collection)       |
| - Mengambil sampel kasus scam baru dari riwayat laporan di database     |
|   backend utama aplikasi web atau temuan tren siber terbaru.            |
| - Menghapus data sensitif/PII dan melabeli kategori modus serta SOP.    |
+------------------------------------+------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
| TAHAP 2: Pembaruan Aset Pengetahuan & Prompt (Knowledge & Model Update) |
| - Menambahkan pola kata kunci & SOP baru ke knowledge_base_cegahscam.json|
| - Memperbarui daftar call center di Bank_Call_Senter_Final.json         |
| - Menyesuaikan prompt di prompts.py atau mengganti ID model OpenRouter. |
+------------------------------------+------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
| TAHAP 3: Pengujian Mutu & Evaluasi Kuantitatif (MLOps Quality Gate)     |
| - Menjalankan 65 automated unit/integration tests (pytest).             |
| - Menjalankan skrip evaluasi (eval/evaluate_phase2.py) terhadap         |
|   Golden Dataset untuk memastikan Precision, Recall, & F1 tidak turun.  |
+------------------------------------+------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
| TAHAP 4: Manajemen Versi & Audit Dependensi (Versioning & Security)     |
| - Mencatat perubahan di Git (git commit & push ke repositori utama).    |
| - Memastikan pip-audit bebas dari kerentanan (0 CVE).                   |
+------------------------------------+------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
| TAHAP 5: Deployment & Pemantauan Produksi di VPS (Release & Monitoring) |
| - Menarik pembaruan di VPS (git pull) & sudo systemctl restart.         |
| - Memantau endpoint /health, journalctl, latensi respons, sisa kuota,   |
|   serta mendeteksi kemunculan modus baru yang belum terklasifikasi.     |
+-------------------------------------------------------------------------+
```

---

### 3.3. Prosedur Standar (SOP) Pembaruan Model Ketika Muncul Modus Scam Baru

Apabila di masa mendatang muncul modus penipuan baru di masyarakat (misalnya modus *Tagihan Pajak CoreTax Palsu via APK*), MLOps dapat memperbarui kemampuan deteksi AI tanpa mengubah kontrak API maupun kode utama melalui langkah berikut:

1. **Tambahkan Entri Pengetahuan Baru ke `app/data/knowledge_base_cegahscam.json`:**
   ```json
   {
       "kategori_pola": "Modus Sniffing / Malware APK",
       "keywords_terkait": [
           "coretax",
           "pajak",
           "apk",
           "instal"
       ],
       "sop_mitigasi": "JANGAN UNDUH atau BUKA file .apk. Direktorat Jenderal Pajak tidak pernah mengirimkan aplikasi perpajakan melalui pesan WhatsApp/SMS."
   }
   ```
2. **Tambahkan Kasus Uji Baru ke *Golden Dataset* (`eval/data/`) dan Jalankan Verifikasi:**
   ```powershell
   venv\Scripts\python.exe -m pytest
   venv\Scripts\python.exe -u eval\evaluate_phase2.py
   ```
3. **Push ke GitHub & Terapkan di VPS Produksi:**
   ```bash
   cd /var/www/cegahscam-ai
   git pull origin main
   sudo systemctl restart cegahscam-ai
   ```

---

## 4. Bukti Eksperimen Optimasi & Evaluasi Kinerja Model

Sebagai bukti nyata pelaksanaan jobdesk **Optimasi Model** dan **Pemantauan Kinerja Model**, dilakukan eksperimen perbandingan terkontrol (*Before vs After*) antara model **Baseline** (sebelum `knowledge_base_cegahscam.json` diaktifkan) dan model **Optimasi Knowledge Base (`min_keywords=3`)**.

### 4.1. Validasi Presisi Aturan `min_keywords=3` pada Dataset Master Penuh (1.164 Baris)
Pada awalnya, berkas `knowledge_base_cegahscam.json` memiliki sejumlah entri dengan hanya 1 kata kunci umum (seperti `"cek"` atau `"pulsa"`) yang berisiko memicu *False Positive* pada percakapan normal. Setelah diterapkan aturan pencocokan minimal **3 kata kunci unik per kategori** (`min_keywords=3`):
- Dari **674 baris percakapan normal** di dataset master, **0 baris** terpicu (0% *false trigger*).
- Dari **490 baris scam**, **66 baris** terpicu dengan presisi pencocokan aturan **100%**.

### 4.2. Perbandingan Metrik Kuantitatif (*Baseline* vs *Optimasi KB `min_keywords=3`*)
Pengujian dilakukan menggunakan sampel berstrata (*stratified sample*, `seed=42`, $N=25$ baris yang mewakili seluruh 11 kategori di dataset master) pada dua skenario:
- **Skenario A (Strict, $N=25$):** Seluruh label `1` (termasuk *Spam* dan *Promo* operator) dihitung sebagai Scam.
- **Skenario B (Fraud-Only, $N=21$):** Mengecualikan 4 baris *Spam/Promo* komersial untuk mengukur akurasi murni pada kejahatan penipuan finansial/rekayasa sosial.

#### Tabel Perbandingan pada Ambang Skor Risiko $\ge 40$ (Kategori Sedang – Sangat Tinggi)
| Skenario Evaluasi | Konfigurasi Model | TP | FP | TN | FN | Precision | Recall | F1-Score | Accuracy |
|---|---|---|---|---|---|---|---|---|---|
| **Skenario A (Strict)** | Baseline (Tanpa KB) | 13 | 0 | 7 | 5 | **100,00%** | 72,22% | 83,87% | 80,00% |
| **Skenario A (Strict)** | **Optimasi KB (`min=3`)** | **14** | **0** | **7** | **4** | **100,00%** | **77,78%** (+5,56%) | **87,50%** (+3,63%) | **84,00%** (+4,00%) |
| **Skenario B (Fraud-Only)** | Baseline (Tanpa KB) | 11 | 0 | 7 | 3 | **100,00%** | 78,57% | 88,00% | 85,71% |
| **Skenario B (Fraud-Only)** | **Optimasi KB (`min=3`)** | **12** | **0** | **7** | **2** | **100,00%** | **85,71%** (+7,14%) | **92,31%** (+4,31%) | **90,48%** (+4,77%) |

#### Tabel Perbandingan pada Ambang Skor Risiko $\ge 50$ & $\ge 60$ (Kategori Tinggi – Sangat Tinggi)
| Skenario Evaluasi | Konfigurasi Model | TP | FP | TN | FN | Precision | Recall | F1-Score | Accuracy |
|---|---|---|---|---|---|---|---|---|---|
| **Skenario A (Strict)** | Baseline (Tanpa KB) | 12 | 0 | 7 | 6 | **100,00%** | 66,67% | 80,00% | 76,00% |
| **Skenario A (Strict)** | **Optimasi KB (`min=3`)** | **13** | **0** | **7** | **5** | **100,00%** | **72,22%** (+5,55%) | **83,87%** (+3,87%) | **80,00%** (+4,00%) |
| **Skenario B (Fraud-Only)** | Baseline (Tanpa KB) | 10 | 0 | 7 | 4 | **100,00%** | 71,43% | 83,33% | 80,95% |
| **Skenario B (Fraud-Only)** | **Optimasi KB (`min=3`)** | **11** | **0** | **7** | **3** | **100,00%** | **78,57%** (+7,14%) | **88,00%** (+4,67%) | **85,71%** (+4,76%) |

### 4.3. Temuan Utama Evaluasi
1. **Precision 100% (Zero False Positive):** Seluruh percakapan normal diklasifikasikan dengan tepat sebagai risiko `Rendah` (skor 5–10).
2. **Konversi *False Negative* menjadi *True Positive*:** Pada kasus *Modus Penipuan Transfer Uang* (Row 892: instruksi transfer singkat ke rekening BNI tanpa tautan phishing), model Baseline memberikan `risk_score: 30` (*False Negative*). Dengan suntikan referensi Knowledge Base (`bni`, `rekening`, `transfer`), skor meningkat menjadi **`65` (`Tinggi`)** (*True Positive*) disertai rekomendasi SOP mitigasi yang akurat.
3. **Kinerja Latensi:** Latensi median (*p50*) tercatat **14,00 detik** (rata-rata *mean* Baseline: **19,91 detik**), menjadi dasar ilmiah penetapan syarat timeout minimal **90 detik** pada konfigurasi Nginx dan kontrak integrasi web.

---

## 5. Matriks Pencapaian 8 Target Utama MLOps

| No | Target Capaian MLOps | Status | Bukti & Implementasi di Repositori |
|---|---|---|---|
| **1** | Sistem AI / model AI bisa live di internet sebagai backend dan bisa digunakan dalam frontend web | **Siap Deploy ke VPS** | Dilengkapi `CORSMiddleware` (`CORS_ORIGINS`), autentikasi `X-API-Token`, dan siap diakses online melalui HTTPS pada VPS Ubuntu mandiri. |
| **2** | Memilih teknologi backend (disarankan: Flask atau FastAPI) | **Selesai 100%** | Menggunakan **FastAPI (Python 3.12)** dengan Pydantic v2 dan Uvicorn. |
| **3** | Membuat API endpoint untuk mengakses model | **Selesai 100%** | 5 endpoint bisnis (`/analyze/text` untuk teks & teks+gambar, `/analyze/image`, `/analyze/phone`, `/emergency/financial`, `/emergency/data-breach`) + `/health`. |
| **4** | Melakukan pengujian input-output agar sesuai dengan kontrak API | **Selesai 100%** | **65 skenario pengujian otomatis (`pytest`) lulus 100%**, terdokumentasi di `api-contract.md` dan `PENGUJIAN.md`. |
| **5** | Melakukan optimasi model di backend agar performa lebih baik | **Selesai 100%** | Eksekusi *threadpool non-blocking*, *chunked upload* 1 MB, serta optimasi *Lightweight RAG* (`min_keywords=3`) yang menaikkan F1-Score ke **92,31%** (Fraud-Only). |
| **6** | Menguji integrasi model ke dalam sistem web | **Siap Integrasi** | Tersedia sakelar `MOCK_MODE=true` (untuk uji integrasi online tanpa kuota) $\leftrightarrow$ `MOCK_MODE=false` (Mode Live) beserta panduan [`panduan_implementasi.md`](panduan_implementasi.md). |
| **7** | Menyediakan dokumentasi penggunaan model | **Selesai 100%** | Tersedia di `README.md`, `api-contract.md`, `panduan_implementasi.md`, `PENGUJIAN.md`, `SECURITY.md`, berkas ini (`dokumentasi.md`), dan Swagger `/docs`. |
| **8** | Mempersiapkan deployment ke platform cloud (VPS) | **Selesai 100%** | Arsitektur deployment **Metode A (VPS Ubuntu + `.venv` + `systemd` + `Nginx` + `Certbot HTTPS`)** siap dijalankan. |
