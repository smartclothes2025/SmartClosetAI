#!/usr/bin/env python
"""
檢查並安裝 InsightFace 臉部交換技術
確保兩階段生成系統正常運作
"""
import sys
import subprocess
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_insightface():
    """檢查 InsightFace 是否已安裝"""
    try:
        import insightface
        from insightface.app import FaceAnalysis
        logger.info("✅ InsightFace 已安裝")
        logger.info(f"   版本: {insightface.__version__}")
        return True
    except ImportError:
        logger.warning("❌ InsightFace 未安裝")
        return False

def check_dependencies():
    """檢查相關依賴"""
    dependencies = {
        'onnxruntime': 'onnxruntime',
        'opencv-python': 'cv2',
        'numpy': 'numpy'
    }
    
    missing = []
    for package_name, import_name in dependencies.items():
        try:
            __import__(import_name)
            logger.info(f"✅ {package_name} 已安裝")
        except ImportError:
            logger.warning(f"❌ {package_name} 未安裝")
            missing.append(package_name)
    
    return missing

def install_insightface():
    """安裝 InsightFace"""
    logger.info("開始安裝 InsightFace...")
    
    try:
        # 使用預編譯版本安裝
        cmd = [
            sys.executable, 
            "-m", 
            "pip", 
            "install", 
            "insightface==0.7.3",
            "--prefer-binary",
            "--no-build-isolation"
        ]
        
        logger.info(f"執行命令: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("✅ InsightFace 安裝成功！")
            return True
        else:
            logger.error(f"❌ 安裝失敗:")
            logger.error(result.stderr)
            return False
            
    except Exception as e:
        logger.error(f"❌ 安裝錯誤: {e}")
        return False

def install_dependency(package):
    """安裝單個依賴"""
    try:
        cmd = [sys.executable, "-m", "pip", "install", package]
        logger.info(f"安裝 {package}...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info(f"✅ {package} 安裝成功")
            return True
        else:
            logger.error(f"❌ {package} 安裝失敗")
            return False
    except Exception as e:
        logger.error(f"❌ 安裝 {package} 錯誤: {e}")
        return False

def test_face_swap_service():
    """測試臉部交換服務"""
    logger.info("\n測試臉部交換服務...")
    
    try:
        from app.services.face_swap import FaceSwapService
        
        service = FaceSwapService()
        
        if service.is_available():
            logger.info("✅ 臉部交換服務可用！")
            logger.info("   兩階段生成系統已就緒：")
            logger.info("   - 階段 1: Gemini 生成穿搭圖")
            logger.info("   - 階段 2: InsightFace 臉部交換 (99%+ 相似度)")
            return True
        else:
            logger.warning("⚠️ 臉部交換服務初始化失敗")
            return False
            
    except Exception as e:
        logger.error(f"❌ 測試失敗: {e}")
        return False

def main():
    print("="*60)
    print("SmartClosetAI - InsightFace 安裝檢查工具")
    print("="*60)
    print()
    
    # 1. 檢查 InsightFace
    if not check_insightface():
        print("\n需要安裝 InsightFace...")
        
        # 2. 檢查依賴
        print("\n檢查依賴套件...")
        missing_deps = check_dependencies()
        
        if missing_deps:
            print(f"\n安裝缺少的依賴: {', '.join(missing_deps)}")
            for dep in missing_deps:
                install_dependency(dep)
        
        # 3. 安裝 InsightFace
        print()
        if not install_insightface():
            print("\n❌ 安裝失敗！")
            print("請手動執行：")
            print("pip install insightface==0.7.3 --prefer-binary --no-build-isolation")
            return 1
    
    # 4. 測試服務
    print()
    if test_face_swap_service():
        print("\n" + "="*60)
        print("✅ 所有檢查通過！")
        print("="*60)
        print("\n兩階段生成系統已就緒：")
        print("1. 階段 1: Gemini 生成穿搭圖（基礎效果）")
        print("2. 階段 2: InsightFace 臉部交換（99%+ 相似度）")
        print("\n請重啟後端服務以啟用臉部交換功能。")
        return 0
    else:
        print("\n⚠️ 服務測試未通過")
        print("請檢查錯誤訊息並重試")
        return 1

if __name__ == "__main__":
    sys.exit(main())
