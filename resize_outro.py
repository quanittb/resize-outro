import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import subprocess
import os
import sys
import threading
import queue
import re
import shutil
import platform
import glob
import zipfile
import uuid
import json
import math
import traceback
from concurrent.futures import ThreadPoolExecutor

DEFAULT_SIZES = [
    '1080x1920',
    '1920x1080',
    '1080x1080',
    '720x1080',
    '768x1024',
    '1024x768'
]

MODE_CONCAT = 'concat'
MODE_OVERLAY_LAST = 'overlay_last'
MODE_REPLACE_LAST = 'replace_last'

IS_MAC = platform.system() == 'Darwin'
IS_WIN = platform.system() == 'Windows'

# Bảng màu chuẩn giao diện Light/White đồng nhất như bản Windows
BG_COLOR = '#f0f0f0'
FG_COLOR = '#000000'
HINT_COLOR = '#666666'
ENTRY_BG = '#ffffff'
BTN_START_BG = '#2e7d32'
BTN_STOP_BG = '#c62828'

FONT_FAMILY = 'Helvetica' if IS_MAC else 'Segoe UI'
FONT_TITLE = (FONT_FAMILY, 10, 'bold')
FONT_NORMAL = (FONT_FAMILY, 9)
FONT_BOLD = (FONT_FAMILY, 9, 'bold')

class ActionButton(tk.Label):
    """
    Nút bấm hành động (BẮT ĐẦU RENDER / DỪNG LẠI) dạng khối 3D bevel.
    Khắc phục triệt để việc macOS Cocoa tự động biến các nút màu xanh/đỏ thành nút xám native.
    """
    def __init__(self, parent, text, command=None, bg=BTN_START_BG, fg='white',
                 relief='raised', bd=2, padx=16, pady=7, font=FONT_TITLE, **kwargs):
        self.command = command
        self.normal_bg = bg
        self.normal_fg = fg
        self.relief_style = relief
        self.disabled_bg = bg
        self.disabled_fg = '#5c1313' if bg == BTN_STOP_BG else '#1a401c'
        self._state = 'normal'
        super().__init__(
            parent, text=text, bg=bg, fg=fg, relief=relief, bd=bd,
            padx=padx, pady=pady, font=font, cursor='pointinghand' if IS_MAC else 'hand2', **kwargs
        )
        self.bind('<ButtonPress-1>', self._on_press)
        self.bind('<ButtonRelease-1>', self._on_release)

    def _on_press(self, _e):
        if self._state == 'normal':
            self.config(relief='sunken')

    def _on_release(self, _e):
        if self._state == 'normal':
            self.config(relief=self.relief_style)
            if self.command:
                self.command()

    def config(self, **kwargs):
        if 'state' in kwargs:
            state = kwargs.pop('state')
            self._state = state
            if state == 'disabled':
                super().config(bg=self.disabled_bg, fg=self.disabled_fg, relief=self.relief_style, cursor='arrow', **kwargs)
                return
            else:
                super().config(bg=self.normal_bg, fg=self.normal_fg, relief=self.relief_style, cursor='pointinghand' if IS_MAC else 'hand2', **kwargs)
                return
        super().config(**kwargs)

def get_app_dir():
    """Lấy thư mục gốc chứa file thực thi (hỗ trợ cả script Python, macOS .app bundle và PyInstaller onefile .exe)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    if '__file__' in globals():
        return os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.getcwd())

def extract_ffmpeg_from_zip(app_dir):
    """Tự động dò tìm và giải nén ffmpeg.exe / ffprobe.exe từ file zip nếu có trong thư mục app."""
    zips = glob.glob(os.path.join(app_dir, 'ffmpeg*.zip'))
    for zpath in zips:
        try:
            with zipfile.ZipFile(zpath, 'r') as zf:
                for member in zf.namelist():
                    basename = os.path.basename(member)
                    if basename.lower() in ('ffmpeg.exe', 'ffprobe.exe'):
                        target = os.path.join(app_dir, basename)
                        if not os.path.exists(target):
                            with zf.open(member) as src, open(target, 'wb') as dst:
                                dst.write(src.read())
        except Exception:
            continue

def get_ffmpeg_binaries():
    """
    Tự động tìm kiếm ffmpeg và ffprobe theo thứ tự ưu tiên:
    1. Bundle nội bộ PyInstaller (sys._MEIPASS)
    2. Cạnh file thực thi (app_dir), app_dir/bin, Contents/Resources, Contents/Frameworks
    3. Biến môi trường hệ thống PATH
    4. Thư mục cài đặt tiêu chuẩn trên macOS (Homebrew / MacPorts)
    """
    ffmpeg_name = 'ffmpeg.exe' if IS_WIN else 'ffmpeg'
    ffprobe_name = 'ffprobe.exe' if IS_WIN else 'ffprobe'

    ffmpeg_path = None
    ffprobe_path = None

    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        cand_ffmpeg = os.path.join(meipass, ffmpeg_name)
        cand_ffprobe = os.path.join(meipass, ffprobe_name)
        if os.path.isfile(cand_ffmpeg) and (IS_WIN or os.access(cand_ffmpeg, os.X_OK)):
            ffmpeg_path = cand_ffmpeg
        if os.path.isfile(cand_ffprobe) and (IS_WIN or os.access(cand_ffprobe, os.X_OK)):
            ffprobe_path = cand_ffprobe

    app_dir = get_app_dir()
    if IS_WIN and (not ffmpeg_path or not ffprobe_path):
        extract_ffmpeg_from_zip(app_dir)

    candidate_dirs = [
        app_dir,
        os.path.join(app_dir, 'bin'),
        os.path.join(app_dir, '..', 'Resources'),
        os.path.join(app_dir, '..', 'Frameworks'),
    ]

    for c_dir in candidate_dirs:
        norm_dir = os.path.normpath(c_dir)
        cand_ffmpeg = os.path.join(norm_dir, ffmpeg_name)
        cand_ffprobe = os.path.join(norm_dir, ffprobe_name)
        if not ffmpeg_path and os.path.isfile(cand_ffmpeg) and (IS_WIN or os.access(cand_ffmpeg, os.X_OK)):
            ffmpeg_path = cand_ffmpeg
        if not ffprobe_path and os.path.isfile(cand_ffprobe) and (IS_WIN or os.access(cand_ffprobe, os.X_OK)):
            ffprobe_path = cand_ffprobe

    if not ffmpeg_path:
        ffmpeg_path = shutil.which('ffmpeg')
    if not ffprobe_path:
        ffprobe_path = shutil.which('ffprobe')

    if IS_MAC:
        mac_paths = [
            ('/opt/homebrew/bin/ffmpeg', '/opt/homebrew/bin/ffprobe'),
            ('/usr/local/bin/ffmpeg', '/usr/local/bin/ffprobe'),
            ('/opt/local/bin/ffmpeg', '/opt/local/bin/ffprobe'),
        ]
        for m_ffmpeg, m_ffprobe in mac_paths:
            if not ffmpeg_path and os.path.isfile(m_ffmpeg) and os.access(m_ffmpeg, os.X_OK):
                ffmpeg_path = m_ffmpeg
            if not ffprobe_path and os.path.isfile(m_ffprobe) and os.access(m_ffprobe, os.X_OK):
                ffprobe_path = m_ffprobe

    return ffmpeg_path, ffprobe_path

def get_cpu_fallback_args(workers=2):
    total_cores = os.cpu_count() or 4
    threads_per_worker = max(1, total_cores // max(1, workers))
    return ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22', '-threads', str(threads_per_worker)]

def detect_best_encoder(ffmpeg_bin, workers=2):
    if not ffmpeg_bin:
        return get_cpu_fallback_args(workers), 'CPU libx264 (Đa luồng)', 'cpu'

    candidates = []
    if IS_MAC:
        candidates = [
            (['-c:v', 'h264_videotoolbox', '-b:v', '6000k'], 'Apple VideoToolbox (GPU M1-M4)', 'videotoolbox'),
            (get_cpu_fallback_args(workers), 'CPU libx264 (Đa luồng)', 'cpu')
        ]
    elif IS_WIN:
        candidates = [
            (['-c:v', 'h264_nvenc', '-preset', 'p4', '-cq', '19'], 'NVIDIA NVENC (GPU)', 'nvenc'),
            (['-c:v', 'h264_qsv', '-preset', 'fast', '-global_quality', '21'], 'Intel QuickSync (GPU)', 'qsv'),
            (['-c:v', 'h264_amf', '-quality', 'speed'], 'AMD AMF (GPU)', 'amf'),
            (get_cpu_fallback_args(workers), 'CPU libx264 (Đa luồng)', 'cpu')
        ]
    else:
        candidates = [
            (['-c:v', 'h264_nvenc', '-preset', 'p4', '-cq', '19'], 'NVIDIA NVENC (GPU)', 'nvenc'),
            (['-c:v', 'h264_vaapi'], 'VAAPI (GPU)', 'vaapi'),
            (get_cpu_fallback_args(workers), 'CPU libx264 (Đa luồng)', 'cpu')
        ]

    for enc_args, name, enc_type in candidates:
        if enc_type == 'cpu':
            return enc_args, name, enc_type
        try:
            cmd = [
                ffmpeg_bin, '-y',
                '-f', 'lavfi', '-i', 'color=c=black:s=64x64:d=0.04',
                *enc_args,
                '-f', 'null', '-'
            ]
            flags = subprocess.CREATE_NO_WINDOW if IS_WIN else 0
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags, timeout=2.0)
            if res.returncode == 0:
                return enc_args, name, enc_type
        except Exception:
            continue

    return get_cpu_fallback_args(workers), 'CPU libx264 (Đa luồng)', 'cpu'

def normalize_filename_key(filename):
    """
    Chuẩn hóa tên file theo tính chất hệ điều hành:
    Windows và macOS không phân biệt hoa thường (case-insensitive) -> chuyển về chữ thường.
    """
    if platform.system() in ('Windows', 'Darwin'):
        return filename.lower()
    return filename

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('resize + outro QuanPH')
        self.geometry('880x720')
        self.minsize(840, 660)
        self.configure(bg=BG_COLOR)

        # Dò tìm FFmpeg & FFprobe
        self.ffmpeg_bin, self.ffprobe_bin = get_ffmpeg_binaries()

        # Dữ liệu cấu hình
        self.inputs = []
        self.outro = None
        self.output_dir = ''

        self.blur_percent = tk.IntVar(value=80)
        self.outro_mode = tk.StringVar(value=MODE_CONCAT)
        self.overlay_duration = tk.StringVar(value='3')
        self.replace_duration = tk.StringVar(value='')
        self.max_workers = tk.IntVar(value=2)

        # Hàng đợi đồng bộ giao diện an toàn (Thread-Safe UI Queue)
        self.ui_queue = queue.Queue()

        # Kiểm soát dừng tiến trình con
        self.stop_flag = False
        self.active_processes = set()
        self.proc_lock = threading.Lock()

        # Trạng thái encoder ban đầu
        self.encoder_args = get_cpu_fallback_args(2)
        self.encoder_name = 'Đang kiểm tra phần cứng...'
        self.encoder_type = 'detecting'

        self.create_ui()
        self.toggle_outro_mode_ui()

        # Khóa nút Start và nút STOP ban đầu khi chưa kiểm tra xong
        self.btn_start.config(state='disabled')
        self.btn_stop.config(state='disabled')
        self.status_label.config(text='Đang kiểm tra cấu hình phần cứng...')

        # Bắt đầu vòng lặp cập nhật UI từ Queue trên Main Thread
        self.after(50, self.process_ui_queue)

        initial_workers = int(self.max_workers.get())
        threading.Thread(target=self.async_detect_encoder, args=(initial_workers,), daemon=True).start()

        self.check_ffmpeg_installed()

    def async_detect_encoder(self, workers):
        try:
            args, name, enc_type = detect_best_encoder(self.ffmpeg_bin, workers)
        except Exception:
            args = get_cpu_fallback_args(workers)
            name = 'CPU libx264 (Dự phòng)'
            enc_type = 'cpu'
        self.ui_queue.put(('encoder_detected', args, name, enc_type))

    def check_ffmpeg_installed(self):
        missing = []
        if not self.ffmpeg_bin:
            missing.append("FFmpeg")
        if not self.ffprobe_bin:
            missing.append("FFprobe")

        if missing:
            msg = (
                f"Không tìm thấy {' và '.join(missing)} trên máy tính của bạn!\n\n"
                "- Trên Windows: Hãy đặt file 'ffmpeg.exe' và 'ffprobe.exe' "
                "(hoặc file 'ffmpeg*.zip') cùng thư mục với file chạy này.\n"
                "- Trên macOS: Hãy mở Terminal và cài đặt bằng lệnh: brew install ffmpeg"
            )
            messagebox.showwarning("Cảnh báo thiếu công cụ", msg)

    def create_ui(self):
        """Khởi tạo bố cục giao diện chuẩn xác 100% như ảnh bản Windows (Image 2)."""
        main_frame = tk.Frame(self, bg=BG_COLOR, padx=15, pady=15)
        main_frame.pack(fill='both', expand=True)

        row = 0

        # 1. Thông tin Hardware Acceleration (Khung viền nổi bật)
        hw_frame = tk.LabelFrame(
            main_frame, text='Hệ thống & Tăng tốc phần cứng',
            bg=BG_COLOR, fg=FG_COLOR, font=FONT_BOLD,
            bd=1, relief='groove', padx=10, pady=8
        )
        hw_frame.grid(row=row, column=0, columnspan=2, sticky='ew', pady=(0, 10))

        tk.Label(
            hw_frame, text=f'Hệ điều hành: {platform.system()} ({platform.machine()})',
            bg=BG_COLOR, fg=FG_COLOR, font=FONT_NORMAL
        ).pack(anchor='w')

        self.hw_label = tk.Label(
            hw_frame, text=f'Bộ mã hóa: {self.encoder_name}',
            bg=BG_COLOR, fg=FG_COLOR, font=FONT_BOLD
        )
        self.hw_label.pack(anchor='w', pady=(2, 0))
        row += 1

        # 2. Chọn video input
        self.btn_pick_inputs = tk.Button(main_frame, text='Chọn video input', command=self.pick_inputs, width=22)
        self.btn_pick_inputs.grid(row=row, column=0, sticky='w', pady=4)
        self.input_label = tk.Label(main_frame, text='Chưa chọn video nào', anchor='w', bg=BG_COLOR, fg=FG_COLOR, font=FONT_NORMAL)
        self.input_label.grid(row=row, column=1, sticky='w', padx=10, pady=4)
        row += 1

        # 3. Chọn outro
        self.btn_pick_outro = tk.Button(main_frame, text='Chọn outro (optional)', command=self.pick_outro, width=22)
        self.btn_pick_outro.grid(row=row, column=0, sticky='w', pady=4)
        self.outro_label = tk.Label(main_frame, text='Không có', anchor='w', bg=BG_COLOR, fg=FG_COLOR, font=FONT_NORMAL)
        self.outro_label.grid(row=row, column=1, sticky='w', padx=10, pady=4)
        row += 1

        # 4. Chế độ ghép outro
        tk.Label(main_frame, text='Chế độ ghép outro:', bg=BG_COLOR, fg=FG_COLOR, font=FONT_NORMAL).grid(row=row, column=0, sticky='w', pady=4)
        self.outro_mode_frame = tk.Frame(main_frame, bg=BG_COLOR)
        self.outro_mode_frame.grid(row=row, column=1, sticky='w', padx=10, pady=4)

        self.radio_concat = tk.Radiobutton(
            self.outro_mode_frame,
            text='Nối video + audio outro',
            variable=self.outro_mode,
            value=MODE_CONCAT,
            command=self.toggle_outro_mode_ui,
            bg=BG_COLOR, fg=FG_COLOR, activebackground=BG_COLOR, activeforeground=FG_COLOR,
            selectcolor=ENTRY_BG, font=FONT_NORMAL, highlightthickness=0
        )
        self.radio_concat.pack(anchor='w')

        self.radio_overlay = tk.Radiobutton(
            self.outro_mode_frame,
            text='Đè outro vào X giây cuối, giữ audio video gốc',
            variable=self.outro_mode,
            value=MODE_OVERLAY_LAST,
            command=self.toggle_outro_mode_ui,
            bg=BG_COLOR, fg=FG_COLOR, activebackground=BG_COLOR, activeforeground=FG_COLOR,
            selectcolor=ENTRY_BG, font=FONT_NORMAL, highlightthickness=0
        )
        self.radio_overlay.pack(anchor='w')

        self.radio_replace = tk.Radiobutton(
            self.outro_mode_frame,
            text='Thay outro cũ (cắt phần cuối rồi nối outro mới)',
            variable=self.outro_mode,
            value=MODE_REPLACE_LAST,
            command=self.toggle_outro_mode_ui,
            bg=BG_COLOR, fg=FG_COLOR, activebackground=BG_COLOR, activeforeground=FG_COLOR,
            selectcolor=ENTRY_BG, font=FONT_NORMAL, highlightthickness=0
        )
        self.radio_replace.pack(anchor='w')
        row += 1

        # 5. Cấu hình đè outro
        self.overlay_duration_label = tk.Label(main_frame, text='Độ dài đè outro cuối (giây):', bg=BG_COLOR, fg=FG_COLOR, font=FONT_NORMAL)
        self.overlay_duration_label.grid(row=row, column=0, sticky='w', pady=2)
        self.overlay_duration_entry = tk.Entry(
            main_frame, width=12, textvariable=self.overlay_duration,
            bg=ENTRY_BG, fg=FG_COLOR, relief='solid', bd=1,
            highlightbackground='#b0b0b0', highlightcolor='#0078d7', highlightthickness=1, font=FONT_NORMAL
        )
        self.overlay_duration_entry.grid(row=row, column=1, sticky='w', padx=10, pady=2)
        row += 1

        self.overlay_duration_hint = tk.Label(
            main_frame,
            text='Ví dụ nhập 3 = đè outro lên 3 giây cuối, audio vẫn lấy từ video gốc',
            bg=BG_COLOR, fg=HINT_COLOR, font=FONT_NORMAL
        )
        self.overlay_duration_hint.grid(row=row, column=1, sticky='w', padx=10, pady=(0, 4))

        self.replace_duration_label = tk.Label(main_frame, text='Cắt bao nhiêu giây cuối video gốc:', bg=BG_COLOR, fg=FG_COLOR, font=FONT_NORMAL)
        self.replace_duration_label.grid(row=row - 1, column=0, sticky='w', pady=2)
        self.replace_duration_entry = tk.Entry(
            main_frame, width=12, textvariable=self.replace_duration,
            bg=ENTRY_BG, fg=FG_COLOR, relief='solid', bd=1,
            highlightbackground='#b0b0b0', highlightcolor='#0078d7', highlightthickness=1, font=FONT_NORMAL
        )
        self.replace_duration_entry.grid(row=row - 1, column=1, sticky='w', padx=10, pady=2)
        self.replace_duration_hint = tk.Label(
            main_frame,
            text='Để trống = theo thời lượng outro mới; giá trị cắt phải ngắn hơn video gốc',
            bg=BG_COLOR, fg=HINT_COLOR, font=FONT_NORMAL
        )
        self.replace_duration_hint.grid(row=row, column=1, sticky='w', padx=10, pady=(0, 4))
        row += 1

        # 6. Chọn thư mục output
        self.btn_pick_output = tk.Button(main_frame, text='Chọn thư mục output', command=self.pick_output, width=22)
        self.btn_pick_output.grid(row=row, column=0, sticky='w', pady=4)
        self.output_label = tk.Label(main_frame, text='Chưa chọn thư mục', anchor='w', bg=BG_COLOR, fg=FG_COLOR, font=FONT_NORMAL)
        self.output_label.grid(row=row, column=1, sticky='w', padx=10, pady=4)
        row += 1

        # 7. Tiền tố & Hậu tố
        tk.Label(main_frame, text='Tiền tố file:', bg=BG_COLOR, fg=FG_COLOR, font=FONT_NORMAL).grid(row=row, column=0, sticky='w', pady=2)
        self.prefix_entry = tk.Entry(
            main_frame, width=40, bg=ENTRY_BG, fg=FG_COLOR, relief='solid', bd=1,
            highlightbackground='#b0b0b0', highlightcolor='#0078d7', highlightthickness=1, font=FONT_NORMAL
        )
        self.prefix_entry.grid(row=row, column=1, sticky='w', padx=10, pady=2)
        row += 1

        tk.Label(main_frame, text='Hậu tố file:', bg=BG_COLOR, fg=FG_COLOR, font=FONT_NORMAL).grid(row=row, column=0, sticky='w', pady=2)
        self.suffix_entry = tk.Entry(
            main_frame, width=40, bg=ENTRY_BG, fg=FG_COLOR, relief='solid', bd=1,
            highlightbackground='#b0b0b0', highlightcolor='#0078d7', highlightthickness=1, font=FONT_NORMAL
        )
        self.suffix_entry.grid(row=row, column=1, sticky='w', padx=10, pady=2)
        row += 1

        # 8. Slider Độ blur
        tk.Label(main_frame, text='Độ blur nền (%) [Fast Blur]:', bg=BG_COLOR, fg=FG_COLOR, font=FONT_NORMAL).grid(row=row, column=0, sticky='w', pady=4)
        blur_container = tk.Frame(main_frame, bg=BG_COLOR)
        blur_container.grid(row=row, column=1, sticky='w', padx=10, pady=4)

        blur_subframe = tk.Frame(blur_container, bg=BG_COLOR)
        blur_subframe.pack(side='left')

        self.blur_scale_val = tk.Label(blur_subframe, text='80', bg=BG_COLOR, fg=FG_COLOR, font=FONT_NORMAL)
        self.blur_scale_val.pack()

        self.blur_scale = tk.Scale(
            blur_subframe,
            from_=0,
            to=200,
            orient='horizontal',
            length=300,
            variable=self.blur_percent,
            bg=BG_COLOR, fg=FG_COLOR,
            troughcolor='#d9d9d9',
            highlightthickness=0,
            bd=1,
            showvalue=False,
            command=self._on_blur_slide
        )
        self.blur_scale.pack()

        tk.Label(
            blur_container,
            text='(0% = tắt blur, 80% = tiêu chuẩn, tối ưu tốc độ x5-x15)',
            bg=BG_COLOR, fg=HINT_COLOR, font=FONT_NORMAL
        ).pack(side='left', padx=8)
        row += 1

        # 9. Số luồng chạy song song
        tk.Label(main_frame, text='Số luồng song song (Workers):', bg=BG_COLOR, fg=FG_COLOR, font=FONT_NORMAL).grid(row=row, column=0, sticky='w', pady=4)
        workers_frame = tk.Frame(main_frame, bg=BG_COLOR)
        workers_frame.grid(row=row, column=1, sticky='w', padx=10, pady=4)

        self.workers_spinbox = tk.Spinbox(
            workers_frame, from_=1, to=16, width=5, textvariable=self.max_workers,
            bg=ENTRY_BG, fg=FG_COLOR, relief='solid', bd=1,
            highlightbackground='#b0b0b0', highlightcolor='#0078d7', highlightthickness=1, font=FONT_NORMAL
        )
        self.workers_spinbox.pack(side='left')

        self.workers_hint = tk.Label(
            workers_frame, text='Gợi ý: đang tính...',
            bg=BG_COLOR, fg=HINT_COLOR, wraplength=390, justify='left', font=FONT_NORMAL
        )
        self.workers_hint.pack(side='left', padx=8)

        self.btn_apply_workers = tk.Button(workers_frame, text='Dùng gợi ý', command=self.apply_worker_recommendation)
        self.btn_apply_workers.pack(side='left', padx=4)
        row += 1

        # 10. Danh sách kích thước (size)
        tk.Label(
            main_frame, text='Danh sách kích thước (mỗi dòng 1 size WxH chẵn):',
            bg=BG_COLOR, fg=FG_COLOR, font=FONT_NORMAL
        ).grid(row=row, column=0, columnspan=2, sticky='w', pady=(8, 2))
        row += 1

        self.size_text = tk.Text(
            main_frame, height=6, width=35,
            bg=ENTRY_BG, fg=FG_COLOR, insertbackground=FG_COLOR,
            relief='solid', bd=1,
            highlightbackground='#b0b0b0', highlightcolor='#0078d7', highlightthickness=1,
            font=FONT_NORMAL
        )
        self.size_text.grid(row=row, column=0, columnspan=2, sticky='w', pady=2)
        self.size_text.insert('1.0', '\n'.join(DEFAULT_SIZES))
        row += 1

        # 11. Progress bar
        self.progress = ttk.Progressbar(main_frame, length=640)
        self.progress.grid(row=row, column=0, columnspan=2, sticky='ew', pady=(12, 4))
        row += 1

        # 12. Status label
        self.status_label = tk.Label(main_frame, text='Sẵn sàng', bg=BG_COLOR, fg=FG_COLOR, font=FONT_NORMAL)
        self.status_label.grid(row=row, column=0, columnspan=2, sticky='w', pady=2)
        row += 1

        # 13. Nút Bắt đầu (Xanh lá) & Dừng (Đỏ) chuẩn màu Windows
        btn_frame = tk.Frame(main_frame, bg=BG_COLOR)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=12)

        self.btn_start = ActionButton(
            btn_frame, text='BẮT ĐẦU RENDER', command=self.start,
            bg=BTN_START_BG, fg='white', font=FONT_TITLE, padx=16, pady=7
        )
        self.btn_start.pack(side='left', padx=10)

        self.btn_stop = ActionButton(
            btn_frame, text='DỪNG LẠI (STOP)', command=self.stop,
            bg=BTN_STOP_BG, fg='white', font=FONT_TITLE, padx=16, pady=7
        )
        self.btn_stop.pack(side='left', padx=10)

        self.size_text.bind('<KeyRelease>', self.update_worker_recommendation)
        self.blur_scale.config(command=self.update_worker_recommendation)
        self.after_idle(self.update_worker_recommendation)

    def _on_blur_slide(self, val):
        self.blur_scale_val.config(text=str(int(float(val))))
        self.update_worker_recommendation()

    def set_inputs_enabled(self, enabled=True):
        """Khóa hoặc mở lại toàn bộ các nút điều khiển cấu hình trên giao diện khi đang render."""
        config_state = 'normal' if enabled else 'disabled'
        stop_state = 'disabled' if enabled else 'normal'

        self.btn_start.config(state=config_state)
        self.btn_stop.config(state=stop_state)
        self.btn_pick_inputs.config(state=config_state)
        self.btn_pick_outro.config(state=config_state)
        self.btn_pick_output.config(state=config_state)
        self.btn_apply_workers.config(state=config_state)

        self.prefix_entry.config(state=config_state)
        self.suffix_entry.config(state=config_state)
        self.workers_spinbox.config(state=config_state)
        self.overlay_duration_entry.config(state=config_state)
        self.replace_duration_entry.config(state=config_state)
        self.size_text.config(state=config_state)
        self.radio_concat.config(state=config_state)
        self.radio_overlay.config(state=config_state)
        self.radio_replace.config(state=config_state)
        self.blur_scale.config(state=config_state)

    def toggle_outro_mode_ui(self):
        is_overlay = (self.outro_mode.get() == MODE_OVERLAY_LAST)
        is_replace = (self.outro_mode.get() == MODE_REPLACE_LAST)
        for widget, visible in (
            (self.overlay_duration_label, is_overlay),
            (self.overlay_duration_entry, is_overlay),
            (self.overlay_duration_hint, is_overlay),
            (self.replace_duration_label, is_replace),
            (self.replace_duration_entry, is_replace),
            (self.replace_duration_hint, is_replace),
        ):
            if visible:
                widget.grid()
            else:
                widget.grid_remove()

    def get_worker_recommendation(self):
        """Ước lượng workers theo CPU, encoder, số job và độ phân giải đích."""
        cpu_count = max(1, os.cpu_count() or 1)
        size_pairs = set()
        for line in self.size_text.get('1.0', 'end').splitlines():
            match = re.match(r'^\s*(\d+)\s*[xX]\s*(\d+)\s*$', line)
            if match:
                width, height = int(match.group(1)), int(match.group(2))
                if width > 0 and height > 0:
                    size_pairs.add((width, height))

        size_count = max(1, len(size_pairs))
        task_count = max(1, len(self.inputs) * size_count)
        max_pixels = max((width * height for width, height in size_pairs), default=0)

        is_hardware_encoder = self.encoder_type not in ('cpu', 'detecting')
        cores_per_worker = 6 if is_hardware_encoder else 4
        capacity = min(4, max(1, math.ceil(cpu_count / cores_per_worker)))

        if max_pixels >= 3840 * 2160:
            capacity = min(capacity, 2)
        elif max_pixels >= 2560 * 1440:
            capacity = min(capacity, 3)

        try:
            if int(self.blur_percent.get()) >= 160:
                capacity = max(1, capacity - 1)
        except (ValueError, tk.TclError):
            pass

        return max(1, min(16, capacity, task_count))

    def update_worker_recommendation(self, _event=None):
        """Cập nhật gợi ý trên Main Thread khi cấu hình render thay đổi."""
        if not hasattr(self, 'workers_hint'):
            return
        recommended = self.get_worker_recommendation()
        cpu_count = os.cpu_count() or 1
        encoder_label = 'GPU' if self.encoder_type not in ('cpu', 'detecting') else 'CPU'
        sizes = set()
        for line in self.size_text.get('1.0', 'end').splitlines():
            match = re.match(r'^\s*(\d+)\s*[xX]\s*(\d+)\s*$', line)
            if match:
                sizes.add((int(match.group(1)), int(match.group(2))))
        task_count = max(1, len(self.inputs) * max(1, len(sizes)))
        largest_size = max(sizes, key=lambda size: size[0] * size[1], default=None)
        size_label = f" · tới {largest_size[0]}x{largest_size[1]}" if largest_size else ''
        self.workers_hint.config(
            text=f'Gợi ý: {recommended} luồng · {task_count} tác vụ · {cpu_count} CPU · {encoder_label}{size_label}'
        )

    def apply_worker_recommendation(self):
        self.max_workers.set(self.get_worker_recommendation())

    def pick_inputs(self):
        files = filedialog.askopenfilenames(
            title='Chọn danh sách video đầu vào',
            filetypes=[('Video Files', '*.mp4 *.mov *.mkv *.avi *.webm *.m4v'), ('All Files', '*.*')]
        )
        if files:
            self.inputs = list(files)
            self.input_label.config(text=f'Đã chọn {len(self.inputs)} video')
            self.update_worker_recommendation()

    def pick_outro(self):
        file = filedialog.askopenfilename(
            title='Chọn video outro',
            filetypes=[('Video Files', '*.mp4 *.mov *.mkv *.avi *.webm *.m4v'), ('All Files', '*.*')]
        )
        if file:
            self.outro = file
            self.outro_label.config(text=os.path.basename(self.outro))
        else:
            self.outro = None
            self.outro_label.config(text='Không có')
        self.update_worker_recommendation()

    def pick_output(self):
        folder = filedialog.askdirectory(title='Chọn thư mục lưu video xuất ra')
        if folder:
            self.output_dir = folder
            self.output_label.config(text=self.output_dir)

    def validate_before_start(self):
        """Xác thực toàn bộ dữ liệu nhập trên Main Thread trước khi khởi chạy."""
        if not self.ffmpeg_bin or not self.ffprobe_bin:
            missing = []
            if not self.ffmpeg_bin:
                missing.append("FFmpeg")
            if not self.ffprobe_bin:
                missing.append("FFprobe")
            messagebox.showerror('Lỗi thiếu công cụ', f"Không tìm thấy {' và '.join(missing)}! Bắt buộc phải có cả hai để xử lý video.")
            return False

        if not self.inputs:
            messagebox.showerror('Lỗi', 'Chưa chọn video input!')
            return False
        if not self.output_dir:
            messagebox.showerror('Lỗi', 'Chưa chọn thư mục output!')
            return False
        if self.outro_mode.get() not in (MODE_CONCAT, MODE_OVERLAY_LAST, MODE_REPLACE_LAST):
            messagebox.showerror('Lỗi', 'Chế độ xử lý outro không hợp lệ!')
            return False
        if self.outro_mode.get() in (MODE_OVERLAY_LAST, MODE_REPLACE_LAST) and not self.outro:
            messagebox.showerror('Lỗi', 'Chế độ đè hoặc thay outro yêu cầu chọn file outro mới!')
            return False
        if self.outro_mode.get() == MODE_OVERLAY_LAST:
            try:
                duration = float(self.overlay_duration.get().strip())
                if not math.isfinite(duration) or duration <= 0:
                    messagebox.showerror('Lỗi', 'Độ dài đè outro cuối phải lớn hơn 0 giây!')
                    return False
            except ValueError:
                messagebox.showerror('Lỗi', 'Độ dài đè outro cuối phải là số hợp lệ!')
                return False

        if self.outro_mode.get() == MODE_REPLACE_LAST and self.replace_duration.get().strip():
            try:
                duration = float(self.replace_duration.get().strip())
                if not math.isfinite(duration) or duration <= 0:
                    messagebox.showerror('Lỗi', 'Thời lượng cắt outro cũ phải là số hữu hạn lớn hơn 0 giây!')
                    return False
            except ValueError:
                messagebox.showerror('Lỗi', 'Thời lượng cắt outro cũ phải là số hợp lệ hoặc để trống để tự động!')
                return False

        try:
            workers = int(self.max_workers.get())
            if workers < 1 or workers > 16:
                messagebox.showerror('Lỗi', 'Số luồng song song (Workers) phải trong khoảng 1 đến 16!')
                return False
        except (ValueError, tk.TclError):
            messagebox.showerror('Lỗi', 'Số luồng song song (Workers) không hợp lệ!')
            return False

        raw_lines = [s.strip() for s in self.size_text.get('1.0', 'end').splitlines() if s.strip()]
        if not raw_lines:
            messagebox.showerror('Lỗi', 'Danh sách kích thước (size) không được để trống!')
            return False

        parsed_sizes = []
        seen_sizes = set()
        for idx, line in enumerate(raw_lines, 1):
            m = re.match(r'^(\d+)\s*[xX]\s*(\d+)$', line)
            if not m:
                messagebox.showerror(
                    'Lỗi định dạng size',
                    f'Dòng {idx} trong danh sách size không đúng định dạng WxH: "{line}"\n'
                    'Ví dụ hợp lệ: 1080x1920'
                )
                return False
            w, h = int(m.group(1)), int(m.group(2))
            if w <= 0 or h <= 0:
                messagebox.showerror('Lỗi', f'Kích thước dòng {idx} phải lớn hơn 0: "{line}"')
                return False
            if w % 2 != 0 or h % 2 != 0:
                messagebox.showerror(
                    'Lỗi kích thước lẻ',
                    f'Kích thước dòng {idx} ({w}x{h}) có chiều không chia hết cho 2!\n'
                    'Chuẩn H.264 yêu cầu cả chiều rộng và chiều cao phải là số chẵn.\n'
                    f'Gợi ý: đổi thành {w + (w % 2)}x{h + (h % 2)}'
                )
                return False

            if (w, h) not in seen_sizes:
                seen_sizes.add((w, h))
                parsed_sizes.append((w, h))

        self.validated_sizes = parsed_sizes
        return True

    def start(self):
        if not self.validate_before_start():
            return

        self.stop_flag = False
        self.set_inputs_enabled(False)
        self.status_label.config(text='Đang khởi tạo danh sách render...')

        workers = int(self.max_workers.get())

        if self.encoder_type == 'cpu':
            batch_encoder_args = get_cpu_fallback_args(workers)
            batch_encoder_type = 'cpu'
        else:
            batch_encoder_args = list(self.encoder_args)
            batch_encoder_type = self.encoder_type

        job_config = {
            'inputs': list(self.inputs),
            'outro': self.outro,
            'output_dir': self.output_dir,
            'sizes': list(self.validated_sizes),
            'prefix': self.prefix_entry.get().strip(),
            'suffix': self.suffix_entry.get().strip(),
            'blur_percent': self.blur_percent.get(),
            'outro_mode': self.outro_mode.get(),
            'overlay_duration': float(self.overlay_duration.get().strip()) if self.outro_mode.get() == MODE_OVERLAY_LAST else 0.0,
            'replace_duration': (
                float(self.replace_duration.get().strip())
                if self.outro_mode.get() == MODE_REPLACE_LAST and self.replace_duration.get().strip()
                else None
            ),
            'workers': workers,
            'encoder_args': batch_encoder_args,
            'encoder_type': batch_encoder_type
        }

        threading.Thread(target=self.render_all_thread, args=(job_config,), daemon=True).start()

    def stop(self):
        """Khóa chặt chẽ (Atomic Lock) ngắt ngay toàn bộ tiến trình con FFmpeg/FFprobe đang chạy."""
        with self.proc_lock:
            self.stop_flag = True
            for p in list(self.active_processes):
                try:
                    p.terminate()
                except Exception:
                    pass
            self.active_processes.clear()
        self.ui_queue.put(('status', 'Đang dừng và hủy các tiến trình...'))

    def process_ui_queue(self):
        """Chạy định kỳ 50ms trên Main Thread để cập nhật Tkinter UI an toàn tuyệt đối."""
        try:
            while True:
                msg = self.ui_queue.get_nowait()
                msg_type = msg[0]

                if msg_type == 'encoder_detected':
                    _, args, name, enc_type = msg
                    self.encoder_args = args
                    self.encoder_name = name
                    self.encoder_type = enc_type
                    self.hw_label.config(text=f'Bộ mã hóa: {self.encoder_name}')
                    self.update_worker_recommendation()
                    self.stop_flag = False
                    self.btn_start.config(state='normal')
                    self.btn_stop.config(state='disabled')
                    self.status_label.config(text='Sẵn sàng')

                elif msg_type == 'progress':
                    _, done, total, curr_file = msg
                    self.progress['maximum'] = total
                    self.progress['value'] = done
                    self.status_label.config(text=f'Đang render ({done}/{total}): {curr_file}')

                elif msg_type == 'status':
                    _, text = msg
                    self.status_label.config(text=text)

                elif msg_type == 'finished':
                    _, success_cnt, fail_cnt, total, fail_details, batch_output_dir = msg
                    self.set_inputs_enabled(True)
                    if fail_cnt == 0:
                        self.status_label.config(text=f'HOÀN TẤT TOÀN BỘ: {success_cnt}/{total} video thành công!')
                        messagebox.showinfo('Hoàn tất', f'Đã render thành công toàn bộ {success_cnt}/{total} video!')
                    else:
                        self.status_label.config(text=f'HOÀN TẤT CÓ LỖI: {success_cnt} thành công, {fail_cnt} thất bại.')
                        log_path = os.path.join(batch_output_dir or '.', 'render_errors.log')
                        log_saved = False
                        try:
                            with open(log_path, 'w', encoding='utf-8') as f:
                                for fn, err in fail_details:
                                    f.write(f"========================================\nFILE: {fn}\nERROR:\n{err}\n\n")
                            log_saved = True
                        except Exception:
                            log_saved = False

                        if log_saved:
                            msg_text = (
                                f'Quá trình render hoàn tất:\n'
                                f'- Thành công: {success_cnt} video\n'
                                f'- Thất bại: {fail_cnt} video\n\n'
                                f'Chi tiết lỗi đã được lưu vào file:\n{log_path}'
                            )
                        else:
                            first_err = fail_details[0][1][:200] if fail_details else 'Lỗi không xác định'
                            msg_text = (
                                f'Quá trình render hoàn tất:\n'
                                f'- Thành công: {success_cnt} video\n'
                                f'- Thất bại: {fail_cnt} video\n\n'
                                f'Lỗi ví dụ:\n{first_err}...'
                            )

                        messagebox.showwarning('Cảnh báo lỗi render', msg_text)

                elif msg_type == 'stopped':
                    self.set_inputs_enabled(True)
                    self.status_label.config(text='Đã dừng tác vụ theo yêu cầu.')

        except queue.Empty:
            pass
        finally:
            self.after(50, self.process_ui_queue)

    def run_tracked_subprocess(self, cmd, timeout=5.0):
        """Khởi chạy tiến trình con có theo dõi trong active_processes để lệnh STOP hủy được ngay."""
        flags = subprocess.CREATE_NO_WINDOW if IS_WIN else 0
        with self.proc_lock:
            if self.stop_flag:
                raise RuntimeError('Tác vụ đã bị dừng bởi người dùng')
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=flags
            )
            self.active_processes.add(proc)

        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            return proc.returncode, stdout, stderr
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise TimeoutError(f"Tiến trình hết thời gian chờ ({timeout}s)")
        finally:
            with self.proc_lock:
                self.active_processes.discard(proc)

    def probe_duration(self, path):
        """
        Lấy thời lượng theo video stream (v:0) bằng định dạng JSON chuẩn:
        1. stream.duration hoặc duration_ts * time_base nếu stream có metadata thời lượng.
        2. stream tags (DURATION): Thường có trong container Matroska/WebM.
        3. nb_frames / avg_frame_rate: Ước lượng dự phòng nếu metadata container cung cấp frame count và framerate trung bình.
        4. format.duration: Mức dự phòng cuối cùng từ container header.
        """
        if self.stop_flag:
            raise RuntimeError('Tác vụ đã bị dừng bởi người dùng')
        if not self.ffprobe_bin:
            raise RuntimeError('Không tìm thấy ffprobe')

        cmd = [
            self.ffprobe_bin,
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=duration,duration_ts,time_base,nb_frames,avg_frame_rate:stream_tags:format=duration',
            '-of', 'json',
            path
        ]

        try:
            ret, stdout, stderr = self.run_tracked_subprocess(cmd, timeout=5.0)
            if ret != 0:
                raise RuntimeError(f"ffprobe lỗi khi đọc file (mã {ret}): {stderr.strip()}")
            if not stdout.strip():
                raise RuntimeError(f"ffprobe trả về kết quả rỗng khi đọc {path}")

            data = json.loads(stdout)

            def positive_seconds(value):
                try:
                    seconds = float(value)
                except (TypeError, ValueError):
                    return None
                return seconds if math.isfinite(seconds) and seconds > 0 else None

            streams = data.get('streams', [])
            if streams:
                s = streams[0]
                duration = positive_seconds(s.get('duration'))
                if duration is not None:
                    return duration

                duration_ts = positive_seconds(s.get('duration_ts'))
                time_base = s.get('time_base') or ''
                if duration_ts is not None and '/' in time_base:
                    try:
                        numerator, denominator = time_base.split('/', 1)
                        seconds_per_tick = float(numerator) / float(denominator)
                        if math.isfinite(seconds_per_tick) and seconds_per_tick > 0:
                            duration = positive_seconds(duration_ts * seconds_per_tick)
                            if duration is not None:
                                return duration
                    except (TypeError, ValueError, ZeroDivisionError):
                        pass

                tags = s.get('tags', {})
                for k, v in tags.items():
                    if 'duration' in k.lower() and v and v != 'N/A':
                        try:
                            if ':' in v:
                                parts = v.split(':')
                                tag_duration = positive_seconds(
                                    float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                                )
                            else:
                                tag_duration = positive_seconds(v)
                            if tag_duration is not None:
                                return tag_duration
                        except Exception:
                            pass

                nb_frames = s.get('nb_frames')
                avg_fps = s.get('avg_frame_rate')
                if nb_frames and nb_frames != 'N/A' and avg_fps and avg_fps != 'N/A' and '/' in avg_fps:
                    try:
                        num, den = avg_fps.split('/', 1)
                        fps = float(num) / float(den)
                        frame_count = float(nb_frames)
                        if math.isfinite(fps) and fps > 0 and math.isfinite(frame_count) and frame_count > 0:
                            duration = positive_seconds(frame_count / fps)
                            if duration is not None:
                                return duration
                    except (TypeError, ValueError, ZeroDivisionError):
                        pass

            fmt = data.get('format', {})
            duration = positive_seconds(fmt.get('duration'))
            if duration is not None:
                return duration

        except Exception as exc:
            if isinstance(exc, RuntimeError):
                raise
            raise RuntimeError(f'Lỗi phân tích thời lượng video {path}: {exc}') from exc

        raise RuntimeError(f'Không thể xác định thời lượng của video: {path}')

    def has_audio_stream(self, path):
        """
        Kiểm tra video có stream âm thanh hay không qua JSON output chuẩn.
        Bắt buộc fail-safe: nếu ffprobe lỗi đọc file, ném ngoại lệ rõ ràng, không coi là silent.
        """
        if self.stop_flag:
            return False
        if not path or not self.ffprobe_bin:
            raise RuntimeError('Không tìm thấy ffprobe để kiểm tra luồng âm thanh')

        cmd = [
            self.ffprobe_bin,
            '-v', 'error',
            '-select_streams', 'a',
            '-show_entries', 'stream=codec_type',
            '-of', 'json',
            path
        ]
        try:
            ret, stdout, stderr = self.run_tracked_subprocess(cmd, timeout=5.0)
            if ret != 0:
                raise RuntimeError(f'Lỗi kiểm tra âm thanh (ffprobe mã lỗi {ret}): {stderr.strip()}')
            if not stdout.strip():
                raise RuntimeError('ffprobe trả về kết quả rỗng khi kiểm tra âm thanh')

            data = json.loads(stdout)
            return len(data.get('streams', [])) > 0
        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            raise RuntimeError(f'Lỗi phân tích âm thanh file {path}: {e}') from e

    def build_fast_blur_filter(self, w, h, p, input_label='[0:v]', output_label='[bg]'):
        """Kỹ thuật Fast Blur: Hạ độ phân giải nền -> BoxBlur (O(1)) -> Upscale Bicubic."""
        if p <= 0:
            return f"{input_label}scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1{output_label}"

        scale_div = 4 if p <= 120 else 8
        w_low = max(32, (int(w) // scale_div // 2) * 2)
        h_low = max(32, (int(h) // scale_div // 2) * 2)

        radius = max(2, min(40, int((p / 100.0) * 10)))
        power = 2

        blur_op = f"boxblur={radius}:{power}"
        return (
            f"{input_label}scale={w_low}:{h_low}:force_original_aspect_ratio=increase,"
            f"crop={w_low}:{h_low},{blur_op},"
            f"scale={w}:{h}:flags=bicubic,setsar=1{output_label}"
        )

    def execute_ffmpeg(self, cmd):
        """Thực thi lệnh FFmpeg có bảo vệ tiến trình (Atomic lock) và bắt lỗi stderr."""
        flags = subprocess.CREATE_NO_WINDOW if IS_WIN else 0
        with self.proc_lock:
            if self.stop_flag:
                return False, 'Tác vụ đã bị dừng bởi người dùng'
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, creationflags=flags)
                self.active_processes.add(proc)
            except Exception as e:
                return False, f'Lỗi khởi chạy tiến trình FFmpeg: {e}'

        _, stderr = proc.communicate()

        with self.proc_lock:
            self.active_processes.discard(proc)

        if proc.returncode != 0:
            return False, stderr or f'FFmpeg kết thúc với mã lỗi {proc.returncode}'
        return True, ''

    def render_one(self, input_video, output_path, w, h, config):
        """
        Xử lý 1 video an toàn tuyệt đối:
        - Cắt audio theo thời lượng video xác định được từ metadata (atrim=duration=...)
        - Render vào file tạm riêng (temp output), chỉ swap sang file đích khi thành công 100%.
        - Kiểm tra file tạm tồn tại và có dung lượng > 0 trước khi hoán đổi.
        """
        if self.stop_flag:
            return False, 'Tác vụ đã bị dừng'

        temp_output_path = f"{output_path}.tmp_{uuid.uuid4().hex[:8]}.mp4"

        p = config['blur_percent']
        outro_mode = config['outro_mode']
        outro_path = config['outro']

        has_in_audio = self.has_audio_stream(input_video)
        is_concat = bool(outro_path and outro_mode == MODE_CONCAT)
        is_replace = bool(outro_path and outro_mode == MODE_REPLACE_LAST)
        is_overlay = bool(outro_path and outro_mode == MODE_OVERLAY_LAST)
        has_out_audio = self.has_audio_stream(outro_path) if (is_concat or is_replace) else False

        needs_input_duration = (
            has_in_audio
            or is_replace
            or is_overlay
            or (is_concat and not has_in_audio and has_out_audio)
        )
        input_duration = self.probe_duration(input_video) if needs_input_duration else None

        configured_replace_duration = config.get('replace_duration')
        needs_outro_duration = (
            is_overlay
            or (is_replace and (configured_replace_duration is None or has_in_audio or has_out_audio))
            or (is_concat and (has_in_audio or has_out_audio))
        )
        outro_duration = self.probe_duration(outro_path) if needs_outro_duration else None

        kept_input_duration = input_duration
        if is_replace:
            replace_duration = config.get('replace_duration')
            replace_duration = outro_duration if replace_duration is None else replace_duration
            if not math.isfinite(replace_duration) or replace_duration <= 0:
                raise RuntimeError('Thời lượng cắt outro cũ phải lớn hơn 0 giây.')
            if replace_duration >= input_duration:
                raise RuntimeError(
                    f'Thời lượng cắt ({replace_duration:.3f}s) phải ngắn hơn video gốc '
                    f'({input_duration:.3f}s) để giữ lại phần nội dung chính.'
                )
            kept_input_duration = input_duration - replace_duration

        input_audio_duration = kept_input_duration if is_replace else input_duration

        input_args = ['-i', input_video]
        filter_parts = [
            "[0:v]split=2[bg_src][fg_src]",
            self.build_fast_blur_filter(w, h, p, '[bg_src]', '[bg]'),
            f"[fg_src]scale={w}:{h}:force_original_aspect_ratio=decrease,setsar=1[fg]",
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[v_base]"
        ]

        vmap = '[v_base]'
        amap = None

        if outro_path:
            filter_parts.extend([
                "[1:v]split=2[outro_bg_src][outro_fg_src]",
                self.build_fast_blur_filter(w, h, p, '[outro_bg_src]', '[outro_bg]'),
                f"[outro_fg_src]scale={w}:{h}:force_original_aspect_ratio=decrease,setsar=1[outro_fg]",
                "[outro_bg][outro_fg]overlay=(W-w)/2:(H-h)/2,setsar=1[outro_canvas]"
            ])

        if has_in_audio:
            filter_parts.append(f"[0:a]aresample=48000,asetpts=N/SR/TB,atrim=duration={input_audio_duration}[a0]")
            amap = '[a0]'

        if is_concat or is_replace:
            input_args.extend(['-i', outro_path])

            if is_replace:
                filter_parts.append(
                    f"[v_base]trim=duration={kept_input_duration},setpts=PTS-STARTPTS[v0]"
                )
            else:
                filter_parts.append("[v_base]setpts=PTS-STARTPTS[v0]")
            filter_parts.append("[outro_canvas]setpts=PTS-STARTPTS[v1]")

            if has_in_audio and has_out_audio:
                filter_parts.append(f"[1:a]aresample=48000,asetpts=N/SR/TB,atrim=duration={outro_duration}[a1]")
                filter_parts.append("[v0][a0][v1][a1]concat=n=2:v=1:a=1[vout][aout]")
                vmap = '[vout]'
                amap = '[aout]'
            elif has_in_audio and not has_out_audio:
                filter_parts.append(f"anullsrc=channel_layout=stereo:sample_rate=48000,atrim=duration={outro_duration}[a1]")
                filter_parts.append("[v0][a0][v1][a1]concat=n=2:v=1:a=1[vout][aout]")
                vmap = '[vout]'
                amap = '[aout]'
            elif not has_in_audio and has_out_audio:
                filter_parts.append(f"anullsrc=channel_layout=stereo:sample_rate=48000,atrim=duration={input_audio_duration}[a0]")
                filter_parts.append(f"[1:a]aresample=48000,asetpts=N/SR/TB,atrim=duration={outro_duration}[a1]")
                filter_parts.append("[v0][a0][v1][a1]concat=n=2:v=1:a=1[vout][aout]")
                vmap = '[vout]'
                amap = '[aout]'
            else:
                filter_parts.append("[v0][v1]concat=n=2:v=1:a=0[vout]")
                vmap = '[vout]'
                amap = None

        elif is_overlay:
            input_args.extend(['-i', outro_path])
            requested_duration = config['overlay_duration']
            effective_duration = min(requested_duration, input_duration)
            overlay_start = max(input_duration - effective_duration, 0)
            base_outro_duration = min(outro_duration, effective_duration)
            pad_duration = max(effective_duration - base_outro_duration, 0)

            filter_parts.append(
                f"[outro_canvas]trim=duration={base_outro_duration}[v1base]"
            )
            if pad_duration > 0:
                filter_parts.append(
                    f"[v1base]tpad=stop_mode=clone:stop_duration={pad_duration},"
                    f"setpts=PTS-STARTPTS+{overlay_start}/TB[v1shift]"
                )
            else:
                filter_parts.append(f"[v1base]setpts=PTS-STARTPTS+{overlay_start}/TB[v1shift]")

            filter_parts.append("[v_base][v1shift]overlay=eof_action=pass[vout]")
            vmap = '[vout]'
            amap = '[a0]' if has_in_audio else None

        filter_complex = ';'.join(filter_parts)
        audio_args = ['-map', amap, '-c:a', 'aac', '-b:a', '192k'] if amap else ['-an']

        def make_cmd(enc_args):
            return [
                self.ffmpeg_bin, '-y',
                *input_args,
                '-filter_complex', filter_complex,
                '-map', vmap,
                *audio_args,
                *enc_args,
                temp_output_path
            ]

        success = False
        err = ''
        try:
            cmd_primary = make_cmd(config['encoder_args'])
            success, err = self.execute_ffmpeg(cmd_primary)

            cpu_args = get_cpu_fallback_args(config['workers'])
            if not success and not self.stop_flag and config['encoder_type'] != 'cpu':
                cmd_fallback = make_cmd(cpu_args)
                success, err = self.execute_ffmpeg(cmd_fallback)

            if success and not self.stop_flag:
                if not os.path.isfile(temp_output_path) or os.path.getsize(temp_output_path) == 0:
                    success = False
                    err = 'Lỗi render: FFmpeg báo hoàn tất nhưng file tạm không tồn tại hoặc có kích thước 0 byte.'
                else:
                    try:
                        os.replace(temp_output_path, output_path)
                    except Exception as replace_err:
                        success = False
                        err = f'Lỗi hoán đổi file kết quả (os.replace): {replace_err}'

        finally:
            if os.path.isfile(temp_output_path):
                try:
                    os.remove(temp_output_path)
                except Exception:
                    pass

        return success, err

    def render_all_thread(self, config):
        """Luồng nền xử lý danh sách render và gửi kết quả về Main Thread qua Queue."""
        try:
            tasks = []
            used_output_norm_keys = set()

            for input_video in config['inputs']:
                base = os.path.splitext(os.path.basename(input_video))[0]
                for w, h in config['sizes']:
                    size_str = f"{w}x{h}"
                    pfx = config['prefix']
                    sfx = config['suffix']
                    parts = [p for p in [pfx, base, size_str, sfx] if p]
                    cand_name = f"{'_'.join(parts)}.mp4"

                    norm_key = normalize_filename_key(cand_name)
                    if norm_key in used_output_norm_keys:
                        idx = 2
                        stem = '_'.join(parts)
                        while normalize_filename_key(f"{stem}_{idx}.mp4") in used_output_norm_keys:
                            idx += 1
                        cand_name = f"{stem}_{idx}.mp4"

                    used_output_norm_keys.add(normalize_filename_key(cand_name))
                    output_path = os.path.join(config['output_dir'], cand_name)
                    tasks.append((input_video, output_path, w, h, cand_name))

            total_jobs = len(tasks)
            done_jobs = 0
            success_count = 0
            failed_details = []
            done_lock = threading.Lock()

            workers = max(1, min(16, config['workers']))
            self.ui_queue.put(('status', f'Đang render {total_jobs} video ({workers} luồng song song)...'))

            def job_wrapper(item):
                nonlocal done_jobs, success_count
                if self.stop_flag:
                    return

                input_v, out_p, w, h, out_n = item
                try:
                    success, err_msg = self.render_one(input_v, out_p, w, h, config)
                except Exception as e:
                    success = False
                    err_msg = f"Ngoại lệ worker: {e}\n{traceback.format_exc()}"

                with done_lock:
                    done_jobs += 1
                    if success:
                        success_count += 1
                    else:
                        if not self.stop_flag:
                            failed_details.append((out_n, err_msg))
                    self.ui_queue.put(('progress', done_jobs, total_jobs, out_n))

            with ThreadPoolExecutor(max_workers=workers) as executor:
                for item in tasks:
                    if self.stop_flag:
                        break
                    executor.submit(job_wrapper, item)

            if self.stop_flag:
                self.ui_queue.put(('stopped',))
            else:
                fail_count = total_jobs - success_count
                self.ui_queue.put(('finished', success_count, fail_count, total_jobs, failed_details, config['output_dir']))

        except Exception as e:
            self.ui_queue.put(('status', f'Lỗi hệ thống: {e}'))
            self.ui_queue.put(('stopped',))

if __name__ == '__main__':
    app = App()
    app.mainloop()
