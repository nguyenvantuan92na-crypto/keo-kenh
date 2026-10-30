@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Cau noi GPM-Login - Keo Kenh
rem Chay tren MAY CO GPM-LOGIN de tool o may khac dung duoc profile GPM cua may nay.
set "PY=python"
if exist "%~dp0python\python.exe" set "PY=%~dp0python\python.exe"
"%PY%" "he_thong\gpm_bridge.py"
pause
