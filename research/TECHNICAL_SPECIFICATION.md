# Spesifikasi Teknis & Dokumentasi: RECELL-AI

**Proyek:** RECELL-AI (Mesin Penyortir/Grading Baterai Second-Life Otomatis)
**Kompetisi:** KIWIE Korea 2026

## 1. Tinjauan Sistem (System Overview)
RECELL-AI adalah sistem otomasi yang dirancang untuk mengklasifikasi kondisi baterai Li-ion tipe 18650 dengan menggabungkan dua metode pengujian: analisis elektrikal dan *computer vision*. Mesin ini menjembatani kesenjangan dalam ekonomi sirkular dengan menyediakan solusi pengelolaan limbah elektronik (e-waste) yang terdesentralisasi, otomatis, dan dapat diandalkan.

## 2. Arsitektur Teknis
Sistem ini menggunakan arsitektur pengendali ganda (Dual-Controller):
*   **Mikrokontroler (STM32F411 BlackPill):** 
    *   Akuisisi data sensor (Tegangan, Arus) dengan resolusi ADC 12-bit dan teknik *oversampling*.
    *   Kendali pergerakan (Konveyor, mekanisme pendorong Motor Stepper).
    *   Implementasi uji pelepasan daya menggunakan metode **Constant Current Load**.
*   **Prosesor Edge AI (NVIDIA Jetson Orin Nano):**
    *   Inspeksi visual (Computer Vision) berbasis akselerasi perangkat keras.
    *   Deteksi anomali fisik (Karat, Penyok, Kerusakan bungkus/wrapper).
    *   Integrasi klasifikasi AI (XGBoost) berbasis data *time-series* dari STM32.
    *   Antarmuka Pengguna (HMI) berstandar industri.

## 3. Metodologi Penilaian (Grading)
### 3.1. Penilaian Elektrik (State of Health - SoH)
*   **Metode:** Beban Arus Konstan (Constant Current Load).
*   **Proses:** Memberikan beban tinggi singkat (~1C / 2 Ampere) selama 2 detik untuk mengukur *Voltage Drop* dan *Internal Resistance*.
*   **Kecerdasan Buatan:** Memasukkan nilai-nilai tersebut ke dalam model regresi XGBoost yang dilatih dengan dataset baterai NASA.
*   **Output:** Persentase Kesehatan Baterai (SoH).

### 3.2. Penilaian Visual (Integritas Fisik)
*   **Metode:** Computer Vision menggunakan model YOLOv8n yang dijalankan di atas TensorRT.
*   **Target Deteksi:** 
    *   Karat (Rust) / Korosi.
    *   Penyok (Dents) / Deformasi fisik.
    *   Kerusakan label / Kebocoran bahan kimia.

### 3.3. Klasifikasi Akhir
Berdasarkan perpaduan skor Visi dan Elektrik, baterai dikategorikan menjadi:
*   **Grade A / B (Reusable):** Layak untuk digunakan kembali dalam aplikasi kehidupan kedua (contoh: Bank daya/Powerbank, sepeda listrik, sistem UPS).
*   **Grade R (Recycle):** Sel baterai yang mengalami degradasi parah atau kerusakan fisik ekstrim. Disarankan untuk segera dihancurkan dan didaur ulang secara kimiawi.

## 4. Komponen Perangkat Keras Utama
| Komponen | Fungsi Utama |
| :--- | :--- |
| **STM32F411CEU6** | Mikrokontroler utama untuk elektronika analog dan pengaturan waktu (timing) motor. |
| **NVIDIA Jetson Orin Nano** | Komputasi AI tingkat tinggi, penyimpanan data, dan *Graphical User Interface* (GUI). |
| **Rangkaian Constant Current** | MOSFET dan Op-Amp (atau INA219) untuk pengosongan baterai yang akurat. |
| **Sensor Proximity (IR)** | Mendeteksi posisi baterai di atas konveyor (Stasiun Uji dan Stasiun Ejector). |
| **Motor Stepper** | Mekanisme pendorong baterai yang presisi (Ejector & Pendorong Sensor). |
| **Sistem Konveyor** | Transportasi baterai yang digerakkan oleh motor DC lambat ber-PWM. |
| **Modul Kamera** | Akuisisi citra (gambar) beresolusi tinggi untuk disuapkan ke algoritma YOLO. |

## 5. Kebutuhan Perangkat Lunak
*   **Firmware:** C++ (Arduino IDE / STM32duino Core). Menggunakan library `ArduinoJson`.
*   **Sistem Operasi Master:** Ubuntu 22.04 (NVIDIA JetPack 6.x).
*   **Inferensi AI:** Python 3.10+, TensorRT (YOLOv8), XGBoost (Data Elektrik).
*   **Antarmuka Visual (GUI):** PyQt5 dengan PyQTGraph (mendukung akselerasi OpenGL) untuk pemantauan grafik *real-time*.
*   **Komunikasi Antar-Perangkat:** USB Serial (CDC) dengan baud rate 115200.

## 6. Fungsionalitas Khusus Industri
*   **Digital Battery Passport:** Setiap sel baterai yang diuji akan menghasilkan file sertifikat digital dalam format PDF. Dokumen ini berisi foto baterai, ID unik, nilai tegangan/arus, estimasi SoH, dan Grade Akhir (sebagai bukti ketertelusuran / *traceability*).
