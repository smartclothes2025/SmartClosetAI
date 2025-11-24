#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
下載 InsightFace 臉部交換所需的模型
"""
import os
import sys
from pathlib import Path
import urllib.request
import zipfile

print("="*60)
print("InsightFace Model Downloader")
print("="*60)

# 設置模型目錄
model_dir = Path.home() / '.insightface' / 'models' / 'buffalo_l'
model_dir.mkdir(parents=True, exist_ok=True)

print(f"\nModel directory: {model_dir}")

# 模型文件 URLs（來自 InsightFace 官方）
models = {
    'det_10g.onnx': 'https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip',
    'w600k_r50.onnx': 'https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip',
}

# Inswapper 模型
inswapper_url = 'https://huggingface.co/deepinsight/inswapper/resolve/main/inswapper_128.onnx'
inswapper_path = Path.home() / '.insightface' / 'models' / 'inswapper_128.onnx'

print("\n[1] Downloading buffalo_l models...")
buffalo_zip = model_dir.parent / 'buffalo_l.zip'

try:
    if not buffalo_zip.exists():
        print(f"     Downloading from GitHub...")
        urllib.request.urlretrieve(
            'https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip',
            buffalo_zip
        )
        print("[OK] Downloaded buffalo_l.zip")
    
    # Extract
    print("     Extracting...")
    with zipfile.ZipFile(buffalo_zip, 'r') as zip_ref:
        zip_ref.extractall(model_dir.parent)
    print("[OK] Extracted buffalo_l models")
    
    # Clean up
    buffalo_zip.unlink()
    
except Exception as e:
    print(f"[ERROR] Failed to download buffalo_l: {e}")
    print("\nManual download instructions:")
    print("1. Visit: https://github.com/deepinsight/insightface/releases/tag/v0.7")
    print("2. Download buffalo_l.zip")
    print(f"3. Extract to: {model_dir.parent}")

print("\n[2] Downloading inswapper_128.onnx...")
try:
    if not inswapper_path.exists():
        print(f"     Downloading from HuggingFace...")
        urllib.request.urlretrieve(inswapper_url, inswapper_path)
        print("[OK] Downloaded inswapper_128.onnx")
    else:
        print("[OK] inswapper_128.onnx already exists")
        
except Exception as e:
    print(f"[ERROR] Failed to download inswapper: {e}")
    print("\nManual download instructions:")
    print("1. Visit: https://huggingface.co/deepinsight/inswapper/tree/main")
    print("2. Download inswapper_128.onnx")
    print(f"3. Save to: {inswapper_path}")

print("\n" + "="*60)
print("Download complete!")
print("="*60)
print("\nNext steps:")
print("1. Restart the backend service")
print("2. Test face swap functionality")
