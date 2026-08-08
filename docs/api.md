# API 文档

服务仅监听 `127.0.0.1`，基础地址 `http://127.0.0.1:8866/`（端口被占用时自动 +1，以 start.bat 窗口显示为准）。
交互式文档（Swagger）：`http://127.0.0.1:8866/docs`

## 1. GET /health — 健康检查

### 响应
```json
{
  "status": "ok",
  "engine": "onnxruntime",
  "default_model_set": "v6-medium",
  "model_sets": {
    "v6-medium": {
      "replicas": 1,
      "providers": ["CUDAExecutionProvider"],
      "gpu_fail_reason": null
    }
  },
  "engine_replicas": 1,
  "use_gpu_expected": true,
  "version": "1.0.1",
  "port": 8866,
  "host": "127.0.0.1"
}
```

### 字段说明
| 字段 | 说明 |
|---|---|
| `model_sets` | 已加载的档位；`providers` 为实际生效的 ORT provider（CUDAExecutionProvider=GPU） |
| `gpu_fail_reason` | GPU 未生效的原因（null 表示正常） |
| `engine_replicas` | 配置的副本数（实际生效数见各档位 `replicas`） |
| `use_gpu_expected` | 配置期望值（不等于实际 provider 时说明发生了降级） |

## 2. POST /ocr — 图片识别（文件上传）

### 请求
```
Content-Type: multipart/form-data
字段:
  file      (必填) 图片文件，支持 PNG/JPG/BMP 等 PIL 可解码格式
  model_set (可选) v6-medium（默认，更准）/ v5-mobile（更快）
```

### 成功响应（HTTP 200）
```json
{
  "text": "你好，世界！\n订单号: 20260808-001",
  "results": [
    {
      "text": "你好，世界！",
      "score": 0.9982,
      "box": [[16, 27], [531, 27], [531, 67], [16, 67]]
    }
  ],
  "time_ms": 28.4,
  "provider": "CUDAExecutionProvider",
  "model_set": "v6-medium",
  "filename": "sample1.png"
}
```

| 字段 | 说明 |
|---|---|
| `text` | 全部识别文本，按行拼接（`\n` 分隔） |
| `results[].text` | 单行文本 |
| `results[].score` | 置信度 0~1 |
| `results[].box` | 文本框四点坐标（原图像素，顺序: 左上→右上→右下→左下） |
| `time_ms` | 推理耗时（不含网络传输） |
| `provider` | 实际引擎（`CUDAExecutionProvider`=GPU / `CPUExecutionProvider`=CPU） |
| `model_set` | 本次实际使用的档位 |

### 错误响应
| HTTP | detail 示例 | 场景 |
|---|---|---|
| 400 | `上传的图片为空` | 文件内容为空 |
| 400 | `不是有效的图片文件，请上传 PNG/JPG/BMP 等图片格式` | 文件不是可解码图片 |
| 400 | `未知模型档位: xxx（可选: v6-medium, v5-mobile）` | model_set 非法 |
| 500 | `识别失败: <异常信息>` | 引擎内部异常（详见 logs/server.log 堆栈） |

## 3. POST /ocr_base64 — 图片识别（base64）

### 请求
```json
{
  "image_base64": "<base64 编码的图片>",
  "model_set": "v5-mobile"
}
```
`model_set` 可选。base64 解码失败返回 400 `base64 解码失败`。
其余响应与错误行为同 `/ocr`。

## 4. 调用示例

### curl
```bash
# 文件上传，指定 v5-mobile
curl -F "file=@test.png" -F "model_set=v5-mobile" http://127.0.0.1:8866/ocr

# base64
curl -X POST http://127.0.0.1:8866/ocr_base64 \
  -H "Content-Type: application/json" \
  -d '{"image_base64": "<...>"}'
```

### Python
```python
import requests

# 文件
r = requests.post("http://127.0.0.1:8866/ocr",
                  files={"file": open("test.png", "rb")},
                  data={"model_set": "v6-medium"})
data = r.json()
print(data["text"])

# base64
import base64
b64 = base64.b64encode(open("test.png", "rb").read()).decode()
r = requests.post("http://127.0.0.1:8866/ocr_base64",
                  json={"image_base64": b64})
print(r.json()["text"])
```

### JavaScript（浏览器）
```js
const fd = new FormData();
fd.append('file', fileInput.files[0]);
fd.append('model_set', 'v6-medium');
const r = await fetch('http://127.0.0.1:8866/ocr', { method: 'POST', body: fd });
const data = await r.json();
console.log(data.text);
```

## 5. 并发与限制

- 单 worker（uvicorn 默认），请求经线程池执行
- 同档位请求由副本锁串行；不同档位 / 多副本可并行（见 docs/architecture.md §5）
- 上传大小无显式限制，但超大图片（>5000px 边）推理耗时与显存占用会显著上升
- 服务重启后首次请求某档位有 ~2s 的懒加载耗时（warmup 已在启动时完成默认档）
