# Panduan Visualisasi Data (Untuk Poster KIWIE & Karya Tulis Ilmiah)

Untuk perlombaan tingkat internasional seperti KIWIE, dewan juri tidak hanya melihat alat yang bergerak, tetapi juga **landasan ilmiah (scientific merit)** di baliknya. Gambar grafis (*graphs*) yang baik akan membuat poster Anda terlihat profesional dan meyakinkan.

Saya telah membuatkan *script* Python khusus di folder ini (`generate_graphs.py`) untuk memproduksi grafik berkualitas akademis (300 DPI). 

## Rekomendasi Grafik untuk Poster / Paper

Berikut adalah 3 jenis grafik utama yang **WAJIB** ada di poster atau presentasi Anda, yang ketiganya sudah diakomodasi oleh *script* yang saya buatkan:

### 1. Kurva Uji Pembebanan Elektrik (Discharge Curve)
*   **Visual:** Grafik garis (Line Chart) perbandingan antara Tegangan (V) vs Waktu (ms).
*   **Tujuan:** Menunjukkan bukti empiris bagaimana mikrokontroler STM32 Anda mengukur perbedaan antara baterai sehat (tegangan turun sedikit) dan baterai usang (tegangan *drop* drastis saat diberi beban konstan).
*   **Cara Pakai:** Jalankan *script*, ambil file `03_discharge_curve_sim.png`.

### 2. Scatter Plot: Pemetaan Keputusan "Multimodal AI" (Fusion)
*   **Visual:** Grafik titik-titik (*Scatter Plot*) dengan Sumbu X (SoH Elektrik) dan Sumbu Y (Skor Visi Fisik), dipisahkan oleh garis batas putus-putus.
*   **Tujuan:** Menjelaskan secara visual algoritma **Decision Engine** Anda. Ini menunjukkan keunikan invensi Anda: bahwa kecerdasan alat ini adalah gabungan antara *Computer Vision* (YOLO) dan Analisis Elektrik (XGBoost).
*   **Cara Pakai:** Jalankan *script*, ambil file `02_ai_fusion_scatter.png`. Juri akan sangat menyukai grafik analitik seperti ini.

### 3. Distribusi Hasil Penyortiran (Throughput Statistics)
*   **Visual:** Grafik Batang (Bar Chart) jumlah baterai Grade A, B, dan R.
*   **Tujuan:** Menunjukkan bahwa prototipe Anda telah diuji coba secara masal (*mass testing*), bukan hanya sekadar pajangan. Menandakan kesiapan alat ini untuk skala industri.
*   **Cara Pakai:** Jalankan *script*, ambil file `01_grade_distribution.png`.

## Cara Menghasilkan Grafik (Eksekusi)

Jika Anda sudah memiliki laptop dengan Python, Anda bisa langsung menjalankan ini untuk meng-*generate* contoh gambarnya sekarang juga:

```bash
cd research/paper_visuals
pip install pandas numpy matplotlib seaborn
python3 generate_graphs.py
```

Semua gambar akan otomatis muncul di folder `research/paper_visuals/output/`. Anda tinggal meletakkannya di Adobe Illustrator, CorelDraw, atau Canva saat membuat poster.

**Catatan:** *Script* ini dilengkapi fitur *mock data* (pembuat data pura-pura). Jika besok mesin Anda sudah berjalan dan menyimpan data log asli ke `.csv`, Anda bisa mengedit *script* ini untuk menggunakan data asli tersebut agar poster Anda 100% otentik!
