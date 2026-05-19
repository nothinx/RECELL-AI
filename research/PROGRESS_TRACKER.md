# RECELL-AI: Progress Tracker

Gunakan daftar ini untuk melacak apa saja yang sudah kita kerjakan dan apa yang harus dikerjakan selanjutnya. Kita akan memperbarui (mencentang) daftar ini seiring berjalannya waktu.

## ✅ TAHAP 1: PERENCANAAN & ARSITEKTUR (SELESAI)
- [x] Diskusi konsep awal & alur sistem.
- [x] Pembuatan struktur repositori (*Monorepo*).
- [x] Desain Arsitektur Software (Master-Slave: Jetson + STM32).
- [x] Desain Protokol Komunikasi (JSON via USB-Serial).
- [x] Pembuatan spesifikasi AI & Hardware.
- [x] Inisialisasi GitHub Repository.

## ✅ TAHAP 2: PEMBUATAN KERANGKA PROGRAM / BOILERPLATE (SELESAI)
- [x] Program STM32: State Machine untuk Konveyor lambat, 2 Proximity, 2 Stepper, dan Beban CC (`RECELL_STM32.ino`).
- [x] Program Jetson: Skrip utama yang mengatur orkestrasi/alur (`main.py`).
- [x] Program Jetson: Modul pembuat Digital Battery Passport / PDF (`passport_generator.py`).
- [x] Program Jetson: Kerangka GUI menggunakan PyQt5 (`ui_dashboard.py`).
- [x] Program Jetson: Mode Simulasi & CLI terintegrasi untuk *testing* hardware.

## ⏳ TAHAP 3: AI DEVELOPMENT - NASA DATASET (SEGERA DIMULAI)
- [ ] Unduh NASA Battery Dataset dari Kaggle.
- [ ] Buat skrip *Data Preprocessing* Python (Jupyter Notebook) untuk mem-parsing data NASA.
- [ ] Ekstraksi fitur (Tegangan awal, tegangan beban, durasi).
- [ ] Training model XGBoost/RandomForest untuk prediksi SoH.
- [ ] Integrasikan model XGBoost yang sudah dilatih ke `main.py`.

## ⏳ TAHAP 4: AI DEVELOPMENT - COMPUTER VISION (SEGERA DIMULAI)
- [ ] Kumpulkan foto baterai.
- [ ] Anotasi foto (Normal, Rust, Dent).
- [ ] Train YOLOv8n.
- [ ] Ekspor ke TensorRT (`.engine`).
- [ ] Integrasi model asli ke `main.py`.

## ⏳ TAHAP 5: HARDWARE INTEGRATION & TESTING (MENUNGGU ELEKTRIKAL)
- [ ] Masukkan pinout asli dari tim elektrikal ke file `RECELL_STM32.ino`.
- [ ] Uji coba komunikasi serial Jetson <-> STM32 dengan perangkat asli.
- [ ] Kalibrasi *delay* Stepper Motor (Sensor & Ejector).
- [ ] Kalibrasi pembacaan tegangan (Voltage Divider) STM32.
- [ ] Uji coba konveyor dan Proximity 1 & 2.

## ⏳ TAHAP 6: FINALISASI & KIWIE PREP
- [ ] Hubungkan UI PyQt5 dengan data asli (hilangkan mock data).
- [ ] Uji coba *End-to-End* (Taruh baterai -> Keluar PDF Passport).
- [ ] Dokumentasi & Video Presentasi.
