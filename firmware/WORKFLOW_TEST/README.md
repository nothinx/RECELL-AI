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

**Perintah idle:**
| Perintah | Fungsi |
|----------|--------|
| `START`  | 1 siklus **MANUAL** (konfirmasi ENTER tiap step) |
| `AUTO`   | 1 siklus **OTOMATIS** (tanpa ENTER; grade dari ambang tegangan) |
| `AUTO n` | Jalankan `n` siklus otomatis berturut (uji throughput) |
| `STATUS` | Print pembacaan semua sensor (cek pinout) |
| `HELP` / `?` | Bantuan |

**Abort kapan saja:** ketik `ABORT` di serial atau tekan tombol EMERGENCY (PB5).
Di mode AUTO, jika satu siklus abort, seluruh batch `AUTO n` berhenti.

### Mode AUTO

Sama persis dengan alur MANUAL, tapi semua gate ENTER dilewati (jeda kecil
`AUTO_STEP_PAUSE_MS`, tetap abort-aware). Karena tak ada operator, **grade
diputuskan otomatis**: `v_load >= GRADE_A_MIN_V` (default 3.60 V) → Grade A,
selain itu Grade B/R. Kolom CSV `grade_source` = `AUTO_THRESH` (vs `MANUAL`).

### Proteksi stepper (debounce confirm-hit)

`pushStepperUntilLimit` kini mengonfirmasi limit: saat pin LOW, dibaca ulang
`LIMIT_CONFIRM_SAMPLES` (=4) kali tiap `LIMIT_CONFIRM_US` (=200µs). Hanya jika
**semua LOW** baru dianggap kena → glitch/noise 1 sampel tidak menghentikan
stepper di tengah jalan. Arming HIGH (boleh berhenti hanya setelah pernah BEBAS)
tetap dipertahankan supaya tidak instant-stop kalau carriage sudah menempel limit.

### Logging per-step

Tiap step mencetak baris snapshot `.snap[TAG] LimDrain=.. LimSort=.. IR1=.. IR2=..
EMG=.. V=.. I=.. T=..` (TAG = AWAL/STEP1/DRAIN/SORTING/AKHIR) untuk audit kondisi
sensor di tiap titik tanpa perlu `STATUS` manual.

## Alur Siklus

| # | Step | Trigger lanjut |
|---|------|----------------|
| 1 | Konveyor maju → otomatis stop di IR Drain (PB14) | otomatis |
| 2 | Stepper drain **dorong maju sampai kena Limit Drain** (PB15) | Enter / AUTO |
| 3 | Ukur SoH: Vopen, lalu DAC=4095 beban 2s, 10 sampel V/I, Rint, ΔT | Enter / AUTO |
| 4 | Stepper drain **mundur sampai kena limit (home)** (PB15) | Enter / AUTO |
| 5 | **Keputusan grade** (tepat setelah ukur+retract) | MANUAL: `1`/`2` · AUTO: ambang |
| 6 | Konveyor jalan & sortir sesuai grade | Enter / AUTO |
| 6A | (Grade A) stop di IR Sorting (PB12) **+0.2s settle** → eject ke Limit Sort (PA4) → **mundur sampai kena limit home** | Enter |
| 6B | (Grade B/R) Konveyor jalan 5 detik → stop | — |
| 7 | Cetak baris CSV, counter++, balik ke IDLE | otomatis |

> **Limit ganda per pin:** tiap stepper punya 2 limit switch (tiap ujung) diparalel
> di 1 pin. Maju berhenti di limit ujung satu, mundur berhenti di limit ujung lain —
> keduanya lewat logika `armed` + debounce confirm-hit yang sama.
>
> **IR2 settle (Grade A):** setelah IR Sorting terdeteksi, konveyor sengaja jalan
> `IR2_SETTLE_MS` (0.2s) lagi agar baterai pas di posisi ejector sebelum berhenti —
> mencegah posisi terlalu mepet/nabrak ujung saat eject.

## Format Log CSV

Header dicetak sekali saat boot. Per siklus selesai → 1 baris `CSV,...`.

```
CSV_HEADER,cycle_id,timestamp_ms,mode,grade_manual,grade_source,v_open_V,v_load_V,i_load_A,r_internal_mOhm,temp_init_C,temp_final_C,temp_delta_C,t_to_ir1_ms,t_push_ms,t_measure_ms,t_retract_ms,t_to_ir2_or_end_ms,abort_reason
CSV,1,12450,MANUAL,A,MANUAL,3.980,3.752,1.430,159.4,28.50,31.20,2.70,2310,1820,2100,720,1840,OK
CSV,2,28760,AUTO,B,AUTO_THRESH,3.520,3.210,1.380,224.6,28.60,29.10,0.50,2280,1790,2100,710,5120,OK
```

Kolom baru: `mode` (MANUAL/AUTO), `grade_source` (MANUAL/AUTO_THRESH),
`v_open_V` (tegangan open-circuit sebelum beban), `r_internal_mOhm`
(≈ (Vopen−Vload)/Iload, indikator SoH).

Untuk ekstrak ke file:
```bash
# Tangkap log serial → filter baris CSV → siap dipakai pandas
cat serial.log | grep -E '^(CSV|CSV_HEADER),' > sortir_data.csv
```

`abort_reason` = `OK` jika siklus mulus, atau alasan singkat (`EMERGENCY_BUTTON`, `ABORT_USER`, `ABORT_AT_GRADE_DECISION`) untuk troubleshooting.

> **Catatan:** push-to-limit kini **tanpa batas step** — stepper jalan sampai limit
> benar-benar kena (berhenti hanya via EMERGENCY/ABORT/limit). Kalau carriage start
> **menempel limit**, ia jalan dulu sampai limit **LEPAS** (HIGH stabil
> `RELEASE_CONFIRM_STEPS` step) → baru berhenti saat limit **KENA lagi** (limit lawan).
> Debounce "lepas" ini mencegah bounce di titik awal dianggap sudah-lepas-lalu-kena.
> Pulse stepper = 50 µs (cepat).

## Konfigurasi

Edit konstanta di blok `PARAMETER WORKFLOW` di `WORKFLOW_TEST.ino`:

| Konstanta | Default | Keterangan |
|-----------|---------|------------|
| `CONVEYOR_SPEED` | 30 | PWM 0-255 (pelan untuk testing; produksi pakai 100) |
| `STEPPER_PULSE_US` | 50 | Setengah pulsa stepper (µs) — lebih cepat |
| `RELEASE_CONFIRM_STEPS` | 40 | Limit harus LEPAS (HIGH) stabil sekian step sebelum boleh berhenti di limit lawan |
| `IR2_SETTLE_MS` | 200 | Grade A: konveyor lanjut 0.2s setelah IR2 baru stop |
| `DAC_LOAD_VALUE` | 4095 | Beban DAC (0-4095) |
| `LOAD_HOLD_MS` | 2000 | Tahan beban (ms) |
| `SOH_SAMPLE_COUNT` | 10 | Jumlah sampel V/I |
| `END_OF_LINE_MS` | 5000 | Timer Grade B/R |
| `LIMIT_CONFIRM_SAMPLES` | 4 | Sampel LOW beruntun untuk konfirmasi limit |
| `LIMIT_CONFIRM_US` | 200 | Jeda antar sampel konfirmasi (µs) |
| `GRADE_A_MIN_V` | 3.60 | Ambang v_load utk Grade A di mode AUTO |
| `AUTO_STEP_PAUSE_MS` | 400 | Jeda antar-step di mode AUTO |

## Catatan Pin & Arah

- **Wiring stepper drain ↔ sorting tertukar di lapangan vs label CSV.** Pin `PIN_STP_DRAIN_*` di kode sudah diluruskan ke motor fisikal yang benar (lihat komentar di file).
- **Arah DIR:** `LOW` = maju ke arah limit switch, `HIGH` = mundur. Kalau di tempat user terbalik, swap nilai `LOW`/`HIGH` di 4 call site `pushStepperUntilLimit` / `moveStepperSteps` di `runCycle()`.
- Verifikasi semua di atas pakai `firmware/STEPPER_TEST/` dulu.
