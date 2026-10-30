@echo off
cd /d "%~dp0"
title Keo Kenh - YouTube Toolkit
rem Ban mang di (co thu muc python ben canh) dung Python co san; ban thuong dung Python da cai tren may.
set "PY=python"
set "PYW=pythonw"
if exist "%~dp0python\python.exe" set "PY=%~dp0python\python.exe"
if exist "%~dp0python\pythonw.exe" set "PYW=%~dp0python\pythonw.exe"
"%PY%" -c "import playwright, PIL, openpyxl, yaml" 1>nul 2>nul
if not errorlevel 1 goto run
echo ============================================================
echo   Dang chuan bi thu vien cho tool (can mang Internet, 1-3 phut).
echo   KHONG tat cua so nay. Chi lam 1 lan.
echo ============================================================
"%PY%" -m pip install --disable-pip-version-check --no-warn-script-location -q -r "he_thong\requirements.txt"
"%PY%" -c "import playwright, PIL, openpyxl, yaml" 1>nul 2>nul
if errorlevel 1 goto fail
:run
start "" "%PYW%" "he_thong\gui.py"
exit /b 0
:fail
echo.
echo CHUA CHUAN BI XONG THU VIEN.
echo - Kiem tra mang Internet roi mo lai Mo_Tool.bat.
echo - May chua cai Python: dung ban mang di KeoKenh_Portable, hoac cai Python 3.12 (tick Add to PATH).
pause
exit /b 1
