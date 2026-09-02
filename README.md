# RVM-Spec · 实时人像抠图与智能背景融合系统

> Real-time human video matting with edge-sharpening, lighting-agnostic color fusion, and a no-reference quality evaluation suite — built on top of RobustVideoMatting (RVM).

基于 **RobustVideoMatting (RVM)** 的实时人像抠图与背景替换系统。本项目在 RVM 基础模型之上，自研了**双无参考评测体系、Alpha 边缘优化、LAB 色彩光照融合、后台采样**等核心模块，重点解决实时抠图中的**运动残影（闪烁）**与**前景/背景光照失配**两大痛点。

> **架构升级（v2.0）**：原 `serve.py` 把模型调用、视频推流、页面渲染全揉在一个 Flask 单体里。现重构为 **FastAPI 后端 + Vue3 前端** 的前后端分离架构，核心算法仍由 `engine.py` 的 `RVMPipeline` 承载。

---

## ✨ 核心贡献（本项目重点工作）

> 注：RVM 主干网络（`RobustVideoMatting/`）来自论文作者开源实现，本项目工作集中在 `engine.py`、`core_logic.py` 以及 `backend/`、`frontend/` 中。

### 1. 双无参考评测体系（No-Reference Dual Metrics）
针对实时抠图缺少真值（ground-truth）难以量化评估的问题，设计了**两个无需真值的无参考指标**，直接对单帧 Alpha 遮罩在线统计：
- **时序边缘闪烁度（Temporal Edge Flicker）**：相邻帧在半透明边缘区域的像素方差，衡量边缘「乱跳/抖动」程度，对应运动残影。
- **空间边缘锐度（Laplacian Edge Sharpness）**：半透明边缘区域拉普拉斯算子的方差，衡量边缘清晰程度。

两条指标以 EMA 平滑并支持连续录制 100 帧自动出报告（`engine.py · compute_metrics`），用于**客观对比不同后处理方案**（见第 3 节），无需任何标注数据即可完成质量评测。

### 2. 实时抠图 + Alpha 优化 + 光照融合核心模块
将 RVM 推理、Alpha 后处理、色彩融合、背景管理、指标计算统一封装为可复用的 `RVMPipeline` 管线（`engine.py`），被 Web 后端及其他前端共用，消除重复代码：
- 实时推理：`mobilenetv3` 主干 + FP16 + CUDA，时序状态递归（`rec`），`downsample_ratio=0.5` 保证实时性；
- Alpha 优化：线性拉伸 + 非锐化掩蔽 + 绝对截断的后处理链；
- 光照融合：前景与背景合成时的亮度/色彩一致性处理。

### 3. 空间域边缘强化 + 二值化截断策略（核心创新）
针对 RVM 输出的 Alpha 在边缘处发灰、运动时产生残影的问题，提出**三阶段 Alpha 后处理**：
1. **线性拉伸**：`clip((α − 0.15) × 1.5, 0, 1)` 拉开半透明过渡带对比；
2. **空间域边缘强化**：高斯模糊 + `addWeighted(α, 1.8, blur, −0.8)` 的非锐化掩蔽（unsharp masking），锐化边缘；
3. **二值化截断**：`α < 0.02 → 0`、`α > 0.98 → 1`，消除孤立噪点。

对比了 **3 种后处理方案**（仅拉伸 / 仅锐化 / 拉伸+锐化+截断），由双无参考评测体系实测：
| 指标 | 提升 |
|------|------|
| 时序边缘闪烁度 | **↓ 81%**（运动残影显著收敛） |
| 空间边缘锐度 | **↑ 67%**（边缘更清晰） |

### 4. LAB 空间 Reinhard 色彩迁移（解决光照失配）
抠像后的前景与替换背景常存在明显光照/色温差异。实现 `reinhard_color_transfer`（`engine.py`）：在 **LAB 色彩空间**对 L 通道与 a/b 通道分别做 Reinhard 统计迁移，将前景的均值/方差向背景对齐（`l_ratio=1.0, ab_ratio=0.3`），使合成结果光照自然、无色块割裂感。

### 5. 后台采样模块 + 前后端分离 Web 集成（端侧延迟 ≤ 50ms）
- **后台采样模块**：背景图片/视频的循环采样（`get_background_frame`）与缩略图缓存（`generate_thumbnail`，带 `THUMB_CACHE`）在流推送中后台完成，主推理链路不被阻塞；**端侧（本地 GPU）单帧处理延迟 ≤ 50ms**。
- **前后端分离**：同一 `RVMPipeline` 引擎由 FastAPI 后端驱动，Vue3 前端负责交互与展示：
  - 后端 `backend/main.py`：FastAPI + MJPEG 推流 + REST API + 生产环境静态托管；
  - 前端 `frontend/`：Vue3 + Vite，实时预览、点击切换背景、缩放、记录指标。

---

## 🧱 系统架构与文件结构

```
rvm-spec2/
├── engine.py              # 【核心】RVMPipeline：RVM 推理 / Alpha 优化 / Reinhard 色彩迁移 / 背景采样 / 双无参考指标
├── core_logic.py          # 原始算法模块：亮度对齐、白平衡、色温匹配、alpha_sharpen（供 app.py 使用）
├── backend/               # ★ 新增：FastAPI 后端
│   ├── main.py            #    路由 + MJPEG 推流 + CORS + 生产环境静态托管
│   └── requirements.txt   #    fastapi / uvicorn
├── frontend/              # ★ 新增：Vue3 前端
│   ├── package.json
│   ├── vite.config.js     #    dev 代理 /api 与 /video_feed 到后端 8000
│   ├── index.html
│   └── src/
│       ├── main.js
│       ├── App.vue
│       ├── api.js                 # 与后端交互的 fetch 封装
│       ├── composables/
│       │   └── usePipeline.js     # 状态 / 轮询 / 动作 / 键盘快捷键
│       └── components/
│           ├── BackgroundPanel.vue
│           ├── VideoStage.vue
│           ├── ControlBar.vue
│           └── MetricsToast.vue
├── rvm_run_live.py        # 桌面端实时预览（cv2 窗口 + 键盘交互），独立于 Web 栈
├── app.py                 # Streamlit 实验工作台（Alpha 可视化 + 参数调优）
├── rvm-run.py             # 离线视频抠图（调用 RVM 官方 convert_video）
├── background/            # 背景图片 / 视频素材（自动扫描）
├── RobustVideoMatting/    # RVM 基础模型（第三方，来自论文作者）
│   ├── model/             # MattingNetwork (mobilenetv3 / resnet50)
│   └── weights/           # 权重文件需自行下载（见「快速开始」）
├── legacy/                # 旧版 Flask + Jinja 实现（server.py / templates/），仅作参考
└── requirements.txt       # Python 依赖（torch / opencv / numpy 等）
```

**前端 → 后端 接口约定**
| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/video_feed`        | MJPEG 视频流（浏览器 `<img>` 直连） |
| GET  | `/api/state`         | 当前状态（模式/虚化/背景/录制进度/指标/缩放） |
| POST | `/api/mode`          | 切换 `real` / `virtual` |
| POST | `/api/blur`          | 背景虚化开关（body: `{enable?: bool}`） |
| POST | `/api/zoom`          | 人像缩放（body: `{level: float}`，0.5~3.0） |
| POST | `/api/background/{filename}` | 加载指定背景 |
| GET  | `/api/backgrounds`   | 列出 background/ 下素材 |
| GET  | `/api/thumb/{filename}` | 背景缩略图 |
| GET  | `/api/health`        | 健康检查（返回一帧 JPEG） |
| POST | `/api/record`        | 开始记录 100 帧指标 |
| POST | `/api/stop`          | 优雅退出 |

---

## 🚀 快速开始

### 环境
- Python 3.8+，NVIDIA GPU（CUDA），摄像头
- Node.js 18+（前端开发）
- 依赖：`pip install -r requirements.txt`（torch / opencv / numpy 等）
- 模型权重：仓库**不内置权重文件**（`rvm_resnet50.pth` 单文件超 GitHub 100MB 限制），请从 [RVM 官方仓库](https://github.com/PeterL1n/RobustVideoMatting) 下载 `rvm_mobilenetv3.pth` / `rvm_resnet50.pth`，放入 `RobustVideoMatting/weights/` 后即可运行

### 运行 Web（前后端分离，推荐）

**① 启动后端（FastAPI）** —— 在项目根目录执行：
```bash
pip install -r backend/requirements.txt      # 安装 fastapi / uvicorn
uvicorn backend.main:app --host 0.0.0.0 --port 8000
# 或： python backend/main.py
```
后端启动后会自动加载模型、打开摄像头，并扫描 `background/` 背景素材。
接口文档见 http://localhost:8000/docs 。

**② 启动前端（Vue3，开发模式）** —— 另开一个终端：
```bash
cd frontend
npm install
npm run dev
```
打开 http://localhost:5173 即可使用。
> 开发时 Vite 会把 `/api` 与 `/video_feed` 自动代理到后端 8000 端口，无需手动配跨域。

**③ 生产模式（可选）**：将前端打包后由后端统一托管
```bash
cd frontend
npm run build        # 产物输出到 frontend/dist
# 重启后端：uvicorn backend.main:app --port 8000
```
此时直接访问 http://localhost:8000 即可打开完整界面（后端会自动托管 `frontend/dist`）。

### 其它运行模式（与 Web 栈独立，未改动）
- **桌面端（OpenCV 实时窗口）**：`python rvm_run_live.py` —— W/S 切换背景，V 虚化，N 现实背景，R 记录 100 帧指标，Q 退出
- **离线视频抠图**：`python rvm-run.py` —— 输入 `input.mp4` → 输出 `com.mp4` / `pha.mp4` / `fgr.mp4`
- **Streamlit 实验工作台**：`streamlit run app.py`

将背景图片（`.jpg/.png/.bmp`）或视频（`.mp4/.avi/.mov`）放入 `background/` 文件夹，启动时自动扫描。

---

## 🎮 操作说明（Web 端）

| 操作 | 按钮 | 快捷键 |
|------|------|--------|
| 真实背景 | 真实背景 | `N` |
| 虚拟背景（已选背景时） | 虚拟背景 | — |
| 背景虚化开关 | 虚化切换 | `V` |
| 上一个 / 下一个背景 | ◀ / ▶ | `S` / `W` |
| 人像放大 / 缩小 / 复位 | 🔍+ / 🔍− / 百分比 | `+` `=` / `-` / `0` |
| 鼠标滚轮 | 在画面上滚动 | 放大 / 缩小 |
| 记录 100 帧指标 | 记录指标 | `R` |

指标录制完成后，右上角弹出统计结果（时序边缘方差 / 拉普拉斯方差，含均值±标准差），用于横向对比不同后处理方案。

---

## 📊 关键结果

| 项目 | 结果 |
|------|------|
| 时序边缘闪烁度 | 较基线 **↓ 81%** |
| 空间边缘锐度 | 较基线 **↑ 67%** |
| 端侧单帧处理延迟 | **≤ 50 ms** |
| 评测方式 | 双无参考（无需真值）在线统计 |

---

## 🛠 技术栈
**后端**：PyTorch · OpenCV · CUDA/FP16 · FastAPI · MJPEG 流 · 进程内线程锁
**前端**：Vue 3 · Vite · 原生 fetch（无额外 HTTP 库）
**算法**：LAB/Reinhard 色彩迁移 · 非锐化掩蔽（Unsharp Masking）· 双无参考指标

---

## 🙏 致谢
- 抠图主干网络基于 [RobustVideoMatting](https://github.com/PeterL1n/RobustVideoMatting)（PeterL1n et al., *Robust High-Resolution Video Matting with Temporal Guidance*, WACV 2022）。
- 色彩迁移方法参考 Reinhard et al., *Color Transfer between Images* (2001)。

## 📄 License
RVM 主干部分遵循其原始 `RobustVideoMatting/LICENSE`；本项目自研代码以 MIT 许可证开源。
