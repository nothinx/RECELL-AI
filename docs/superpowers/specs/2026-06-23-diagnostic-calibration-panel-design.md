# Panel Diagnostik & Kalibrasi Lengkap

Tanggal: 2026-06-23 · Status: disetujui, siap implementasi (butuh 1× reflash STM32).

## Masalah
Wiring IR/stepper berkali-kali jadi tersangka (IR tertukar, stepper diam/STEP_TIMEOUT)
tapi tak ada alat untuk membaca state sensor live atau menggerakkan tiap aktuator
sendiri-sendiri. Kalibrasi sekarang hanya speed konveyor + pulsa stepper. Stepper
juga tak punya ramp akselerasi → kemungkinan stall saat start (penyebab STEP_TIMEOUT).

## Tujuan
Panel kalibrasi jadi panel diagnostik penuh: baca SEMUA input (sensor) live,
kontrol SEMUA output manual, set SEMUA parameter motion+ukur runtime — plus ramp
akselerasi stepper sebagai fix akar "stepper diam".

## 1. Format telemetri (firmware → Jetson)
Mode diag: panel buka → `{"cmd":"START_DIAG"}`; tutup → `{"cmd":"STOP_DIAG"}`.
Saat aktif, firmware broadcast snapshot tiap ~200 ms (5 Hz, ~250 B → aman di 115200):

```json
{"status":"DIAG",
 "ir_d":1,"ir_s":0,"ir_b":0,      // IR drain/sorting/backup (1=objek)
 "lim_d":0,"lim_s":0,             // limit drain/sorting (1=tersentuh)
 "emg":0,                         // emergency (1=ditekan)
 "v":3.852,"i":0.021,             // INA226 V / A
 "t_obj":25.3,"t_amb":24.8,       // MLX90614 °C
 "rdy":{"ina":1,"mlx":1,"dac":1}, // I2C terdeteksi
 "st":"IDLE","dac":0,             // state machine + beban DAC aktif?
 "cfg":{"spd":25,"pul":50,"ramp":600,"rstep":300,"load":4095,"dsmp":40,"dper":50,"ir2":0}}
```
`"status":"DIAG"` dipakai ulang → `serial_listener` cukup tambah satu cabang,
route ke panel (bukan log siklus). `cfg` echo = konfirmasi nilai yang BENAR aktif.

## 2. Command firmware baru
- `START_DIAG` / `STOP_DIAG` → toggle `diagMode`. Balas `DIAG_ON`/`DIAG_OFF`.
- `JOG_STEPPER {which:"drain"|"sort", dir:"fwd"|"rev", steps:N}` → jog MENTAH N step,
  TANPA limit (isolasi motor/driver dari sensor). Balas `JOG_DONE`.
- `HOME_STEPPER {which}` → dorong ke limit lalu mundur ke home (pakai
  `moveStepperUntilLimit`, tanpa DAC). Balas `HOME_DONE` / `STEP_TIMEOUT`.
- `CONVEYOR {dir:"fwd"|"rev"|"stop"}` → konveyor manual (rev = LPWM). Balas status.
- `DAC_LOAD {on:1|0, value:N}` → beban DAC manual on/off + nilai. Balas `DAC_SET`.

## 3. Parameter tunable (SET_CONFIG + calibration.json)
Lama: `conveyor_speed`, `step_pulse_us`. Baru:
- `ramp_start_us` (pulsa awal lambat), `ramp_steps` (panjang ramp) — ramp akselerasi.
- `dac_load` (0-4095), `discharge_samples`, `discharge_period` — pengukuran.
- `ir2_settle` (ms) — delay sebelum stop di sorting.
Timeout keamanan TIDAK di-expose (tetap default firmware).
Const firmware `DAC_LOAD_VALUE`/`DISCHARGE_SAMPLES`/`DISCHARGE_PERIOD_MS` jadi variabel.

## 4. Ramp akselerasi stepper (fix akar STEP_TIMEOUT)
`moveStepperUntilLimit` + jog mentah pakai lebar pulsa per-step:
`pulse(i) = rampStartPulseUs - (rampStartPulseUs - stepPulseUs) * min(i,rampSteps)/rampSteps`
→ mulai pelan (anti-stall) lalu cepat. Default start 600 µs, ramp 300 step.

## 5. UI — dialog kalibrasi ber-tab (layar sentuh)
`CalibrationDialog` jadi 3 tab tombol besar:
- **Monitor**: indikator live tiap sensor (IR/limit hijau-abu, V/I/suhu angka,
  rdy flags, state). Update via signal `on_diag`.
- **Parameter**: spinbox semua param §3 + Apply (live) / Simpan.
- **Manual**: tombol jog stepper (mentah ±, ke-limit) ×2, konveyor maju/mundur/stop,
  DAC on/off+nilai, RESET, STOP semua.

Data flow: buka dialog → `master.start_diag()` → firmware stream → `serial_listener`
deteksi `status=="DIAG"` → `bridge.diag_signal` → tab Monitor. Tutup → `stop_diag()`.

## Testing
- Firmware: kompilasi bersih; uji jog mentah stepper drain & sort gerak; HOME kena limit;
  diag stream muncul saat START_DIAG.
- Jetson: `serial_listener` route DIAG tanpa mengganggu siklus; SET_CONFIG kirim
  semua field baru; reconnect aman.
- UI: tab Monitor update live; Manual menggerakkan aktuator yang benar; Parameter
  Apply→`cfg` echo berubah; tutup dialog → stream berhenti.

## Risiko
- Reflash wajib (firmware berubah). Satu kali, dibundel semua.
- Jog mentah tanpa limit bisa menabrak ujung bila step terlalu banyak → default step kecil
  (mis. 200) & operator awasi. Tandai di UI.
