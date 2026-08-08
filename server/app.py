# -*- coding: utf-8 -*-
"""OCR HTTP 服务（FastAPI）。

接口:
    GET  /            网页上传界面
    GET  /health      服务与引擎状态
    POST /ocr         图片文件识别 (multipart)
    POST /ocr_base64  base64 图片识别 (JSON)

仅绑定 127.0.0.1，供本机使用。
"""
import asyncio
import base64
import io
import logging
import time
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .config import PROJECT_ROOT, load_config
from .engine import OCREngineManager

STATIC_DIR = Path(__file__).resolve().parent / "static"
LOG_DIR = PROJECT_ROOT / "logs"


def setup_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # 控制台
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)
    # 滚动文件
    file_handler = RotatingFileHandler(
        LOG_DIR / "server.log", maxBytes=5 * 1024 * 1024, backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    log = logging.getLogger("ocr.app")

    config = load_config()
    app.state.config = config
    log.info("启动引擎: model_set=%s use_gpu=%s replicas=%s port=%s",
             config.model_set, config.use_gpu, config.engine_replicas, config.port)
    t0 = time.time()
    app.state.engine = OCREngineManager(config)
    log.info("引擎就绪 (%.1fs), %s", time.time() - t0, app.state.engine.health()["model_sets"])
    yield
    log.info("服务关闭")


app = FastAPI(
    title="OCR 一键服务",
    description="PaddleOCR 3.7 + ONNX Runtime 本地 OCR 服务",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health():
    return {
        **app.state.engine.health(),
        "port": app.state.config.port,
        "host": app.state.config.host,
    }


@app.post("/ocr")
async def ocr(file: UploadFile = File(...), model_set: str | None = Form(None)):
    log = logging.getLogger("ocr.app")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="上传的图片为空")
    try:
        engine = app.state.engine.get(model_set)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        t0 = time.time()
        result = await asyncio.to_thread(engine.predict, data)
        log.info("OCR 完成: filename=%s model_set=%s time_ms=%s provider=%s lines=%s",
                 file.filename, engine.config.model_set, result["time_ms"],
                 result["provider"], len(result["results"]))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("OCR 请求失败: filename=%s", file.filename)
        if exc.__class__.__name__ == "UnidentifiedImageError":
            raise HTTPException(status_code=400,
                                detail="不是有效的图片文件，请上传 PNG/JPG/BMP 等图片格式") from exc
        raise HTTPException(status_code=500, detail=f"识别失败: {exc}") from exc
    result["filename"] = file.filename
    result["model_set"] = engine.config.model_set
    return result


class OCRBase64Request(BaseModel):
    image_base64: str
    model_set: str | None = None


@app.post("/ocr_base64")
async def ocr_base64(req: OCRBase64Request):
    log = logging.getLogger("ocr.app")
    try:
        data = base64.b64decode(req.image_base64)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="base64 解码失败") from exc
    try:
        engine = app.state.engine.get(req.model_set)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        t0 = time.time()
        result = await asyncio.to_thread(engine.predict, data)
        log.info("OCR 完成(base64): model_set=%s time_ms=%s provider=%s lines=%s",
                 engine.config.model_set, result["time_ms"],
                 result["provider"], len(result["results"]))
        result["model_set"] = engine.config.model_set
        return result
    except Exception as exc:  # noqa: BLE001
        log.exception("OCR 请求失败(base64)")
        if exc.__class__.__name__ == "UnidentifiedImageError":
            raise HTTPException(status_code=400,
                                detail="不是有效的图片文件，请上传 PNG/JPG/BMP 等图片格式") from exc
        raise HTTPException(status_code=500, detail=f"识别失败: {exc}") from exc
