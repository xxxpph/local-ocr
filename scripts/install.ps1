<# OCR 一键部署脚本 #>
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
& chcp.com 65001 | Out-Null

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$log = Join-Path $root 'install.log'
$venvPython = Join-Path $root '.venv\Scripts\python.exe'
$pythonUrl = 'https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe'

function Log([string]$msg) {
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    "[$ts] $msg" | Out-File -FilePath $log -Append -Encoding utf8
    Write-Host $msg
}

function Fail([string]$msg) {
    Log "========== 安装失败 =========="
    Write-Host ""
    Write-Host "  =========================================="
    Write-Host "   安装失败: $msg"
    Write-Host "   详细日志: $log"
    Write-Host "   可截图日志内容反馈给开发者"
    Write-Host "  =========================================="
    exit 1
}

function RunDetect([string]$python) {
    $out = & $python server\detect_env.py 2>&1 | Out-String
    $kv = @{}
    foreach ($line in ($out -split "`r?`n")) {
        if ($line -match '^([A-Z_]+)=(.*)$') {
            $kv[$matches[1]] = $matches[2]
        }
    }
    return $kv
}

function FindPython {
    # 返回 python 可执行文件路径（py 启动器或 PATH）
    try { & py -3.12 -c "import sys; print(sys.executable)" 2>$null | ForEach-Object { if ($_) { return $_.Trim() } } } catch {}
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

Log "========== OCR 一键安装开始 =========="

# ---------- 1. Python ----------
Log "[1/6] 检测 Python 环境..."
$python = FindPython
$kv = @{}
if ($python) { $kv = RunDetect $python }

if ($kv.PYTHON_OK -ne '1') {
    Log "未检测到可用的 64 位 Python 3.11+，开始自动安装 Python 3.12.7..."
    $installer = Join-Path $env:TEMP 'python-3.12.7-amd64.exe'
    Write-Host "  正在下载 Python 3.12.7 (约 25MB)..."
    curl.exe -L -sS -o $installer $pythonUrl
    if ($LASTEXITCODE -ne 0) { Fail "Python 下载失败，请检查网络后重试" }
    Write-Host "  正在静默安装（仅当前用户）..."
    Start-Process -FilePath $installer -ArgumentList '/quiet', 'InstallAllUsers=0', 'PrependPath=0', 'Include_launcher=1', 'Include_pip=1' -Wait
    $python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
    if (-not (Test-Path $python)) { $python = FindPython }
    if (-not $python) { Fail "Python 安装后仍不可用，请手动安装 64 位 Python 3.11+ 后重试" }
    $kv = RunDetect $python
    if ($kv.PYTHON_OK -ne '1') { Fail "Python 安装后仍不可用: $($kv.PYTHON_REASON)" }
    Log "Python 安装完成: $($kv.PYTHON_VERSION)"
} else {
    Log "Python 已就绪: $($kv.PYTHON_VERSION) ($python)"
}

# ---------- 2. 环境检测报告 ----------
Log "[2/6] 环境检测: 显卡=$($kv.GPU_NAME) 驱动=$($kv.GPU_DRIVER) 决策=$($kv.DECISION)"
if ($kv.DECISION -eq 'cpu_driver_old') {
    Write-Host "  [提示] NVIDIA 驱动过旧（需 >= 560.28），将安装 CPU 版。"
    Write-Host "         更新驱动后删除 .venv 重新安装即可启用 GPU 加速。"
    Write-Host "         驱动下载: https://www.nvidia.cn/drivers/"
}

# ---------- 3. 已安装检查 ----------
if (Test-Path $venvPython) {
    if ($env:OCR_SKIP_PROMPT -eq '1') {
        Log "检测到已安装环境，OCR_SKIP_PROMPT=1，自动重装"
    } else {
        try { $answer = Read-Host "检测到已安装过环境，是否重新安装? (Y=重装 N=退出)" } catch { $answer = 'N' }
        if ($answer -notmatch '^[Yy]') { exit 0 }
    }
    Remove-Item -Recurse -Force (Join-Path $root '.venv')
}

# ---------- 4. venv 与依赖 ----------
Log "[3/6] 创建 Python 虚拟环境..."
& $python -m venv (Join-Path $root '.venv')
if ($LASTEXITCODE -ne 0) { Fail "虚拟环境创建失败" }

Log "[4/6] 安装依赖（首次约 3-10 分钟，视网速）..."
& $venvPython -m pip install --upgrade pip --disable-pip-version-check | Out-Null
if ($LASTEXITCODE -ne 0) { Fail "pip 升级失败" }

function Pip([string[]]$argList) {
    & $venvPython -m pip install @argList --disable-pip-version-check --no-warn-script-location
    if ($LASTEXITCODE -ne 0) {
        Log "[重试] pip 默认源失败，切换清华镜像源..."
        & $venvPython -m pip install @argList -i https://pypi.tuna.tsinghua.edu.cn/simple --disable-pip-version-check --no-warn-script-location
    }
    if ($LASTEXITCODE -ne 0) { Fail "依赖安装失败: $($argList -join ' ')" }
}

Pip @('-r', 'requirements.txt')

if ($kv.DECISION -eq 'gpu') {
    Write-Host ""
    Write-Host "  ============================================================"
    Write-Host "   检测到 NVIDIA 显卡，正在安装 GPU 加速版..."
    Write-Host "   需要下载约 2GB 的 CUDA/cuDNN 运行库（仅首次安装需要）"
    Write-Host "  ============================================================"
    Write-Host ""
    Pip @('-r', 'requirements-gpu.txt')
} else {
    Log "安装 CPU 版依赖..."
    Pip @('-r', 'requirements-cpu.txt')
}

# ---------- 5. 配置 ----------
Log "[5/6] 写入配置..."
$useGpu = if ($kv.DECISION -eq 'gpu') { 'True' } else { 'False' }
& $venvPython -c "from server.config import Config, save_config; save_config(Config(use_gpu=$useGpu, model_set='v6-medium'))"
if ($LASTEXITCODE -ne 0) { Fail "配置写入失败" }

# ---------- 6. 自测 ----------
Log "[6/6] 运行自测（首次加载模型约 5-20 秒）..."
& $venvPython scripts\self_test.py
if ($LASTEXITCODE -ne 0) { Fail "自测未通过，详见上方输出" }

Write-Host ""
Write-Host "  ============================================================"
Write-Host "   安装成功! 接下来请双击 start.bat 启动 OCR 服务"
Write-Host "  ============================================================"
Write-Host ""
try { Read-Host "按回车键退出" } catch {}
exit 0
