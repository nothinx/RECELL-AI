# Panduan Komprehensif Penyusunan Paper Ilmiah & Poster KIWIE

Dokumen ini adalah panduan lengkap (*blue-print*) untuk menyusun Karya Tulis Ilmiah (Paper) dan Desain Poster untuk kompetisi KIWIE 2026. Panduan ini dirancang untuk menonjolkan inovasi **Multimodal AI (Vision + Electrical)** dari proyek RECELL-AI.

---

## BAGIAN I: STRUKTUR KARYA TULIS ILMIAH (PAPER)

Untuk memenangkan penghargaan, paper Anda harus mengikuti struktur IMRaD (*Introduction, Methods, Results, and Discussion*).

### 1. Abstrak (Abstract)
*   **Konteks:** Limbah baterai Li-ion (e-waste) meningkat, namun daur ulang manual berbahaya dan tidak efisien.
*   **Invensi:** Memperkenalkan RECELL-AI, mesin penyortir otomatis menggunakan metode *Constant Current Load* (STM32) dan AI *Computer Vision* (Jetson Orin Nano).
*   **Hasil:** Sistem mampu memilah baterai ke dalam Grade A (Reusable), Grade B, dan R (Recycle) dengan akurasi tinggi secara *real-time*, meminimalisir intervensi manusia.

### 2. Pendahuluan (Introduction)
*   **Masalah (Problem Statement):** 
    *   Pengujian baterai menggunakan multimeter manual memakan waktu berminggu-minggu untuk skala industri.
    *   Bahaya fisik: Risiko korsleting atau baterai meledak jika baterai yang berkarat/bocor diuji secara listrik tanpa inspeksi visual terlebih dahulu.
*   **Kebaruan (Novelty):** Sebagian besar mesin hanya mengetes listriknya, atau hanya mengecek visualnya. RECELL-AI melakukan **Sensor Fusion**—menggabungkan YOLOv8n (AI Visual) dan XGBoost (AI Time-Series) dalam satu alur terotomatisasi.

### 3. Metodologi (Methodology)
*(Bagian ini menunjukkan tingkat kerumitan teknik mesin Anda)*
*   **Arsitektur Hardware:** Jelaskan model Master-Slave. Jetson sebagai pengambil keputusan tingkat tinggi, STM32 sebagai *real-time actuator* pembaca sensor.
*   **Protokol Mekanik:** Jelaskan urutan Sensor Konveyor -> Proximity 1 -> Stepper Pendorong Sensor -> Constant Current -> Proximity 2 -> Ejector.
*   **AI Vision Pipeline:** Jelaskan arsitektur YOLOv8n yang dikuantisasi dengan TensorRT untuk mendeteksi `rust`, `dent`, `leaking`.
*   **Electrical Pipeline:** Jelaskan bagaimana *Voltage Drop* ($\Delta V$) diukur dengan memberikan beban MOSFET 1C secara stabil, lalu menggunakan algoritma AI untuk memprediksi State of Health (SoH).

### 4. Hasil dan Pembahasan (Results & Discussion)
*(Gunakan 3 gambar dari `generate_graphs.py` di sini)*
*   **Pembahasan 1 (Discharge Curve):** Masukkan gambar `03_discharge_curve_sim.png`. Bahas bagaimana mikrokontroler mendeteksi perbedaan kemiringan antara baterai sehat dan baterai degradasi.
*   **Pembahasan 2 (AI Fusion Scatter Plot):** Masukkan gambar `02_ai_fusion_scatter.png`. Ini adalah **grafik paling penting**. Jelaskan bahwa baterai dengan kelistrikan bagus (SoH > 80%) BISA SAJA ditolak (Grade R) karena AI Visual menemukan karat parah. Grafik scatter plot membuktikan bahwa keputusan sistem sangat *robust* (tangguh).
*   **Pembahasan 3 (Digital Passport):** Jelaskan fitur pembuatan PDF otomatis sebagai bukti ketertelusuran industri (ISO 9001).

---

## BAGIAN II: DESAIN LAYOUT POSTER KIWIE (A0 / Portrait)

Poster harus mengundang juri untuk membaca tanpa membuat mereka bosan. Gunakan rasio 30% Teks, 40% Gambar/Grafik, 30% Ruang Kosong (*White Space*).

### Blok Atas (Header - 15%)
*   **Kiri/Kanan:** Logo KIWIE, Logo Institusi/Universitas/Tim.
*   **Tengah:** Judul Invensi dalam font tebal, besar, dan jelas (Misal: **RECELL-AI: Automated Multimodal Second-Life Battery Grading System**). Di bawah judul, tulis nama anggota tim.

### Blok Kiri (Masalah & Inovasi - 25%)
*   **Background (Bullet points):** 3 poin utama tentang krisis limbah baterai 18650. Tambahkan 1 foto ilustrasi tumpukan baterai bekas.
*   **Our Solution (RECELL-AI):** Sebutkan fitur unggulan (YOLOv8 Vision, Constant Current SoH, Digital Passport).

### Blok Tengah (Cara Kerja & Mesin - 35%)
*(Ini adalah daya tarik utama poster)*
*   **3D CAD Render:** Masukkan render gambar 3D mesin/konveyor Anda dalam ukuran besar di tengah. Tunjuk bagian-bagiannya dengan panah (Kamera, Stepper 1, Sensor Area, Stepper 2 Ejector).
*   **Flowchart Singkat:** Feed -> Visual Check (YOLO) -> Electrical Check (STM32) -> Fusion Decision -> Sort & Print PDF.

### Blok Kanan (Hasil Pengujian Ilmiah - 25%)
*   **Grafik 1 (Atas):** Masukkan `02_ai_fusion_scatter.png`. Beri *caption*: *"AI Decision Boundaries mapping visual integrity against electrical health."*
*   **Grafik 2 (Tengah):** Masukkan `03_discharge_curve_sim.png`. Beri *caption*: *"Empirical discharge curve differentiation using Constant Current."*
*   **Hasil Akhir (Bawah):** Masukkan cuplikan *screenshot* dari **Digital Battery Passport (PDF)** yang digenerate oleh sistem untuk menunjukkan produk akhir yang siap komersialisasi.

---

## BAGIAN III: PANDUAN MENGUBAH *MOCK DATA* KE *REAL DATA*

Saat perlombaan sudah dekat, Anda **wajib** mengubah data pura-pura di file `generate_graphs.py` dengan data uji coba mesin asli Anda.

**Langkah-langkah di `generate_graphs.py`:**
1. Buka file tersebut.
2. Cari fungsi `generate_mock_data()`.
3. Ganti isinya agar membaca file `.csv` dari Jetson menggunakan Pandas:

```python
def generate_mock_data():
    # HAPUS logika np.random, GANTI DENGAN:
    
    # 1. Jetson harus menyimpan log grading ke CSV setiap baterai selesai diuji
    # 2. Baca file tersebut:
    df = pd.read_csv('/path/to/real_machine_log.csv')
    
    # Pastikan CSV memiliki kolom: 'Battery_ID', 'Voltage_Drop', 'Internal_Resistance', 'SOH', 'Vision_Score', 'Final_Grade'
    return df
```

Dengan mengganti fungsi ini, ketika Anda menjalankan `python3 generate_graphs.py`, grafik yang keluar 100% adalah hasil nyata kinerja mesin Anda. Juri KIWIE sangat menghargai data autentik dari uji coba fisik perangkat!
