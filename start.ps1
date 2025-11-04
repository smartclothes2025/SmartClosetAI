# Smart Clothes 一鍵啟動腳本
# 自動啟動後端服務

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   Smart Clothes 後端啟動腳本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 設定工作目錄
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# 檢查 Python
Write-Host "[檢查] Python 環境..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "  ✓ $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Python 未安裝或不在 PATH 中" -ForegroundColor Red
    Write-Host "  請先安裝 Python 3.8 或更高版本" -ForegroundColor Yellow
    pause
    exit
}

# 檢查虛擬環境
Write-Host "[檢查] 虛擬環境..." -ForegroundColor Yellow
if (Test-Path "venv") {
    Write-Host "  ✓ 虛擬環境已存在" -ForegroundColor Green
} else {
    Write-Host "  ! 虛擬環境不存在，正在創建..." -ForegroundColor Yellow
    python -m venv venv
    Write-Host "  ✓ 虛擬環境已創建" -ForegroundColor Green
}

# 啟動虛擬環境
Write-Host "[啟動] 虛擬環境..." -ForegroundColor Yellow
& ".\venv\Scripts\Activate.ps1"
Write-Host "  ✓ 虛擬環境已啟動" -ForegroundColor Green
Write-Host ""

# 檢查依賴
Write-Host "[檢查] 依賴套件..." -ForegroundColor Yellow
$hasFastapi = pip list 2>$null | Select-String "fastapi"
if (-not $hasFastapi) {
    Write-Host "  ! 正在安裝依賴套件..." -ForegroundColor Yellow
    pip install -r requirements.txt -q
    Write-Host "  ✓ 依賴套件已安裝" -ForegroundColor Green
} else {
    Write-Host "  ✓ 依賴套件已安裝" -ForegroundColor Green
}
Write-Host ""

# 檢查 uploads 資料夾
Write-Host "[檢查] 資料夾結構..." -ForegroundColor Yellow
if (-not (Test-Path "uploads")) {
    New-Item -ItemType Directory -Path "uploads" -Force | Out-Null
    Write-Host "  ✓ 已創建 uploads 資料夾" -ForegroundColor Green
} else {
    Write-Host "  ✓ uploads 資料夾已存在" -ForegroundColor Green
}
Write-Host ""

# 顯示環境資訊
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   環境資訊" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "後端地址: http://localhost:8000" -ForegroundColor White
Write-Host "API 文檔: http://localhost:8000/docs" -ForegroundColor White
Write-Host "前端地址: http://localhost:5173" -ForegroundColor White
Write-Host ""
Write-Host "按 Ctrl+C 停止服務" -ForegroundColor Gray
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 啟動後端
Write-Host "[啟動] 後端服務..." -ForegroundColor Green
Write-Host ""
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
