"""
測試 Gemini API 連接
"""
import os
from dotenv import load_dotenv
import google.generativeai as genai

# 載入環境變數
load_dotenv()

print("=" * 60)
print("Gemini API Connection Test")
print("=" * 60)

# 檢查環境變數
gemini_key = os.getenv("GEMINI_API_KEY")
gcp_project = os.getenv("GCP_PROJECT_ID")
gcp_location = os.getenv("GCP_LOCATION")

print("\n1. Environment Variables Check:")
print(f"   GEMINI_API_KEY: {'[OK] Set' if gemini_key else '[NO] Not Set'}")
if gemini_key:
    print(f"   Key Length: {len(gemini_key)} characters")
    print(f"   Key Preview: {gemini_key[:10]}...{gemini_key[-5:]}")

print(f"   GCP_PROJECT_ID: {'[OK] Set' if gcp_project else '[NO] Not Set'}")
if gcp_project:
    print(f"   Project: {gcp_project}")

print(f"   GCP_LOCATION: {'[OK] Set' if gcp_location else '[NO] Not Set (default: us-central1)'}")
if gcp_location:
    print(f"   Location: {gcp_location}")

# 測試 Gemini API
if gemini_key:
    print("\n2. Testing Gemini API Connection:")
    try:
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel('gemini-pro')
        
        print("   Sending test prompt...")
        response = model.generate_content("Say hello in one word")
        
        print("   [SUCCESS] Gemini API is working")
        print(f"   Response: {response.text}")
        
    except Exception as e:
        print(f"   [FAILED] {str(e)}")
        print(f"   Error Type: {type(e).__name__}")
else:
    print("\n2. Skipping Gemini API test (no API key)")

# 測試 Imagen (Vertex AI)
if gcp_project:
    print("\n3. Testing Vertex AI (Imagen) Setup:")
    try:
        from google.cloud import aiplatform
        
        aiplatform.init(project=gcp_project, location=gcp_location or "us-central1")
        print("   [OK] Vertex AI initialized successfully")
        
        # 嘗試載入 Imagen 模型
        try:
            from vertexai.preview.vision_models import ImageGenerationModel
            model = ImageGenerationModel.from_pretrained("imagegeneration@006")
            print("   [OK] Imagen model loaded successfully")
        except Exception as e:
            print(f"   [FAILED] Imagen model load failed: {str(e)}")
            
    except Exception as e:
        print(f"   [FAILED] Vertex AI initialization failed: {str(e)}")
else:
    print("\n3. Skipping Vertex AI test (no GCP project ID)")

print("\n" + "=" * 60)
print("Test Complete")
print("=" * 60)
