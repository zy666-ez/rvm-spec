"""
共享引擎 —— 消除 server.py 与 rvm_run_live.py 之间的冗余代码。
两个文件只需 import 此类，不再各自重复实现 RVM 推理 / 色彩迁移 / 背景管理 / 指标计算。
"""

import torch
import cv2
import numpy as np
import os
import sys

# ── 路径：确保能 import RobustVideoMatting ──────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(BASE_DIR, 'RobustVideoMatting'))
from RobustVideoMatting.model import MattingNetwork


# ===================== 1. 色彩迁移（只写一次）=====================
def reinhard_color_transfer(fg_bgr, bg_bgr, alpha, l_ratio=1.0, ab_ratio=0.3):
    """基于 LAB 空间的 Reinhard 色彩迁移"""
    if len(alpha.shape) == 3:
        alpha = alpha.squeeze(-1)
    alpha = alpha.astype(np.float32)

    fg_lab = cv2.cvtColor(fg_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    bg_lab = cv2.cvtColor(bg_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)

    mask = alpha > 0.5
    if not np.any(mask):
        return fg_bgr

    out_lab = np.zeros_like(fg_lab)
    for i in range(3):
        fg_pixels = fg_lab[:, :, i][mask]
        bg_pixels = bg_lab[:, :, i]

        fg_mean, fg_std = np.mean(fg_pixels), np.std(fg_pixels) + 1e-6
        bg_mean, bg_std = np.mean(bg_pixels), np.std(bg_pixels) + 1e-6

        ratio = l_ratio if i == 0 else ab_ratio
        target_mean = fg_mean * (1 - ratio) + bg_mean * ratio
        target_std = fg_std * (1 - ratio) + bg_std * ratio

        channel_out = (target_std / fg_std) * (fg_lab[:, :, i] - fg_mean) + target_mean
        out_lab[:, :, i] = channel_out

    out_lab = np.clip(out_lab, 0, 255).astype(np.uint8)
    return cv2.cvtColor(out_lab, cv2.COLOR_LAB2BGR)


# ===================== 2. OpenCV 中文路径兼容 =====================
def imread_utf8(path):
    """cv2.imread 兼容非 ASCII 路径"""
    try:
        data = np.fromfile(path, dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return None


def videocap_from_path(path):
    """cv2.VideoCapture 兼容非 ASCII 路径"""
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        try:
            cap = cv2.VideoCapture(os.fsencode(path))
        except Exception:
            pass
    return cap


# ===================== 3. 核心管线类 =============================
class RVMPipeline:
    """RVM 实时抠图管线 —— server.py 和 rvm_run_live.py 共用"""

    def __init__(self, camera_id=0, weight_path=None, bg_folder='background'):
        # ── 模型 ──
        if weight_path is None:
            weight_path = os.path.join(BASE_DIR, 'RobustVideoMatting', 'weights', 'rvm_mobilenetv3.pth')
        self.model = MattingNetwork(variant='mobilenetv3').eval().cuda()
        self.model.load_state_dict(torch.load(weight_path))
        self.model = self.model.half()
        self.rec = [None] * 4   # RVM 时序状态

        # ── 摄像头 ──
        self.cap = cv2.VideoCapture(camera_id)
        if not self.cap.isOpened():
            raise RuntimeError(f"无法打开摄像头 (id={camera_id})")

        # ── 背景 ──
        self.bg_folder = bg_folder
        self.current_bg_img = None
        self.current_bg_video = None
        self.is_video_background = False
        self.valid_exts = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff',
                           '.mp4', '.avi', '.mov', '.mkv', '.flv')

        # ── 指标状态 ──
        self.prev_raw_alpha = None
        self.smooth_temp_var = 0.0
        self.smooth_lap_var = 0.0
        self.metrics_recording = False
        self.metrics_count = 0
        self.metrics_max = 100
        self.temporal_vars = []
        self.laplacian_vars = []
        self.metrics_result = None

        # ── 人像缩放（背景不变）──
        self.zoom_level = 1.0     # 1.0=原始, >1放大, <1缩小
        self.ZOOM_MIN = 0.5
        self.ZOOM_MAX = 3.0

    # ────── 摄像头 ──────────────────────────────────────────
    def read_frame(self):
        """返回 (ret, frame)"""
        return self.cap.read()

    def release(self):
        if self.current_bg_video is not None:
            self.current_bg_video.release()
        self.cap.release()

    # ────── 背景管理 ────────────────────────────────────────
    def scan_backgrounds(self):
        """返回 background 文件夹下所有有效文件名列表"""
        if not os.path.exists(self.bg_folder):
            os.makedirs(self.bg_folder, exist_ok=True)
            return []
        files = [f for f in os.listdir(self.bg_folder)
                 if f.lower().endswith(self.valid_exts)]
        files.sort()
        return files

    def load_background(self, filename):
        """根据文件名加载背景，自动识别图片/视频；返回 (ok, message)"""
        path = os.path.join(self.bg_folder, filename)
        if not os.path.exists(path):
            return False, f"文件不存在：{filename}"

        img = imread_utf8(path)
        if img is not None:
            if self.current_bg_video is not None:
                self.current_bg_video.release()
                self.current_bg_video = None
            self.current_bg_img = img
            self.is_video_background = False
            return True, f"已加载背景图片: {filename}"

        cap_video = videocap_from_path(path)
        if cap_video.isOpened():
            if self.current_bg_video is not None:
                self.current_bg_video.release()
            self.current_bg_video = cap_video
            self.is_video_background = True
            return True, f"已加载动态背景: {filename}"

        return False, f"无法识别的文件格式: {filename}"

    def get_background_frame(self, target_w, target_h):
        """获取当前背景的一帧，缩放到目标尺寸"""
        if self.is_video_background and self.current_bg_video is not None:
            ret, frame = self.current_bg_video.read()
            if not ret:
                self.current_bg_video.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.current_bg_video.read()
            if ret:
                return cv2.resize(frame, (target_w, target_h))
        if self.current_bg_img is not None:
            return cv2.resize(self.current_bg_img, (target_w, target_h))
        return np.zeros((target_h, target_w, 3), dtype=np.uint8)

    # ────── 推理核心（单帧）──────────────────────────────────
    def infer(self, frame):
        """
        输入 BGR frame (numpy)，返回:
            alpha: (H, W) float32 [0,1]
            fgr:   (1,3,H,W) tensor (GPU half)
            pha:   (1,1,H,W) tensor (GPU half)
        """
        img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = torch.from_numpy(img).permute(2, 0, 1).unsqueeze(0).cuda().half() / 255.0

        with torch.no_grad():
            fgr, pha, *self.rec = self.model(img, *self.rec, downsample_ratio=0.5)

        # 后处理 alpha
        alpha = pha.squeeze(0).permute(1, 2, 0).cpu().numpy().astype(np.float32)
        if len(alpha.shape) == 3:
            alpha = alpha.squeeze(-1)

        # 边缘优化
        alpha = np.clip((alpha - 0.15) * 1.5, 0.0, 1.0)
        blurred_alpha = cv2.GaussianBlur(alpha, (3, 3), 0)
        alpha = cv2.addWeighted(alpha, 1.8, blurred_alpha, -0.8, 0)
        alpha = np.clip(alpha, 0.0, 1.0)
        alpha[alpha < 0.02] = 0.0
        alpha[alpha > 0.98] = 1.0

        return alpha, fgr, pha

    # ────── 指标计算 ────────────────────────────────────────
    def compute_metrics(self, alpha):
        """
        计算并累积时序方差 / 拉普拉斯方差。
        返回 (temp_var, lap_var)，若正在录制且满 100 帧则自动停止并生成 result。
        """
        edge_mask = (alpha > 0.0) & (alpha < 1.0)
        lap = cv2.Laplacian(alpha, cv2.CV_32F)
        lap_var = np.var(lap[edge_mask]) if np.any(edge_mask) else 0.0

        temp_var = 0.0
        if self.prev_raw_alpha is not None:
            if np.any(edge_mask):
                temp_var = np.var(alpha[edge_mask] - self.prev_raw_alpha[edge_mask])
        self.prev_raw_alpha = alpha.copy()

        # EMA 平滑
        self.smooth_lap_var = 0.8 * self.smooth_lap_var + 0.2 * lap_var
        self.smooth_temp_var = 0.8 * self.smooth_temp_var + 0.2 * temp_var

        # 录制逻辑
        if self.metrics_recording:
            self.temporal_vars.append(temp_var)
            self.laplacian_vars.append(lap_var)
            self.metrics_count += 1
            if self.metrics_count >= self.metrics_max:
                self.metrics_recording = False
                mean_temp = np.mean(self.temporal_vars)
                std_temp = np.std(self.temporal_vars)
                mean_lap = np.mean(self.laplacian_vars)
                std_lap = np.std(self.laplacian_vars)
                self.metrics_result = {
                    'frames': self.metrics_max,
                    'mean_temp': round(float(mean_temp), 6),
                    'std_temp': round(float(std_temp), 6),
                    'mean_lap': round(float(mean_lap), 6),
                    'std_lap': round(float(std_lap), 6),
                }

        return temp_var, lap_var

    def start_recording(self):
        """开始录制 100 帧指标"""
        self.metrics_recording = True
        self.metrics_count = 0
        self.temporal_vars.clear()
        self.laplacian_vars.clear()
        self.metrics_result = None

    # ────── 合成 ────────────────────────────────────────────
    def composite(self, frame, alpha, mode='real', blur=False):
        """
        将 frame 与背景合成。
        mode: 'real' 显示原背景，'virtual' 替换为自定义背景
        zoom_level 只缩放前景人像，背景保持不变
        返回 BGR view (uint8)
        """
        h, w = frame.shape[:2]
        fg = frame.astype(np.float32)
        a = alpha.copy()

        # ── 人像缩放：裁剪中心 → 缩放回原尺寸，背景不动 ──
        if abs(self.zoom_level - 1.0) > 0.001:
            crop_w = int(w / self.zoom_level)
            crop_h = int(h / self.zoom_level)
            x1 = max(0, (w - crop_w) // 2)
            y1 = max(0, (h - crop_h) // 2)
            x2 = min(w, x1 + crop_w)
            y2 = min(h, y1 + crop_h)
            fg = cv2.resize(fg[y1:y2, x1:x2], (w, h))
            a = cv2.resize(a[y1:y2, x1:x2], (w, h))

        alpha_3d = np.expand_dims(a, axis=-1).astype(np.float32)
        alpha_3 = np.repeat(alpha_3d, 3, axis=2)

        if mode == 'real':
            bg_frame = frame.copy().astype(np.float32)
        else:
            bg_frame = self.get_background_frame(w, h).astype(np.float32)

        if blur:
            bg_frame = cv2.GaussianBlur(bg_frame, (35, 35), 0)

        if mode == 'virtual':
            harmonized_fg = reinhard_color_transfer(
                np.clip(fg, 0, 255).astype(np.uint8),
                np.clip(bg_frame, 0, 255).astype(np.uint8),
                a
            )
            view = (harmonized_fg.astype(np.float32) * alpha_3 +
                    bg_frame * (1 - alpha_3)).astype(np.uint8)
        else:
            view = (fg * alpha_3 + bg_frame * (1 - alpha_3)).astype(np.uint8)

        return view

    def set_zoom(self, level):
        """设置人像缩放级别，clamp 到有效范围"""
        self.zoom_level = max(self.ZOOM_MIN, min(self.ZOOM_MAX, float(level)))

    # ────── 缩略图（供 Web 端使用）───────────────────────────
    def generate_thumbnail(self, filename, max_width=200, cache=None):
        """生成背景文件缩略图的 JPEG bytes"""
        if cache is None:
            cache = {}
        if filename in cache:
            return cache[filename]

        path = os.path.join(self.bg_folder, filename)
        thumb = None

        img = imread_utf8(path)
        if img is not None:
            thumb = img
        else:
            cap_video = videocap_from_path(path)
            if cap_video.isOpened():
                ret, frame = cap_video.read()
                if ret:
                    thumb = frame
                cap_video.release()

        if thumb is None:
            return None

        h, w = thumb.shape[:2]
        new_h = int(h * max_width / w)
        thumb = cv2.resize(thumb, (max_width, new_h))
        _, buf = cv2.imencode('.jpg', thumb, [cv2.IMWRITE_JPEG_QUALITY, 70])
        cache[filename] = buf.tobytes()
        return cache[filename]

    # ────── 信息打印 ────────────────────────────────────────
    def print_info(self):
        print(f"CUDA 可用: {torch.cuda.is_available()}")
        print(f"摄像头: {'OK' if self.cap.isOpened() else 'FAIL'}")
        ret, test = self.cap.read()
        if ret:
            print(f"摄像头分辨率: {test.shape[1]}x{test.shape[0]}")
        else:
            print("警告: 摄像头读取测试失败")