# -*- coding: utf-8 -*-
"""M0 技术验证脚本：PaddleOCR 3.7 + ONNX Runtime 全链路。

验证目标（对应计划 M0-5/M0-6）:
1. 无 paddlepaddle 环境下 PaddleOCR(engine="onnxruntime") 能否跑通
2. 模型是否自动下载（官方 PP-OCRv6 medium 默认档）
3. 当前生效的 ONNX Runtime provider（CPU / CUDA）
4. 推理结果正确性与耗时

用法:
    .venv\\Scripts\\python tools\\verify_onnx_pipeline.py [图片路径] [模型档位]

模型档位可选: v6-medium (默认) / v5-mobile
"""
import importlib.util
import json
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


def check_environment():
    """输出关键依赖与 provider 状态。

    注意: 用 importlib.metadata 读版本号而不是 import 模块本身——
    paddle2onnx 2.1.0 在无 paddle 环境下 import 即报错（符合预期，
    用户环境不应装 paddle2onnx）。
    """
    from importlib import metadata
    report = {}
    for name in ("paddleocr", "onnxruntime", "paddlex", "paddle2onnx"):
        try:
            report[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            report[name] = "未安装"
    # paddlepaddle 是否被意外装上（用户侧不应存在）
    report["paddlepaddle"] = (
        "已安装(异常)" if importlib.util.find_spec("paddle") is not None
        else "未安装(符合预期)"
    )
    if importlib.util.find_spec("onnxruntime") is not None:
        import onnxruntime as ort
        report["onnxruntime_providers"] = ort.get_available_providers()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def _resolve_model_args(model_set):
    """把模型档位映射为 PaddleOCR 3.x 的模型参数。

    v6-medium 是 3.7.0 的默认档（不传即默认）；
    v5-mobile 显式指定 PP-OCRv5 mobile 系列。
    """
    if model_set == "v6-medium":
        return {}  # 官方默认 PP-OCRv6_medium
    if model_set == "v5-mobile":
        return {
            "text_detection_model_name": "PP-OCRv5_mobile_det",
            "text_recognition_model_name": "PP-OCRv5_mobile_rec",
        }
    raise ValueError(f"未知模型档位: {model_set}")


def main():
    image_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        BASE_DIR, "tools", "sample_data", "sample1.png")
    model_set = sys.argv[2] if len(sys.argv) > 2 else "v6-medium"
    # 可选: 指定 ONNX Runtime provider, 如 "CUDAExecutionProvider"
    provider = os.environ.get("OCR_PROVIDER")

    check_environment()

    from paddleocr import PaddleOCR

    model_args = _resolve_model_args(model_set)
    print(f"\n[模型档位] {model_set}  参数: {model_args or '(官方默认)'}")

    engine_config = None
    if provider:
        engine_config = {"providers": [provider, "CPUExecutionProvider"]}
        print(f"[provider] {provider}")

    t0 = time.time()
    ocr = PaddleOCR(
        lang="ch",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        engine="onnxruntime",
        engine_config=engine_config,
        **model_args,
    )
    print(f"[引擎创建] 耗时 {time.time() - t0:.1f}s")

    t1 = time.time()
    results = ocr.predict(image_path)
    elapsed = time.time() - t1
    print(f"[推理] 耗时 {elapsed:.2f}s\n")

    for page in results:
        d = page.json
        if isinstance(d, dict) and "res" in d:
            d = d["res"]
        rec_texts = d.get("rec_texts", []) or []
        rec_scores = d.get("rec_scores", []) or []
        print("识别文本:")
        for t, s in zip(rec_texts, rec_scores):
            print(f"  [{s:.3f}] {t}")
        print(f"\n(共 {len(rec_texts)} 行)")


if __name__ == "__main__":
    main()
