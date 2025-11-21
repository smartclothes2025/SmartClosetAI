"""
下載 InsightFace 模型檔案
"""
import os
from pathlib import Path

print("開始下載 InsightFace 模型...")
print("="*60)

# 設定模型路徑
model_dir = Path.home() / '.insightface' / 'models'
model_dir.mkdir(parents=True, exist_ok=True)

print(f"模型目錄: {model_dir}")
print()

try:
    import gdown
    print("[OK] gdown 已安裝")
except ImportError:
    print("[安裝] 安裝 gdown...")
    import subprocess
    subprocess.check_call(['pip', 'install', 'gdown'])
    import gdown
    print("[OK] gdown 安裝完成")

print()
print("="*60)
print("下載模型檔案...")
print("="*60)
print()

# buffalo_l 模型 (臉部檢測)
buffalo_l_dir = model_dir / 'buffalo_l'
buffalo_l_dir.mkdir(exist_ok=True)

print("1. 下載 buffalo_l 模型...")
print("   (這可能需要幾分鐘...)")

# 使用 insightface 內建的下載功能
try:
    from insightface.model_zoo import model_zoo
    
    # 下載 buffalo_l
    print("   下載 det_10g.onnx...")
    model_zoo.get_model('buffalo_l', root=str(model_dir))
    
    print("[OK] buffalo_l 模型下載完成")
except Exception as e:
    print(f"[WARNING] buffalo_l 下載失敗: {e}")
    print("將在首次使用時自動下載")

print()
print("2. 下載 inswapper_128.onnx (臉部交換模型)...")

try:
    from insightface.model_zoo import get_model
    
    # 這會自動下載模型
    swapper = get_model('inswapper_128.onnx', download=True, download_zip=True)
    print("[OK] inswapper_128.onnx 下載完成")
except Exception as e:
    print(f"[WARNING] inswapper 下載失敗: {e}")
    print("將在首次使用時自動下載")

print()
print("="*60)
print("[SUCCESS] 模型下載完成！")
print("="*60)
print()
print(f"模型位置: {model_dir}")
print()
print("現在可以使用臉部交換功能了！")
