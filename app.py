import streamlit as st
import cv2
import torch
import numpy as np
import os
import time
import sys
from core_logic import *  # --- 1. 基础配置与模型加载 ---

sys.path.append('./RobustVideoMatting')
from RobustVideoMatting.model import MattingNetwork

st.set_page_config(layout="wide", page_title="RVM Professional Workstation")


@st.cache_resource
def get_model():
    weight_path = 'RobustVideoMatting/weights/rvm_mobilenetv3.pth'
    model = MattingNetwork(variant='mobilenetv3').eval().cuda().half()
    model.load_state_dict(torch.load(weight_path))
    return model


# --- 2. UI 侧边栏 (修正布局) ---
st.sidebar.title("🛠️ 控制面板")
run_toggle = st.sidebar.toggle("启动系统", True)
show_alpha = st.sidebar.checkbox("显示 Alpha 遮罩", True)

# A. 算法参数
with st.sidebar.expander("算法参数", expanded=True):
    ds_ratio = st.slider("推理分辨率 (DS)", 0.1, 1.0, 0.4)
    sharpen_val = st.slider("边缘锐化强度", 1.0, 2.5, 1.8)

# B. 背景选择 (修复下拉框位置)
with st.sidebar.expander("背景选择", expanded=True):
    bg_folder = "background"
    if not os.path.exists(bg_folder): os.makedirs(bg_folder)
    bg_files = [f for f in os.listdir(bg_folder) if f.lower().endswith(('.jpg', '.png', '.mp4'))]
    # 核心修正：将 selectbox 放在 with 块内
    selected_bg = st.selectbox("选择背景文件", ["现实背景"] + bg_files)

# C. 高级增强 (包含背景虚化)
with st.sidebar.expander("高级增强", expanded=True):
    # 核心修正：将虚化移动到这里
    blur_val = st.slider("背景虚化强度", 0, 50, 0)
    use_match = st.checkbox("自动亮度对齐", True)
    use_temp = st.checkbox("自动色温匹配", True)

# D. 统计功能
st.sidebar.subheader("📊 边缘指标统计")
if st.sidebar.button("开始记录 100 帧数据 (R)"):
    st.session_state.start_record = True

# --- 3. 界面布局逻辑 ---
if show_alpha:
    col_mask, col_res = st.columns(2)
    mask_win = col_mask.empty()
    res_win = col_res.empty()
else:
    _, mid, _ = st.columns([1, 8, 1])
    res_win = mid.empty()
    mask_win = None

# --- 4. 核心运行循环 ---
# (此部分保持你之前的逻辑，确保流畅度)
if "start_record" not in st.session_state:
    st.session_state.start_record = False

model = get_model()
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

rec = [None] * 4
last_alpha = None
record_buffer = {"temporal_var": [], "laplacian_var": []}
record_counter = 0
bg_cap = None
last_bg_path = ""

while run_toggle and cap.isOpened():
    ret, frame = cap.read()
    if not ret: break

    start_t = time.perf_counter()

    # 模型推理
    img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    img_tensor = torch.from_numpy(img_rgb).permute(2, 0, 1).unsqueeze(0).cuda().half() / 255.0
    with torch.no_grad():
        fgr, pha, *rec = model(img_tensor, *rec, downsample_ratio=ds_ratio)

    alpha = alpha_sharpen(pha.squeeze(0).permute(1, 2, 0).cpu().numpy(), sharpen_val)

    # 计算指标
    t_var = np.mean((alpha - last_alpha) ** 2) * 1000 if last_alpha is not None else 0.0
    last_alpha = alpha.copy()
    lap_var = cv2.Laplacian((alpha * 255).astype(np.uint8), cv2.CV_64F).var()

    # 统计逻辑
    if st.session_state.start_record:
        record_buffer["temporal_var"].append(t_var)
        record_buffer["laplacian_var"].append(lap_var)
        record_counter += 1
        if record_counter >= 100:
            t_m, t_s = np.mean(record_buffer["temporal_var"]), np.std(record_buffer["temporal_var"])
            l_m, l_s = np.mean(record_buffer["laplacian_var"]), np.std(record_buffer["laplacian_var"])
            st.sidebar.info(f"📊 统计结果:\nT-Var: {t_m:.3f}±{t_s:.3f}\nLap-Var: {l_m:.1f}±{l_s:.1f}")
            st.session_state.start_record = False
            record_counter = 0
            record_buffer = {"temporal_var": [], "laplacian_var": []}

    # 背景合成
    h, w = frame.shape[:2]
    if selected_bg == "现实背景":
        bg_frame = frame.copy()
    else:
        bg_path = os.path.join(bg_folder, selected_bg)
        if bg_path.lower().endswith(('.mp4', '.avi', '.mov')):
            if bg_path != last_bg_path:
                if bg_cap: bg_cap.release()
                bg_cap = cv2.VideoCapture(bg_path)
                last_bg_path = bg_path
            res, bg_frame = bg_cap.read()
            if not res:
                bg_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                _, bg_frame = bg_cap.read()
        else:
            bg_frame = cv2.imread(bg_path)
        bg_frame = cv2.resize(bg_frame, (w, h)) if bg_frame is not None else np.zeros_like(frame)

    if blur_val > 0:
        k = blur_val * 2 + 1
        bg_frame = cv2.GaussianBlur(bg_frame, (k, k), 0)

    # 合成
    fg_adj = frame.copy()
    if use_match: fg_adj = brightness_match(fg_adj, bg_frame)
    if use_temp: fg_adj = local_color_temp_match(fg_adj, bg_frame, alpha)
    view = (fg_adj * alpha + bg_frame * (1 - alpha)).astype(np.uint8)

    # 更新 UI
    try:
        fps = 1.0 / (time.perf_counter() - start_t)
        view_rgb = cv2.cvtColor(view, cv2.COLOR_BGR2RGB)
        metrics = f"FPS: {fps:.1f} | T-Var: {t_var:.3f} | Lap: {lap_var:.1f}"
        if show_alpha and mask_win:
            mask_win.image(alpha, caption="Alpha Mask", width='stretch')
        res_win.image(view_rgb, caption=metrics, width='stretch')
    except:
        pass

    time.sleep(0.005)

cap.release()
if bg_cap: bg_cap.release()