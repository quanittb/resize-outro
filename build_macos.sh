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

# 5. Kiểm tra PyInstaller (Ưu tiên Homebrew PyInstaller chạy Tcl/Tk 9.1 mới nhất)
if command -v /opt/homebrew/bin/pyinstaller &> /dev/null; then
    PYINSTALLER_CMD="/opt/homebrew/bin/pyinstaller"
elif command -v pyinstaller &> /dev/null; then
    PYINSTALLER_CMD="pyinstaller"
else
    echo "[+] Đang cài đặt PyInstaller qua brew..."
    brew install pyinstaller
    PYINSTALLER_CMD="/opt/homebrew/bin/pyinstaller"
fi

# 6. Tìm đường dẫn binary FFmpeg & FFprobe
FFMPEG_BIN=$(which ffmpeg)
FFPROBE_BIN=$(which ffprobe)

echo "[+] Sử dụng FFmpeg: $FFMPEG_BIN"
echo "[+] Sử dụng FFprobe: $FFPROBE_BIN"
echo "[+] Sử dụng PyInstaller: $PYINSTALLER_CMD"

# 7. Đóng gói độc lập nhúng sẵn FFmpeg/FFprobe bằng PyInstaller (Tcl/Tk 9.1)
echo "[+] Bắt đầu đóng gói PyInstaller..."
"$PYINSTALLER_CMD" --clean -y \
  --windowed \
  --noconsole \
  --osx-bundle-identifier "com.prox.resizeoutro" \
  --add-binary "${FFMPEG_BIN}:." \
  --add-binary "${FFPROBE_BIN}:." \
  --name "ResizeOutro" \
  resize_outro.py

# 8. Cấu hình ép buộc giao diện Light Mode (Aqua Light) và gỡ chặn Gatekeeper
if [ -d "dist/ResizeOutro.app" ]; then
    INFO_PLIST="dist/ResizeOutro.app/Contents/Info.plist"
    if [ -f "$INFO_PLIST" ]; then
        /usr/libexec/PlistBuddy -c "Add :NSRequiresAquaSystemAppearance bool true" "$INFO_PLIST" 2>/dev/null || \
        /usr/libexec/PlistBuddy -c "Set :NSRequiresAquaSystemAppearance true" "$INFO_PLIST" 2>/dev/null || true
        /usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName 'resize + outro QuanPH'" "$INFO_PLIST" 2>/dev/null || \
        /usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string 'resize + outro QuanPH'" "$INFO_PLIST" 2>/dev/null || true
    fi
    xattr -cr "dist/ResizeOutro.app" 2>/dev/null || true
    codesign --force --deep --sign - "dist/ResizeOutro.app" 2>/dev/null || true
fi

echo "=========================================="
echo " Build thành công!"
echo " Ứng dụng: dist/ResizeOutro.app"
echo " Đã tự động gỡ chặn Gatekeeper (xattr -cr)!"
echo "=========================================="
