# Spec A — Firmware Produksi v2 (Jetson-master, mekanik WORKFLOW_TEST) + Sinkronisasi GUI

**Tanggal:** 2026-06-15
**Status:** Disetujui untuk perencanaan
**File terdampak:** `firmware/RECELL_STM32/RECELL_STM32.ino`, `jetson/src/main.py`

---

## 1. Tujuan

Menyatukan dua aset yang selama ini terpisah:

- **WORKFLOW_TEST** — firmware yang paling teruji di lapangan (pin terkoreksi, arah DIR benar,
  logika stepper return-to-home + debounce limit, siklus end-to-end abort-aware).
- **GUI Jetson + `main.py`** — punya grading AI canggih (YOLO vision + XGBoost SoH), logging,
  passport, plot discharge live — tetapi firmware produksinya (`RECELL_STM32.ino`) memakai pin
  lama yang belum diverifikasi dan memiliki celah penanganan emergency.

Hasil: **Jetson tetap jadi master**, firmware produksi ditulis ulang agar memakai mekanik gerakan
WORKFLOW_TEST yang valid, dengan protokol JSON yang sudah dipahami `main.py` tidak berubah.

## 2. Arsitektur

- **Jetson (`main.py`) = master.** Mengorkestrasi sekuens, menghitung grade (YOLO + XGBoost),
  logging, passport.
- **STM32 (`RECELL_STM32.ino`) = kumpulan primitive gerakan teruji.** Tiap perintah JSON =
  satu gerakan blocking utuh; Jetson tidak pernah mengatur pulsa per-step.
- **Keputusan grade WAJIB lewat Jetson** (vision hanya ada di Jetson). Setelah pengukuran,
  firmware mengembalikan data dan menunggu perintah routing berikutnya dari Jetson.

### Caveat yang diterima (didokumentasikan, bukan bug)
- Tombol **STOP di GUI tidak menghentikan** perintah blocking yang sedang berjalan.
- **Tombol EMERGENCY fisik (PB5) adalah satu-satunya safety-stop sejati.** Ia dicek di dalam
  setiap loop gerakan stepper dan loop sampling pengukuran.

## 3. Yang diadopsi dari WORKFLOW_TEST ke firmware produksi

| Aspek | Lama (`RECELL_STM32.ino`) | Baru (dari WORKFLOW_TEST) |
|---|---|---|
| Pin stepper **drain** (PUL/DIR) | PB9 / PB0 | **PA8 / PA3** |
| Pin stepper **sort** (PUL/DIR) | PA8 / PA3 | **PB9 / PB0** |
| Arah DIR | HIGH = maju | **LOW = maju ke limit, HIGH = mundur ke home** |
| Enable stepper | toggle PA7/PA6 (EN) | **tidak di-toggle** — driver always-on (EN di-tie hardware); PA7/PA6 = input encoder |
| Conveyor stop | EN tetap HIGH | **EN LOW saat stop** |
| Push-to-limit | ada ceiling `STEPPER_MAX_STEPS` 25000 | **tanpa ceiling**, berhenti hanya via limit-kena/EMERGENCY |
| Logika stepper | armed sederhana | **armed + RELEASE_CONFIRM_STEPS + confirm-hit debounce** (anti-bounce di titik start) |
| Pulse width | 400 µs | **50 µs** |
| Init INA226 | hanya `init()` | **`setResistorRange(0.002, 10.0)` + `setMeasureMode(CONTINUOUS)`** (tanpa ini arus salah baca) |

Pinout selengkapnya (identik konstanta WORKFLOW_TEST):

```
LIMIT_DRAIN=PB15  LIMIT_SORTING=PA4  IR_DRAIN=PB14  IR_SORTING=PB12  IR_BACKUP=PB13  EMERGENCY=PB5
CONVEYOR: EN=PA5  RPWM=PA1  LPWM=PA2
STEPPER DRAIN: PUL=PA8  DIR=PA3      STEPPER SORT: PUL=PB9  DIR=PB0
DAC_GATE=PB1   I2C: SDA=PB7 SCL=PB6
I2C addr: INA226=0x40  MLX90614=0x5A  MCP4725=0x62   INA shunt=0.002Ω max=10A
```

## 4. Yang DIPERTAHANKAN dari firmware produksi (GUI bergantung padanya)

- **Streaming discharge curve.** `APPLY_SENSOR_AND_MEASURE` tetap men-stream `DISCHARGE_SAMPLE`
  (40 × 50 ms ≈ 2 s) selama beban aktif, lalu mengirim `MEASUREMENT_DONE`. Plot live di dashboard
  bergantung pada ini.
- **Vocabulary command & status JSON tidak berubah** → parser `main.py` tetap cocok 1:1.

## 5. Kontrak protokol (TIDAK berubah dari implementasi saat ini)

### Perintah Jetson → STM32 (`{"cmd": "..."}`)
| Command | Aksi firmware | Status balasan |
|---|---|---|
| `RESET` | clear EMERGENCY → STATE_IDLE | `RESET_OK` |
| `MOVE_TO_PROX_1` | conveyor maju, tunggu IR_DRAIN (non-blocking) | `AT_PROX_1` |
| `APPLY_SENSOR_AND_MEASURE` | push drain→ukur→retract (blocking) | stream `DISCHARGE_SAMPLE` + `MEASUREMENT_DONE` |
| `MOVE_TO_PROX_2` | conveyor maju, tunggu IR_SORTING (non-blocking) | `AT_PROX_2` |
| `EJECT_A` | sort stepper push ke limit → mundur ke home (blocking) | `EJECTED_A` |
| `MOVE_TO_END` | conveyor maju 5 s → stop | `DROPPED_B` |
| `STOP_CONVEYOR` | stop conveyor → STATE_IDLE | `STOPPED` |

### Status STM32 → Jetson (`{"status": "...", ...}`)
- `BOOT_OK` (saat boot)
- `AT_PROX_1`, `AT_PROX_2`
- `DISCHARGE_SAMPLE` → fields: `t_ms, volt, curr, temp`
- `MEASUREMENT_DONE` → fields: `volt, curr, v_resting, temp_pre, temp_post, temp_delta`
- `EJECTED_A`, `DROPPED_B`, `STOPPED`, `RESET_OK`
- `EMERGENCY_STOP` (saat PB5 ditekan)

### Detail `APPLY_SENSOR_AND_MEASURE` (urutan internal firmware)
1. Push stepper drain ke limit (DIR LOW).
2. Baca `v_resting` (INA226 bus voltage open-circuit) + `temp_pre` (MLX).
3. DAC gate HIGH, DAC=4095 (beban maksimal).
4. Loop 40× (50 ms): baca v/i/temp, akumulasi, kirim `DISCHARGE_SAMPLE`. **Cek PB5 tiap iterasi** —
   jika ditekan, hentikan beban & abort ke EMERGENCY.
5. Rata-rata → `volt`, `curr`; hitung `temp_post`, `temp_delta`.
6. DAC=0, gate LOW.
7. Retract stepper drain ke home (DIR HIGH).
8. Kirim `MEASUREMENT_DONE`.

(Catatan: `v_drop = v_resting − volt` dan `internal_r` dihitung di **Jetson**, seperti sekarang.)

## 6. Perbaikan celah EMERGENCY

**a. Recovery dari deadlock.** Firmware tetap masuk `STATE_EMERGENCY` saat PB5 ditekan dan
memblokir semua perintah kecuali yang mengandung `RESET`. Perbaikan di sisi Jetson:
**`main.py` mengirim `RESET` otomatis di awal `run_automated_cycle()`** sebelum perintah gerak
pertama. Operator cukup melepas tombol fisik lalu menekan START lagi — mesin pulih sendiri tanpa
power-cycle. (Jika tombol fisik masih ditekan, loop firmware langsung masuk EMERGENCY lagi → aman.)

**b. Pengukuran abort-aware.** Loop sampling 2 detik kini mengecek PB5 tiap sampel (lihat §5 langkah 4),
sehingga E-stop fisik dapat menghentikan pengukuran yang sedang berjalan.

## 7. Perubahan di Jetson (`main.py`) — minimal

- Tambah `self.send_command("RESET")` di awal `run_automated_cycle()` (sebelum `MOVE_TO_PROX_1`).
- (Opsional kosmetik) abaikan/handle `RESET_OK` & `BOOT_OK` untuk indikator — tidak wajib.
- **Tidak ada** perubahan parser, callback, atau UI logic lain.

## 8. Verifikasi / testing

- Kompilasi firmware: `arduino-cli compile --fqbn STMicroelectronics:stm32:GenF4:pnum=BLACKPILL_F411CE`.
- `python main.py --sim` tetap jalan (protokol tidak berubah) — sanity check parser tidak rusak.
- Cek silang manual: tabel command↔handler & status↔parser tetap 1:1.
- Uji hardware: jalankan `STEPPER_TEST` dulu untuk konfirmasi pin & arah DIR (sesuai catatan
  WORKFLOW_TEST), baru siklus penuh via GUI.

## 9. Di luar cakupan (YAGNI)

- Mode standalone/AUTO di firmware produksi — itu tugas WORKFLOW_TEST, tidak diduplikasi.
- Membuat tombol RESET terpisah di GUI — auto-RESET di awal siklus sudah cukup.
- Mengubah algoritma grading atau model AI.
- Membuat STOP GUI bisa menginterupsi perintah blocking (diterima sebagai caveat; safety = PB5 fisik).
