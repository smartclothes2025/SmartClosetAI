"""
修復 InsightFace 模型問題
"""
import os
from pathlib import Path
import urllib.request
import zipfile

print("修復 InsightFace 模型...")
print("="*60)

# 模型目錄
model_dir = Path.home() / '.insightface' / 'models' / 'buffalo_l'
model_dir.mkdir(parents=True, exist_ok=True)

print(f"模型目錄: {model_dir}")
print()

# 需要的模型檔案
models = {
    'det_10g.onnx': 'https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip',
    'w600k_r50.onnx': 'https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip',
}

print("檢查現有檔案...")
for filename in ['det_10g.onnx', 'w600k_r50.onnx', 'genderage.onnx', '2d106det.onnx', '1k3d68.onnx']:
    filepath = model_dir / filename
    if filepath.exists():
        print(f"  [OK] {filename} ({filepath.stat().st_size} bytes)")
    else:
        print(f"  [MISSING] {filename}")

print()
print("="*60)
print("建議：")
print("1. 手動下載 buffalo_l.zip:")
print("   https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip")
print()
print(f"2. 解壓縮到: {model_dir}")
print()
print("3. 或者使用 insightface 內建下載（首次使用時自動）")
print("="*60)
