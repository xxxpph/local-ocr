# -*- coding: utf-8 -*-
"""安装自测：建引擎 + 样例图推理 + provider 报告。

由 install.bat 调用（venv 内运行）。退出码 0=通过 1=失败。
"""
import os
import sys
import traceback
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


def make_sample_image():
    """生成一张带文字的样例图（无需外部字体也可运行）。"""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (520, 90), "white")
    draw = ImageDraw.Draw(img)
    font_path = r"C:\Windows\Fonts\msyh.ttc"
    if os.path.exists(font_path):
        draw.text((15, 22), "你好 OCR 12345", fill="black",
                  font=ImageFont.truetype(font_path, 36))
    else:
        draw.text((15, 22), "Hello OCR 12345", fill="black")
    return img


def main():
    print("=" * 50)
    print("  OCR 安装自测")
    print("=" * 50)

    from server.config import load_config
    from server.engine import OCREngineManager

    config = load_config()
    print(f"配置: model_set={config.model_set} use_gpu={config.use_gpu} replicas={config.engine_replicas}")

    try:
        manager = OCREngineManager(config)
        engine = manager.get()
    except Exception:  # noqa: BLE001
        print("\n[失败] 引擎初始化异常:")
        traceback.print_exc()
        return 1

    provider_text = "GPU (CUDA)" if engine.provider == "CUDAExecutionProvider" else "CPU"
    print(f"引擎: PaddleOCR 3.7 + ONNX Runtime")
    print(f"Provider: {provider_text}")

    if engine.gpu_fail_reason:
        print(f"[提示] GPU 未生效: {engine.gpu_fail_reason}")
        print("       已自动降级 CPU，服务可正常使用。")

    try:
        result = engine.predict(make_sample_image())
    except Exception:  # noqa: BLE001
        print("\n[失败] 推理异常:")
        traceback.print_exc()
        return 1

    lines = len(result["results"])
    print(f"样例图识别: {lines} 行, 耗时 {result['time_ms']}ms")
    for item in result["results"]:
        print(f"  [{item['score']:.2f}] {item['text']}")

    if lines == 0:
        print("\n[失败] 未识别到任何文字")
        return 1

    print("\n" + "=" * 50)
    print("  自测通过 ✅")
    print("  请双击 start.bat 启动 OCR 服务")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
