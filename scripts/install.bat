@echo off
rem OCR 一键部署 - 安装入口 (ASCII only, 中文内容在 install.ps1)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
