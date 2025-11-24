#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
診斷臉部交換服務問題
"""
import sys
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

print("="*60)
print("Face Swap Service Diagnostic Tool")
print("="*60)

# 1. 檢查 InsightFace 是否已安裝
print("\n[1] Checking InsightFace installation...")
try:
    import insightface
    print(f"[OK] InsightFace installed")
    print(f"     Version: {insightface.__version__}")
except ImportError as e:
    print(f"[ERROR] InsightFace not installed: {e}")
    sys.exit(1)

# 2. Check dependencies
print("\n[2] Checking dependencies...")
dependencies = {
    'onnxruntime': 'onnxruntime',
    'opencv-python': 'cv2',
    'numpy': 'numpy'
}

for package_name, import_name in dependencies.items():
    try:
        mod = __import__(import_name)
        version = getattr(mod, '__version__', 'unknown')
        print(f"[OK] {package_name}: {version}")
    except ImportError:
        print(f"[ERROR] {package_name} not installed")

# 3. Test FaceAnalysis initialization
print("\n[3] Testing FaceAnalysis initialization...")
try:
    from insightface.app import FaceAnalysis
    print("     Initializing FaceAnalysis...")
    
    # Use CPU (ctx_id=-1)
    app = FaceAnalysis(name='buffalo_l')
    app.prepare(ctx_id=-1, det_size=(640, 640))
    print("[OK] FaceAnalysis initialized successfully (CPU mode)")
    
except Exception as e:
    print(f"[ERROR] FaceAnalysis initialization failed: {e}")
    import traceback
    traceback.print_exc()

# 4. Test face swap model loading
print("\n[4] Testing face swap model...")
try:
    import insightface
    print("     Loading inswapper_128.onnx...")
    
    swapper = insightface.model_zoo.get_model(
        'inswapper_128.onnx',
        download=True,
        download_zip=True
    )
    print("[OK] Face swap model loaded successfully")
    
except Exception as e:
    print(f"[ERROR] Model loading failed: {e}")
    import traceback
    traceback.print_exc()

# 5. Test FaceSwapService
print("\n[5] Testing FaceSwapService...")
try:
    from app.services.face_swap import FaceSwapService
    
    print("     Creating FaceSwapService instance...")
    service = FaceSwapService()
    
    print(f"     Checking service availability...")
    if service.is_available():
        print("[OK] FaceSwapService is available!")
    else:
        print("[ERROR] FaceSwapService is not available")
        print(f"     app: {service.app}")
        print(f"     swapper: {service.swapper}")
        
except Exception as e:
    print(f"[ERROR] FaceSwapService test failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
print("Diagnosis complete")
print("="*60)
