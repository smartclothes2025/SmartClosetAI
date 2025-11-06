"""
測試 Gemini 可用模型
"""
import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

gemini_key = os.getenv("GEMINI_API_KEY")

if not gemini_key:
    print("ERROR: GEMINI_API_KEY not set")
    exit(1)

print("Configuring Gemini API...")
genai.configure(api_key=gemini_key)

print("\nListing available models:")
print("=" * 60)

try:
    models = genai.list_models()
    
    for model in models:
        print(f"\nModel: {model.name}")
        print(f"  Display Name: {model.display_name}")
        print(f"  Supported Methods: {model.supported_generation_methods}")
        
except Exception as e:
    print(f"Error listing models: {str(e)}")

print("\n" + "=" * 60)
print("\nTesting text generation with gemini-1.5-flash:")

try:
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content("Say hello in one word")
    print(f"[SUCCESS] Response: {response.text}")
except Exception as e:
    print(f"[FAILED] {str(e)}")
