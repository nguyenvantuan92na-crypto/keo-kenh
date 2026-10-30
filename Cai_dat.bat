@echo off
cd /d "%~dp0"
title Cai dat thu vien - Keo Kenh
set "PY=python"
if exist "%~dp0python\python.exe" set "PY=%~dp0python\python.exe"
echo Dang cai lai thu vien cho tool - can mang Internet...
"%PY%" -m pip install --disable-pip-version-check --no-warn-script-location -r "he_thong\requirements.txt"
echo.
echo Xong. Nhap dup Mo_Tool.bat de mo tool.
pause
