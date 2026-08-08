# 架构与技术设计

## 1. 总览

```
浏览器/客户端 ──HTTP──> FastAPI (server/app.py)
                            │
                            ▼
                    OCREngineManager (server/engine.py)
                    ├── 档位白名单懒加载（v6-medium / v5-mobile）
                    ├── 每档位 N 个引擎副本（engine_replicas，默认 1）
                    └── 轮询分发 + 每副本独立锁
                            │
                            ▼
                    PaddleOCR 3.7 pipeline（engine="onnxruntime"）
                    ├── text_detection_model（官方预转 ONNX）
                    ├── text_recognition_model
                    └── 本地模型目录 models/onnx/<档位>/（零联网）
                            │
                            ▼
                    ONNX Runtime（onnxruntime-gpu 1.26.0 / CPU 1.26.0）
```

## 2. 技术栈与版本锁定

| 组件 | 版本 | 说明 |
|---|---|---|
| Python | 3.11+（推荐 3.12） | 自动安装 3.12.7 per-user，免管理员 |
| paddleocr | ==3.7.0 | 最新版，含 GPU 慢 50 倍修复 #17970 |
| paddlex | 3.7.x（自动解析） | 无 paddlepaddle 依赖 → 用户侧无需安装 PaddlePaddle |
| onnxruntime-gpu | ==1.26.0 | CUDA 12.8 线，内嵌 cudnn_frontend v1.12 |
| nvidia-cudnn-cu12 | ==9.11.1.4 | **必须 pin**，9.2x 与 ORT 1.26 不兼容（见 M0 验证） |
| onnxruntime | ==1.26.0 | CPU 场景（与 GPU 版互斥，安装器二选一） |
| fastapi / uvicorn | 最新稳定 | HTTP 服务，单 worker |

> 版本锁定依据与血泪教训：见 [M0_verification.md](M0_verification.md)

## 3. 模块职责

| 文件 | 职责 |
|---|---|
| `server/app.py` | FastAPI 路由、请求日志、错误分类（400/500 + 中文 detail） |
| `server/engine.py` | `OCREngine`（单引擎：GPU 配方 + 降级 + warmup + 锁）与 `OCREngineManager`（多档位 + 副本池） |
| `server/config.py` | 配置模型（config.json / 环境变量 / 默认值）、模型档位白名单 |
| `server/detect_env.py` | 安装前环境检测（GPU/驱动/Python），stdlib-only |
| `server/static/index.html` | 单文件 Web UI（无构建） |
| `scripts/install.ps1` | 一键安装主流程（.bat 为 ASCII 壳，ps1 承载中文逻辑） |
| `scripts/self_test.py` | 安装自测（建引擎 + 样例图推理 + provider 报告） |
| `tools/collect_models.py` | 维护者：从 PaddleX 缓存收集官方 ONNX 模型 |
| `tools/make_release.py` | 维护者：打发布 zip |

## 4. GPU 配方（engine.py 实现基准）

Windows 下 GPU 推理必须满足三个条件（缺一不可，实测得出）：

```python
# 1. 预加载 pip 安装的 nvidia DLL（onnxruntime-gpu[cuda,cudnn] extras 安装，
#    但 ORT 不会自动找它们；清单缺 nvrtc/curand 需手动补）
ort.preload_dlls()
ctypes.CDLL(site_packages / "nvidia/cuda_nvrtc/bin/nvrtc64_120_0.dll")
ctypes.CDLL(site_packages / "nvidia/curand/bin/curand64_10.dll")

# 2. cuDNN 版本必须为 9.11.x（9.2x 后端与 ORT 内嵌前端 v1.12 不兼容，
#    表现为 Conv 图构建失败后静默回退 CPU，GPU 利用率 0%）
#    requirements-gpu.txt: nvidia-cudnn-cu12==9.11.1.4

# 3. CUDA EP 必须带 HEURISTIC 算法搜索（DEFAULT 固定 IMPLICIT_PRECOMP_GEMM，
#    cuDNN 9 对多数卷积配置拒绝该算法 → 运行时回退 CPU）
engine_config = {
    "providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
    "provider_options": [
        {"device_id": 0, "cudnn_conv_algo_search": "HEURISTIC"},
        {},
    ],
}
```

防静默回退校验：引擎初始化后遍历所有 ORT session 的 `get_providers()`，
若实际不含 CUDAExecutionProvider 则如实记录原因并重建 CPU 引擎——
不信任"创建成功"即"GPU 生效"。

## 5. 并发模型

### 5.1 单引擎（默认，replicas=1）

- 每个 `OCREngine` 内部一把 `threading.Lock`，`predict` 串行化
- 原因：PaddleX pipeline 未声明线程安全，串行是保守正确
- 吞吐：GPU 约 10-30ms/张 → 每秒 30-100 张；CPU 0.3-0.8s/张 → 每秒 1-3 张

### 5.2 多档位 + 副本池（replicas=N）

```
请求 model_set=v5 ──→ 档位 v5 副本池（轮询）──→ 副本 i（独立锁）
请求 model_set=v6 ──→ 档位 v6 副本池（轮询）──→ 副本 j（独立锁）
```

- **副本间零共享状态** → 天然并行安全（不依赖 predict 线程安全）
- 懒加载：默认档启动加载；其他档首次请求才创建（双重检查锁，并发安全）
- 创建失败（显存不足等）自动减半回退
- 代价：每副本 ~300-500MB 显存 + ~2s 初始化；CPU 模式不建议 >1（抢核反而变慢）

## 6. 模型档位

| 档位 | 模型 | 体积 | GPU 稳态 | CPU 稳态 | 定位 |
|---|---|---|---|---|---|
| v6-medium（默认） | PP-OCRv6 medium det/rec | ~134MB | ~10ms | ~0.78s | 更准（det +4.6% / rec +5.1% vs v5_server） |
| v5-mobile | PP-OCRv5 mobile det/rec | ~21MB | ~8ms | ~0.35s | 更快、包更小 |

- 模型为**官方预转换 ONNX**（PaddleX 直接提供 `*_onnx` 产物），无需 paddle2onnx
- 本地模式必须同时传 `model_name` + `model_dir`（PaddleX 用 model_name 校验 yml，
  只传目录会用默认档名比对导致 v5 报 Model name mismatch）
- 接口请求可带 `model_set` 参数动态选档（白名单校验）

## 7. 请求链路

```
POST /ocr (multipart: file, model_set?)
  → 校验 model_set 白名单（非法 → 400）
  → asyncio.to_thread(engine.predict, bytes)
      → 图片解码（PIL）→ PaddleOCR.predict（锁内）
      → 结果规范化 {text, results[], time_ms, provider, model_set}
  → 成功：INFO 日志（filename/耗时/provider/行数）
  → UnidentifiedImageError → 400 "不是有效的图片文件..."
  → 其他异常 → 500 + logging.exception（含堆栈）
```

服务仅绑定 127.0.0.1（不触发防火墙弹窗），端口占用自动 +1。

## 8. 安全设计

- model_set 走 `MODEL_SETS` 白名单，无路径注入面
- 仅监听 loopback，不对外网开放
- 模型/配置均为本地文件，无远程代码执行面
- 驱动由用户自行安装更新（NVIDIA EULA 禁止再分发，不随包携带）
