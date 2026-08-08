# 测试矩阵（M3 验收）

发布前需在以下环境组合实测通过。每项记录: 安装结果 / 自测结果 / 实际 provider / 备注。

## 环境矩阵

| # | 环境 | GPU | Python | 预期 |
|---|---|---|---|---|
| 1 | Win11 + 新驱动 RTX | NVIDIA 30/40 系, 驱动 ≥ 560.28 | 无 | 自动装 Python → GPU 版 → CUDA EP |
| 2 | Win10 22H2 + 旧驱动 RTX | NVIDIA, 驱动 < 560.28 | 有 3.12 | CPU 版 + 驱动过旧提示 |
| 3 | Win11 + Intel 核显 | Intel | 有 | CPU 版 |
| 4 | Win11 + AMD 核显 | AMD | 无 | 自动装 Python → CPU 版 |
| 5 | 无 GPU VM | 无 | 有 | CPU 版 |
| 6 | 中文/空格路径安装 | 任意 | 任意 | 安装/启动正常（README 建议纯英文路径） |

## 用例清单

| 用例 | 步骤 | 通过标准 |
|---|---|---|
| 全新安装 | 解压 → install.bat | 自测通过，显示"安装成功" |
| 重装 | 已有 .venv → install.bat → Y | 环境重建成功 |
| 断网安装 | 无网络 → install.bat | 明确中文报错 + 日志路径，不崩溃 |
| 启动 | start.bat | 自动开浏览器，页面状态显示 GPU/CPU |
| 网页识别 | 拖入样例图 | 画框 + 文本正确 + 置信度 |
| 复制 | 点"复制全部" | 剪贴板内容正确 |
| API | curl /health /ocr /ocr_base64 | JSON 正确，provider 符合预期 |
| 端口占用 | 先占 8866 → start.bat | 自动切 8867 |
| 模型切换 | config.json model_set=v5-mobile → 重启 | /health 显示 v5-mobile，识别正常 |
| 卸载 | uninstall.bat → Y | .venv/config/logs 删除，models 保留 |
| GPU 失效兜底 | 安装 GPU 版后禁用 CUDA EP（或删驱动） | 服务启动自动降级 CPU，/health 显示原因 |
| 杀软 | 360/Defender 扫描 | 无拦截或明确提示文案 |

## 本机（RTX 3080 Ti, 驱动 591.86, Win11）已验证

| 用例 | 结果 |
|---|---|
| M0 技术验证 | ✅ 见 docs/M0_verification.md |
| 全流程安装（install.bat） | ✅ GPU 版，自测 CUDA EP 通过（v1.0.1 后含 PowerShell 兼容修复） |
| 启动（start.bat） | ✅ 端口 8866→8867 自动避让，浏览器自动打开 |
| 网页/API | ✅ /health /ocr /ocr_base64，GPU 识别正确 |
| 引擎兜底 | ✅ GPU 初始化失败自动降级 CPU（修复 walker 前实测） |
| v5-mobile 本地模型目录 | ✅ 修复 Model name mismatch 后双档位均可用（GPU 57.5ms / 266ms 首次） |
| 接口选模型 | ✅ /ocr 与 /ocr_base64 带 model_set 均生效，非法值 400 |
| 并发并行 | ✅ 跨档并发总耗时≈max（真并行）；replicas=2 同档并行 |
| 并发 smoke | ✅ 8 并发 + 双档混合全 200 |
| 副本创建回退 | ✅ 逻辑实测（失败自动减半），真实 OOM 场景待低配机验证 |
| 性能基准 | v6-medium 稳态 ~10ms / v5-mobile ~8ms（GPU）；CPU 0.78s / 0.35s |
| CI 发布 | ✅ v1.0.0/v1.0.1 Release 构建成功，zip 资产 113.7MB |
| PowerShell 环境兼容 | ✅ cp1252 模拟 + PS5.1 模拟均通过（修复后） |

### 待外部环境验证

| 环境 | 用例 |
|---|---|
| Win10 22H2 + 旧驱动 RTX | 驱动过旧提示 + CPU 降级 |
| Intel / AMD 核显 | CPU 链路 |
| 无 GPU VM | CPU 链路 |
| 无 Python 机器 | 自动静默安装 Python 3.12 |
| 断网安装 | 明确中文报错 + 日志路径 |
| 杀软（360/Defender） | 无拦截或明确提示 |
| 4GB 小显存显卡 | replicas>1 的 OOM 回退 |
