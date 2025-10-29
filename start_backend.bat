@echo off
chcp 65001 >nul
echo ============================================================
echo 正在啟動 SmartClosetAI 後端服務器...
echo ============================================================
echo.

cd /d "%~dp0"

REM 檢查 Python 是否安裝
python --version >nul 2>&1
if errorlevel 1 (
    echo [錯誤] 未找到 Python，請先安裝 Python
    pause
    exit /b 1
)

REM 檢查虛擬環境（如果有的話）
if exist venv\Scripts\activate.bat (
    echo [檢測到虛擬環境] 正在啟動...
    call venv\Scripts\activate.bat
)

REM 啟動服務器
echo [啟動] FastAPI 服務器...
echo.
python start_server.py

pause
