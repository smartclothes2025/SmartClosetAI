"""
下載 InsightFace inswapper_128.onnx 模型
"""
import os
from pathlib import Path
import requests
from tqdm import tqdm

def download_file(url, destination):
    """下載文件並顯示進度條"""
    response = requests.get(url, stream=True)
    total_size = int(response.headers.get('content-length', 0))
    
    with open(destination, 'wb') as file, tqdm(
        desc=destination.name,
        total=total_size,
        unit='B',
        unit_scale=True,
        unit_divisor=1024,
    ) as bar:
        for data in response.iter_content(chunk_size=1024):
            size = file.write(data)
            bar.update(size)

def main():
    # 設定模型路徑
    model_dir = Path.home() / '.insightface' / 'models'
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / 'inswapper_128.onnx'
    
    print(f"📥 準備下載 inswapper_128.onnx 模型")
    print(f"📁 目標路徑: {model_path}")
    
    if model_path.exists():
        print(f"✅ 模型已存在，無需下載")
        return
    
    # 嘗試多個下載源
    urls = [
        # 主要來源：Hugging Face（需要授權）
        "https://huggingface.co/deepinsight/inswapper/resolve/main/inswapper_128.onnx",
        # 備用來源：GitHub Release（如果有的話）
        # "https://github.com/deepinsight/insightface/releases/download/v0.7/inswapper_128.onnx",
    ]
    
    print("\n⚠️ 注意：此模型需要從 Hugging Face 下載")
    print("📌 請訪問：https://huggingface.co/deepinsight/inswapper")
    print("📌 手動下載 inswapper_128.onnx 到以下路徑：")
    print(f"   {model_path}")
    print("\n或者使用 huggingface-cli 下載：")
    print("   pip install huggingface_hub")
    print("   huggingface-cli download deepinsight/inswapper inswapper_128.onnx --local-dir ~/.insightface/models")
    
    # 嘗試自動下載（可能失敗）
    for url in urls:
        try:
            print(f"\n🔄 嘗試從 {url} 下載...")
            download_file(url, model_path)
            print(f"✅ 模型下載成功！")
            return
        except Exception as e:
            print(f"❌ 下載失敗: {e}")
            if model_path.exists():
                model_path.unlink()
    
    print("\n❌ 自動下載失敗，請手動下載")

if __name__ == "__main__":
    main()
