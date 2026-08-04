"""relaxASMR Tkinter GUI。"""

import os

# OpenCV 的 FFmpeg 后端默认把解码告警直接写到进程 stderr（C 层，Python 端捕获不到）。
# 遇到尚未写完或损坏的 mp4 时会刷 "partial file" / "Invalid NAL unit size" 之类的噪音，
# 我们已在读取侧做了校验，这里把它降到静默。必须在首次 import cv2 之前设置。
os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "-8")
