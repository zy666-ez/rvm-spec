import cv2
import numpy as np
import time
import os
import threading
from engine import RVMPipeline

# ── 初始化共享引擎 ──────────────────────────────────────────
pipeline = RVMPipeline(camera_id=0)

# ── 桌面端特有状态 ──────────────────────────────────────────
is_running = True
current_mode = 'real'
blur_enabled = False
current_bg_index = 0

bg_file_list = []   # 完整路径列表（含 bg_folder 前缀）


# ── 背景列表扫描（桌面端使用完整路径）─────────────────────────
def scan_background_folder():
    global bg_file_list
    folder = pipeline.bg_folder
    if not os.path.exists(folder):
        os.makedirs(folder)
        print(f"已创建 {folder} 文件夹，请放入背景图片或视频")
        return
    valid_exts = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff',
                  '.mp4', '.avi', '.mov', '.mkv', '.flv')
    files = [f for f in os.listdir(folder) if f.lower().endswith(valid_exts)]
    files.sort()
    bg_file_list = [os.path.join(folder, f) for f in files]
    if bg_file_list:
        print(f"已扫描到 {len(bg_file_list)} 个背景文件 (按 w/s 键切换)")
    else:
        print(f"{folder} 文件夹为空，请放入背景图片或视频")


# ── 终端输入线程（支持拖入路径）─────────────────────────────
def input_thread():
    global is_running, current_mode
    print("\n===== 操作说明 =====")
    print("【键盘按键】")
    print("  w / s  : 切换 background 文件夹中的图片/视频")
    print("  v      : 切换当前背景 虚化/不虚化")
    print("  n      : 回到现实背景")
    print("  r      : 触发记录接下来100帧的【时序边缘方差】和【拉普拉斯方差】")
    print("  q      : 退出程序")
    print("====================================\n")
    while is_running:
        try:
            path = input()
            if path.strip().lower() == 'q':
                is_running = False
                break
            if path.strip():
                if not os.path.isabs(path) and not os.path.exists(path):
                    try_path = os.path.join(pipeline.bg_folder, path)
                    if os.path.exists(try_path):
                        path = try_path
                ok, msg = pipeline.load_background(os.path.basename(path))
                if ok:
                    current_mode = 'virtual'
                    print(f"背景: {os.path.basename(path)}")
                else:
                    print(msg)
        except Exception:
            continue


# ── 启动 ────────────────────────────────────────────────────
scan_background_folder()
thread = threading.Thread(target=input_thread, daemon=True)
thread.start()

pipeline.print_info()
print("--- 摄像头实时监控已启动 (当前：现实背景) ---")

# ── 主循环 ──────────────────────────────────────────────────
while pipeline.cap.isOpened() and is_running:
    ret, frame = pipeline.read_frame()
    if not ret:
        break
    start_time = time.perf_counter()

    # 推理 → engine
    alpha, fgr, pha = pipeline.infer(frame)

    # 指标 → engine
    _, _ = pipeline.compute_metrics(alpha)

    # 合成 → engine
    view = pipeline.composite(frame, alpha, mode=current_mode, blur=blur_enabled)

    # FPS
    end_time = time.perf_counter()
    latency = (end_time - start_time) * 1000
    fps = 1.0 / (end_time - start_time)

    # UI 叠加
    cv2.putText(view, f"Latency: {latency:.1f}ms  FPS: {fps:.1f}", (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

    if pipeline.metrics_recording:
        cv2.putText(view, f"Recording: {pipeline.metrics_count}/{pipeline.metrics_max}",
                    (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        cv2.putText(view, f"Temp Var (Jump): {pipeline.smooth_temp_var:.5f}",
                    (20, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        cv2.putText(view, f"Lap Var (Sharp): {pipeline.smooth_lap_var:.5f}",
                    (20, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

    cv2.imshow('RVM-Spec Live Preview', view)

    # 检查指标完成
    if pipeline.metrics_result is not None:
        r = pipeline.metrics_result
        print(f"\n[指标统计完成] 过去 {r['frames']} 帧边缘数据:")
        print(f"  时序边缘方差 (乱跳度): {r['mean_temp']} ± {r['std_temp']}")
        print(f"  拉普拉斯方差 (锋利度): {r['mean_lap']} ± {r['std_lap']}\n")
        pipeline.metrics_result = None

    # 键盘交互
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        is_running = False
        break
    if key == ord('r'):
        pipeline.start_recording()
        print(f"开始记录边缘指标（{pipeline.metrics_max}帧）...")
    if key == ord('v'):
        blur_enabled = not blur_enabled
        print(f"背景虚化：{'开启' if blur_enabled else '关闭'}")
    if key == ord('n'):
        current_mode = 'real'
        print("已切换到：现实背景")
    if key == ord('w'):
        if bg_file_list:
            current_bg_index = (current_bg_index + 1) % len(bg_file_list)
            ok, msg = pipeline.load_background(os.path.basename(bg_file_list[current_bg_index]))
            if ok:
                current_mode = 'virtual'
                print(f"背景: {os.path.basename(bg_file_list[current_bg_index])}")
            else:
                print(msg)
    if key == ord('s'):
        if bg_file_list:
            current_bg_index = (current_bg_index - 1) % len(bg_file_list)
            ok, msg = pipeline.load_background(os.path.basename(bg_file_list[current_bg_index]))
            if ok:
                current_mode = 'virtual'
                print(f"背景: {os.path.basename(bg_file_list[current_bg_index])}")
            else:
                print(msg)

# ── 退出 ────────────────────────────────────────────────────
is_running = False
pipeline.release()
cv2.destroyAllWindows()
cv2.waitKey(1)
print("\n程序已退出")
os._exit(0)