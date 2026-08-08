# -*- coding: utf-8 -*-
"""打发布包 zip（维护者使用）。

用法:
    python tools/make_release.py [--version 1.0.0]

输出:
    dist/local-ocr-v<版本>-win64.zip

内容:
    server/  scripts/  models/onnx/  requirements*.txt  README.md  LICENSE
"""
import argparse
import shutil
import sys
import zipfile
from pathlib import Path

# CI 等环境默认 stdout 可能是 cp1252/GBK，中文 print 会崩（UnicodeEncodeError）
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = BASE_DIR / "dist"

INCLUDE_DIRS = ["server", "scripts"]
INCLUDE_FILES = ["README.md", "LICENSE", "requirements.txt",
                 "requirements-gpu.txt", "requirements-cpu.txt"]
EXCLUDE_PARTS = ("__pycache__", ".pyc")


def build(version: str) -> Path:
    DIST_DIR.mkdir(exist_ok=True)
    # tag 名可能带 v 前缀（如 v1.0.0），zip 名里避免双 v
    version = version.lstrip("v")
    zip_name = f"local-ocr-v{version}-win64.zip"
    zip_path = DIST_DIR / zip_name

    models_root = BASE_DIR / "models" / "onnx"
    if not models_root.is_dir():
        raise SystemExit(
            f"未找到模型目录 {models_root}，请先运行 tools/collect_models.py"
        )

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirname in INCLUDE_DIRS:
            src = BASE_DIR / dirname
            if not src.is_dir():
                raise SystemExit(f"缺少目录: {src}")
            for f in src.rglob("*"):
                if f.is_file() and not any(p in f.parts for p in EXCLUDE_PARTS):
                    zf.write(f, f.relative_to(BASE_DIR))
        for fname in INCLUDE_FILES:
            f = BASE_DIR / fname
            if f.is_file():
                zf.write(f, fname)
        for f in models_root.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(BASE_DIR))

    size_mb = zip_path.stat().st_size / 1024 / 1024
    print(f"发布包已生成: {zip_path} ({size_mb:.1f} MB)")
    return zip_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="1.0.0")
    args = parser.parse_args()
    build(args.version)
