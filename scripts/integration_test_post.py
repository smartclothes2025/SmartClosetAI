import requests
import traceback

url = 'http://localhost:8000/api/v1/fitting/generate-with-photo'
file_path = r'C:\Users\Administrator\Desktop\SmartClosetAI\uploads\bags\bag_1.jpg'

files = None
try:
    files = {'user_photo': open(file_path, 'rb')}
except Exception as e:
    print('Failed to open file:', e)
    raise

data = {
    'clothing_items': '[{"id":"test1","name":"Demo Top","category":"上衣","img":"https://via.placeholder.com/512.png"}]',
    'user_input': '測試整合'
}

try:
    r = requests.post(url, files=files, data=data, timeout=120)
    print('Status:', r.status_code)
    print('Headers:', r.headers)
    print('Body (first 8000 chars):')
    print(r.text[:8000])
except Exception as e:
    print('Request exception:')
    traceback.print_exc()
finally:
    if files and 'user_photo' in files:
        files['user_photo'].close()
