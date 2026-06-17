#!/usr/bin/env bash
# ============================================================================
#  RECELL-AI — DEPLOY dari laptop ke Jetson (SSH key + transfer + run setup)
# ----------------------------------------------------------------------------
#  Jalankan di LAPTOP (Git Bash di Windows / Linux / macOS):
#      bash deploy/deploy.sh                      # target default r2c@r2c.local
#      bash deploy/deploy.sh user@host [destdir]  # target lain
#
#  Alur:
#    1. Buat SSH key lokal bila belum ada, salin ke Jetson (password DIMINTA
#       SEKALI di sini — tidak pernah disimpan ke file).
#    2. Transfer proyek + wheelhouse/ via tar-over-ssh (artefak di-exclude).
#    3. Jalankan `bash setup.sh` di Jetson (install offline + pasang service).
#
#  CATATAN: ini deployment OFFLINE/air-gapped — folder wheelhouse/ HARUS sudah
#  dibangun di laptop lebih dulu (lihat docs/DEPLOY_GUIDE_RECELL.md, Tahap 1).
# ============================================================================
set -euo pipefail

JETSON="${1:-r2c@r2c.local}"
DEST="${2:-RECELL-AI}"                       # relatif terhadap home Jetson
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "============================================="
echo " RECELL-AI DEPLOY"
echo "   Target : $JETSON  ->  ~/$DEST"
echo "   Sumber : $PROJECT_ROOT"
echo "============================================="

# 0. Peringatan bila wheelhouse belum ada (deploy offline butuh ini)
if [ ! -d "$PROJECT_ROOT/wheelhouse" ]; then
  echo "[WARN] Folder wheelhouse/ tidak ada di laptop."
  echo "       Deploy offline akan GAGAL di Jetson tanpa wheel aarch64."
  echo "       Bangun dulu (lihat DEPLOY_GUIDE_RECELL.md Tahap 1), lalu ulangi."
  read -r -p "       Lanjut transfer tanpa wheelhouse? [y/N] " ans
  [ "${ans:-N}" = "y" ] || [ "${ans:-N}" = "Y" ] || { echo "Dibatalkan."; exit 1; }
fi

# 1. SSH key lokal (buat sekali bila belum ada)
KEY="$HOME/.ssh/id_ed25519"
if [ ! -f "$KEY" ]; then
  echo "[*] Membuat SSH key baru (ed25519, tanpa passphrase)..."
  ssh-keygen -t ed25519 -N "" -f "$KEY"
fi

# 2. Salin public key ke Jetson — password Jetson diminta SEKALI di langkah ini
echo "[*] Menyalin public key ke $JETSON (masukkan password Jetson bila diminta)..."
if command -v ssh-copy-id >/dev/null 2>&1; then
  ssh-copy-id -i "$KEY.pub" "$JETSON" || true
else
  # Fallback (mis. Git Bash tanpa ssh-copy-id)
  ssh "$JETSON" "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys" < "$KEY.pub"
fi

# 3. Transfer proyek (wheelhouse IKUT; artefak lokal di-exclude)
echo "[*] Transfer proyek ke ~/$DEST ..."
ssh "$JETSON" "mkdir -p ~/$DEST"
tar czf - -C "$PROJECT_ROOT" \
    --exclude='./.git' \
    --exclude='./venv' \
    --exclude='./jetson/data' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='./_smoketest_out' \
    --exclude='./CATATAN_RECELL_AI.pdf' \
    --exclude='./CATATAN_RECELL_AI.txt' \
    --exclude='./generate_catatan_pdf.py' \
    . | ssh "$JETSON" "tar xzf - -C ~/$DEST"

# 4. Jalankan setup.sh di Jetson (-t agar sudo bisa prompt password interaktif)
echo "[*] Menjalankan setup.sh di Jetson..."
ssh -t "$JETSON" "cd ~/$DEST && bash setup.sh"

echo "============================================="
echo " DEPLOY SELESAI."
echo " Service 'recell' di-enable — GUI jalan otomatis saat Jetson boot ke desktop."
echo " Jalankan sekarang (butuh sesi desktop aktif):"
echo "   ssh -t $JETSON 'sudo systemctl start recell'"
echo " Update kode saja (tanpa pasang ulang service):"
echo "   bash deploy/deploy.sh $JETSON   # transfer + setup.sh (idempotent)"
echo "============================================="
