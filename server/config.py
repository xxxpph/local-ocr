# -*- coding: utf-8 -*-
"""配置管理：端口、模型档位、路径。

配置来源优先级: config.json（install.bat 生成）> 环境变量 > 默认值。
"""
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = PROJECT_ROOT / "config.json"
DEFAULT_PORT = 8866

# 模型档位 -> 子目录名（目录内容: inference.onnx / inference.yml / inference.json）
MODEL_SETS = {
    "v6-medium": {
        "det": "PP-OCRv6_medium_det_onnx",
        "rec": "PP-OCRv6_medium_rec_onnx",
    },
    "v5-mobile": {
        "det": "PP-OCRv5_mobile_det_onnx",
        "rec": "PP-OCRv5_mobile_rec_onnx",
    },
}
DEFAULT_MODEL_SET = "v6-medium"


@dataclass
class Config:
    host: str = "127.0.0.1"
    port: int = DEFAULT_PORT
    model_set: str = DEFAULT_MODEL_SET
    use_gpu: bool = True  # 期望值；实际生效 provider 以 engine 运行结果为准
    engine_replicas: int = 1  # 每档位的引擎副本数（>1 可并行，显存×N，默认 1）

    @property
    def models_root(self) -> Path:
        return PROJECT_ROOT / "models" / "onnx"

    def model_dir(self, kind: str) -> Path:
        """返回 det/rec 模型的本地目录（发布包内置）。"""
        set_conf = MODEL_SETS.get(self.model_set) or MODEL_SETS[DEFAULT_MODEL_SET]
        return self.models_root / self.model_set / set_conf[kind]

    def model_names(self) -> dict:
        """返回官方模型名（本地模型缺失时的联网兜底；本地模式也需显式传名，
        否则 PaddleX 会用默认档位名校验 yml 导致 v5 档位不匹配）。"""
        if self.model_set == "v5-mobile":
            return {
                "text_detection_model_name": "PP-OCRv5_mobile_det",
                "text_recognition_model_name": "PP-OCRv5_mobile_rec",
            }
        return {
            "text_detection_model_name": "PP-OCRv6_medium_det",
            "text_recognition_model_name": "PP-OCRv6_medium_rec",
        }


def load_config() -> Config:
    """读取 config.json（不存在则用默认值）。"""
    cfg = Config()
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            for key in asdict(cfg):
                if key in data:
                    setattr(cfg, key, data[key])
        except (json.JSONDecodeError, OSError) as exc:
            # 配置损坏不阻断启动，回退默认值
            print(f"[警告] config.json 解析失败，使用默认配置: {exc}")
    cfg.port = int(os.environ.get("OCR_PORT", cfg.port))
    return cfg


def save_config(cfg: Config) -> None:
    """写回 config.json（供 install.bat 生成与 uninstall 清理）。"""
    CONFIG_FILE.write_text(
        json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8"
    )
