import torch
import sys
import os



print("Python路径:", sys.executable)
print("Torch版本:", torch.__version__)
print("CUDA可用:", torch.cuda.is_available())
sys.path.append('./RobustVideoMatting')

from RobustVideoMatting.model import MattingNetwork
from RobustVideoMatting.inference import convert_video # 导入官方 API

weight_path = 'RobustVideoMatting/weights/rvm_mobilenetv3.pth' # 确认权重路径
input_path = 'input.mp4'

model = MattingNetwork('mobilenetv3').eval().cuda()
model.load_state_dict(torch.load(weight_path))
model = model.half()

print("开始抠图转换，请稍后...")
convert_video(
    model,
    input_source=input_path,
    output_type='video',
    output_composition='com.mp4',    # 抠图后的合成视频 默认黑底
    output_alpha="pha.mp4",          # 提取出的 Alpha 遮罩
    output_foreground="fgr.mp4",     # 提取出的前景
    output_video_mbps=4,
    downsample_ratio=0.5,
    seq_chunk=12,                    # 利用 GPU 并行处理 12 帧
)
print("转换完成！请检查 com.mp4, pha.mp4 和 fgr.mp4")

