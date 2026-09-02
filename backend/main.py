"""
RVM-Spec 后端（FastAPI 版）
─────────────────────────────
职责：承载模型推理、MJPEG 推流、REST 控制接口。
真正的算法逻辑全部来自 engine.RVMPipeline，本文件只负责「接收请求 → 调用管线 → 返回结果」。

前端约定（见 frontend/）：
  - 视频流：  GET  /video_feed            （multipart/x-mixed-replace，浏览器 <img> 直连）
  - 状态轮询：GET  /api/state
  - 控制接口：POST /api/mode | /api/blur | /api/zoom | /api/background/{filename}
             GET  /api/backgrounds | /api/thumb/{filename} | /api/health
             POST /api/record | /api/stop
生产环境下，若 frontend/dist 存在，FastAPI 会直接托管打包后的前端静态资源。
"""

import os
import sys
import threading
import time

import cv2

# ── 让项目根目录（engine.py 与 RobustVideoMatting 所在处）可被 import ──
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from engine import RVMPipeline

# ── FastAPI app ───────────────────────────────────────────
app = FastAPI(title="RVM-Spec Backend", version="2.0.0")

# 开发环境：Vue 走 Vite 开发服务器（不同端口），需要 CORS。
# 生产环境（前端打包并由本服务托管）同源，无影响。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 共享引擎与状态 ───────────────────────────────────────
# RVMPipeline 在 import 阶段即加载模型并打开摄像头，请确保环境就绪。
pipeline = RVMPipeline(camera_id=0)

# 粗粒度锁：序列化对 pipeline / state 的并发访问（推流线程 + 控制接口线程）
lock = threading.RLock()

state = {
    'current_mode': 'real',        # 'real' | 'virtual'
    'blur_enabled': False,
    'current_bg_name': None,
    'bg_file_list': [],
}

THUMB_CACHE = {}  # filename -> thumbnail bytes (JPEG)


# ── 请求体模型 ───────────────────────────────────────────
class ModeReq(BaseModel):
    mode: str = 'real'

class BlurReq(BaseModel):
    enable: bool | None = None

class ZoomReq(BaseModel):
    level: float = 1.0


# ── MJPEG 推流 ───────────────────────────────────────────
def generate_frames():
    """逐帧：读摄像头 → 推理 → 指标 → 合成 → 叠加 HUD → 编码 JPEG。"""
    print("[stream] MJPEG 流已连接，开始推帧...")
    last_time = time.perf_counter()
    frame_count = 0

    while True:
        try:
            if not pipeline.cap.isOpened():
                print("[stream] 摄像头已关闭，停止推流")
                break

            with lock:
                ret, frame = pipeline.read_frame()
                if not ret:
                    time.sleep(0.01)
                    continue

                # 推理 + alpha 后处理
                alpha, fgr, pha = pipeline.infer(frame)
                # 指标计算（含录制逻辑）
                pipeline.compute_metrics(alpha)

                # 读取当前 Web 状态
                cur_mode = state['current_mode']
                cur_blur = state['blur_enabled']
                cur_rec = pipeline.metrics_recording
                cur_cnt = pipeline.metrics_count
                cur_max = pipeline.metrics_max
                cur_smooth_temp = pipeline.smooth_temp_var
                cur_smooth_lap = pipeline.smooth_lap_var
                if pipeline.metrics_result is not None:
                    state['metrics_result'] = pipeline.metrics_result

                # 合成画面
                view = pipeline.composite(frame, alpha, mode=cur_mode, blur=cur_blur)

            # ── HUD 叠加（在锁外，纯 CPU 绘制，不阻塞管线）──
            now = time.perf_counter()
            latency = (now - last_time) * 1000
            last_time = now
            fps = 1000.0 / latency if latency > 0 else 0

            cv2.putText(view, f"FPS: {fps:.1f}", (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            mode_label = "Virtual" if cur_mode == 'virtual' else "Real"
            cv2.putText(view, f"Mode: {mode_label}  Blur: {'ON' if cur_blur else 'OFF'}",
                        (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            if cur_rec:
                cv2.putText(view, f"Recording: {cur_cnt}/{cur_max}", (20, 130),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
                cv2.putText(view, f"Temp Var: {cur_smooth_temp:.5f}", (20, 170),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
                cv2.putText(view, f"Lap  Var: {cur_smooth_lap:.5f}", (20, 210),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

            _, jpeg = cv2.imencode('.jpg', view, [cv2.IMWRITE_JPEG_QUALITY, 95])
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')

            frame_count += 1
            if frame_count == 1:
                print(f"[stream] 第一帧已推送，尺寸={view.shape[1]}x{view.shape[0]}")

        except Exception as e:
            import traceback
            print(f"[stream] 推帧异常: {e}")
            traceback.print_exc()
            time.sleep(0.1)


@app.get("/video_feed")
def video_feed():
    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0',
        },
    )


# ── REST 接口 ────────────────────────────────────────────
@app.get("/api/state")
def api_state():
    with lock:
        return {
            'current_mode': state['current_mode'],
            'blur_enabled': state['blur_enabled'],
            'current_bg_name': state['current_bg_name'],
            'is_recording': pipeline.metrics_recording,
            'record_count': pipeline.metrics_count,
            'record_max': pipeline.metrics_max,
            'bg_list': state['bg_file_list'],
            'metrics_result': state.get('metrics_result'),
            'zoom_level': pipeline.zoom_level,
        }


@app.post("/api/mode")
def api_set_mode(req: ModeReq):
    with lock:
        if req.mode in ('real', 'virtual'):
            state['current_mode'] = req.mode
    return {'ok': True, 'mode': state['current_mode']}


@app.post("/api/blur")
def api_toggle_blur(req: BlurReq):
    with lock:
        if req.enable is not None:
            state['blur_enabled'] = bool(req.enable)
        else:
            state['blur_enabled'] = not state['blur_enabled']
    return {'ok': True, 'blur_enabled': state['blur_enabled']}


@app.post("/api/zoom")
def api_set_zoom(req: ZoomReq):
    with lock:
        pipeline.set_zoom(req.level)
        zl = pipeline.zoom_level
    return {'ok': True, 'zoom_level': zl}


@app.post("/api/background/{filename}")
def api_set_background(filename: str):
    with lock:
        ok, msg = pipeline.load_background(filename)
        if ok:
            state['current_bg_name'] = filename
            state['current_mode'] = 'virtual'
    return {'ok': ok, 'message': msg}


@app.get("/api/backgrounds")
def api_list_backgrounds():
    files = pipeline.scan_backgrounds()
    with lock:
        state['bg_file_list'] = files
    return files


@app.get("/api/thumb/{filename}")
def api_thumbnail(filename: str):
    with lock:
        data = pipeline.generate_thumbnail(filename, cache=THUMB_CACHE)
    if data is None:
        return Response(status_code=404)
    return Response(data, media_type='image/jpeg')


@app.get("/api/health")
def api_health():
    with lock:
        ret, frame = pipeline.read_frame()
        if not ret:
            return JSONResponse({'error': '摄像头读取失败'}, status_code=500)
        alpha, fgr, pha = pipeline.infer(frame)
        view = pipeline.composite(frame, alpha, mode='real')
    cv2.putText(view, "HEALTH CHECK OK", (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    _, jpeg = cv2.imencode('.jpg', view)
    return Response(jpeg.tobytes(), media_type='image/jpeg')


@app.post("/api/record")
def api_start_record():
    with lock:
        pipeline.start_recording()
    return {'ok': True}


@app.post("/api/stop")
def api_stop():
    """优雅退出（释放摄像头与窗口）。"""
    with lock:
        state['metrics_result'] = None
        pipeline.release()
    cv2.destroyAllWindows()
    os._exit(0)


# ── 生产环境：托管打包后的前端 ───────────────────────────
frontend_dist = os.path.join(PROJECT_ROOT, 'frontend', 'dist')
if os.path.isdir(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
else:
    @app.get("/")
    def root():
        return {
            "message": "RVM-Spec API 运行中",
            "docs": "/docs",
            "video_feed": "/video_feed",
            "note": "前端尚未构建；开发请启动 Vite（npm run dev），"
                    "或在本服务所在目录执行 npm run build 后重启。",
        }


# ── 启动初始化 ───────────────────────────────────────────
def init():
    pipeline.print_info()
    files = pipeline.scan_backgrounds()
    with lock:
        state['bg_file_list'] = files
    if files:
        pipeline.load_background(files[0])
    print(f"已扫描 {len(files)} 个背景文件")
    print("后端接口文档: http://localhost:8000/docs")


@app.on_event("startup")
def on_startup():
    init()


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
