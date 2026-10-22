#!/usr/bin/env bash
set -e

echo "=========================================="
echo "  Build ResizeOutro cho macOS (Apple Silicon & Intel)"
echo "=========================================="

# 1. Nạp đầy đủ PATH (Homebrew, Python User Scripts)
USER_PY_BIN=$(python3 -m site --user-base 2>/dev/null)/bin
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:$HOME/Library/Python/3.9/bin:$USER_PY_BIN:$PATH"

# 2. Kiểm tra Homebrew
if ! command -v brew &> /dev/null; then
    echo "[!] Không tìm thấy Homebrew. Đang hướng dẫn cài đặt..."
    echo "Vui lòng chạy: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    exit 1
fi

# 3. Kiểm tra FFmpeg & FFprobe
if ! command -v ffmpeg &> /dev/null || ! command -v ffprobe &> /dev/null; then
    echo "[+] Đang cài đặt FFmpeg qua brew..."
    brew install ffmpeg
fi

# 4. Kiểm tra Tkinter của Python
if ! python3 -c "import tkinter" &> /dev/null; then
    echo "[!] Python hiện tại thiếu Tkinter. Đang cài đặt python-tk qua Homebrew..."
    brew install python-tk || true
fi

# 5. Cài đặt thư viện PyInstaller
echo "[+] Cài đặt / Cập nhật PyInstaller..."
python3 -m pip install --upgrade pyinstaller

# 6. Tìm đường dẫn binary FFmpeg & FFprobe
FFMPEG_BIN=$(which ffmpeg)
FFPROBE_BIN=$(which ffprobe)

echo "[+] Sử dụng FFmpeg: $FFMPEG_BIN"
echo "[+] Sử dụng FFprobe: $FFPROBE_BIN"

# 7. Đóng gói độc lập nhúng sẵn FFmpeg/FFprobe bằng python3 -m PyInstaller
echo "[+] Bắt đầu đóng gói PyInstaller..."
python3 -m PyInstaller --clean -y \
  --windowed \
  --noconsole \
  --add-binary "${FFMPEG_BIN}:." \
  --add-binary "${FFPROBE_BIN}:." \
  --name "ResizeOutro" \
  resize_outro.py

echo "=========================================="
echo " Build thành công!"
echo " Ứng dụng: dist/ResizeOutro.app"
echo " Nếu macOS báo file bị hỏng hoặc chặn, chạy:"
echo " xattr -cr dist/ResizeOutro.app"
echo "=========================================="
