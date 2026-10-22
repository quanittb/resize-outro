# FFmpeg Batch Blur & Outro (High Performance Multiplatform)

Ứng dụng xử lý video hàng loạt: tự động căn chỉnh tỷ lệ khung hình (resize), tạo nền mờ (Fast Blur) và ghép video outro. Tương thích hoàn toàn trên cả **Windows** và **macOS** (Apple Silicon M1-M4 & Intel).

---

## 🚀 Các cải tiến & Cơ chế bảo vệ chính

1. **Hiệu năng cao & Fast Blur Engine (Tăng tốc 5x – 15x)**:
   - Thay thế thuật toán `gblur` đơn luồng bằng cơ chế *Downscale $\rightarrow$ BoxBlur (O(1)) $\rightarrow$ Upscale*. Giảm hơn 85% tải tính toán nhưng phông nền bokeh vẫn mịn mượt.
   - **Tự động nhận diện phần cứng (Hardware Acceleration)**:
     - **macOS**: Kích hoạt **Apple VideoToolbox** (`h264_videotoolbox`), khai thác Media Engine của chip M1/M2/M3/M4 (đạt 150 – 300+ FPS).
     - **Windows**: Tự động nhận diện **NVIDIA NVENC**, **Intel QuickSync (QSV)** hoặc **AMD AMF**. Có cơ chế tự động fallback về CPU `libx264` nếu hardware encoder gặp lỗi trên video thực tế.
     - **Tối ưu luồng CPU**: Tự động phân bổ số luồng `threads_per_worker = max(1, cpu_count // workers)` để các tiến trình không tranh chấp lõi CPU.
   - **Đa tiến trình song song (Parallel Workers)**: Hỗ trợ render 1 – 16 video cùng lúc.
   - **Gợi ý Workers tự động**: Ước lượng số luồng theo số CPU logic, encoder CPU/GPU, số tác vụ, độ phân giải lớn nhất và mức blur. Nút **Dùng gợi ý** áp dụng mức đề xuất; người dùng vẫn có thể chọn số khác.

2. **Xử lý lỗi âm thanh & Đồng bộ Outro**:
   - **Kiểm tra âm thanh Fail-Safe**: Dùng `ffprobe` trích xuất thông tin stream audio chuẩn JSON. Nếu `ffprobe` gặp lỗi đọc file hoặc mã lỗi khác 0, chương trình ném ngoại lệ rõ ràng thay vì âm thầm coi video là không tiếng.
   - **Hỗ trợ video không tiếng (Silent Video)**: Hỗ trợ đầy đủ mọi kịch bản (video câm, outro câm, cả hai câm) bằng cách bỏ stream audio (`-an`) hoặc bù audio câm qua `anullsrc`.
   - **Đồng bộ thời lượng Audio (`atrim`)**: Cắt audio theo thời lượng video lấy được từ metadata để tránh audio dài hơn hình làm trễ điểm nối outro hoặc kéo dài phần tiếng sau hình.
   - **Ba chế độ outro**:
     1. Nối outro mới sau toàn bộ video gốc.
     2. Đè outro lên đoạn cuối và giữ audio video gốc.
     3. Thay outro cũ: cắt số giây cuối video gốc rồi nối outro mới. Để trống thời lượng cắt để tự dùng thời lượng video của outro mới; có thể nhập số giây riêng.
     - Không chọn outro ở chế độ nối thì ứng dụng chỉ resize video gốc.
   - **Giữ khung hình outro ở mọi kích thước**: Outro được đặt vừa trong khung đích; phần nền được phóng to, crop và làm mờ theo mức blur đã chọn. Nội dung chính của outro không bị crop ở cả ba chế độ.
   - **Chuẩn hóa Timestamp (`setpts`)**: Bổ sung `setpts=PTS-STARTPTS` cho cả 2 nhánh video trước khi concat, tránh hiện tượng khựng khung hình hoặc mất đồng bộ.
   - **Đo thời lượng video đa tầng (Multi-tier Stream Duration)**:
      1. `stream.duration` hoặc `duration_ts × time_base` nếu stream có metadata thời lượng.
      2. Stream tags `DURATION` cho một số container Matroska / WebM.
      3. Ước lượng dự phòng bằng `nb_frames / avg_frame_rate`; hữu ích khi thiếu duration trực tiếp nhưng không bảo đảm chính xác tuyệt đối với mọi video VFR.
      4. `format.duration` là fallback cuối từ container. Giá trị này có thể bao gồm audio dài hơn video, nên file thiếu metadata thời lượng riêng của video có thể vẫn lệch thời điểm trim/ghép.

3. **Giao diện & Kiểm soát tiến trình an toàn tuyệt đối**:
   - **Thread-Safe UI Queue**: Dữ liệu nhập được đọc trên Main Thread; worker thread giao tiếp độc quyền qua `queue.Queue()`, không bao giờ gọi trực tiếp widget Tkinter.
   - **Dò Encoder bất đồng bộ an toàn**: Luồng dò phần cứng chạy nền an toàn; nút STOP được khóa khi ứng dụng chưa chạy render; nút START được tự động kích hoạt ngay khi dò xong.
   - **Khóa ngắt tiến trình (Atomic STOP)**: Dừng 100% các tiến trình con FFmpeg/FFprobe đang chạy ngay lập tức khi bấm STOP qua `active_processes` có bảo vệ `proc_lock`.
   - **Hoán đổi file nguyên tử (Atomic File Swap)**: Quá trình render luôn ghi vào file tạm `output.tmp_<uuid>.mp4`. Chỉ khi FFmpeg hoàn tất 100% và file có dung lượng hợp lệ mới dùng `os.replace` sang file đích, bảo vệ tuyệt đối file tốt cũ nếu người dùng bấm Dừng hoặc gặp lỗi.
   - **Bắt ngoại lệ toàn diện & Ghi Log**: Bắt trọn vẹn mọi ngoại lệ trong worker, lưu đầy đủ lỗi vào `render_errors.log` và cảnh báo người dùng.
   - **Chống đụng tên file chuẩn hóa**: Tự động nhận diện và thêm hậu tố phân biệt theo cơ chế không phân biệt hoa thường (case-insensitive) của Windows và macOS.
   - **Kiểm tra kích thước chẵn**: Bắt buộc chiều rộng và chiều cao phải chia hết cho 2 theo đúng tiêu chuẩn codec H.264.

---

## 🍎 Hướng dẫn sử dụng trên macOS

### Bước 1: Cài đặt FFmpeg & Python Tkinter (chỉ cần làm 1 lần)
Mở ứng dụng **Terminal** trên Mac và chạy:
```bash
# Cài đặt Homebrew (nếu máy chưa có Homebrew):
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Cài đặt FFmpeg và Python Tkinter:
brew install ffmpeg python-tk
```

### Bước 2: Chạy trực tiếp từ mã nguồn
```bash
python3 resize_outro.py
```

### Bước 3: Đóng gói thành ứng dụng macOS (.app)

#### Lựa chọn 3A: Gói tiêu chuẩn (Dùng FFmpeg đã cài qua Homebrew)
```bash
pip install pyinstaller
pyinstaller --windowed --noconsole --name "ResizeOutro" resize_outro.py
```
*Ứng dụng `dist/ResizeOutro.app` sẽ tự động tìm binary `ffmpeg` và `ffprobe` trong `PATH` hoặc các đường dẫn Homebrew chuẩn (`/opt/homebrew/bin` trên Apple Silicon, `/usr/local/bin` trên Intel).*

#### Lựa chọn 3B: Gói độc lập trọn gói (All-in-One Standalone - Nhúng sẵn FFmpeg)
```bash
pip install pyinstaller
pyinstaller --windowed --noconsole \
  --add-binary "$(which ffmpeg):." \
  --add-binary "$(which ffprobe):." \
  --name "ResizeOutro_AllInOne" resize_outro.py
```
*Gói `.app` này đã nhúng sẵn cả `ffmpeg` và `ffprobe` bên trong bundle, có thể copy sang các máy Mac khác chạy ngay mà không cần cài Homebrew.*

> **Lưu ý macOS Gatekeeper**: Nếu macOS chặn không cho mở ứng dụng tải về/đóng gói ngoài App Store (báo *"App is damaged and can't be opened"*), hãy chạy lệnh sau trong Terminal:
> ```bash
> xattr -cr /path/to/ResizeOutro.app
> ```

---

## 🪟 Hướng dẫn sử dụng trên Windows

### Chạy trực tiếp bằng Python:
```bash
python resize_outro.py
```

### Hai phương án đóng gói `.exe` trên Windows:

#### Phương án 1: Bản Siêu Gọn (~12 MB) + File ZIP / Binary FFmpeg đi kèm (Khuyên dùng)
- Đóng gói file `.exe` gọn nhẹ, đặt cùng thư mục với file `ffmpeg*.zip` (hoặc đặt cùng `ffmpeg.exe` và `ffprobe.exe`):
```bash
pyinstaller --onefile --windowed --name "Resize_Optimized" resize_outro.py
```
*Khi chạy lần đầu, ứng dụng sẽ tự động trích xuất `ffmpeg.exe` và `ffprobe.exe` từ file zip nếu máy chưa cài đặt.*

#### Phương án 2: Bản Độc Lập Trọn Gói All-in-One (~125 MB - Không cần bất kỳ file nào đi kèm)
- Nhúng trực tiếp cả 2 binary `ffmpeg.exe` và `ffprobe.exe` vào trong 1 file `.exe` duy nhất. Người dùng chỉ cần 1 file duy nhất để chạy trên mọi máy tính Windows:
```bash
# Đảm bảo đã có ffmpeg.exe và ffprobe.exe trong thư mục hiện tại trước khi chạy:
pyinstaller --onefile --windowed --add-binary "ffmpeg.exe;." --add-binary "ffprobe.exe;." --name "Resize_AllInOne" resize_outro.py
```
