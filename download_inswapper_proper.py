"""
正確下載 InsightFace inswapper_128.onnx 模型
使用 Hugging Face 的直接下載連結
"""
import os
from pathlib import Path
import requests
from tqdm import tqdm

def download_file_with_progress(url, destination):
    """下載文件並顯示進度條"""
    print(f"正在從 {url} 下載...")
    print(f"目標位置: {destination}")
    
    # 使用 stream=True 來處理大文件
    response = requests.get(url, stream=True, allow_redirects=True, timeout=30)
    response.raise_for_status()
    
    # 獲取文件大小
    total_size = int(response.headers.get('content-length', 0))
    print(f"文件大小: {total_size / (1024*1024):.2f} MB")
    
    # 下載文件
    with open(destination, 'wb') as file, tqdm(
        desc="下載進度",
        total=total_size,
        unit='B',
        unit_scale=True,
        unit_divisor=1024,
    ) as bar:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                file.write(chunk)
                bar.update(len(chunk))
    
    print(f"下載完成！文件大小: {destination.stat().st_size / (1024*1024):.2f} MB")

def main():
    # 設定模型路徑
    model_dir = Path.home() / '.insightface' / 'models'
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / 'inswapper_128.onnx'
    
    print("="*60)
    print("InsightFace 臉部交換模型下載器")
    print("="*60)
    
    if model_path.exists():
        size_mb = model_path.stat().st_size / (1024*1024)
        if size_mb > 100:  # 正常模型應該 > 100 MB
            print(f"模型已存在且大小正常: {size_mb:.2f} MB")
            return
        else:
            print(f"偵測到損壞的模型文件 ({size_mb:.2f} MB)，將重新下載")
            model_path.unlink()
    
    # Hugging Face 直接下載連結
    # 注意：這個 URL 會自動重定向到 CDN
    url = "https://huggingface.co/deepinsight/inswapper/resolve/main/inswapper_128.onnx"
    
    try:
        download_file_with_progress(url, model_path)
        
        # 驗證文件大小
        size_mb = model_path.stat().st_size / (1024*1024)
        if size_mb < 100:
            print(f"警告：下載的文件過小 ({size_mb:.2f} MB)，可能下載失敗")
            print("請嘗試手動下載：")
            print(f"1. 訪問：{url}")
            print(f"2. 下載完成後，複製到：{model_path}")
            return False
        
        print("\n" + "="*60)
        print("成功！模型已就緒")
        print("="*60)
        print(f"模型路徑: {model_path}")
        print(f"文件大小: {size_mb:.2f} MB")
        print("\n請重啟後端服務以使用臉部交換功能")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"\n下載失敗: {e}")
        print("\n請嘗試手動下載：")
        print(f"1. 訪問：https://huggingface.co/deepinsight/inswapper/tree/main")
        print(f"2. 點擊 inswapper_128.onnx")
        print(f"3. 點擊右側的下載按鈕")
        print(f"4. 下載完成後，複製到：{model_path}")
        return False

if __name__ == "__main__":
    main()
