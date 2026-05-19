# Panduan Setup, Flashing, dan Deployment RECELL-AI

Dokumen ini adalah panduan lengkap (*Survival Guide*) untuk menyebarkan (*deploy*) seluruh kode yang telah kita buat ke perangkat keras fisik (Jetson Orin Nano dan STM32).

---

## 1. Remote Access ke Jetson via SSH

**Pertanyaan Anda:** *"Mungkin saya ke Jetson pakai SSH apakah bisa?"*
**Jawaban:** **Tentu saja BISA, TAPI ada catatannya.** 

Jetson berjalan dengan sistem operasi Ubuntu Linux. Anda bisa melakukan SSH untuk keperluan *coding*, *training* AI, atau sekadar menjalankan script CLI. Namun, karena program utama kita (`ui_dashboard.py`) menggunakan **GUI PyQt5**, program tersebut **tidak akan muncul di layar laptop Anda jika Anda hanya menggunakan SSH biasa**, karena SSH biasa tidak mentransfer tampilan grafis.

### Opsi A: SSH Biasa (Hanya untuk Coding & Training AI)
Gunakan ini jika Anda hanya ingin men-*download* kode dari GitHub dan melatih YOLO/XGBoost.
1. Sambungkan Jetson dan Laptop Anda ke WiFi yang sama.
2. Cari IP Jetson Anda (misal: `192.168.1.10`).
3. Buka Terminal/CMD di Laptop Anda:
   ```bash
   ssh username_jetson@192.168.1.10
   ```
4. Masukkan password Jetson. Anda sekarang berada di terminal Jetson.

### Opsi B: SSH + X11 Forwarding (Membuka GUI lewat SSH)
Jika Anda menggunakan Linux/Mac di laptop Anda, Anda bisa meneruskan tampilan GUI PyQt5 ke layar laptop Anda.
1. Jalankan koneksi SSH dengan *flag* `-X`:
   ```bash
   ssh -X username_jetson@192.168.1.10
   ```
2. Saat Anda menjalankan `python3 ui_dashboard.py` di terminal tersebut, jendelanya akan muncul di laptop Anda. *(Kekurangan: Sangat lambat dan lag, video kamera YOLO akan patah-patah).*

### Opsi C: Remote Desktop (SANGAT DIREKOMENDASIKAN)
Daripada repot dengan X11 Forwarding, install **NoMachine** atau **AnyDesk** di Jetson dan Laptop Anda. Ini memungkinkan Anda melihat *Desktop Ubuntu* Jetson secara penuh dan lancar dari laptop Anda, seolah-olah Anda menancapkan kabel HDMI.

---

## 2. Setup Lingkungan Jetson (Deployment)

Setelah Anda masuk ke Jetson (via SSH/Remote Desktop/HDMI langsung), ikuti langkah ini:

### Langkah 1: Kloning Repositori
```bash
cd ~
git clone https://github.com/nothinx/RECELL-AI.git
cd RECELL-AI/jetson
```

### Langkah 2: Buat Virtual Environment
Ini wajib agar instalasi *library* tidak merusak sistem Jetson bawaan.
```bash
sudo apt update
sudo apt install python3.10-venv python3-pip
python3 -m venv venv
source venv/bin/activate
```
*(Catatan: Setiap kali Anda masuk ke SSH baru, Anda WAJIB menjalankan `source venv/bin/activate` sebelum menjalankan script Python).*

### Langkah 3: Install Dependencies
```bash
pip install -r requirements.txt
```
*(Ingat: Untuk PyTorch/Torchvision, Anda mungkin perlu menginstalnya dari [NVIDIA Jetson Wheel](https://forums.developer.nvidia.com/t/pytorch-for-jetson/72048) agar CUDA aktif).*

### Langkah 4: Jalankan Program Utama
Pastikan Anda sedang menggunakan monitor langsung di Jetson atau Remote Desktop (Bukan sekadar SSH biasa).
```bash
python3 src/ui_dashboard.py
```

---

## 3. Flashing Firmware ke STM32 (Via Arduino IDE)

Untuk mengunggah (`flash`) kode ke mikrokontroler STM32F411, ikuti langkah berikut di Laptop Anda (Windows/Mac/Linux):

### Langkah 1: Persiapan Arduino IDE
1. Buka Arduino IDE.
2. Pergi ke **File > Preferences**.
3. Di bagian *Additional Boards Manager URLs*, tambahkan URL ini:
   `https://github.com/stm32duino/BoardManagerFiles/raw/main/package_stmicroelectronics_index.json`
4. Pergi ke **Tools > Board > Boards Manager...**, cari **"STM32 MCU based boards"** lalu install.

### Langkah 2: Konfigurasi Board
Setelah terinstal, pilih konfigurasi berikut di menu **Tools**:
*   **Board:** Generic STM32F4 series
*   **Board Part Number:** BlackPill F411CE (Sesuai dengan board yang Anda beli)
*   **U(S)ART Support:** Enabled (generic 'Serial')
*   **USB Support (if available):** CDC (generic 'Serial' supersede U(S)ART) -> *Ini penting agar komunikasi dengan Jetson via USB lancar*.
*   **Upload Method:** STM32CubeProgrammer (DFU) atau STLink (Tergantung alat flash yang Anda punya).

### Langkah 3: Install Library ArduinoJson
1. Di Arduino IDE, pergi ke **Sketch > Include Library > Manage Libraries...**
2. Cari **"ArduinoJson"** (oleh Benoit Blanchon) dan klik Install.

### Langkah 4: Buka dan Edit Kode
1. Buka file `firmware/RECELL_STM32/RECELL_STM32.ino`.
2. Minta tim elektrikal Anda untuk menentukan pin mana saja yang terhubung ke motor dan sensor.
3. Ubah bagian `// --- KONFIGURASI PIN ---` sesuai arahan mereka.

### Langkah 5: Flashing (Upload)
1. Colokkan STM32 ke Laptop menggunakan kabel USB tipe-C (Jika menggunakan mode DFU, tekan dan tahan tombol BOOT, tekan tombol NRST, lepas NRST, lalu lepas BOOT untuk masuk ke mode DFU).
2. Tekan tombol **Upload** (Tanda panah ke kanan) di Arduino IDE.
3. Tunggu hingga tulisan di bawah menunjukkan "Done Uploading".

### Langkah 6: Pindahkan ke Jetson
Setelah di-*flash* dari laptop, cabut STM32, lalu colokkan kabel USB tersebut ke port USB **Jetson Orin Nano**. STM32 sekarang siap menerima perintah Serial dari kode Python di Jetson.
