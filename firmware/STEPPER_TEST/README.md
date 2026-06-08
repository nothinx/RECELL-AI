# STEPPER_TEST

Program **mini fokus** untuk verifikasi:
1. Pasangan pin PUL/DIR yang dipakai sudah benar (tidak tertukar dengan stepper lain).
2. Arah `DIR=LOW` vs `DIR=HIGH` mana yang **maju ke arah limit switch** vs **mundur**.

Hasilnya dipakai untuk seting akhir di `WORKFLOW_TEST.ino`.

## Pinout yang Dipakai (sesuai CSV "Konfirmasi Pinout Final")

| Label di menu | PUL | DIR | CSV name |
|---|---|---|---|
| Stepper **A** | PB9 | PB0 | "DRAIN" |
| Stepper **B** | PA8 | PA3 | "SORT"  |

Limit switch (active LOW, INPUT_PULLUP):
| Label | Pin  | CSV name |
|-------|------|----------|
| LIMIT 1 | PB15 | "LIMIT DRAIN" |
| LIMIT 2 | PA4  | "LIMIT SORT"  |

> Label "A/B" sengaja netral — supaya operator observasi motor fisik mana yang bergerak saat tiap pin pair dipakai, tanpa terprasangka "ini drain / ini sort".

## Cara Pakai

1. Flash ke STM32F411 BlackPill.
2. Buka Serial Monitor: **115200 baud, Newline**.
3. Pilih menu:

```
 1. Stepper A , DIR=LOW , 200 step
 2. Stepper A , DIR=HIGH, 200 step
 3. Stepper B , DIR=LOW , 200 step
 4. Stepper B , DIR=HIGH, 200 step
 5. Stepper A -> LIMIT 1 (PB15), DIR=LOW
 6. Stepper A -> LIMIT 1 (PB15), DIR=HIGH
 7. Stepper B -> LIMIT 2 (PA4),  DIR=LOW
 8. Stepper B -> LIMIT 2 (PA4),  DIR=HIGH
 9. Stepper A MAJU-MUNDUR kontinu (2 limit @ PB15)
 m. Stepper B MAJU-MUNDUR kontinu (2 limit @ PA4)
 +. Lebih CEPAT   -. Lebih PELAN  (atur live)
 c. Custom (pilih stepper / dir / step)
 s. Status sensor (limit, IR, emergency)
```

### Mode MAJU-MUNDUR (opsi 9 / m)

Tiap stepper punya **2 limit switch (1 di tiap ujung) yang diparalel ke 1 pin**
(active LOW). MCU hanya tahu "ada limit kena", tidak tahu ujung mana. Logika:

- **Stop instan** saat pin LOW + `armed` → balik arah (toggle DIR).
- **Re-arm dengan debounce:** `armed` baru `true` lagi setelah pin **HIGH stabil
  `REARM_CLEAR_STEPS` (=40) langkah beruntun**. Setiap bounce LOW mereset hitungan.
  Ini mencegah pantulan kontak saat switch lepas dipakai sebagai "kena limit baru"
  (penyebab balik-arah di tempat → mematahkan limit).
- Limit **tidak pernah diabaikan** (tak ada blind-backoff), jadi aman walau jarak
  antar-limit pendek.
- Tiap kena limit: log `[LIMIT] kena #N setelah X step (DIR=...) -> balik arah`.
- Pengaman: kalau 1 leg > `STEPS_MAX_TO_LIMIT` (25000) tanpa kena limit →
  berhenti + warning (cek wiring/polaritas limit).

Stop kapan saja: **ENTER** atau tombol **EMERGENCY**.

### Atur kecepatan (`+` / `-`)

`PULSE_US` = lebar setengah-pulsa (default **150 us** → ~3300 step/s). Tekan `+`
mempercepat (pulse −20us), `-` memperlambat (pulse +20us), batas 40–800 us.
Kalau motor **stall / bunyi tapi diam** saat cepat → tekan `-` beberapa kali.

4. **Tekan ENTER** atau **EMERGENCY** kapan saja untuk stop.

## Yang Harus Dicatat

Untuk konfigurasi WORKFLOW_TEST nanti, dari hasil test isi tabel ini:

| Pertanyaan | Jawaban |
|---|---|
| Saat pilih `1` (Stepper A, DIR=LOW), motor fisik mana yang bergerak? | drain / sort |
| Saat pilih `1` (DIR=LOW), arahnya maju ke limit switch atau mundur? | maju / mundur |
| Saat pilih `5`, apakah berhenti karena LIMIT 1 (PB15) atau jalan terus sampai max? | LIMIT 1 / MAX |
| Saat pilih `3` (Stepper B, DIR=LOW), motor fisik mana yang bergerak? | drain / sort |
| Saat pilih `3` (DIR=LOW), arahnya maju ke limit switch atau mundur? | maju / mundur |
| Saat pilih `7`, apakah berhenti karena LIMIT 2 (PA4) atau jalan terus sampai max? | LIMIT 2 / MAX |

Hasil 6 jawaban di atas menentukan:
- Apakah `PIN_STP_DRAIN_*` di WORKFLOW_TEST mesti pakai PA8/PA3 atau PB9/PB0.
- Apakah parameter `dir` untuk `pushStepperUntilLimit` mesti `LOW` atau `HIGH`.

## Flash via CLI

```bash
arduino-cli compile --fqbn STMicroelectronics:stm32:GenF4:pnum=BLACKPILL_F411CE STEPPER_TEST.ino
arduino-cli upload  --fqbn STMicroelectronics:stm32:GenF4:pnum=BLACKPILL_F411CE -p /dev/ttyUSB0 STEPPER_TEST.ino
```
