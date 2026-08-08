@echo off
rem OCR 一键部署 - 启动入口 (ASCII only, 中文内容在 start.ps1)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
