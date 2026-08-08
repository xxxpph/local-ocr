# local-ocr — OCR 一键部署服务

Windows 本地一键部署的 OCR 识别服务。下载 → 双击 `install.bat` → 双击 `start.bat`，即可在浏览器里使用。图片数据全程在本机处理，不出本地。

**技术栈**: PaddleOCR 3.7 + ONNX Runtime + FastAPI（用户环境无需安装 PaddlePaddle）

## ✨ 特性

- **一键安装**: 自动检测显卡/驱动/Python，缺什么装什么（无需管理员权限）
- **GPU 自动加速**: NVIDIA 显卡 + 驱动达标 → 自动使用 CUDA 推理（实测比 CPU 快约 28 倍）；不达标或没有 → 自动降级 CPU，服务照常可用
- **零联网使用**: 官方预转换 ONNX 模型已直接入库（克隆即用），安装后完全离线
- **网页界面**: 拖拽图片即可识别，结果画框标注、一键复制
- **REST API**: 提供 `/ocr` 与 `/ocr_base64` 接口，方便程序调用
- **中英双语识别**: 内置 PP-OCRv6 medium（默认，更准）与 PP-OCRv5 mobile（更快）两档模型

## 📋 系统要求

| 项目 | 要求 |
|---|---|
| 系统 | Windows 10 / 11 x64 |
| CPU | 任意 x64 处理器（ARM 架构暂不支持） |
| 显卡 | 可选。NVIDIA 显卡 + 驱动 ≥ 560.28 可 GPU 加速；AMD/Intel/无显卡自动用 CPU |
| 内存 | 建议 8GB 以上 |
| 磁盘 | 安装后约 4GB（含模型与 CUDA 运行库） |

> GPU 加速版首次安装需下载约 2GB 的 CUDA/cuDNN 运行库（自动完成，仅一次）。
> CPU 版仅需约 200MB。

## 🚀 快速开始

1. 下载发布包并解压（路径建议**不要**包含中文和空格，如 `D:\ocr`）
2. 双击 **`install.bat`** — 自动检测环境并安装（约 3-10 分钟，视网速）
   - 首次安装会提示"检测到 NVIDIA 显卡，下载约 2GB CUDA 运行库"，耐心等待
   - 安装完成后自动运行自测，显示 `安装成功` 即完成
3. 双击 **`start.bat`** — 自动启动服务并打开浏览器
4. 浏览器中拖入图片即可识别 🎉

停止服务：关闭弹出的黑色服务窗口即可。

## 🌐 Web 界面

- 拖拽/点击上传图片 → 自动识别
- 识别框叠加显示，置信度标注
- "复制全部"一键复制文本
- 页面顶部实时显示当前引擎（GPU/CPU）与模型档位

## 🔌 REST API

服务仅监听 `127.0.0.1`，地址 `http://127.0.0.1:8866/`（端口被占用时自动 +1）。

### 健康检查
```
GET /health
```
返回默认档位、已加载档位列表及各档实际生效的 provider（GPU/CPU）、副本数等。

### 图片识别（文件上传）
```
POST /ocr
Content-Type: multipart/form-data
字段: file      = 图片文件
      model_set = 可选。v6-medium（默认，更准）/ v5-mobile（更快）
```

### 图片识别（base64）
```json
POST /ocr_base64
{
  "image_base64": "<base64 编码的图片>",
  "model_set": "v5-mobile"
}
```

### 接口选模型
请求时传 `model_set` 即可切换模型，无需重启：
- 不传 → 用 `config.json` 里的默认档
- 首次使用某档位会自动加载（约 2 秒），之后零延迟复用
- 非法档位名返回 400

响应示例:
```json
{
  "text": "你好，世界！\n订单号: 20260808-001",
  "results": [
    {"text": "你好，世界！", "score": 0.998, "box": [[16,27],[531,27],[531,67],[16,67]]}
  ],
  "time_ms": 28.4,
  "provider": "CUDAExecutionProvider",
  "model_set": "v6-medium"
}
```

接口文档（Swagger）: `http://127.0.0.1:8866/docs`

## ❓ 常见问题

**Q: install.bat 提示驱动过旧怎么办？**
安装 CPU 版可以正常使用，只是慢一些。想启用 GPU：去 [NVIDIA 驱动下载](https://www.nvidia.cn/drivers/) 更新驱动后，删除 `.venv` 文件夹重新运行 install.bat。

**Q: 安装时被杀毒软件拦截/误报？**
本项目为纯脚本（.bat/.ps1/.py），不含可执行程序，安全无风险。如 360 等提示，请选择"允许"。下载 Python 安装包时也可能触发联网提示。

**Q: 启动后浏览器没自动打开？**
手动访问 `http://127.0.0.1:8866/`（端口以启动窗口显示为准）。

**Q: 识别中文标点有细微差异（如全角/半角）？**
属模型自身特性，非故障。

**Q: 想切换模型档位？**
两种方式：
1. 网页界面右上角下拉框直接选（更准 v6 / 更快 v5）
2. 接口请求带 `model_set` 参数
3. 编辑项目根目录 `config.json` 改 `model_set` 为默认档，保存后重启服务

**Q: 并发请求多时怎么提速？**
编辑 `config.json` 增加 `"engine_replicas": 2`（默认 1 = 串行），每档位会加载多个独立引擎副本并行处理请求。注意：
- 每副本额外占用显存/内存（GPU 约 300-500MB/副本），显存小的显卡慎用
- CPU 模式下不建议 >1（多副本会争抢 CPU 核心，反而变慢）
- 副本创建失败会自动减半回退，不影响服务可用

**Q: 端口被占用？**
start.bat 会自动探测并 +1，无需手动处理。

## 📁 项目结构

```
├── server/            # FastAPI 服务 (app.py / engine.py / config.py)
├── scripts/           # 一键脚本 (install.bat / start.bat / uninstall.bat)
├── models/onnx/       # 内置模型（官方预转换 ONNX）
├── tools/             # 维护者工具（模型收集/发布打包/自测样例）
├── requirements*.txt  # 依赖清单（GPU/CPU 版本锁定）
└── docs/              # 技术文档
```

## 🤝 开源说明

- 本项目: [Apache-2.0](LICENSE)
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR): Apache-2.0
- [ONNX Runtime](https://github.com/microsoft/onnxruntime): MIT
- PP-OCR 模型: Apache-2.0
- NVIDIA 显卡驱动由用户自行安装更新，不随本项目分发

---

## English Summary

A one-click OCR service for Windows: download → run `install.bat` → run `start.bat` → use in browser.

- Stack: PaddleOCR 3.7 + ONNX Runtime + FastAPI (no PaddlePaddle needed on user machines)
- Auto-detects GPU/driver; uses CUDA when available, falls back to CPU otherwise
- Models (official pre-converted ONNX, PP-OCRv6 medium / PP-OCRv5 mobile) bundled in the release — fully offline after install
- Web UI + REST API (`/ocr`, `/ocr_base64`), bound to 127.0.0.1
- System: Windows 10/11 x64. NVIDIA GPU optional (driver ≥ 560.28)
- License: Apache-2.0
