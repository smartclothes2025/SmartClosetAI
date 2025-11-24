"""
使用 Hugging Face Hub 下載 inswapper 模型（最可靠的方式）
"""
import os
from pathlib import Path

def main():
    try:
        from huggingface_hub import hf_hub_download
        print("Hugging Face Hub 已安裝")
    except ImportError:
        print("正在安裝 huggingface_hub...")
        os.system("pip install huggingface_hub")
        from huggingface_hub import hf_hub_download
    
    print("\n" + "="*60)
    print("使用 Hugging Face Hub 下載 inswapper_128.onnx")
    print("="*60)
    
    # 目標路徑
    model_dir = Path.home() / '.insightface' / 'models'
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / 'inswapper_128.onnx'
    
    print(f"目標路徑: {model_path}")
    
    if model_path.exists():
        size_mb = model_path.stat().st_size / (1024*1024)
        if size_mb > 100:
            print(f"模型已存在且大小正常: {size_mb:.2f} MB")
            return
        else:
            print(f"刪除損壞的文件...")
            model_path.unlink()
    
    try:
        print("\n開始下載...")
        print("（這可能需要幾分鐘，文件約 550 MB）")
        
        # 使用 hf_hub_download 下載
        downloaded_path = hf_hub_download(
            repo_id="deepinsight/inswapper",
            filename="inswapper_128.onnx",
            cache_dir=str(model_dir.parent),
            local_dir=str(model_dir),
            local_dir_use_symlinks=False
        )
        
        print(f"\n下載完成！")
        print(f"文件位置: {downloaded_path}")
        
        # 如果不在目標位置，複製過去
        if Path(downloaded_path) != model_path:
            import shutil
            shutil.copy2(downloaded_path, model_path)
            print(f"已複製到: {model_path}")
        
        # 驗證
        size_mb = model_path.stat().st_size / (1024*1024)
        print(f"文件大小: {size_mb:.2f} MB")
        
        if size_mb > 100:
            print("\n" + "="*60)
            print("成功！模型已就緒")
            print("="*60)
            print("\n請重啟後端服務：")
            print("1. 停止當前後端（Ctrl+C）")
            print("2. 重新運行：python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload")
        else:
            print(f"\n警告：文件大小異常 ({size_mb:.2f} MB)")
            
    except Exception as e:
        print(f"\n錯誤：{e}")
        print("\n請嘗試手動下載：")
        print("1. 訪問：https://huggingface.co/deepinsight/inswapper/tree/main")
        print("2. 點擊 inswapper_128.onnx")
        print("3. 點擊下載按鈕")
        print(f"4. 下載後移動到：{model_path}")

if __name__ == "__main__":
    main()
