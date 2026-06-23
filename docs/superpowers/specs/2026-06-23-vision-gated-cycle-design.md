# Vision-Gated Sorting Cycle (Approach B)

Tanggal: 2026-06-23 · Status: implemented (Jetson-only), perlu uji hardware.

## Masalah
Kamera C930e (top-down, **di hulu** stasiun ukur) selama ini hanya menghitung skor
grade — **tidak** mengendalikan konveyor. Penghentian 100% berbasis sensor IR di
firmware. Operator melihat "kamera mendeteksi tapi tak berhenti" (memang belum
di-wire) dan deteksi buruk karena foto diambil saat baterai bergerak (blur →
kemarin hanya kelas SOBEK yang terbaca).

## Tujuan
Masukkan kamera ke state machine siklus (dipegang Jetson) tanpa mengorbankan
presisi posisi: kamera memicu **stop inspeksi** (foto diam), IR tetap untuk
**stop presisi** di depan stepper.

## Layout fisik
`start → (lewat bawah kamera, hulu) → stasiun drain (IR PB14 + stepper, ukur) →
stasiun sorting (IR PB12) → eject A / jalan ke ujung (B/R)`

## Pembagian kendali
- **Vision (Jetson):** deteksi kehadiran baterai + grade cacat dari frame diam.
  Stop inspeksi via vision boleh sedikit over-shoot (cuma untuk foto).
- **IR lokal (firmware):** stop presisi di stasiun ukur & sorting (cepat, tanpa
  lag serial). TIDAK diubah.

## Sekuens baru (`run_automated_cycle`)
1. `RESET` + **flush buffer serial** (cegah status basi meng-clear `wait_flag`).
2. **[1] Inspeksi:** kalau baterai belum terlihat → `JOG_FWD` (maju bebas,
   firmware auto-stop 10s). Tunggu `battery_in_view` (≥`BATTERY_PRESENT_FRAMES`
   frame ada deteksi) atau timeout 8s → `STOP_CONVEYOR`. Settle 0.8s, reset
   hitungan cacat, akumulasi ~1.2s **frame diam** → simpan foto + grade.
3. **[2]** `MOVE_TO_PROX_1` → tunggu `AT_PROX_1` (IR lokal stop presisi).
4. **[3]** `APPLY_SENSOR_AND_MEASURE` → `MEASUREMENT_DONE` (SoH).
5. **[4]** grade = vision (langkah 2) + SoH → routing A/B/R (tak berubah).

## Tanpa reflash firmware
Semua primitif sudah ada: `JOG_FWD`, `STOP_CONVEYOR`, `MOVE_TO_PROX_1`,
`APPLY_SENSOR_AND_MEASURE`, `MOVE_TO_PROX_2`, `EJECT_A`, `MOVE_TO_END`.

## Catatan / risiko
- Stop presisi tetap bergantung IR PB14/PB12 sehat. Bug "lewat PROX 1" kemarin
  (IR ter-trigger dini) wajib dipastikan via log `[TX]`/`[RX]` saat uji.
- `battery_in_view` dari deteksi kelas apa pun; persistensi 3 frame buang noise.
- Mock-AI: gating dilewati.
