# 實時監看後端輸出（找上傳相關的日誌）
Write-Host "正在監看後端輸出..." -ForegroundColor Green
Write-Host "請在前端上傳圖片，這裡會顯示後端的即時輸出" -ForegroundColor Yellow
Write-Host "按 Ctrl+C 停止監看" -ForegroundColor Yellow
Write-Host ""
Write-Host "=" * 60

# 找到 Python 進程並監看
$pythonProcess = Get-Process python -ErrorAction SilentlyContinue | Select-Object -First 1

if ($pythonProcess) {
    Write-Host "找到後端進程 PID: $($pythonProcess.Id)" -ForegroundColor Green
    Write-Host ""
} else {
    Write-Host "警告: 找不到正在運行的 Python 進程" -ForegroundColor Red
}

# 監看最近的日誌（需要手動刷新）
Write-Host "開始監看..." -ForegroundColor Cyan
Write-Host ""

while ($true) {
    Start-Sleep -Seconds 2
    
    # 每2秒讀取最新的 20 行並過濾相關內容
    $lines = Get-Content -Path ".\start_server.log" -Tail 20 -ErrorAction SilentlyContinue | 
             Select-String -Pattern "上傳|GCS|配置|成功|警告|ERROR|POST.*clothes" -Context 0,1
    
    if ($lines) {
        foreach ($line in $lines) {
            Write-Host $line -ForegroundColor White
        }
    }
}
