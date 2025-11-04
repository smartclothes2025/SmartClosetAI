# 啟動後端並記錄日誌
Write-Host "正在啟動後端伺服器..." -ForegroundColor Green
Write-Host "日誌將儲存到: upload_debug.log" -ForegroundColor Yellow
Write-Host "按 Ctrl+C 停止伺服器" -ForegroundColor Yellow
Write-Host ""

# 啟動後端，同時輸出到終端和檔案
python start_server.py 2>&1 | Tee-Object -FilePath "upload_debug.log"
