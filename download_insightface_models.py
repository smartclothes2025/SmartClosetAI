"""
下載 InsightFace 模型檔案
"""
import os
from pathlib import Path

print("="*60)
print("下載 InsightFace 模型...")
print("="*60)
print()

# 設定模型路徑
model_dir = Path.home() / '.insightface' / 'models' / 'buffalo_l'
model_dir.mkdir(parents=True, exist_ok=True)

print(f"模型目錄: {model_dir}")
print()

# 使用 insightface 內建的下載功能
try:
    print("正在下載模型檔案...")
    print("這可能需要幾分鐘，請耐心等待...")
    print()
    
    from insightface.app import FaceAnalysis
    
    # 這會自動下載 buffalo_l 模型
    app = FaceAnalysis(name='buffalo_l')
    app.prepare(ctx_id=0, det_size=(640, 640))
    
    print()
    print("="*60)
    print("[SUCCESS] 模型下載完成！")
    print("="*60)
    print()
    print(f"模型位置: {model_dir}")
    print()
    print("現在可以使用臉部交換功能了！")
    
except Exception as e:
    print()
    print("="*60)
    print(f"[ERROR] 下載失敗: {e}")
    print("="*60)
    print()
    print("請嘗試手動下載：")
    print("1. 訪問: https://github.com/deepinsight/insightface/releases")
    print("2. 下載 buffalo_l.zip")
    print(f"3. 解壓縮到: {model_dir}")
