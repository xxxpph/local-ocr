# -*- coding: utf-8 -*-
"""生成 OCR 自测样例图（中英文混合，白底黑字）。

用法:
    python tools/make_sample_image.py [输出目录]

输出:
    <输出目录>/sample1.png   多行中英文文本
    <输出目录>/sample2.png   单行数字
"""
import os
import sys
from PIL import Image, ImageDraw, ImageFont

# Windows 自带微软雅黑，Linux/macOS 需自行指定字体路径
_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",      # Windows 微软雅黑
    r"C:\Windows\Fonts\simhei.ttf",    # Windows 黑体
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",  # Linux 文泉驿
]

_SAMPLES = [
    {
        "name": "sample1.png",
        "lines": [
            "你好，世界！Hello OCR World",
            "订单号: 20260808-001 金额: ¥128.50",
            "PaddleOCR 3.7 + ONNX Runtime",
        ],
        "font_size": 36,
    },
    {
        "name": "sample2.png",
        "lines": [
            "1234567890 0987654321",
        ],
        "font_size": 48,
    },
]


def _find_font():
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    raise FileNotFoundError(
        "未找到中文字体，请修改 _FONT_CANDIDATES 指定字体文件路径"
    )


def _make_image(lines, font_size, font_path):
    font = ImageFont.truetype(font_path, font_size)
    line_height = int(font_size * 1.6)
    width = max(font.getbbox(line)[2] for line in lines) + font_size * 2
    height = line_height * len(lines) + font_size
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        y = font_size // 2 + i * line_height
        draw.text((font_size // 2, y), line, fill="black", font=font)
    return img


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "sample_data")
    os.makedirs(out_dir, exist_ok=True)
    font_path = _find_font()
    for sample in _SAMPLES:
        img = _make_image(sample["lines"], sample["font_size"], font_path)
        out_path = os.path.join(out_dir, sample["name"])
        img.save(out_path)
        print(f"已生成: {out_path} ({img.width}x{img.height})")
    return out_dir


if __name__ == "__main__":
    main()
