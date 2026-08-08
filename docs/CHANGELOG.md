# 变更日志

## [v1.0.1] - 2026-08-08

### 修复
- **双击 install.bat 报 `NativeCommandError`**：detect_env.py 中文输出在非 UTF-8 环境崩溃（UnicodeEncodeError，与 CI 上 make_release.py 同类问题）；install.ps1 兼容 PowerShell 5.1 的 native stderr 行为（EAP=Stop 会中断流程），检测异常时完整写入 install.log
- **CI 构建失败**：make_release.py 的 `print("发布包已生成...")` 在 GitHub runner（cp1252）上 UnicodeEncodeError；tools/*.py 统一 reconfigure stdout 为 UTF-8

## [v1.0.0] - 2026-08-08

### 功能
- 一键安装：自动检测 GPU/驱动/Python，缺什么装什么（无需管理员）
- GPU 自动加速（实测比 CPU 快约 28 倍），不达标自动降级 CPU
- 接口可选模型档位（`model_set`：v6-medium 更准 / v5-mobile 更快）
- 引擎副本池并发（`engine_replicas`，默认 1 串行）
- Web UI：拖拽上传、画框标注、一键复制、模型下拉框
- REST API：/health /ocr /ocr_base64（127.0.0.1 绑定）
- 官方预转 ONNX 模型直接入库，零联网使用
- 中英双语识别（PP-OCRv6 medium + PP-OCRv5 mobile）

### 技术要点
- 用户环境零 PaddlePaddle 依赖（onnxruntime 引擎 + 官方预转 ONNX）
- cuDNN 9.11 pin（9.2x 与 ORT 1.26 不兼容，见 docs/M0_verification.md）
- GPU 配方：preload_dlls + HEURISTIC 算法搜索 + 防静默回退校验
