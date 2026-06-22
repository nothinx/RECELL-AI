# Checklist Trial Lapangan — RECELL-AI

Bawa ini saat uji di alat (Jetson + STM32). Centang berurutan; kalau satu langkah
gagal, beresin dulu sebelum lanjut.

---

## A. Persiapan (sekali)
- [ ] **Flash firmware** `firmware/RECELL_STM32/RECELL_STM32.ino` ke STM32 (lihat `DEPLOY_GUIDE_RECELL.md` Bagian 5). Tunggu "Done Uploading".
- [ ] Colok STM32 ke port USB **Jetson**.
- [ ] Di Jetson: `cd ~/RECELL-AI && git pull` (ambil kode + `best.pt` terbaru).
- [ ] **E-STOP terjangkau tangan** sebelum menyalakan motor. Uji tekan E-stop → motor mati.

## B. Nyalakan software
- [ ] `cd jetson/src && source ../../venv/bin/activate && python ui_dashboard.py`
- [ ] Pill header menyala: **STM32 = ONLINE**, **YOLO = ONLINE**, **CAMERA = ONLINE**, **XGB = ONLINE**.
- [ ] Di terminal UI muncul: `[Comm] Pushed calibration: {...}` dan dari STM32 `Calibration applied`.
- [ ] Kartu *Conveyor Control* menampilkan `Kalibrasi: speed 25 · pulse 50 µs`.

> STM32 OFFLINE? Cek `ls /dev/ttyUSB*`, sesuaikan `SERIAL_PORT` di `main.py`, pastikan user di grup `dialout`. Atau klik pill STM32 → pilih port.

## C. Kalibrasi kecepatan (F12)
- [ ] Tekan **F12** (atau tombol ⚙ KALIBRASI).
- [ ] **Jog Forward** → amati konveyor. Terlalu cepat? Turunkan *Conveyor speed*, Jog lagi. Ulang sampai pas.
- [ ] **■ Stop** (atau biarkan auto-stop 10 dtk).
- [ ] Stepper terlalu cepat/kasar saat siklus? Naikkan *Stepper pulse (µs)*.
- [ ] **Simpan & Tutup**. Label di kartu berubah sesuai nilai baru.

## D. Uji 1 baterai (siklus penuh)
- [ ] Taruh 1 baterai di awal konveyor.
- [ ] **START AUTO CYCLE**. Pantau progress bar & log per tahap.
- [ ] Konveyor **berhenti tepat di sensor** (tidak overshoot). Overshoot? → turunkan speed di F12, ulang.
- [ ] Stepper drain menekan sensor → balik ke home (tidak mentok/macet).
- [ ] Grafik discharge muncul, kartu V / A / SOH terisi.
- [ ] Grade keluar (A/B/R), passport PDF tergenerate (log "Passport Generated").
- [ ] Routing benar (A → eject bin; B/R → ujung konveyor).

## E. Uji aman
- [ ] Tekan **EMERGENCY STOP** di tengah siklus → semua motor mati, grade "ABORTED".
- [ ] Tekan **E-stop fisik** di tengah siklus → log `HARDWARE EMERGENCY STOP`, motor mati.

## F. Backup tuning (setelah angka pas)
- [ ] `git add jetson/calibration.json && git commit -m "calib: tuning mesin" && git push`

---

### Kalau ada masalah, catat:
- Gejala persis (cepat? overshoot? arah salah? macet?)
- Nilai kalibrasi saat itu (dari label kartu)
- Isi log terminal UI (baris error / status STM32)

Bawa catatan itu kembali untuk perbaikan tepat sasaran. Lihat tabel **Troubleshooting**
di `DEPLOY_GUIDE_RECELL.md` Bagian 7 untuk solusi cepat.
