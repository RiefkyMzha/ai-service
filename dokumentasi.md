# Dokumentasi Laporan Peran & Implementasi MLOps — CegahScam AI Service

Dokumen ini merupakan laporan teknis komprehensif mengenai pelaksanaan tanggung jawab **MLOps (Machine Learning Operations)** pada proyek **CegahScam**, mencakup arsitektur layanan AI, keamanan, pengujian kontrak API, optimasi model, evaluasi kuantitatif, hingga **siklus hidup pemeliharaan dan pembaruan model (*Model Lifecycle Management*)**.

---

## 1. Profil Peran & Ruang Lingkup Tanggung Jawab MLOps

Sebagai **MLOps Engineer** sekaligus penanggung jawab DevOps untuk sistem kecerdasan buatan CegahScam, fokus utama peran ini adalah menjembatani aset data dan model AI agar menjadi layanan produksi (*production-grade microservice*) yang aman, terukur, memiliki ketersediaan tinggi (*high availability*), dan mudah dipelihara.

### 1.1. Rincian 10 Area Jobdesk MLOps di Proyek CegahScam

| No | Area Jobdesk | Implementasi Nyata pada CegahScam AI Service |
|---|---|---|
| **1** | **Manajemen Deploy Model** | Membungkus layanan inferensi AI menggunakan **FastAPI (Python 3.12)** dan **Docker** (*non-root container* `appuser` UID 10001) dengan orkestrasi terpisah dari backend utama aplikasi web. |
| **2** | **Pemantauan Kinerja Model** | Membangun pipeline evaluasi kuantitatif (`eval/evaluate_phase2.py`) untuk mengukur *Precision*, *Recall*, *F1-Score*, *Accuracy*, *Confusion Matrix*, dan distribusi latensi (*mean*, *p50/median*, *max*). |
| **3** | **Skalabilitas & Ketersediaan** | Menerapkan arsitektur *stateless* dan eksekusi *non-blocking I/O* (`run_in_threadpool`) pada pemanggilan eksternal (OpenRouter & GetContact) agar *event loop* dan endpoint `/health` tidak pernah membeku saat trafik padat. |
| **4** | **Manajemen Versi Model** | Mengelola versi konfigurasi model LLM (`nvidia/nemotron-3.5-super-vl:free`), versi prompt sistem, versi basis pengetahuan statis via Git, serta skema *tagging* image Docker. |
| **5** | **Keamanan (*Security*)** | Menerapkan autentikasi antar-layanan (*fail-closed* `X-API-Token` dengan `hmac.compare_digest`), penyamaran data pribadi/PII di log (`+6281*******90`), pembatasan streaming upload gambar (maksimal 15 MB per *chunk* 1 MB), pertahanan *anti-prompt injection* (`<untrusted_evidence>`), dan audit dependensi (**0 CVE** via `pip-audit`). |
| **6** | **Monitoring & Debugging** | Menyediakan endpoint `/health` untuk *container healthcheck*, pencatatan log terstruktur yang aman dari kebocoran *raw payload*, dan pemetaan kode status HTTP yang presisi (`400`, `401`, `408`, `413`, `422`, `500`, `502`). |
| **7** | **Manajemen Data & Feature** | Mengelola indeks pencarian cepat di memori (*in-memory indexing*) untuk 2 aset data utama: whitelist kontak resmi bank (`Bank_Call_Senter_Final.json`) dan basis pengetahuan pola penipuan (`knowledge_base_cegahscam.json`). |
| **8** | **Dependency & Integrasi** | Mengunci versi pustaka produksi di `requirements.txt` dan menyusun kontrak integrasi baku (`api-contract.md`) bagi **backend utama aplikasi web** dan **frontend aplikasi web**. |
| **9** | **Kolaborasi Antar-Tim** | Menyediakan dokumentasi teknis lengkap (`README.md`, `api-contract.md`, `PENGUJIAN.md`, `SECURITY.md`, `CONTEXT.md`, serta Swagger UI `/docs`) agar tim pengembang web dapat berintegrasi tanpa hambatan. |
| **10** | **Pengelolaan Sumber Daya** | Mengatur efisiensi kuota API eksternal (kuota pencarian GetContact 200/periode dan rate limit OpenRouter), menerapkan *stratified sampling* saat evaluasi, serta menjaga jejak memori (*RAM footprint*) kontainer tetap ringan. |

---

## 2. Arsitektur Integrasi & Prinsip *Stateless Microservice*

Dalam ekosistem CegahScam, komponen sistem dipisahkan menjadi tiga lapis independen:

```
+-------------------------------------------------------------------+
|                      FRONTEND APLIKASI WEB                        |
|        (Antarmuka pengguna untuk cek teks, gambar, nomor,         |
|                     dan pelaporan darurat)                        |
+---------------------------------+---------------------------------+
                                  | HTTP / REST
                                  v
+-------------------------------------------------------------------+
|                   BACKEND UTAMA APLIKASI WEB                      |
|  - Mengelola sesi pengguna & logika bisnis aplikasi web           |
|  - Menyimpan riwayat pengecekan ke Database Utama                 |
|  - Meneruskan permintaan analisis ke AI Service (Timeout >= 90s)  |
+---------------------------------+---------------------------------+
                                  | HTTP Internal + Header X-API-Token
                                  v
+-------------------------------------------------------------------+
|                 CEGAHSCAM AI SERVICE (MLOps Scope)                |
|  - FastAPI Python 3.12 (Stateless, Non-Root Docker Container)     |
|  - In-Memory Knowledge Base (RAG Ringan) & Bank Whitelist         |
|  - Integrasi Upstream: OpenRouter Multimodal LLM & GetContact     |
+-------------------------------------------------------------------+
```

### Keputusan Arsitektural MLOps:
1. **Mengapa Memilih FastAPI dibanding Flask?**
   FastAPI mendukung pemrograman asinkron (*native async/await*) secara bawaan yang sangat krusial untuk beban kerja berbasis jaringan (*I/O-bound*) seperti pemanggilan LLM dan API pihak ketiga. Selain itu, FastAPI memvalidasi skema input-output secara ketat menggunakan **Pydantic v2** dan menghasilkan dokumentasi OpenAPI/Swagger secara otomatis.
2. **Mengapa AI Service Dirancang *Stateless* (Tidak Menyentuh Database Langsung)?**
   Penyimpanan riwayat cek scam pengguna ke database dilakukan oleh **backend utama aplikasi web**, bukan oleh AI Service. Desain ini mencegah duplikasi kredensial database, menghilangkan risiko *database connection exhaustion* di sisi model AI, dan memungkinkan kontainer AI Service di-*scale* atau di-*restart* kapan saja tanpa risiko korupsi data.
3. **Mengapa Menggunakan *Multi-Container* (Docker Compose) dibanding Satu Kontainer Monolit?**
   Menyatukan Frontend, Backend Utama, dan AI Service di dalam satu kontainer tunggal melanggar prinsip *single responsibility per container*. Dengan memisahkan AI Service ke dalam kontainer Docker tersendiri yang berkomunikasi lewat jaringan internal Docker Compose, pembaruan model AI dapat dilakukan tanpa mematikan layanan web utama.

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
| - Menjalankan 63 automated unit/integration tests (pytest).             |
| - Menjalankan skrip evaluasi (eval/evaluate_phase2.py) terhadap         |
|   Golden Dataset untuk memastikan Precision, Recall, & F1 tidak turun.  |
+------------------------------------+------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
| TAHAP 4: Kontainerisasi & Manajemen Versi (Container Versioning)        |
| - Mencatat perubahan di Git (commit terstruktur).                       |
| - Membangun ulang image Docker (docker build -t cegahscam-ai:v1.x .)    |
|   dan memastikan pip-audit bebas dari kerentanan (0 CVE).               |
+------------------------------------+------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
| TAHAP 5: Deployment & Pemantauan Produksi (Release & Drift Monitoring)  |
| - Me-restart kontainer AI Service di server cloud via Docker Compose.   |
| - Memantau endpoint /health, latensi respons, sisa kuota API eksternal, |
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
3. **Bangun & Rilis Ulang Kontainer Docker:**
   ```powershell
   docker build -t cegahscam-ai:latest .
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
3. **Kinerja Latensi:** Latensi median (*p50*) tercatat **14,00 detik** (rata-rata *mean* Baseline: **19,91 detik**), menjadi dasar ilmiah penetapan syarat timeout minimal **90 detik** pada kontrak integrasi backend utama.

---

## 5. Matriks Pencapaian 13 Target MLOps

| No | Target Capaian MLOps | Status | Bukti & Implementasi di Repositori |
|---|---|---|---|
| **1** | Sistem/model AI live di internet sebagai backend untuk web | **Siap Deploy (Fase 4–5)** | Seluruh endpoint bisnis dan kontainer produksi siap di-deploy ke server cloud. |
| **2** | Memilih teknologi backend (Flask / FastAPI) | **Selesai 100%** | Menggunakan **FastAPI (Python 3.12)** dengan Pydantic v2 dan Uvicorn. |
| **3** | Membuat API endpoint untuk mengakses model | **Selesai 100%** | 5 endpoint bisnis (`/analyze/text` untuk teks & teks+gambar, `/analyze/image`, `/analyze/phone`, `/emergency/financial`, `/emergency/data-breach`) + `/health`. |
| **4** | Pengujian input-output sesuai kontrak API | **Selesai 100%** | **64 skenario pengujian otomatis (`pytest`) lulus 100%**, terdokumentasi di `api-contract.md` dan `PENGUJIAN.md`. |
| **5** | Optimasi model di backend agar performa lebih baik | **Selesai 100%** | Eksekusi *threadpool non-blocking*, *chunked upload* 1 MB, serta optimasi *Lightweight RAG* (`min_keywords=3`) yang menaikkan F1-Score ke **92,31%** (Fraud-Only). |
| **6** | Menguji integrasi model ke dalam sistem web | **Fase 3** | Kontrak API, fitur simulasi `MOCK_MODE=true`, dan panduan [`PANDUAN_INTEGRASI.md`](PANDUAN_INTEGRASI.md) siap digunakan begitu backend utama dan frontend dari tim web siap. |
| **7** | Menyediakan dokumentasi penggunaan model | **Selesai 100%** | Tersedia di `README.md`, `api-contract.md`, `PANDUAN_INTEGRASI.md`, `PENGUJIAN.md`, `SECURITY.md`, `CONTEXT.md`, berkas ini (`dokumentasi.md`), dan Swagger `/docs`. |
| **8** | Mempersiapkan deployment ke platform cloud | **Fase 4** | Direkomendasikan menggunakan **VPS Linux mandiri + Docker Compose** untuk menghindari masalah *cold start* pada PaaS gratis. |
| **9** | Membungkus aset ke dalam "kotak pelindung" Docker | **Selesai 100%** | `Dockerfile` multi-stage dengan user non-root `appuser` (UID 10001), `HEALTHCHECK` terpasang, dan dependensi bersih (**0 CVE**). |
| **10** | Menyambungkan layanan ke sistem web & database utama | **Selesai (Arsitektur Stateless)** | Dirancang sebagai *stateless microservice* yang dipanggil oleh backend utama via REST API; penyimpanan database ditangani oleh backend utama. |
| **11** | Menyewa & mengatur server cloud (OS, port, domain) | **Fase 4** | Rencana pengerasan server: Ubuntu LTS, firewall hanya membuka port 80/443/SSH, reverse proxy HTTPS, port 8000 AI Service diisolasi secara internal. |
| **12** | Men-deploy Docker aplikasi ke server cloud | **Fase 5** | Orkestrasi multi-container menggunakan Docker Compose pada server target sebelum tenggat 17 November 2026. |
| **13** | Memantau resource server & mengamankan kunci API | **Selesai di Kode, Lanjut di Server** | `OPENROUTER_API_KEY`, `CEGAHSCAM_API_TOKEN`, dan `gtc_credentials.json` diisolasi dari Git/Docker image; PII disamarkan dari log aplikasi. |
