# -*- coding: utf-8 -*-
"""收集官方 ONNX 模型到发布包目录 models/onnx/<档位>/。

维护者使用（需要 paddleocr 依赖环境，模型可来自首次运行自动下载的缓存）:

    python tools/collect_models.py

从 PaddleX 缓存 (~/.paddlex/official_models/) 拷贝官方预转 ONNX 模型到
models/onnx/<set>/<模型目录>/{inference.onnx, inference.yml, inference.json}。
"""
import os
import shutil
import sys
from pathlib import Path

# 任意环境（含 CI）下中文输出安全
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = Path.home() / ".paddlex" / "official_models"
DEST_ROOT = BASE_DIR / "models" / "onnx"

# 档位 -> (官方缓存目录名列表)
SETS = {
    "v6-medium": ["PP-OCRv6_medium_det_onnx", "PP-OCRv6_medium_rec_onnx"],
    "v5-mobile": ["PP-OCRv5_mobile_det_onnx", "PP-OCRv5_mobile_rec_onnx"],
}

# 只拷贝推理必需文件，跳过 .cache 等杂物
KEEP_FILES = ("inference.onnx", "inference.yml", "inference.json")


def collect():
    if not CACHE_DIR.is_dir():
        raise SystemExit(f"未找到 PaddleX 模型缓存: {CACHE_DIR}\n"
                         "请先运行一次 PaddleOCR 让官方模型自动下载。")
    total = 0
    for model_set, dirs in SETS.items():
        dest_set = DEST_ROOT / model_set
        dest_set.mkdir(parents=True, exist_ok=True)
        for name in dirs:
            src = CACHE_DIR / name
            if not src.is_dir():
                print(f"[跳过] 缓存中不存在: {name}")
                continue
            dest = dest_set / name
            dest.mkdir(exist_ok=True)
            for fname in KEEP_FILES:
                src_file = src / fname
                if src_file.is_file():
                    shutil.copy2(src_file, dest / fname)
            size = sum(f.stat().st_size for f in dest.iterdir()) / 1024 / 1024
            print(f"[完成] {model_set}/{name} ({size:.1f} MB)")
            total += 1
    print(f"\n共收集 {total} 个模型到 {DEST_ROOT}")
    return total


if __name__ == "__main__":
    collect()
