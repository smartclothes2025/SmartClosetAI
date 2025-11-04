# 重新啟動後端
Write-Host "正在重新啟動後端..." -ForegroundColor Green

# 找到並停止現有的 python start_server.py 進程
$pythonProcesses = Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*start_server.py*" }
if ($pythonProcesses) {
    Write-Host "停止現有後端進程..." -ForegroundColor Yellow
    $pythonProcesses | Stop-Process -Force
    Start-Sleep -Seconds 2
}

# 啟動新的後端
Write-Host "啟動新後端..." -ForegroundColor Green
python start_server.py 2>&1 | Tee-Object -FilePath "upload_debug.log"
