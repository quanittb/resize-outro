#!/usr/bin/env bash
set -e

echo "=========================================="
echo "  Build ResizeOutro cho macOS (Apple Silicon & Intel)"
echo "=========================================="

# 1. Kiểm tra Homebrew
if ! command -v brew &> /dev/null; then
    echo "[!] Không tìm thấy Homebrew. Đang hướng dẫn cài đặt..."
    echo "Vui lòng chạy: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    exit 1
fi

# 2. Kiểm tra FFmpeg & Python Tkinter
if ! command -v ffmpeg &> /dev/null || ! command -v ffprobe &> /dev/null; then
    echo "[+] Đang cài đặt FFmpeg qua brew..."
    brew install ffmpeg
fi

# 3. Cài đặt thư viện PyInstaller
echo "[+] Cài đặt PyInstaller..."
pip3 install --upgrade pyinstaller

# 4. Tìm đường dẫn binary FFmpeg & FFprobe
FFMPEG_BIN=$(which ffmpeg)
FFPROBE_BIN=$(which ffprobe)

echo "[+] Sử dụng FFmpeg: $FFMPEG_BIN"
echo "[+] Sử dụng FFprobe: $FFPROBE_BIN"

# 5. Đóng gói độc lập nhúng sẵn FFmpeg/FFprobe
echo "[+] Bắt đầu đóng gói PyInstaller..."
pyinstaller --clean -y \
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
