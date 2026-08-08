<# OCR 一键部署脚本 #>
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
& chcp.com 65001 | Out-Null

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host ""
Write-Host "  将删除: .venv (依赖环境), config.json (配置), logs/ (日志)"
Write-Host "  保留:   models/ (模型文件约 155MB，可手动删除)"
Write-Host ""
$answer = Read-Host "确认卸载? (Y=卸载 N=取消)"
if ($answer -notmatch '^[Yy]') { exit 0 }

foreach ($target in @('.venv', 'config.json', 'detect_result.json', 'logs', 'install.log')) {
    $path = Join-Path $root $target
    if (Test-Path $path) { Remove-Item -Recurse -Force $path }
}

Write-Host ""
Write-Host "  已卸载。模型目录 models/ 如需删除请手动操作。"
try { Read-Host "按回车键退出" } catch {}
