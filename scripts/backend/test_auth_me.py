"""
測試 /auth/me 端點是否正確回傳 user_id

此腳本會:
1. 使用測試 token 呼叫 /auth/me 端點
2. 驗證回傳資料包含 'id' 欄位
3. 驗證 ID 類型 (Integer 或 UUID)
4. 提供建議的環境變數設定
"""

import requests
import sys
import json
from typing import Optional

# 配置
API_BASE = "http://localhost:8000"
AUTH_ME_ENDPOINT = f"{API_BASE}/api/v1/auth/me"

# 測試用的 token (請根據實際情況修改)
# 格式: user-{id}-token
TEST_TOKENS = [
    "user-1-token",  # Integer ID
    "user-9c33c7e9-ce22-4c4d-b385-15504ef368da-token",  # UUID
]


def test_auth_me(token: str) -> Optional[dict]:
    """測試 /auth/me 端點"""
    print(f"\n{'='*60}")
    print(f"測試 Token: {token}")
    print(f"{'='*60}")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(AUTH_ME_ENDPOINT, headers=headers, timeout=5)
        
        print(f"狀態碼: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 成功取得使用者資料")
            print(f"\n回傳資料:")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            
            # 檢查 id 欄位
            if 'id' in data:
                user_id = data['id']
                print(f"\n✅ 包含 'id' 欄位: {user_id}")
                
                # 判斷 ID 類型
                id_type = type(user_id).__name__
                print(f"ID 類型: {id_type}")
                
                if isinstance(user_id, int):
                    print(f"✅ ID 是 Integer 類型")
                    print(f"\n建議前端環境變數:")
                    print(f"  VITE_NOTIF_USER_ID_TYPE=int")
                elif isinstance(user_id, str):
                    # 檢查是否為 UUID 格式
                    import re
                    uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                    if re.match(uuid_pattern, user_id, re.IGNORECASE):
                        print(f"✅ ID 是 UUID 格式")
                        print(f"\n建議前端環境變數:")
                        print(f"  VITE_NOTIF_USER_ID_TYPE=uuid")
                    else:
                        print(f"⚠️ ID 是字串但不是 UUID 格式")
                        print(f"\n建議前端環境變數:")
                        print(f"  VITE_NOTIF_USER_ID_TYPE=string")
                
                return data
            else:
                print(f"\n❌ 回傳資料中沒有 'id' 欄位!")
                print(f"可用欄位: {', '.join(data.keys())}")
                print(f"\n請檢查 app/api/v1/auth.py 的 /me 端點")
                return None
                
        elif response.status_code == 401:
            print(f"❌ 認證失敗 (401 Unauthorized)")
            print(f"可能原因:")
            print(f"  1. Token 格式錯誤")
            print(f"  2. 使用者不存在")
            print(f"  3. Token 已過期")
            try:
                error_data = response.json()
                print(f"\n錯誤詳情: {error_data}")
            except:
                print(f"\n回應內容: {response.text}")
            return None
            
        elif response.status_code == 404:
            print(f"❌ 使用者不存在 (404 Not Found)")
            print(f"請確認:")
            print(f"  1. 資料庫中有此使用者")
            print(f"  2. Token 中的 ID 正確")
            return None
            
        else:
            print(f"❌ 未預期的狀態碼: {response.status_code}")
            print(f"回應內容: {response.text}")
            return None
            
    except requests.exceptions.ConnectionError:
        print(f"❌ 連線失敗: 無法連接到 {API_BASE}")
        print(f"請確認:")
        print(f"  1. 後端伺服器已啟動")
        print(f"  2. API_BASE 設定正確")
        return None
        
    except requests.exceptions.Timeout:
        print(f"❌ 請求逾時")
        return None
        
    except Exception as e:
        print(f"❌ 發生錯誤: {type(e).__name__}: {e}")
        return None


def main():
    print("=" * 60)
    print("測試 /auth/me 端點的 user_id 回傳")
    print("=" * 60)
    
    success_count = 0
    
    for token in TEST_TOKENS:
        result = test_auth_me(token)
        if result:
            success_count += 1
    
    print(f"\n{'='*60}")
    print(f"測試結果摘要")
    print(f"{'='*60}")
    print(f"測試數量: {len(TEST_TOKENS)}")
    print(f"成功數量: {success_count}")
    print(f"失敗數量: {len(TEST_TOKENS) - success_count}")
    
    if success_count > 0:
        print(f"\n✅ 至少有一個 token 測試成功!")
        print(f"\n後續步驟:")
        print(f"  1. 確認前端 .env 檔案設定正確的 VITE_NOTIF_USER_ID_TYPE")
        print(f"  2. 重啟前端開發伺服器 (npm run dev)")
        print(f"  3. 測試通知建立功能")
        print(f"  4. 檢查資料庫確認通知已儲存")
    else:
        print(f"\n❌ 所有測試都失敗!")
        print(f"\n疑難排解:")
        print(f"  1. 確認後端伺服器已啟動並運行在 {API_BASE}")
        print(f"  2. 確認資料庫中有測試使用者")
        print(f"  3. 檢查 app/api/v1/auth.py 的 /me 端點是否已加入 'id' 欄位")
        print(f"  4. 修改 TEST_TOKENS 使用實際存在的使用者 token")
    
    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n測試已中斷")
        sys.exit(0)
