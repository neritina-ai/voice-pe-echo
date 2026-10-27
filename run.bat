@echo off
rem Start voice-pe-echo (Windows). The first run creates .venv and installs the
rem dependencies; later runs reinstall only when pyproject.toml changed.
rem Any arguments are passed through, e.g.: run.bat --host 192.168.1.50
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo 第一次執行：建立 Python 虛擬環境（.venv）...
    py -3 -m venv .venv 2>nul || python -m venv .venv || goto :nopython
)
fc /b pyproject.toml .venv\pyproject.installed >nul 2>&1
if errorlevel 1 (
    echo 安裝／更新相依套件...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
    ".venv\Scripts\python.exe" -m pip install -e . || goto :failed
    copy /y pyproject.toml .venv\pyproject.installed >nul
)
".venv\Scripts\python.exe" -m voice_pe_echo %*
exit /b %errorlevel%

:nopython
echo 找不到 Python。請到 https://www.python.org/downloads/ 安裝 Python 3.12 以上版本，
echo 安裝時勾選「Add python.exe to PATH」，然後再執行一次 run.bat。
pause
exit /b 1

:failed
echo 套件安裝失敗，請檢查網路連線後再試一次。
pause
exit /b 1
