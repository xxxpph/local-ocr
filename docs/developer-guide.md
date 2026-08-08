# 开发与维护指南

本文面向 local-ocr 的维护者/贡献者。最终用户请直接看 [README](../README.md)。

## 1. 环境准备

```bash
git clone git@github.com:xxxpph/local-ocr.git
cd local-ocr

# 创建虚拟环境并安装 GPU 版依赖（无 NVIDIA 显卡用 requirements-cpu.txt）
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-gpu.txt
```

> 注意：`requirements-gpu.txt` 中的 nvidia-cudnn-cu12==9.11.1.4 为关键锁定，
> 勿升级到 9.2x（与 onnxruntime 1.26 不兼容，见 docs/M0_verification.md）。

## 2. 目录结构

```
├── server/            # FastAPI 服务（app/engine/config/detect_env + static）
├── scripts/           # 一键安装/启动/卸载（.bat 壳 + .ps1 主逻辑）
├── tools/             # 维护者工具
│   ├── collect_models.py     # 收集官方 ONNX 模型到 models/onnx/
│   ├── make_release.py       # 打发布 zip（dist/local-ocr-v<版本>-win64.zip）
│   ├── make_sample_image.py  # 生成自测样例图
│   └── verify_onnx_pipeline.py  # 管线验证脚本
├── docs/              # 本文档 + 架构/API/排障/验证结论
└── models/onnx/       # 官方预转 ONNX 模型（已入库）
```

## 3. 本地运行与调试

```bash
# 启动服务（开发模式）
.venv\Scripts\python.exe -m uvicorn server.app:app --host 127.0.0.1 --port 8866

# 安装自测（不依赖外部样例图，内置生成）
.venv\Scripts\python.exe scripts\self_test.py

# 管线验证（输出依赖/模型档位/provider/耗时）
.venv\Scripts\python.exe tools\verify_onnx_pipeline.py tools\sample_data\sample1.png v6-medium
```

- 服务日志：`logs/server.log`（滚动 5MB×3）
- 修改 Web UI 后无需构建（原生 HTML/JS）

## 4. 模型维护

模型为 PaddleX 官方预转换 ONNX（`*_onnx` 产物），**不要手动转换**。

```bash
# ① 首次运行让 PaddleX 自动下载官方模型（联网）
.venv\Scripts\python.exe -c "from paddleocr import PaddleOCR; PaddleOCR(engine='onnxruntime')"

# ② 收集到 models/onnx/<档位>/（只拷贝推理必需文件）
.venv\Scripts\python.exe tools\collect_models.py

# ③ 校验本地模型目录可加载（重点: v5 档位）
.venv\Scripts\python.exe tools\verify_onnx_pipeline.py <图> v5-mobile
```

新增档位步骤：
1. `server/config.py` 的 `MODEL_SETS` 增加条目（目录名 + 官方模型名）
2. `tools/collect_models.py` 的 `SETS` 增加对应缓存目录名
3. 重新收集模型、更新架构文档中的档位表

## 5. 发布流程（CI 自动）

1. 提交代码并推送 master
2. 打 tag（语义化版本）：
   ```bash
   git tag v1.0.1
   git push origin v1.0.1
   ```
3. GitHub Actions（`.github/workflows/release.yml`）自动：
   - checkout（模型已入库，无需联网下载）
   - `python tools/make_release.py --version <tag>` → `dist/local-ocr-v<版本>-win64.zip`
   - 上传为 Release 资产
4. 在 Actions 页面确认 `build-release` 成功；失败可先看对应步骤日志

本地手工打包：`python tools/make_release.py --version 1.0.1`

## 6. 测试

- 完整用例清单：docs/test_matrix.md（环境矩阵 + 用例 + 本机实测记录）
- 关键回归点：
  - 安装全流程（install.bat，含无 Python/无 GPU 场景）
  - v6/v5 双档位本地模型加载（曾出现 Model name mismatch 回归）
  - GPU 静默回退检测（删驱动/断 CUDA 时服务应自动降级 CPU 并记录原因）
  - 并发（engine_replicas=2 时同档并行、跨档并行）
- 新提交前至少跑：`scripts\self_test.py` + 一次 v5-mobile 识别

## 7. 常见开发坑（都是实测踩过的）

| 坑 | 现象 | 对策 |
|---|---|---|
| .bat 中文 | cmd 解析乱码/命令碎片 | .bat 纯 ASCII，中文放 .ps1（BOM + CRLF） |
| .ps1 三引号 | 文件头被当字符串输出 | 注释用 `<# #>` |
| PowerShell 5.1 + native stderr | EAP=Stop 时抛 NativeCommandError | 调用处临时 Continue |
| python 中文 print | cp1252/GBK 环境 UnicodeEncodeError | 脚本开头 reconfigure utf-8 |
| PaddleX 校验模型名 | v5 档 Model name mismatch | 本地模式同时传 model_name + model_dir |
| ORT session 遍历 | pydantic mock 抛 PydanticUserError / 字典迭代中修改 | try/except + 快照迭代 |
