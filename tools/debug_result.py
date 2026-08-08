# -*- coding: utf-8 -*-
"""M0 调试：打印 PaddleOCR onnxruntime 引擎的原始返回结构。"""
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from paddleocr import PaddleOCR

ocr = PaddleOCR(
    lang="ch",
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
    engine="onnxruntime",
)

img = os.path.join(BASE_DIR, "tools", "sample_data", "sample1.png")
res = ocr.predict(img)

for page in res:
    print("=== page type:", type(page))
    if hasattr(page, "json"):
        print(json.dumps(page.json, ensure_ascii=False, indent=2))
    else:
        print("attrs:", [a for a in dir(page) if not a.startswith("_")])
        print(repr(page)[:2000])
