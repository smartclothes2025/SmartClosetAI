@echo off
REM 建立 register_service 及 ai_service 兩個資料夾與虛擬環境

REM 建立 register_service
mkdir register_service
cd register_service
python -m venv venv
call .\venv\Scripts\activate.bat
pip install firebase-admin
cd ..

REM 建立 ai_service
mkdir ai_service
cd ai_service
python -m venv venv
call .\venv\Scripts\activate.bat
pip install openai httpx==0.24.1
cd ..

echo 完成兩個服務資料夾與虛擬環境建立！
pause
