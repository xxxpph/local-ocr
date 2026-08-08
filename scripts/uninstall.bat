@echo off
rem OCR 一键部署 - 卸载入口 (ASCII only, 中文内容在 uninstall.ps1)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1"
