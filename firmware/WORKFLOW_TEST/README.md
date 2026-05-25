# WORKFLOW_TEST

Firmware validasi **alur sortir penuh tanpa Jetson**, dijalankan step-by-step lewat keyboard. Output dilog sebagai 1 baris CSV per siklus — langsung copy-paste dari serial monitor ke file `.csv` untuk dipakai program otomatis & training model SoH.

> **Beda dari firmware lain:**
> - `RECELL_STM32/` — firmware produksi (terima command JSON dari Jetson).
> - `HARDWARE_TEST/` — uji **per-komponen** lewat menu bernomor.
> - `STEPPER_TEST/` — uji **gerakan stepper saja** (verifikasi pinout & arah DIR).
> - `WORKFLOW_TEST/` — uji **alur penuh** end-to-end, semua step manual confirm.
>
> **Disarankan jalankan `STEPPER_TEST` dulu** untuk konfirmasi pin mapping & arah DIR sebelum pakai WORKFLOW_TEST.

## Flash

- **Board:** STM32F411CEU6 (BlackPill)
- **Arduino IDE:** *Tools → Board → STM32 MCU based boards → Generic STM32F4 → BlackPill F411CE*
- **Library wajib:** `INA226_WE`, `Adafruit MLX90614 Library`, `Adafruit MCP4725` (install dari Library Manager)

CLI:
```bash
arduino-cli compile --fqbn STMicroelectronics:stm32:GenF4:pnum=BLACKPILL_F411CE WORKFLOW_TEST.ino
arduino-cli upload  --fqbn STMicroelectronics:stm32:GenF4:pnum=BLACKPILL_F411CE -p /dev/ttyUSB0 WORKFLOW_TEST.ino
```

## Cara Pakai

1. Buka Serial Monitor: **115200 baud**, line ending = **Newline**.
2. Saat `[IDLE]`, ketik `START` → siklus berjalan.
3. Tekan **Enter** di setiap prompt `[STEP n]` untuk lanjut.
4. Saat `[STEP 6]` minta grade: ketik **`1`** = Grade A (eject) atau **`2`** = Grade B/R (end-of-line).
5. Selesai → baris CSV dicetak otomatis → kembali ke `[IDLE]` untuk baterai berikutnya.

**Perintah idle lain:**
| Perintah | Fungsi |
|----------|--------|
| `START`  | Mulai 1 siklus workflow |
| `STATUS` | Print pembacaan semua sensor (cek pinout) |
| `HELP` / `?` | Bantuan |

**Abort kapan saja:** ketik `ABORT` di serial atau tekan tombol EMERGENCY (PB5).

## Alur Siklus

| # | Step | Trigger lanjut |
|---|------|----------------|
| 1 | Konveyor maju → otomatis stop di IR Drain (PB14) | otomatis |
| 2 | Stepper drain dorong ke Limit Drain (PB15) | Enter |
| 3 | Ukur SoH: DAC=4095, beban 2 detik, 10 sampel V/I, ΔT MLX90614 | Enter |
| 4 | Stepper drain mundur 1000 step | Enter |
| 5 | Konveyor maju lagi | Enter |
| 6 | Tunggu input grade | ketik `1` atau `2` |
| 7A | (Grade A) Stop di IR Sorting (PB12) → push ke Limit Sort (PA4) → retract 2500 | Enter |
| 7B | (Grade B/R) Konveyor jalan 5 detik → stop | Enter |
| 8 | Cetak baris CSV, counter++, balik ke IDLE | otomatis |

## Format Log CSV

Header dicetak sekali saat boot. Per siklus selesai → 1 baris `CSV,...`.

```
CSV_HEADER,cycle_id,timestamp_ms,grade_manual,v_load_V,i_load_A,temp_init_C,temp_final_C,temp_delta_C,t_to_ir1_ms,t_push_ms,t_measure_ms,t_retract_ms,t_to_ir2_or_end_ms,abort_reason
CSV,1,12450,A,3.752,1.430,28.50,31.20,2.70,2310,1820,2100,720,1840,OK
CSV,2,28760,B,3.210,1.380,28.60,29.10,0.50,2280,1790,2100,710,5120,OK
```

Untuk ekstrak ke file:
```bash
# Tangkap log serial → filter baris CSV → siap dipakai pandas
cat serial.log | grep -E '^(CSV|CSV_HEADER),' > sortir_data.csv
```

`abort_reason` = `OK` jika siklus mulus, atau alasan singkat (`EMERGENCY_BUTTON`, `ABORT_USER`, `STEPPER_MAX_REACHED`, `ABORT_AT_GRADE_DECISION`) untuk troubleshooting.

## Konfigurasi

Edit konstanta di blok `PARAMETER WORKFLOW` di `WORKFLOW_TEST.ino`:

| Konstanta | Default | Keterangan |
|-----------|---------|------------|
| `CONVEYOR_SPEED` | 30 | PWM 0-255 (pelan untuk testing; produksi pakai 100) |
| `STEPPER_PULSE_US` | 400 | Setengah pulsa stepper |
| `STEPPER_MAX_TO_LIMIT` | 5000 | Batas aman push-to-limit |
| `STEPPER_RETRACT_DRAIN` | 1000 | Mundur sensor drain |
| `STEPPER_RETRACT_SORT` | 2500 | Mundur ejector sorting |
| `DAC_LOAD_VALUE` | 4095 | Beban DAC (0-4095) |
| `LOAD_HOLD_MS` | 2000 | Tahan beban (ms) |
| `SOH_SAMPLE_COUNT` | 10 | Jumlah sampel V/I |
| `END_OF_LINE_MS` | 5000 | Timer Grade B/R |

## Catatan Pin & Arah

- **Wiring stepper drain ↔ sorting tertukar di lapangan vs label CSV.** Pin `PIN_STP_DRAIN_*` di kode sudah diluruskan ke motor fisikal yang benar (lihat komentar di file).
- **Arah DIR:** `LOW` = maju ke arah limit switch, `HIGH` = mundur. Kalau di tempat user terbalik, swap nilai `LOW`/`HIGH` di 4 call site `pushStepperUntilLimit` / `moveStepperSteps` di `runCycle()`.
- Verifikasi semua di atas pakai `firmware/STEPPER_TEST/` dulu.
