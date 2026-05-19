# Spesifikasi Protokol Komunikasi & Algoritma RECELL-AI

**Versi:** 1.0 (Draf Matang)
**Antarmuka:** USB-Serial (115200 bps)
**Format:** JSON (diakhiri dengan baris baru / newline)

---

## 1. Protokol Komunikasi (Skema JSON)

### 1.1. Jetson ke STM32 (Perintah / Commands)
Master (Jetson) mengontrol alur proses.

| Perintah | Parameter | Deskripsi |
| :--- | :--- | :--- |
| `PING` | Tidak ada | Pengecekan konektivitas (Heartbeat). |
| `START_SOH` | `{"duration": 5000}` | Memicu pengukuran Beban Arus Konstan selama X ms. |
| `MOVE_CONVEYOR` | `{"dir": 1, "dist": 100}` | Menggerakkan sabuk konveyor. |
| `SORT` | `{"grade": "A" \| "B" \| "R"}` | Memicu stepper penyortir ke keranjang tertentu. |
| `RESET` | Tidak ada | Mereset State Machine di STM32. |

**Contoh:** `{"cmd": "SORT", "grade": "A"}\n`

### 1.2. STM32 ke Jetson (Telemetri & Event)
Slave (STM32) melaporkan hasil pengukuran dan status penyelesaian tugas.

| Tipe Event | Kolom / Fields | Deskripsi |
| :--- | :--- | :--- |
| `STATUS` | `{"state": "IDLE" \| "BUSY" \| "ERROR"}` | Status STM32 saat ini. |
| `MEASUREMENT` | `{"v": 3.72, "i": 1.05, "t": 32.5}` | Tegangan, Arus, dan Suhu secara real-time. |
| `SOH_RESULT` | `{"soh": 85.2, "internal_r": 0.12}` | Hasil kalkulasi kesehatan baterai akhir. |
| `DONE` | `{"op": "SORT" \| "MEASURE"}` | Konfirmasi bahwa tugas telah selesai. |

**Contoh:** `{"type": "MEASUREMENT", "v": 3.8, "i": 1.0}\n`

---

## 2. Struktur Algoritma Penilaian (Multimodal)

Keputusan akhir merupakan perpaduan (*fusion*) antara **Computer Vision (CV)** dan **Analisis Kelistrikan (EA)**.

### 2.1. Skor Visual (VS) - YOLOv8n
*   **Input:** Frame dari kamera.
*   **Kelas:** `normal`, `rust` (karat), `dent` (penyok), `leaking` (bocor).
*   **Logika:** 
    *   Jika `leaking` atau `major_dent` terdeteksi -> **Grade R (Reject/Daur Ulang)** seketika.
    *   Jika `rust` terdeteksi -> Penalti pengurangan poin diterapkan pada Skor Visual.

### 2.2. Skor Elektrik (ES) - Beban Arus Konstan (Constant Current Load)
*   **Metode:** Pengosongan (discharge) sebesar 1C (sekitar 1-2A) untuk durasi singkat (misal 2 detik).
*   **Metrik:** Penurunan tegangan ($\Delta V$) digunakan untuk menghitung Resistansi Internal ($R_i = \Delta V / I$).
*   **Kalkulasi SoH:** Prediksi berbasis *Machine Learning* (XGBoost) pada kurva pengosongan.

### 2.3. Tabel Keputusan Grade Akhir
| Kondisi Visual | SoH (Elektrik) | Grade Akhir |
| :--- | :--- | :--- |
| Bersih | > 80% | **Grade A** |
| Karat/Penyok Minor | > 75% | **Grade B** |
| Bersih | 60% - 80% | **Grade B** |
| Kerusakan Mayor | Berapa pun | **Grade R (Reject)** |
| Bersih | < 60% | **Grade R (Reject)** |

---

## 3. Sistem State Machine (Gabungan)

1. **BOOT**: Handshake antara Jetson & STM32.
2. **FEEDING**: STM32 menggerakkan konveyor hingga sensor Proximity 1 mendeteksi baterai.
3. **INSPECTION_V**: Jetson menjalankan YOLOv8n -> Menyimpan Skor Visual (VS).
4. **INSPECTION_E**: STM32 menempelkan sensor dan menjalankan tes CC Load -> Mengirim hasil ke Jetson.
5. **DECISION**: Jetson memprediksi SoH menggunakan XGBoost dan mengkalkulasi Grade Akhir. Jetson membuat PDF Paspor Baterai.
6. **SORTING**: Jetson mengirim perintah `SORT {grade}` -> STM32 menggerakkan konveyor dan Stepper Ejector.
7. **FINISH**: Catat hasil ke Database lokal -> Ulangi siklus.
