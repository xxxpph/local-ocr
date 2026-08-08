<# OCR 一键部署脚本 #>
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
& chcp.com 65001 | Out-Null

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$venvPython = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path $venvPython)) {
    Write-Host ""
    Write-Host "  [错误] 尚未安装环境，请先双击运行 install.bat"
    Write-Host ""
    try { Read-Host "按回车键退出" } catch {}
    exit 1
}

# 探测空闲端口（优先 config.json 的端口，占用则自动 +1）
$port = 8866
if (Test-Path (Join-Path $root 'config.json')) {
    $cfg = Get-Content (Join-Path $root 'config.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $port = [int]$cfg.port
}
$script = @"
import socket
for p in range($port, $port + 50):
    s = socket.socket()
    if s.connect_ex(('127.0.0.1', p)) != 0:
        print(p); break
    s.close()
"@
$freePort = (& $venvPython -c $script | Select-Object -First 1).Trim()

Write-Host ""
Write-Host "  ============================================================"
Write-Host "   OCR 服务正在启动..."
Write-Host "   地址: http://127.0.0.1:$freePort/"
Write-Host "   关闭服务窗口即停止"
Write-Host "  ============================================================"
Write-Host ""

$serverCmd = "`"$venvPython`" -m uvicorn server.app:app --host 127.0.0.1 --port $freePort"
Start-Process -FilePath 'cmd.exe' -ArgumentList '/k', $serverCmd -WorkingDirectory $root

# 等待服务就绪后打开浏览器
Start-Sleep -Seconds 8
Start-Process "http://127.0.0.1:$freePort/"
Write-Host "已打开浏览器，若未自动打开请手动访问: http://127.0.0.1:$freePort/"
try { Read-Host "按回车键退出" } catch {}
