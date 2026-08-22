import time
import os
import threading
import cv2
from flask import Flask, Response, request, jsonify, render_template
from engine import RVMPipeline

# ── Flask app ───────────────────────────────────────────────
app = Flask(__name__)

# ── 共享引擎（原来重复的模型/摄像头/背景/指标逻辑全部在这里）──
pipeline = RVMPipeline(camera_id=0)

# ── 线程安全的状态（仅 Web 特有部分）─────────────────────────
state_lock = threading.RLock()

state = {
    'current_mode': 'real',        # 'real' | 'virtual'
    'blur_enabled': False,
    'current_bg_name': None,
    'bg_file_list': [],
    'metrics_result': None,
}

THUMB_CACHE = {}  # filename -> thumbnail bytes (JPEG)

# ── MJPEG streaming generator（核心逻辑改为调用 engine）─────
def generate_frames():
    frame_count = 0
    print("[stream] MJPEG 流已连接，开始推帧...")

    while True:
        try:
            with state_lock:
                if not pipeline.cap.isOpened():
                    print("[stream] 摄像头已关闭，停止推流")
                    break

            ret, frame = pipeline.read_frame()
            if not ret:
                time.sleep(0.01)
                continue

            # 推理 + alpha 后处理 → 全部在 engine 里
            alpha, fgr, pha = pipeline.infer(frame)

            # 指标计算 → engine
            _, _ = pipeline.compute_metrics(alpha)

            # 读取 Web 状态
            with state_lock:
                cur_mode = state['current_mode']
                cur_blur = state['blur_enabled']
                cur_rec  = pipeline.metrics_recording
                cur_cnt  = pipeline.metrics_count
                cur_max  = pipeline.metrics_max
                cur_smooth_temp = pipeline.smooth_temp_var
                cur_smooth_lap  = pipeline.smooth_lap_var
                # 同步 metrics_result
                if pipeline.metrics_result is not None:
                    state['metrics_result'] = pipeline.metrics_result

            # 合成 → engine
            view = pipeline.composite(frame, alpha, mode=cur_mode, blur=cur_blur)

            # FPS
            now = time.perf_counter()
            latency = (now - getattr(generate_frames, 'last_time', now)) * 1000
            generate_frames.last_time = now
            fps = 1000.0 / latency if latency > 0 else 0

            # UI overlay
            cv2.putText(view, f"FPS: {fps:.1f}", (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            mode_label = "Virtual" if cur_mode == 'virtual' else "Real"
            cv2.putText(view, f"Mode: {mode_label}  Blur: {'ON' if cur_blur else 'OFF'}", (20, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

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

# ── Routes ──────────────────────────────────────────────────
@app.route('/')
def index():
    with state_lock:
        bg_list = list(state['bg_file_list'])
    return render_template('index.html', backgrounds=bg_list)

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame',
                    headers={'Cache-Control': 'no-cache, no-store, must-revalidate',
                             'Pragma': 'no-cache',
                             'Expires': '0'})

@app.route('/api/state')
def api_state():
    with state_lock:
        return jsonify({
            'current_mode': state['current_mode'],
            'blur_enabled': state['blur_enabled'],
            'current_bg_name': state['current_bg_name'],
            'is_recording': pipeline.metrics_recording,
            'record_count': pipeline.metrics_count,
            'record_max': pipeline.metrics_max,
            'bg_list': state['bg_file_list'],
            'metrics_result': state['metrics_result'],
            'zoom_level': pipeline.zoom_level,
        })

@app.route('/api/mode', methods=['POST'])
def api_set_mode():
    data = request.get_json()
    mode = data.get('mode', 'real')
    with state_lock:
        if mode in ('real', 'virtual'):
            state['current_mode'] = mode
    return jsonify({'ok': True, 'mode': state['current_mode']})

@app.route('/api/blur', methods=['POST'])
def api_toggle_blur():
    data = request.get_json()
    enable = data.get('enable', None)
    with state_lock:
        if enable is not None:
            state['blur_enabled'] = bool(enable)
        else:
            state['blur_enabled'] = not state['blur_enabled']
    return jsonify({'ok': True, 'blur_enabled': state['blur_enabled']})

@app.route('/api/zoom', methods=['POST'])
def api_set_zoom():
    data = request.get_json()
    level = data.get('level', 1.0)
    pipeline.set_zoom(level)
    return jsonify({'ok': True, 'zoom_level': pipeline.zoom_level})

@app.route('/api/background/<filename>', methods=['POST'])
def api_set_background(filename):
    ok, msg = pipeline.load_background(filename)
    with state_lock:
        if ok:
            state['current_bg_name'] = filename
            state['current_mode'] = 'virtual'
    return jsonify({'ok': ok, 'message': msg})

@app.route('/api/backgrounds')
def api_list_backgrounds():
    files = pipeline.scan_backgrounds()
    with state_lock:
        state['bg_file_list'] = files
    return jsonify(files)

@app.route('/api/thumb/<filename>')
def api_thumbnail(filename):
    data = pipeline.generate_thumbnail(filename, cache=THUMB_CACHE)
    if data is None:
        return '', 404
    return Response(data, mimetype='image/jpeg')

@app.route('/api/health')
def api_health():
    ret, frame = pipeline.read_frame()
    if not ret:
        return jsonify({'error': '摄像头读取失败'}), 500

    alpha, fgr, pha = pipeline.infer(frame)
    view = pipeline.composite(frame, alpha, mode='real')
    cv2.putText(view, "HEALTH CHECK OK", (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

    _, jpeg = cv2.imencode('.jpg', view)
    return Response(jpeg.tobytes(), mimetype='image/jpeg')

@app.route('/api/record', methods=['POST'])
def api_start_record():
    pipeline.start_recording()
    return jsonify({'ok': True})

@app.route('/api/stop', methods=['POST'])
def api_stop():
    """Graceful shutdown."""
    with state_lock:
        state['metrics_result'] = None
    pipeline.release()
    cv2.destroyAllWindows()
    os._exit(0)

# ── Startup ─────────────────────────────────────────────────
def init():
    pipeline.print_info()
    files = pipeline.scan_backgrounds()
    with state_lock:
        state['bg_file_list'] = files
    if files:
        pipeline.load_background(files[0])
    print(f"已扫描 {len(files)} 个背景文件")
    print(f"访问 http://localhost:5000 打开前端界面")

if __name__ == '__main__':
    init()
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
