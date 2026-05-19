# 📖 Cheatsheet: Rumus Pengujian & Kalkulasi SoH (State of Health)

Dokumen ini adalah referensi cepat (cheatsheet) mengenai dasar matematis dan kelistrikan yang digunakan di dalam *backend* RECELL-AI untuk mengklasifikasi kondisi internal baterai 18650.

---

## 1. Konsep Dasar Kapasitas (SOH)
State of Health (SOH) adalah persentase yang membandingkan kapasitas baterai saat ini dengan kapasitas aslinya saat baru keluar dari pabrik (Spesifikasi Pabrik).

*   **Rumus SOH Murni:** 
    $$ SOH (\%) = \left( \frac{Capacity_{current}}{Capacity_{nominal}} \right) \times 100 $$
*   *Contoh:* Baterai baru 2000 mAh. Jika saat dites hanya bisa menyimpan 1600 mAh, maka $SOH = (1600 / 2000) \times 100 = 80\%$.

## 2. Pendekatan XGBoost (AI) vs Pengujian Konvensional
Pengujian kapasitas murni memakan waktu 3-4 jam (harus men-*discharge* baterai dari penuh sampai kosong). 
**Inovasi RECELL-AI:** Kita hanya melakukan *discharge* beban berat (1C atau ~2A) selama **2 detik**. Perubahan tegangan dalam 2 detik ini diekstrak menjadi fitur matematis untuk ditebak oleh XGBoost.

### Fitur Utama (Diekstrak oleh Jetson/STM32)

#### A. Internal Resistance ($R_i$)
Semakin tua baterai, hambatan dalamnya ($R_i$) akan semakin besar. Ini menyebabkan baterai cepat panas dan tegangan cepat *drop* saat diberi beban.
*   **Rumus:**
    $$ R_i (\Omega) = \frac{V_{awal} - V_{beban}}{I_{beban}} $$
*   *Keterangan:*
    *   $V_{awal}$: Tegangan baterai saat tanpa beban (Open Circuit Voltage / OCV).
    *   $V_{beban}$: Tegangan baterai di detik ke-2 saat MOSFET dinyalakan.
    *   $I_{beban}$: Arus yang ditarik oleh sirkuit Constant Current.

#### B. Maximum Voltage Drop ($\Delta V_{max}$)
Besarnya penurunan tegangan absolut seketika saat beban diberikan.
*   **Rumus:**
    $$ \Delta V = V_{t=0} - V_{t=2s} $$

#### C. Temperature Delta ($\Delta T$) [Eksperimental]
Jika baterai jelek ($R_i$ besar), ia akan membuang energi menjadi panas ($P = I^2 \times R$).
*   **Rumus:**
    $$ \Delta T = T_{akhir} - T_{awal} $$

---

## 3. Rumus Konversi ADC STM32 (Oversampling)
Karena STM32F411 menggunakan ADC 12-bit (0 - 4095), rumus konversi dari nilai mentah (Raw) menjadi Voltage sesungguhnya adalah:

*   **Tegangan (V):**
    $$ Voltage = \left( \frac{ADC_{raw}}{4095.0} \right) \times V_{ref} \times Divider_{ratio} $$
    *   *Keterangan:* $V_{ref}$ biasanya 3.3V. $Divider_{ratio}$ adalah rasio dari rangkaian resistor pembagi tegangan (misal $R_1=10k\Omega, R_2=10k\Omega \rightarrow Ratio=2.0$).

*   **Arus (I):**
    $$ Current = \frac{Voltage_{shunt}}{R_{shunt}} \times OpAmp_{gain} $$
    *(Pengali akhir di kode disesuaikan dengan komponen INA219 / Op-Amp yang dirakit).*

---

## 4. Matriks Keputusan Akhir (Decision Matrix)

| Kondisi Fisik (YOLOv8) | Kondisi Internal (SOH) | Grade Akhir | Tindakan Konveyor |
| :--- | :--- | :--- | :--- |
| Bersih / Mulus | $> 80\%$ | **GRADE A** | Eject di Proximity 2 |
| Cacat Minor | $60\% - 80\%$ | **GRADE B** | Jatuh di ujung konveyor |
| Bersih / Mulus | $60\% - 80\%$ | **GRADE B** | Jatuh di ujung konveyor |
| Bocor / Penyok Parah | Berapa pun | **GRADE R (Reject)** | Jatuh di ujung konveyor |
| Berapa pun | $< 60\%$ | **GRADE R (Reject)** | Jatuh di ujung konveyor |
