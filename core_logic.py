import torch
import cv2
import numpy as np


# --- 你的原始算法模块 ---

def brightness_match(fg, bg):
    fg_gray = cv2.cvtColor(fg, cv2.COLOR_BGR2GRAY)
    bg_gray = cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY)
    fg_mean = np.mean(fg_gray)
    bg_mean = np.mean(bg_gray)
    ratio = np.clip(bg_mean / (fg_mean + 1e-6), 0.6, 1.4)
    return np.clip(fg * ratio, 0, 255).astype(np.uint8)


def white_balance(img):
    result = img.copy().astype(np.float32)
    avg_gray = np.mean(result)
    for i in range(3):
        channel_mean = np.mean(result[:, :, i])
        ratio = np.clip(avg_gray / (channel_mean + 1e-6), 0.7, 1.3)
        result[:, :, i] *= ratio
    return np.clip(result, 0, 255).astype(np.uint8)


def local_color_temp_match(fg, bg, alpha):
    mask = (alpha.squeeze() > 0.5)
    if not np.any(mask): return fg

    def get_temp(image):
        img_f = image.astype(np.float32)
        r, b = np.mean(img_f[..., 2]), np.mean(img_f[..., 0])
        return (r - b) / (r + b + 1e-6)

    bg_temp = get_temp(bg)
    fg_temp = get_temp(fg[mask])

    img_float = fg.astype(np.float32)
    diff = (bg_temp - fg_temp) * 0.5
    img_float[..., 2] *= (1 + diff)
    img_float[..., 0] *= (1 - diff)

    result = fg.copy()
    res_adj = np.clip(img_float, 0, 255).astype(np.uint8)
    result[mask] = res_adj[mask]
    return result


def alpha_sharpen(alpha, strength=1.8):
    alpha = alpha.astype(np.float32)
    # 暴力拉伸
    alpha = np.clip((alpha - 0.15) * 1.5, 0.0, 1.0)
    # 锐化
    blurred = cv2.GaussianBlur(alpha, (3, 3), 0)
    alpha = cv2.addWeighted(alpha, strength, blurred, 1.0 - strength, 0)
    alpha = np.clip(alpha, 0.0, 1.0)
    # 绝对截断
    alpha[alpha < 0.02] = 0.0
    alpha[alpha > 0.98] = 1.0
    return np.expand_dims(alpha, axis=-1)