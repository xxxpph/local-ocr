# M0 技术验证结论

> 验证日期: 2026-08-08 · 验证环境: Windows 11 + RTX 3080 Ti (驱动 591.86) + Python 3.12.7

## 验证结果总表

| # | 验证项 | 结果 | 结论 |
|---|---|---|---|
| 1 | 无 paddlepaddle 环境跑通 `PaddleOCR(engine="onnxruntime")` | ✅ v6-medium CPU 0.78s/张，v5-mobile CPU 0.35s/张，识别正确 | 用户侧无需安装 PaddlePaddle |
| 2 | 官方模型 | ✅ PaddleX 3.7.2 直接提供**官方预转换 ONNX 模型**（`PP-OCRv6_medium_det_onnx` 等，自动下载） | 转换环节整个取消，无需 paddle2onnx |
| 3 | 模型体积 | v6-medium: det 60M + rec 74M = **134MB**；v5-mobile: det 4.7M + rec 16M = **21MB** | 发布包内置双档（zip 预计 ~110-130MB） |
| 4 | onnxruntime-gpu[cuda,cudnn] extras | ✅ CUDA 12.9 + cuDNN 9.x DLL 自动装入 site-packages，无需手动装 CUDA Toolkit | 但 **cuDNN 版本必须精确锁定**（见下） |
| 5 | GPU 推理 | ✅ 需 3 步配方（见下）：`preload_dlls()` + 补 preload nvrtc/curand + `cudnn_conv_algo_search=HEURISTIC` | v6-medium **0.028s/张**、v5-mobile **0.021s/张**，比 CPU 快 **28 倍** |
| 6 | paddle2onnx | ⚠️ 2.1.0 连 import 都要求 paddle 已安装 | 绝不能进入用户 requirements（仅维护者转换环境） |

## 关键坑与对策（已实测）

### 坑 1: cuDNN 9.24 与 ORT 1.26 不兼容（致命）
- 现象: `CUDNN_FE failure 11: CUDNN_BACKEND_API_FAILED` at `build_operation_graph`，推理**静默回退 CPU**（GPU 利用率 ~0-12%，速度与 CPU 相同）
- 根因: ORT 1.26.0 内嵌 cudnn_frontend v1.12.0，与 cuDNN 9.2x 新后端不兼容（社区同类报告: microsoft/onnxruntime#26274、bytedeco/javacpp-presets#1797）
- 对策: **`pip install nvidia-cudnn-cu12==9.11.1.4`**（9.10/9.11 系列已被社区验证可用）
- 启示: requirements 必须**精确 pin 所有 nvidia-* 包版本**，禁止依赖 `~=9.0` 通配解析

### 坑 2: pip extras 的 DLL 不在加载路径
- `onnxruntime.preload_dlls()` 必须**显式调用**（在创建任何 session 之前）；且其内置清单缺少 nvrtc/curand，需手动补 preload
- 对策: engine 启动时执行下方"GPU 配方"

### 坑 3: 首帧耗时
- 首次推理含 cuDNN 引擎构建（1.7s），后续 0.028s → 服务启动时必须 warmup

## 确定的 GPU 配方（engine.py 实现基准）

```python
import onnxruntime as ort
ort.preload_dlls()                      # 预加载 CUDA/cuDNN DLL（Windows）
# 补 preload: nvidia/cuda_nvrtc/bin/nvrtc64_120_0.dll、nvidia/curand/bin/curand64_10.dll
engine_config = {
    "providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
    "provider_options": [
        {"device_id": 0, "cudnn_conv_algo_search": "HEURISTIC"},  # 绕开 #17970 同类问题
        {},
    ],
}
```

## 版本锁定清单（用户环境 requirements）

| 包 | 版本 | 说明 |
|---|---|---|
| paddleocr | ==3.7.0 | 已含 GPU 慢 50 倍修复 #17970 |
| onnxruntime-gpu | ==1.26.0 | CUDA 12.8 线，内嵌 cudnn_frontend v1.12 |
| nvidia-cudnn-cu12 | ==9.11.1.4 | **关键 pin，9.2x 不兼容** |
| nvidia-cublas-cu12 | ==12.9.2.10 | 实测解析版本，一并 pin |
| nvidia-cuda-runtime-cu12 / nvrtc / cufft / curand / nvjitlink | 实测解析版本 | 一并 pin 防漂移 |
| onnxruntime (CPU 场景) | ==1.26.0 | 与 GPU 版互斥 |

## 引擎实现路线决策

**采用 PaddleX 引擎（不手写 pipeline）**：PaddleX runner 原生支持 `providers` + `provider_options` 透传，配合上方配方即可。M0 预案中的"手写三模型 pipeline"不启用，但保留为 fallback 文档。

## 发布包决策

1. 模型双档内置：`v6-medium`（默认）+ `v5-mobile`（保底），均来自官方 ONNX 产物
2. 用户侧 requirements 不含 paddle2onnx / paddlepaddle
3. GPU 场景安装下载量 ~1.9GB（onnxruntime-gpu 226M + nvidia DLL 包 1.7G），install.bat 必须提前明确提示
4. 模型来源 `~/.paddlex/official_models/`（用户侧首次运行会联网；发布包内置后零联网）
