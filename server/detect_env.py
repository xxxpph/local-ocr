# -*- coding: utf-8 -*-
"""环境检测：GPU / 驱动 / Python（stdlib-only，安装 venv 前即可运行）。

输出:
- detect_result.json   完整 JSON（供程序消费）
- stdout 打印 KEY=VALUE 行（供 install.bat 逐行解析消费）

用法:
    python server/detect_env.py
"""
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

# 任意环境（含双击场景的 cmd/PowerShell 管道）下中文输出安全，
# 避免 stdout 编码为 cp1252 等时 print 中文抛 UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULT_FILE = PROJECT_ROOT / "detect_result.json"

# CUDA 12.8 (onnxruntime-gpu 1.26.0) 最低驱动版本（Windows）
DRIVER_THRESHOLD = (560, 28)
MIN_PYTHON = (3, 11)


def _run(cmd, timeout=30):
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except (subprocess.TimeoutExpired, OSError):
        return -1, "", ""


def _version_tuple(version_str):
    match = re.match(r"(\d+)\.(\d+)", version_str.strip())
    if not match:
        return None
    return tuple(int(x) for x in match.groups())


# ---------- GPU ----------

def detect_nvidia_smi():
    """优先用 nvidia-smi（驱动存在则必有）。"""
    smi = shutil.which("nvidia-smi")
    if not smi and os.name == "nt":
        fallback = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "nvidia-smi.exe"
        if fallback.exists():
            smi = str(fallback)
    if not smi:
        return None
    rc, out, err = _run([smi, "--query-gpu=name,driver_version,memory.total",
                         "--format=csv,noheader"])
    if rc != 0 or not out:
        return None
    try:
        name, driver, memory = [part.strip() for part in out.splitlines()[0].split(",")]
    except ValueError:
        return None
    return {"name": name, "driver": driver, "memory": memory}


def detect_wmi_video():
    """nvidia-smi 缺失时用 WMI 识别显卡厂商。"""
    if os.name != "nt":
        return []
    rc, out, _ = _run([
        "powershell", "-NoProfile", "-Command",
        "Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name }",
    ])
    return [line.strip() for line in out.splitlines() if line.strip()] if rc == 0 else []


def detect_gpu():
    nvidia = detect_nvidia_smi()
    if nvidia:
        return {"vendor": "nvidia", **nvidia}
    names = detect_wmi_video()
    vendor = "none"
    for name in names:
        upper = name.upper()
        if "NVIDIA" in upper:
            vendor = "nvidia"
            break
        if "AMD" in upper or "RADEON" in upper:
            vendor = "amd"
            break
        if "INTEL" in upper:
            vendor = "intel"
            break
    return {"vendor": vendor, "name": names[0] if names else "未知", "driver": None, "memory": None}


def driver_ok(driver):
    if not driver:
        return False
    ver = _version_tuple(driver)
    if not ver:
        return False
    return ver >= DRIVER_THRESHOLD


# ---------- Python ----------

def _find_python_cmd():
    """按优先级找可用的 Python: py 启动器 → PATH 中的 python → python3。"""
    if os.name == "nt":
        rc, out, _ = _run(["py", "-3.12", "--version"])
        if rc == 0:
            return ["py", "-3.12"], out
        rc, out, _ = _run(["py", "-3", "--version"])
        if rc == 0:
            return ["py", "-3"], out
    for cmd in (["python", "--version"], ["python3", "--version"]):
        rc, out, _ = _run(cmd)
        if rc == 0 and out:
            return cmd, out
    return None, None


def detect_python():
    cmd, version_out = _find_python_cmd()
    if not cmd:
        return {"found": False, "version": None, "cmd": None, "ok": False, "reason": "未检测到 Python"}
    # 去掉 "Python " 前缀
    parts = version_out.split()
    ver_str = parts[1] if parts and parts[0].lower() == "python" else version_out
    ver = _version_tuple(ver_str) if ver_str else None
    # 检查 64 位（OCR 依赖需要）。注意不能带 --version 参数，否则 -c 不执行
    arch = None
    rc, out, _ = _run(cmd[:-1] + ["-c", "import platform; print(platform.machine())"])
    if rc == 0:
        arch = out.strip()
    ok = ver is not None and ver >= MIN_PYTHON and arch == "AMD64"
    return {
        "found": True,
        "version": ver_str,
        "cmd": cmd,
        "ok": ok,
        "arch": arch,
        "reason": "" if ok else "需要 64 位 Python >= 3.11",
    }


# ---------- 决策 ----------

def decide(gpu, python):
    """返回安装决策: gpu / cpu_driver_old / cpu_no_nvidia / install_python。"""
    if not python["ok"]:
        return "install_python"
    if gpu["vendor"] == "nvidia":
        if driver_ok(gpu["driver"]):
            return "gpu"
        return "cpu_driver_old"
    return "cpu_no_nvidia"


def main():
    gpu = detect_gpu()
    python = detect_python()
    decision = decide(gpu, python)

    report = {
        "python": python,
        "gpu": gpu,
        "driver_threshold": ".".join(map(str, DRIVER_THRESHOLD)),
        "decision": decision,
    }
    try:
        RESULT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"WARN=无法写入检测结果文件: {exc}")

    # bat 友好输出（KEY=VALUE）
    lines = [
        f"PYTHON_FOUND={'1' if python['found'] else '0'}",
        f"PYTHON_OK={'1' if python['ok'] else '0'}",
        f"PYTHON_CMD={' '.join(python['cmd']) if python['cmd'] else ''}",
        f"PYTHON_VERSION={python['version'] or ''}",
        f"GPU_VENDOR={gpu['vendor']}",
        f"GPU_NAME={gpu.get('name', '')}",
        f"GPU_DRIVER={gpu.get('driver') or ''}",
        f"DECISION={decision}",
    ]
    print("\n".join(lines))

    # 人类可读报告
    print("\n===== 环境检测报告 =====")
    print(f"Python: {python['version'] or '未检测到'} ({python.get('arch') or '?'}) "
          f"{'' if python['ok'] else '← ' + python['reason']}")
    if gpu["vendor"] == "nvidia":
        print(f"显卡: {gpu['name']} (驱动 {gpu['driver']}, {gpu['memory']})")
        ok = driver_ok(gpu["driver"])
        print(f"驱动版本: {'达标 ✅' if ok else '过旧 ⚠️ (需要 >= ' + '.'.join(map(str, DRIVER_THRESHOLD)) + ')'}")
    elif gpu["vendor"] in ("amd", "intel"):
        print(f"显卡: {gpu['name']} (AMD/Intel，v1 走 CPU，DirectML 支持排期 v1.1)")
    else:
        print("显卡: 未检测到 NVIDIA 显卡")
    decision_text = {
        "gpu": "决策: 安装 GPU 版 (ONNX Runtime CUDA)",
        "cpu_driver_old": "决策: 安装 CPU 版（NVIDIA 驱动过旧，可自行更新驱动后重装获得 GPU 加速）",
        "cpu_no_nvidia": "决策: 安装 CPU 版（无 NVIDIA 显卡）",
        "install_python": "决策: 需要先安装 Python 3.12",
    }[decision]
    print(decision_text)
    print(f"\n检测结果已保存: {RESULT_FILE}")


if __name__ == "__main__":
    main()
