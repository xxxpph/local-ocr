# -*- coding: utf-8 -*-
"""OCR 引擎封装。

职责:
1. 按配置选择 ONNX Runtime provider（GPU 优先，失败自动降级 CPU）
2. Windows 下预加载 pip 安装的 nvidia DLL（onnxruntime-gpu[cuda,cudnn]）
3. 校验"声称用了 GPU"是否属实（ORT 可能静默回退 CPU）
4. 启动 warmup，避免首个请求卡顿
5. 线程安全（单实例 + 锁）

验证依据: docs/M0_verification.md
"""
import ctypes
import glob
import itertools
import logging
import os
import sys
import threading
import time
from pathlib import Path

import numpy as np
from PIL import Image
from pydantic import PydanticUserError

from .config import DEFAULT_MODEL_SET, MODEL_SETS, Config

log = logging.getLogger("ocr.engine")

# ONNX Runtime GPU 配方（M0 实测得出，勿随意改动）
GPU_ENGINE_CONFIG = {
    "providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
    "provider_options": [
        # HEURISTIC 绕开 cuDNN 9 对 DEFAULT(IMPLICIT_PRECOMP_GEMM) 的拒绝，
        # 否则 Conv 图构建失败会静默回退 CPU（PaddleOCR#17970 同类问题）
        {"device_id": 0, "cudnn_conv_algo_search": "HEURISTIC"},
        {},
    ],
}


def preload_gpu_dlls() -> None:
    """Windows 下预加载 nvidia pip 包中的 CUDA/cuDNN DLL（幂等）。"""
    if os.name != "nt":
        return
    import onnxruntime as ort

    ort.preload_dlls()
    # ORT 的 preload 清单缺 nvrtc/curand，手动补齐避免 cublas 告警
    site_packages = Path(sys.prefix) / "Lib" / "site-packages"
    for dll_rel in (
        "nvidia/cuda_nvrtc/bin/nvrtc64_120_0.dll",
        "nvidia/curand/bin/curand64_10.dll",
    ):
        dll_path = site_packages / dll_rel
        if dll_path.is_file():
            try:
                ctypes.CDLL(str(dll_path))
            except OSError as exc:
                log.warning("预加载 %s 失败: %s", dll_rel, exc)
    # 兜底: 把 nvidia bin 目录注册进 DLL 搜索路径
    for dll_dir in glob.glob(str(site_packages / "nvidia" / "*" / "bin")):
        try:
            os.add_dll_directory(dll_dir)
        except OSError:
            pass


def _iter_ort_sessions(obj, seen=None):
    """遍历 PaddleX 对象图，找出所有 onnxruntime InferenceSession。

    注意: 对象图中存在 pydantic mock 占位对象，其 __getattr__ 对任何
    属性访问都会抛 PydanticUserError（非 AttributeError，hasattr 无法
    吞掉），因此用 try/except 保护而不是 hasattr 探测。
    """
    if seen is None:
        seen = set()
    if id(obj) in seen:
        return
    seen.add(id(obj))
    if obj.__class__.__name__ == "InferenceSession":
        yield obj
        return
    if isinstance(obj, (list, tuple, set)):
        for item in obj:
            yield from _iter_ort_sessions(item, seen)
    elif isinstance(obj, dict):
        for value in obj.values():
            yield from _iter_ort_sessions(value, seen)
    else:
        try:
            # 快照后迭代：pydantic 懒加载模型会在首次属性访问时扩充 __dict__，
            # 边迭代边变会抛 RuntimeError: dictionary changed size during iteration
            items = list(vars(obj).values())
        except (TypeError, PydanticUserError):
            return
        for value in items:
            yield from _iter_ort_sessions(value, seen)


class OCREngine:
    """OCR 推理引擎（PaddleOCR 3.7 + ONNX Runtime）。"""

    def __init__(self, config: Config):
        self.config = config
        self.provider = "CPUExecutionProvider"
        self.gpu_fail_reason = ""
        self.engine_type = "onnxruntime"
        self._paddleocr = None
        self._lock = threading.Lock()
        self._init_engine()

    # ---------- 初始化 ----------

    def _init_engine(self) -> None:
        from paddleocr import PaddleOCR

        base_args = dict(
            lang="ch",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            engine="onnxruntime",
        )
        model_args = self._resolve_model_args()

        if self.config.use_gpu:
            try:
                preload_gpu_dlls()
                self._paddleocr = PaddleOCR(
                    **base_args, engine_config=GPU_ENGINE_CONFIG, **model_args
                )
                active = self._active_providers()
                if "CUDAExecutionProvider" in active:
                    self.provider = "CUDAExecutionProvider"
                    log.info("GPU 引擎就绪, provider=%s", active)
                else:
                    # ORT 静默回退了 CPU（如 cuDNN 版本不匹配），如实记录并重建
                    self.gpu_fail_reason = (
                        f"CUDAExecutionProvider 未实际生效 (会话 providers={active})"
                    )
                    log.warning("GPU 未实际生效: %s", self.gpu_fail_reason)
                    self._paddleocr = PaddleOCR(**base_args, **model_args)
            except Exception as exc:  # noqa: BLE001 - 任何失败都降级 CPU
                self.gpu_fail_reason = f"{type(exc).__name__}: {exc}"
                log.warning("GPU 初始化失败，降级 CPU: %s", self.gpu_fail_reason)
                self._paddleocr = PaddleOCR(**base_args, **model_args)
        else:
            self._paddleocr = PaddleOCR(**base_args, **model_args)
            log.info("按配置使用 CPU 引擎")

        self._warmup()

    def _resolve_model_args(self) -> dict:
        """优先使用发布包内置模型目录；缺失则退回官方模型名（首次联网下载）。

        本地模式必须同时传 model_name 与 model_dir：PaddleX 会用 model_name
        校验目录内 inference.yml 的 Global.model_name，只传目录时会用默认档位
        名（v6）比对，v5 档位会报 Model name mismatch。
        """
        det_dir = self.config.model_dir("det")
        rec_dir = self.config.model_dir("rec")
        if det_dir.is_dir() and rec_dir.is_dir():
            log.info("使用内置模型: %s / %s", det_dir.name, rec_dir.name)
            return {
                **self.config.model_names(),
                "text_detection_model_dir": str(det_dir),
                "text_recognition_model_dir": str(rec_dir),
            }
        log.warning(
            "未找到内置模型目录 %s，退回官方模型（首次运行需联网下载）",
            det_dir.parent,
        )
        return self.config.model_names()

    def _active_providers(self) -> list:
        """返回当前所有 ORT 会话实际使用的 provider 列表。"""
        providers = set()
        for session in _iter_ort_sessions(self._paddleocr):
            providers.update(session.get_providers())
        return sorted(providers)

    def _warmup(self) -> None:
        """用一张小图预热，避免首个请求承担 cuDNN 引擎构建耗时。"""
        from PIL import ImageDraw, ImageFont

        img = Image.new("RGB", (320, 100), "white")
        draw = ImageDraw.Draw(img)
        for font_path in (
            r"C:\Windows\Fonts\msyh.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        ):
            if os.path.exists(font_path):
                draw.text(
                    (10, 30), "Hello OCR 123", fill="black",
                    font=ImageFont.truetype(font_path, 32),
                )
                break
        else:
            draw.text((10, 30), "Hello OCR 123", fill="black")
        t0 = time.time()
        self.predict(np.array(img))
        log.info("warmup 完成 (%.2fs)", time.time() - t0)

    # ---------- 推理 ----------

    def predict(self, image) -> dict:
        """识别单张图片。

        入参: ndarray(RGB) / PIL.Image / 文件路径 / 字节流
        返回: {text, results:[{text, score, box}], time_ms, provider}
        """
        arr = self._to_ndarray(image)
        with self._lock:
            t0 = time.time()
            pages = self._paddleocr.predict(arr)
            elapsed_ms = round((time.time() - t0) * 1000, 1)

        # 合并多页结果（v1 通常单页）
        results = []
        text_lines = []
        for page in pages:
            d = page.json
            if isinstance(d, dict) and "res" in d:
                d = d["res"]
            for text, score, poly in zip(
                d.get("rec_texts", []),
                d.get("rec_scores", []),
                d.get("rec_polys", d.get("dt_polys", [])),
            ):
                box = [[round(float(v), 1) for v in pt] for pt in poly]
                results.append({"text": text, "score": round(float(score), 4), "box": box})
                text_lines.append(text)

        return {
            "text": "\n".join(text_lines),
            "results": results,
            "time_ms": elapsed_ms,
            "provider": self.provider,
        }

    @staticmethod
    def _to_ndarray(image) -> np.ndarray:
        if isinstance(image, np.ndarray):
            return image
        if isinstance(image, Image.Image):
            return np.array(image.convert("RGB"))
        if isinstance(image, (str, os.PathLike, bytes, bytearray)):
            if isinstance(image, bytes):
                img = Image.open(__import__("io").BytesIO(image))
            else:
                img = Image.open(image)
            return np.array(img.convert("RGB"))
        raise TypeError(f"不支持的图片类型: {type(image)}")

    # ---------- 状态 ----------

    def health(self) -> dict:
        return {
            "status": "ok",
            "engine": self.engine_type,
            "provider": self.provider,
            "gpu_fail_reason": self.gpu_fail_reason or None,
            "model_set": self.config.model_set,
            "use_gpu_expected": self.config.use_gpu,
            "version": "1.0.0",
        }


class OCREngineManager:
    """多档位、多副本引擎管理。

    - model_set 白名单懒加载：首次请求某档位时才创建该档引擎
    - 每档位 engine_replicas 个独立副本（默认 1 = 串行；>1 可并行）
      —— 副本间零共享状态（独立 pipeline / ORT session / 锁），并行安全
    - 副本创建失败（如显存不足）自动减半回退，保证服务可用
    - 轮询分发
    """

    def __init__(self, config: Config):
        self._default_set = config.model_set if config.model_set in MODEL_SETS else DEFAULT_MODEL_SET
        self._use_gpu = config.use_gpu
        self._replicas = max(1, int(config.engine_replicas or 1))
        self._pools: dict = {}          # model_set -> [OCREngine, ...]
        self._counters: dict = {}       # model_set -> itertools.count()
        self._lock = threading.Lock()
        # 启动即加载默认档（保持"开箱即用"，首次请求不等待）
        self._ensure_pool(self._default_set)

    def _ensure_pool(self, model_set: str) -> list:
        """返回某档位的副本池；不存在则创建（双重检查锁，并发安全）。"""
        if model_set not in MODEL_SETS:
            raise ValueError(
                f"未知模型档位: {model_set}（可选: {', '.join(MODEL_SETS)}）"
            )
        with self._lock:
            pool = self._pools.get(model_set)
            if pool:
                return pool
            pool = self._build_pool(model_set)
            self._pools[model_set] = pool
            self._counters[model_set] = itertools.count()
            log.info("模型档位 %s 就绪: %d 个副本", model_set, len(pool))
            return pool

    def _build_pool(self, model_set: str) -> list:
        """按目标副本数逐个创建；失败则减半回退重试。"""
        target = self._replicas
        last_exc = None
        while target >= 1:
            pool = []
            for _ in range(target):
                try:
                    pool.append(OCREngine(Config(model_set=model_set, use_gpu=self._use_gpu)))
                except Exception as exc:  # noqa: BLE001 - 显存不足等均回退
                    last_exc = exc
                    log.warning("副本创建失败，副本数 %d -> %d: %s", target, target // 2, exc)
                    break
            else:
                return pool
            target //= 2
        raise RuntimeError(
            f"模型档位 {model_set} 的所有副本创建失败: {last_exc}"
        )

    def get(self, model_set: str | None = None) -> OCREngine:
        """取一个可用引擎（轮询分发）。model_set 为 None 时用默认档。"""
        ms = model_set or self._default_set
        pool = self._ensure_pool(ms)
        return pool[next(self._counters[ms]) % len(pool)]

    def health(self) -> dict:
        loaded = {}
        for ms, pool in self._pools.items():
            loaded[ms] = {
                "replicas": len(pool),
                "providers": [e.provider for e in pool],
                "gpu_fail_reason": next(
                    (e.gpu_fail_reason for e in pool if e.gpu_fail_reason), None
                ),
            }
        return {
            "status": "ok",
            "engine": "onnxruntime",
            "default_model_set": self._default_set,
            "model_sets": loaded,
            "engine_replicas": self._replicas,
            "use_gpu_expected": self._use_gpu,
            "version": "1.0.0",
        }
