# RVM-Spec · 实时人像抠图与智能背景融合系统

> Real-time human video matting with edge-sharpening, lighting-agnostic color fusion, and a no-reference quality evaluation suite — built on top of RobustVideoMatting (RVM).

基于 **RobustVideoMatting (RVM)** 的实时人像抠图与背景替换系统。本项目在 RVM 基础模型之上，自研了**双无参考评测体系、Alpha 边缘优化、LAB 色彩光照融合、后台采样与 Web 集成**等核心模块，重点解决实时抠图中的**运动残影（闪烁）**与**前景/背景光照失配**两大痛点。

---

## ✨ 核心贡献（本项目重点工作）

> 注：RVM 主干网络（`RobustVideoMatting/`）来自论文作者开源实现，本项目工作集中在 `engine.py`、`core_logic.py`、`server.py`、`rvm_run_live.py`、`app.py` 以及 `templates/` 中。

### 1. 双无参考评测体系（No-Reference Dual Metrics）
针对实时抠图缺少真值（ground-truth）难以量化评估的问题，设计了**两个无需真值的无参考指标**，直接对单帧 Alpha 遮罩在线统计：
- **时序边缘闪烁度（Temporal Edge Flicker）**：相邻帧在半透明边缘区域的像素方差，衡量边缘「乱跳/抖动」程度，对应运动残影。
- **空间边缘锐度（Laplacian Edge Sharpness）**：半透明边缘区域拉普拉斯算子的方差，衡量边缘清晰程度。

两条指标以 EMA 平滑并支持连续录制 100 帧自动出报告（`engine.py · compute_metrics`），用于**客观对比不同后处理方案**（见第 3 节），无需任何标注数据即可完成质量评测。

### 2. 实时抠图 + Alpha 优化 + 光照融合核心模块
将 RVM 推理、Alpha 后处理、色彩融合、背景管理、指标计算统一封装为可复用的 `RVMPipeline` 管线（`engine.py`），被桌面端、Web 端共用，消除重复代码：
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

有效解决了实时抠图中的**运动残影 / 边缘发虚**问题。

### 4. LAB 空间 Reinhard 色彩迁移（解决光照失配）
抠像后的前景与替换背景常存在明显光照/色温差异。实现 `reinhard_color_transfer`（`engine.py`）：在 **LAB 色彩空间**对 L 通道与 a/b 通道分别做 Reinhard 统计迁移，将前景的均值/方差向背景对齐（`l_ratio=1.0, ab_ratio=0.3`），使合成结果光照自然、无色块割裂感。

### 5. 后台采样模块 + Web 集成（端侧延迟 ≤ 50ms）
- **后台采样模块**：背景图片/视频的循环采样（`get_background_frame`）与缩略图缓存（`generate_thumbnail`，带 `THUMB_CACHE`）在流推送中后台完成，主推理链路不被阻塞；**端侧（本地 GPU）单帧处理延迟 ≤ 50ms**。
- **三端集成**：同一 `RVMPipeline` 引擎驱动三种前端——
  - Web 端：`Flask` + MJPEG 推流（`server.py` / `templates/index.html`），浏览器实时预览、点击切换背景、缩放、记录指标；
  - 桌面端：`cv2` 实时窗口（`rvm_run_live.py`），键盘交互；
  - 实验端：`Streamlit` 工作站（`app.py`），可视化 Alpha 与参数调优。

---

## 🧱 系统架构与文件结构

```
rvm-spec/
├── engine.py            # 【核心】RVMPipeline：RVM 推理 / Alpha 优化 / Reinhard 色彩迁移 / 背景采样 / 双无参考指标
├── core_logic.py        # 原始算法模块：亮度对齐、白平衡、色温匹配、alpha_sharpen
├── server.py            # Web 后端：Flask + MJPEG 推流 + REST API
├── templates/
│   └── index.html       # Web 前端：实时预览 / 背景切换 / 缩放 / 指标弹窗
├── rvm_run_live.py      # 桌面端实时预览（cv2 窗口 + 键盘交互）
├── app.py               # Streamlit 实验工作台（Alpha 可视化 + 参数调优）
├── rvm-run.py           # 离线视频抠图（调用 RVM 官方 convert_video）
├── background/          # 背景图片 / 视频素材（自动扫描）
├── RobustVideoMatting/  # RVM 基础模型（第三方，来自论文作者）
│   ├── model/           # MattingNetwork (mobilenetv3 / resnet50)
│   └── weights/         # 权重文件需自行下载（见「快速开始」）
└── requirements.txt     # Python 依赖
```

---

## 🚀 快速开始

### 环境
- Python 3.8+，NVIDIA GPU（CUDA），摄像头
- 依赖：`pip install -r requirements.txt`
- 模型权重：仓库**不内置权重文件**（`rvm_resnet50.pth` 单文件超 GitHub 100MB 限制），请从 [RVM 官方仓库](https://github.com/PeterL1n/RobustVideoMatting) 下载 `rvm_mobilenetv3.pth` / `rvm_resnet50.pth`，放入 `RobustVideoMatting/weights/` 后即可运行

### 运行（任选其一）

**① Web 端（推荐，浏览器实时预览）**
```bash
python server.py
# 浏览器打开 http://localhost:5000
```

**② 桌面端（OpenCV 实时窗口）**
```bash
python rvm_run_live.py
# W/S 切换背景，V 虚化，N 现实背景，R 记录 100 帧指标，Q 退出
```

**③ 离线视频抠图**
```bash
python rvm-run.py        # 输入 input.mp4 → 输出 com.mp4 / pha.mp4 / fgr.mp4
```

**④ Streamlit 实验工作台**
```bash
streamlit run app.py
```

将背景图片（`.jpg/.png/.bmp`）或视频（`.mp4/.avi/.mov`）放入 `background/` 文件夹，启动时自动扫描。

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
PyTorch · OpenCV · CUDA/FP16 · Flask + MJPEG · Streamlit · LAB/Reinhard 色彩迁移 · 非锐化掩蔽（Unsharp Masking）

---

## 🙏 致谢
- 抠图主干网络基于 [RobustVideoMatting](https://github.com/PeterL1n/RobustVideoMatting)（PeterL1n et al., *Robust High-Resolution Video Matting with Temporal Guidance*, WACV 2022）。
- 色彩迁移方法参考 Reinhard et al., *Color Transfer between Images* (2001)。

## 📄 License
RVM 主干部分遵循其原始 `RobustVideoMatting/LICENSE`；本项目自研代码以 MIT 许可证开源。
