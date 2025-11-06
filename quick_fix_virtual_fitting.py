"""
虛擬試衣功能 - 快速診斷和修復工具
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

def check_environment():
    """檢查環境配置"""
    print("\n" + "="*80)
    print("🔍 環境配置檢查")
    print("="*80)
    
    checks = {
        "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY"),
        "GCP_PROJECT_ID": os.getenv("GCP_PROJECT_ID"),
        "GCP_LOCATION": os.getenv("GCP_LOCATION"),
        "GOOGLE_APPLICATION_CREDENTIALS": os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
        "GCS_BUCKET_NAME": os.getenv("GCS_BUCKET_NAME"),
    }
    
    all_ok = True
    
    for key, value in checks.items():
        if value:
            print(f"✅ {key}: 已配置")
            if key == "GEMINI_API_KEY":
                # 檢查是否有錯誤的後綴
                if "USE_GCS" in value or "true" in value:
                    print(f"   ⚠️ 警告: API Key 格式可能錯誤，包含額外字符")
                    print(f"   當前值: {value}")
                    all_ok = False
                else:
                    print(f"   前20字元: {value[:20]}...")
                    
            elif key == "GOOGLE_APPLICATION_CREDENTIALS":
                print(f"   路徑: {value}")
                if os.path.exists(value):
                    print(f"   ✅ 檔案存在")
                else:
                    print(f"   ❌ 檔案不存在!")
                    all_ok = False
                    
        else:
            if key in ["GEMINI_API_KEY", "GCP_PROJECT_ID"]:
                print(f"❌ {key}: 未配置 (必要)")
                all_ok = False
            else:
                print(f"⚠️ {key}: 未配置 (可選)")
    
    return all_ok


def check_api_routes():
    """檢查 API 路由配置"""
    print("\n" + "="*80)
    print("🔍 API 路由檢查")
    print("="*80)
    
    router_file = Path(__file__).parent / "app" / "api" / "v1" / "router.py"
    
    if not router_file.exists():
        print(f"❌ 找不到路由檔案: {router_file}")
        return False
    
    content = router_file.read_text(encoding='utf-8')
    
    # 檢查 virtual_fitting 路由是否註冊
    if "fitting_router" in content and 'prefix="/fitting"' in content:
        print("✅ Virtual Fitting 路由已註冊")
        print("   路徑: /api/v1/fitting/*")
        return True
    else:
        print("❌ Virtual Fitting 路由未正確註冊")
        print("\n請確保 router.py 中包含：")
        print('   from .virtual_fitting import router as fitting_router')
        print('   api_router.include_router(fitting_router, prefix="/fitting", tags=["fitting"])')
        return False


def test_imports():
    """測試關鍵模組導入"""
    print("\n" + "="*80)
    print("🔍 模組導入檢查")
    print("="*80)
    
    modules = [
        ("google.generativeai", "Gemini API"),
        ("vertexai", "Vertex AI"),
        ("PIL", "Pillow (圖片處理)"),
        ("fastapi", "FastAPI"),
    ]
    
    all_ok = True
    for module_name, description in modules:
        try:
            __import__(module_name)
            print(f"✅ {description} ({module_name})")
        except ImportError:
            print(f"❌ {description} ({module_name}) - 未安裝")
            all_ok = False
    
    return all_ok


def generate_fix_suggestions():
    """生成修復建議"""
    print("\n" + "="*80)
    print("💡 修復建議")
    print("="*80)
    
    print("\n如果遇到 404 錯誤：")
    print("-" * 80)
    print("前端調用應該使用：")
    print("  ✅ 正確: fetch('/api/v1/fitting/generate', ...)")
    print("  ❌ 錯誤: fetch('/api/v1/api/v1/fitting/generate', ...)")
    print()
    print("如果使用 axios baseURL:")
    print("  const api = axios.create({")
    print("    baseURL: 'http://127.0.0.1:8000/api/v1'")
    print("  });")
    print("  api.post('/fitting/generate', data);  // 不要再加 /api/v1")
    
    print("\n如果 AI 服務未配置：")
    print("-" * 80)
    print("1. 檢查 .env 檔案中的 GEMINI_API_KEY")
    print("2. 確保沒有多餘的字符（如 USE_GCS=true）")
    print("3. 重啟後端服務以載入新的環境變數")
    print()
    print("重啟命令：")
    print("  PowerShell: .\\start_backend.bat")
    print("  或: python -m uvicorn app.main:app --reload")
    
    print("\n如果需要測試：")
    print("-" * 80)
    print("運行測試腳本：")
    print("  python test_virtual_fitting_api.py")


def main():
    """主函數"""
    print("\n" + "🔧 虛擬試衣功能診斷工具")
    
    env_ok = check_environment()
    routes_ok = check_api_routes()
    imports_ok = test_imports()
    
    print("\n" + "="*80)
    print("📊 診斷結果")
    print("="*80)
    
    if env_ok and routes_ok and imports_ok:
        print("✅ 所有檢查通過！")
        print("\n建議:")
        print("1. 重啟後端服務")
        print("2. 運行 test_virtual_fitting_api.py 進行完整測試")
        print("3. 確認前端 API 調用路徑正確")
    else:
        print("⚠️ 發現問題，請查看上方詳細資訊")
        if not env_ok:
            print("  - 環境變數配置有問題")
        if not routes_ok:
            print("  - API 路由配置有問題")
        if not imports_ok:
            print("  - 缺少必要的 Python 模組")
    
    generate_fix_suggestions()
    
    print("\n" + "="*80)


if __name__ == "__main__":
    main()
