# Laporan Pengujian & Kontrak API — CegahScam AI Service

Dokumen ini mencatat kontrak API dan hasil pengujian **input → output** yang benar-benar dieksekusi terhadap service. Kontrak implementasi ada di [`api-contract.md`](api-contract.md), cara menjalankan ada di [`README.md`](README.md).

## 1. Ringkasan

| Item | Nilai |
|---|---|
| Tanggal eksekusi | 2026-10-28 11:03 (smoke sukses) & 11:19 (uji negatif §5) |
| Metode | `pytest` (42 test, jaringan di-mock) + smoke test HTTP ke container |
| Hasil otomatis | **61 passed** |
| Hasil smoke | **15/15 sesuai kontrak** (8 sukses, 7 negatif) |
| Container | `cegahscam-ai`, status `healthy` |
| Image | `cegahscam-ai:latest` — digest `sha256:53d28a0…6eed5`, 228 MB |
| Base URL | `http://127.0.0.1:8000` |
| Model AI | `nvidia/nemotron-3.5-super-vl:free` via OpenRouter |

## 2. Lingkungan

| Komponen | Versi / keterangan |
|---|---|
| OS host | Windows (Docker Desktop, Linux container) |
| Python (venv) | 3.12.10 |
| FastAPI / Pydantic | 0.162.0 / 2.14.1 |
| Image dasar | `python:3.12-slim` |
| Endpoint health | `GET /health` |

Reproduksi:

```powershell
venv\Scripts\python.exe -m pytest
venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

## 3. Kontrak API

Kontrak implementasi lengkap — skema respons, field wajib/opsional, batasan, contoh request, dan kontrak error — dipisahkan ke **[`api-contract.md`](api-contract.md)** agar tidak duplikatif.

Ringkasan: 5 endpoint bisnis (`text`, `image`, `phone`, `financial`, `data-breach`) + `GET /health`, memakai `AnalysisResponse`/`EmergencyResponse`, dengan `official_contact` yang hanya berasal dari whitelist bank.

## 4. Hasil pengujian input → output

### 4.1 Analisis teks (+ kontak bank)

Request:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/analyze/text `
  -F "text_content=Halo, ini BCA. Akun Anda diblokir, kirim OTP sekarang ke http://bca-verifikasi.xyz"
```

Respons: **HTTP 200**, ±6,9 s

```json
{
  "risk_score": 90,
  "risk_category": "Sangat Tinggi",
  "scam_type": "Phishing / Smishing / Vishing",
  "reasons": [
    "Pesan mengaku berasal dari BCA tanpa verifikasi identitas pengirim.",
    "Pesan mengklaim akun diblokir untuk menciptakan urgensi dan paksaan.",
    "Meminta kode OTP yang bersifat rahasia dan tidak boleh dibagikan kepada siapa pun.",
    "Mengarahkan ke URL mencurigakan (http://bca-verifikasi.xyz) yang bukan domain resmi BCA.",
    "Permintaan mengirim OTP melalui link adalah indikasi pencurian data akun (phishing)."
  ],
  "recommendations": [
    "Jangan klik link atau mengakses URL yang disebutkan dalam pesan.",
    "Jangan memberikan kode OTP kepada siapa pun, termasuk pihak yang mengaku dari bank.",
    "Hubungi BCA melalui nomor telepon resmi atau cabang terdekat untuk memastikan status akun.",
    "Blokir nomor pengirim dan laporkan pesan tersebut kepada bank atau pihak berwajib.",
    "Jika sudah mengklik link atau memberikan OTP, segera ganti password dan laporkan ke bank."
  ],
  "official_contact": {
    "name": "Bank BCA (Bank Central Asia)",
    "phone": "1500888",
    "whatsapp": null
  }
}
```

Catatan: `official_contact` berasal dari whitelist `Bank_Call_Senter_Final.json`, bukan dari LLM.

### 4.2 Analisis gambar

Request:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/analyze/image `
  -F "platform=WhatsApp" -F "image=@bukti.png;type=image/png"
```

Respons: **HTTP 200**, ±4,1 s (contoh gambar uji tanpa teks)

```json
{
  "risk_score": 5,
  "risk_category": "Rendah",
  "scam_type": "Tidak ada indikasi penipuan",
  "reasons": [
    "Gambar tidak mengandung teks, URL, nomor telepon, atau elemen visual yang teridentifikasi.",
    "Teks pengguna hanya menyebutkan 'Platform: WhatsApp' tanpa isi pesan atau konten lainnya.",
    "Tidak ada permintaan OTP, transfer uang, atau ancaman pemblokiran yang terlihat."
  ],
  "recommendations": [
    "Jangan memberikan kode OTP atau data pribadi kepada siapa pun melalui WhatsApp.",
    "Verifikasi identitas pengirim melalui saluran resmi sebelum merespons pesan.",
    "Blokir dan laporir kontak yang mencurigakan langsung dari aplikasi WhatsApp."
  ],
  "official_contact": null
}
```

Catatan: endpoint gambar tidak melakukan OCR di server, sehingga `official_contact` selalu `null`.

### 4.3 Analisis nomor telepon

Request:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/analyze/phone `
  -H "Content-Type: application/json" `
  -d "{\"phone_number\":\"081234567890\"}"
```

Respons: **HTTP 200**, ±9,8 s

```json
{
  "risk_score": 85,
  "risk_category": "Tinggi",
  "scam_type": "Penipuan Kurir / Marketplace",
  "reasons": [
    "Nomor telepon terdaftar di GetContact dengan nama profil 'Kak Depi - Penipuan Tiktok Shop'.",
    "Nama profil secara langsung mengidentifikasi nomor ini sebagai terkait penipuan di platform TikTok Shop.",
    "Tidak ada tag tambahan yang ditemukan, namun nama profil sudah cukup sebagai indikator penipuan."
  ],
  "recommendations": [
    "Jangan menerima panggilan atau pesan dari nomor ini.",
    "Blokir nomor +6281234567890 segera.",
    "Jangan memberikan informasi pribadi, kode OTP, atau melakukan pembayaran kepada nomor ini.",
    "Laporkan nomor ini ke platform TikTok Shop dan pihak berwajib.",
    "Hapus semua obrolan atau kontak terkait nomor ini."
  ],
  "official_contact": null
}
```

Catatan: contoh ini `null` karena profil GetContact tidak menyebut bank. Bila profil memuat nama bank yang ada di whitelist, kontak otomatis terisi (diuji di `tests/test_phone_service.py`).

### 4.4 Emergency finansial

Request:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/emergency/financial `
  -F "bank_korban=BCA" -F "platform_kejadian=WhatsApp" -F "tanggal_kejadian=2026-10-27" `
  -F "tujuan_transaksi=Pembelian barang" -F "nomor_rekening_penipu=1234567890" `
  -F "nominal_kerugian=1500000" -F "nama_institusi_penipu=Toko Online Palsu" `
  -F "kronologi_user=Saya transfer untuk barang yang tidak pernah dikirim." `
  -F "bukti_transfer=@bukti.png;type=image/png"
```

Respons: **HTTP 200**, ±16,4 s

```json
{
  "ai_kronologi": "I. DATA PELAPOR (KORBAN)\n- Platform / Kanal Kejadian: WhatsApp\n- Waktu Kejadian: 2026-10-27\n\nII. DATA TERLAPOR (PELAKU)\n- Nama Institusi / Pengakuan Pelaku: Toko Online Palsu\n- Rekening / Kontak Pelaku: 1234567890\n\nIII. RINCIAN KRONOLOGI KEJADIAN\n1. Kejadian terjadi melalui platform WhatsApp pada tanggal 2026-10-27.\n2. Korban melakukan transfer sebesar Rp 1.500.000,00 untuk tujuan pembelian barang.\n3. Barang yang dibeli tidak pernah dikirim oleh Toko Online Palsu.",
  "langkah_penanganan": [
    {
      "title": "Hubungi Call Center Bank BCA",
      "description": "Segera hubungi layanan pelanggan BCA untuk melaporkan transaksi mencurigakan, meminta pembekuan rekening jika memungkinkan, dan meminta bukti transaksi resmi untuk pelaporan lanjutan."
    },
    {
      "title": "Simpan Bukti Digital",
      "description": "Tangkap layar (screenshot) semua percakapan di WhatsApp, bukti transfer, dan nomor rekening pelaku (1234567890) sebagai bukti penting untuk pelaporan ke pihak berwajib."
    },
    {
      "title": "Laporkan ke Polisi / Satreskrim",
      "description": "Ajukan laporan resmi ke Kepolisian Republik Indonesia (Polri), khususnya Satreskrim, atau gunakan aplikasi LAKSA untuk pelaporan kejahatan siber dan pencurian dana."
    },
    {
      "title": "Blokir Kontak Pelaku",
      "description": "Blokir nomor WhatsApp dan rekening penipu untuk mencegah komunikasi lebih lanjut dan upaya penipuan berulang terhadap korban."
    },
    {
      "title": "Laporkan ke Platform dan Kominfo",
      "description": "Laporkan akun WhatsApp dan toko online palsu ke platform penyedia layanan serta Kementerian Komunikasi dan Informatika (Kominfo) untuk tindakan pemblokiran akun atau situs."
    }
  ],
  "official_contact": {
    "name": "Bank BCA (Bank Central Asia)",
    "phone": "1500888",
    "whatsapp": null
  }
}
```

Catatan: `bank_korban` di luar whitelist (mis. `Bank Gaib`) menghasilkan `official_contact: null`, meskipun LLM mengembalikan kontak.

### 4.5 Emergency kebocoran data

Request:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/emergency/data-breach `
  -F "jenis_data=Data pribadi (nama, email)" -F "tanggal_kejadian=2026-10-27" `
  -F "platform_kejadian=Instagram" -F "tindakan_pelaku=Meminta OTP" `
  -F "status_akses=Masih bisa diakses" -F "kronologi_user=Akun saya diambil alih." `
  -F "bukti_percakapan=@bukti.png;type=image/png"
```

Respons: **HTTP 200**, ±16,1 s

```json
{
  "ai_kronologi": "I. DATA PELAPOR (KORBAN)\n- Platform / Kanal Kejadian: Instagram\n- Waktu Kejadian: 2026-10-27\n\nII. DATA TERLAPOR (PELAKU)\n- Nama Institusi / Pengakuan Pelaku: Tidak disebutkan\n- Rekening / Kontak Pelaku: Tidak disebutkan\n\nIII. RINCIAN KRONOLOGI KEJADIAN\n1. Kejadian terjadi melalui platform Instagram pada tanggal 2026-10-27.\n2. Pelaku melakukan tindakan meminta OTP kepada korban.\n3. Data pribadi korban, yaitu nama dan email, terlibat dalam insiden ini.\n4. Korban melaporkan bahwa akunnya telah diambil alih oleh pelaku.\n5. Terkait status akses, akun korban masih bisa diakses.",
  "langkah_penanganan": [
    {
      "title": "Segera Amankan Akun Instagram",
      "description": "Ganti password akun Instagram segera dan aktifkan verifikasi dua langkah (Two-Factor Authentication) untuk mencegah akses tidak sah lebih lanjut."
    },
    {
      "title": "Jangan Bagikan Kode OTP",
      "description": "Hindari memberikan kode OTP atau kode verifikasi kepada siapa pun, termasuk pihak yang mengaku dari tim support Instagram, karena pelaku sering menggunakan teknik ini untuk mengambil alih akun."
    },
    {
      "title": "Laporkan ke Platform Instagram",
      "description": "Gunakan fitur laporan di aplikasi Instagram atau kunjungi Instagram Help Center untuk melaporkan akun yang dicurigai melakukan penipuan dan mencurigai telah mengambil alih akun Anda."
    },
    {
      "title": "Laporkan ke Satgas Saber atau Polisi Siber",
      "description": "Ajukan laporan resmi melalui situs resmi Satgas Saber (sabersiber.id) atau ke kantor polisi terdekat untuk penanganan hukum terkait pelanggaran data pribadi dan penambangan akun."
    },
    {
      "title": "Pantau Aktivitas Akun",
      "description": "Periksa riwayat login dan aktivitas akun Instagram secara berkala untuk mendeteksi adanya tindakan mencurigakan lainnya atau perubahan data pribadi tanpa izin."
    }
  ],
  "official_contact": null
}
```

## 5. Pengujian negatif (HTTP riil)

Semua baris di bawah adalah respons nyata dari container `cegahscam-ai` pada 2026-10-28 (sesi 11:03 dan 11:19), bukan hasil mock. Latensi ±0 detik karena validasi berhenti sebelum memanggil OpenRouter/GetContact.

| Kasus | Request | Status | Respons aktual |
|---|---|---|---|
| `text_content` tidak dikirim | `POST /analyze/text` tanpa field | **422** | `{"detail":[{"type":"missing","loc":["body","text_content"],"msg":"Field required", …}]}` |
| `text_content` > 10.000 char | 10.001 karakter `"a"` | **422** | `{"detail":[{"type":"string_too_long","loc":["body","text_content"],"msg":"String should have at most 10000 characters","ctx":{"max_length":10000}, …}]}` |
| Nomor telepon tidak valid | `{"phone_number":"abc"}` | **422** | `{"detail":[{"type":"value_error","loc":["body","phone_number"],"msg":"Value error, Format nomor telepon tidak valid (contoh: 081234567890).", …}]}` |
| `nominal_kerugian` negatif | `-5` | **422** | `{"detail":[{"type":"greater_than_equal","loc":["body","nominal_kerugian"],"msg":"Input should be greater than or equal to 0","ctx":{"ge":0.0}, …}]}` |
| File bukan gambar | `x.txt` (`text/plain`) | **400** | `{"detail":"File harus berupa gambar (JPG, PNG, atau WEBP)."}` |
| Gambar > 15 MB | 15 MB + 1 byte (`image/png`) | **413** | `{"detail":"Ukuran gambar maksimal 15MB."}` |
| Bukti wajib tidak dikirim | `/emergency/financial` tanpa `bukti_transfer` | **422** | `{"detail":[{"type":"missing","loc":["body","bukti_transfer"],"msg":"Field required", …}]}` |

Jalur `408`/`500`/`502` belum diuji lewat HTTP karena butuh kondisi khusus (API key kosong, sesi GetContact kedaluwarsa, atau upstream timeout). Jalur tersebut baru diverifikasi lewat `pytest` dengan jaringan di-mock — lihat §6.

## 6. Pengujian otomatis

Perintah: `venv\Scripts\python.exe -m pytest` → **64 passed**.

| File | Fokus |
|---|---|
| `tests/test_data_loader.py` | Ranking alias bank, URL/karakter khusus, `aliases` manual, data hilang, pencocokan `knowledge_base_cegahscam.json` (`min_keywords=3`) |
| `tests/test_ai_service.py` | API key kosong, timeout, 401, JSON cacat, MIME/ukuran gambar, override kontak |
| `tests/test_phone_service.py` | Kredensial hilang/rusak/tidak lengkap, sesi GetContact 401, enrichment kontak |
| `tests/test_routes.py` | 5 endpoint sukses, 422/400/413, kontak per endpoint, kontak palsu ditimpa, simulasi `MOCK_MODE=True` |
| `tests/test_auth.py` | Autentikasi X-API-Token, 401 tanpa/salah token, fail-closed 500 jika token belum diatur, healthcheck terbuka |

Semua akses jaringan di-mock (`AIService._call_openrouter`, `PhoneService._gtc_call`), sehingga test dapat dijalankan offline.

## 7. Kebijakan `official_contact`

Aturan lengkap ada di [`api-contract.md` §4](api-contract.md); tabel di bawah adalah kasus yang diuji otomatis (`tests/test_data_loader.py`).

- Opsional di skema, tetapi **wajib terisi** bila bank terdeteksi ada di `app/data/Bank_Call_Senter_Final.json`.
- Sumber bukti: `text_content`, `bank_korban`, dan profil/tag GetContact.
- Nilai dari LLM selalu ditimpa; bank di luar whitelist → `null`.
- Peringkat: alias sama persis → alias paling spesifik → alias terpanjang → kemunculan paling awal → nama terpendek.

| Input | Hasil |
|---|---|
| `bank mandiri` | Bank Mandiri |
| `mandiri taspen` | Bank Mandiri Taspen |
| `bca` | Bank BCA (Bank Central Asia) |
| `bca syariah` | Bank BCA Syariah |
| `bca dan bri` | Bank BCA (kemunculan paling awal) |
| `bank gaib` | `null` |

## 8. Catatan & limitasi

- Jawaban LLM tidak deterministik: skor dan redaksi `reasons` dapat berubah antar pemanggilan.
- Latensi terukur ±4–24 detik, tergantung endpoint dan model; service berjalan satu proses.
- `/analyze/phone` bergantung pada sesi GetContact di `app/data/gtc_credentials.json`; sesi kedaluwarsa → 502 sampai file diperbarui.
- Service tidak menyimpan riwayat dan tidak membuat PDF; itu tanggung jawab backend utama aplikasi web.
- Semua respons di atas adalah hasil nyata dari container `cegahscam-ai` pada tanggal pengujian, bukan contoh rekaan.

## 9. Evaluasi Kualitas Deteksi & Eksperimen Optimasi (Fase 2)

Dieksekusi pada **2026-11-03** menggunakan skrip [`eval/evaluate_phase2.py`](eval/evaluate_phase2.py) terhadap sampel berstrata (*stratified sample*, `seed=42`, $N=25$ baris mewakili seluruh 11 kategori dari 1.164 baris dataset master) melalui pemanggilan langsung ke OpenRouter (`nvidia/nemotron-3.5-super-vl:free`).

### 9.1 Desain Eksperimen: Baseline vs Optimasi Knowledge Base (`min_keywords=3`)
- **Baseline (`use_knowledge_base=False`):** Analisis murni mengandalkan `REASONING_PROMPT`.
- **Optimasi (`use_knowledge_base=True`, `min_keywords=3`):** Menyuntikkan referensi `kategori_pola` dan `sop_mitigasi` dari [`app/data/knowledge_base_cegahscam.json`](app/data/knowledge_base_cegahscam.json) ke instruksi sistem apabila teks pesan mencocokkan **minimal 3 kata kunci** unik pada suatu kategori scam (mengabaikan kategori `"Bukan Scam"`).
- **Validasi Presisi Aturan Kata Kunci pada Dataset Penuh (1.164 baris):** Aturan `min_keywords=3` mencocokkan 66 baris pada dataset penuh yang seluruhnya berlabel Scam (`1`) dan **0 baris Normal (`0`)** (0% *false trigger*).

### 9.2 Hasil Metrik Kuantitatif

 Evaluasi dihitung pada dua skenario ambang sesuai karakteristik dataset:
- **Skenario A (Strict, $N=25$):** Seluruh baris berlabel `1` (termasuk *Spam Tidak Terklasifikasi* dan *Promo Provider*) dihitung sebagai Scam.
- **Skenario B (Fraud-Only, $N=21$):** Mengecualikan 4 baris *Spam/Promo* komersial agar mengukur murni kinerja deteksi penipuan/kejahatan siber.

#### Ambang Skor Risiko $\ge 40$ (Kategori Sedang–Sangat Tinggi)
| Skenario | Konfigurasi | TP | FP | TN | FN | Precision | Recall | F1-Score | Accuracy |
|---|---|---|---|---|---|---|---|---|---|
| **Skenario A (Strict)** | Baseline | 13 | 0 | 7 | 5 | **100,00%** | 72,22% | 83,87% | 80,00% |
| **Skenario A (Strict)** | **Optimasi KB (`min=3`)** | **14** | **0** | **7** | **4** | **100,00%** | **77,78%** | **87,50%** | **84,00%** |
| **Skenario B (Fraud-Only)** | Baseline | 11 | 0 | 7 | 3 | **100,00%** | 78,57% | 88,00% | 85,71% |
| **Skenario B (Fraud-Only)** | **Optimasi KB (`min=3`)** | **12** | **0** | **7** | **2** | **100,00%** | **85,71%** | **92,31%** | **90,48%** |

#### Ambang Skor Risiko $\ge 50$ & $\ge 60$ (Kategori Tinggi–Sangat Tinggi)
| Skenario | Konfigurasi | TP | FP | TN | FN | Precision | Recall | F1-Score | Accuracy |
|---|---|---|---|---|---|---|---|---|---|
| **Skenario A (Strict)** | Baseline | 12 | 0 | 7 | 6 | **100,00%** | 66,67% | 80,00% | 76,00% |
| **Skenario A (Strict)** | **Optimasi KB (`min=3`)** | **13** | **0** | **7** | **5** | **100,00%** | **72,22%** | **83,87%** | **80,00%** |
| **Skenario B (Fraud-Only)** | Baseline | 10 | 0 | 7 | 4 | **100,00%** | 71,43% | 83,33% | 80,95% |
| **Skenario B (Fraud-Only)** | **Optimasi KB (`min=3`)** | **11** | **0** | **7** | **3** | **100,00%** | **78,57%** | **88,00%** | **85,71%** |

### 9.3 Analisis Dampak Optimasi, False Negative, & Latensi
1. **Zero False Positive (Precision 100%):** Seluruh 7 pesan percakapan normal memperoleh `risk_score` 5–10 (`Rendah`). Tidak ada percakapan normal yang salah dituduh sebagai penipuan.
2. **Dampak Nyata Optimasi Knowledge Base (`min_keywords=3`):**
   - Pada kasus *Modus Penipuan Transfer Uang* (Row 892: instruksi transfer singkat ke rekening BNI tanpa tautan phishing), model **Baseline** hanya memberikan `risk_score: 30` (*False Negative*). Setelah **Optimasi KB** menyuntikkan pola kecocokan 3 kata kunci (`bni`, `rekening`, `transfer`), skor naik menjadi **`risk_score: 65` (`Tinggi`)** (*True Positive*) beserta rekomendasi verifikasi telepon langsung sesuai SOP.
   - Skor keyakinan pada *Penawaran Pinjol Ilegal* (Row 32) meningkat dari `70` menjadi `80` (`Sangat Tinggi`), dan pada *Undian Palsu* (Row 749) meningkat dari `80` menjadi `90`.
3. **Analisis Sisa False Negative (FN):**
   - **2 baris Spam Komersial (Row 566 & Row 977):** Berisi promo diskon restoran lawas dan penawaran NSP operator tanpa unsur pencurian data/uang (`risk_score` 10 dan 25).
   - **2 baris Instruksi Transfer Sangat Pendek (Row 119 & Row 932):** Hanya memuat kalimat singkat nomor rekening Bank Mandiri tanpa konteks percakapan sebelumnya (`risk_score` 15 dan 30). Karena guardrail anti-halusinasi melarang LLM mengarang konteks, skor dijaga rendah–sedang namun sistem tetap berhasil mengekstrak `official_contact` Bank Mandiri (`14000`) dan menyarankan verifikasi identitas penerima.
4. **Latensi Model:**
   - Median (*p50*) latensi Baseline: **14,00 detik** (rata-rata *mean*: **19,91 detik**; rata-rata pada baris dengan injeksi KB: **29,45 detik** karena fluktuasi antrean tier gratis OpenRouter). Menegaskan pentingnya syarat timeout klien backend utama $\ge 90$ detik.
